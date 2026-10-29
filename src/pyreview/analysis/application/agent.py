from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import structlog
from deepagents import FilesystemMiddleware, create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.errors import GraphRecursionError
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from pyreview.analysis.application.prompt import (
    EMPTY_FINDINGS,
    FINAL_REQUEST,
    GATE_MESSAGE,
    LIMIT_MESSAGE,
    SECOND_LOOK,
    SYSTEM_PROMPT,
)
from pyreview.analysis.application.schema import ReviewDraft
from pyreview.analysis.application.trace import STRUCTURED, THINK, Trace
from pyreview.shared.errors import ModelUnavailable

log = structlog.get_logger(__name__)


def _one_call(messages: list[BaseMessage]) -> list[BaseMessage]:
    ai = messages[0] if messages else None
    if not isinstance(ai, AIMessage) or len(ai.tool_calls) <= 1:
        return messages
    answered = {m.tool_call_id for m in messages[1:] if isinstance(m, ToolMessage)}
    keep = [c for c in ai.tool_calls if c["id"] in answered][:1] or ai.tool_calls[:1]
    extra = {k: v for k, v in ai.additional_kwargs.items() if k != "tool_calls"}
    return [ai.model_copy(update={"tool_calls": keep, "additional_kwargs": extra}), *messages[1:]]


class ReviewGuard(AgentMiddleware):
    def __init__(self, trace: Trace, max_tool_calls: int, linters: frozenset[str]) -> None:
        super().__init__()
        self.trace = trace
        self.limit = max_tool_calls
        self.linters = linters

    def _exhausted(self) -> bool:
        return self.trace.tool_calls + self.trace.thoughts >= self.limit

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], Awaitable[ModelResponse]]
    ) -> ModelResponse:
        pending = sorted(f"run_{n}" for n in self.linters - self.trace.runs.keys())
        if self._exhausted():
            self.trace.truncated = True
            request = request.override(tools=[])
        elif pending:
            request = request.override(response_format=None, tool_choice=pending[0])
        try:
            response = await handler(request)
        except Exception as exc:
            log.exception("model_call_failed")
            raise ModelUnavailable from exc
        response.result = _one_call(response.result)
        gate = GATE_MESSAGE.format(", ".join(pending))
        for message in list(response.result):
            if isinstance(message, AIMessage):
                self.trace.record(message)
                response.result += [
                    ToolMessage(gate, tool_call_id=c["id"], name=STRUCTURED)
                    for c in message.tool_calls
                    if c["name"] == STRUCTURED and request.response_format is None
                ]
        return response

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        call = request.tool_call
        if self._exhausted():
            self.trace.truncated = True
            result = ToolMessage(LIMIT_MESSAGE, tool_call_id=call["id"], name=call["name"])
        else:
            result = await handler(request)
            self.trace.thoughts += call["name"] == THINK
            self.trace.tool_calls += call["name"] != THINK
        if call["name"] != THINK and isinstance(result, ToolMessage):
            self.trace.add("tool_result", result.text, tool=call["name"])
        return result


async def run_agent(
    model: BaseChatModel, tools: list[BaseTool], workspace: Path, task: str, guard: ReviewGuard
) -> tuple[list[AnyMessage], ReviewDraft | None]:
    files = FilesystemBackend(root_dir=workspace, virtual_mode=True)
    stack: list[AgentMiddleware[Any, Any, Any]] = [
        guard,
        FilesystemMiddleware(backend=files, tools=["read_file", "ls", "grep"]),
    ]
    agent = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=stack,
        response_format=ToolStrategy(ReviewDraft),
    )
    state: dict[str, Any] = {}
    config: RunnableConfig = {"recursion_limit": 8 * (guard.limit + 5)}
    try:
        stream = agent.astream({"messages": [HumanMessage(task)]}, config, stream_mode="values")
        async for chunk in stream:
            state = chunk
    except GraphRecursionError:
        guard.trace.truncated = True
    return state.get("messages", []), state.get("structured_response")


async def request_review(
    model: BaseChatModel, messages: list[AnyMessage], trace: Trace
) -> ReviewDraft:
    prompt = [SystemMessage(SYSTEM_PROMPT), *messages, HumanMessage(FINAL_REQUEST)]
    draft = await _structured(model, prompt, trace)
    if not draft.findings:
        follow_up = EMPTY_FINDINGS if draft.verdict == "issues" else SECOND_LOOK
        retry = [*prompt, AIMessage(draft.model_dump_json()), HumanMessage(follow_up)]
        draft = await _structured(model, retry, trace)
    return draft


async def _structured(model: BaseChatModel, prompt: list[AnyMessage], trace: Trace) -> ReviewDraft:
    try:
        result = await model.with_structured_output(ReviewDraft, include_raw=True).ainvoke(prompt)
    except Exception as exc:
        log.exception("final_review_failed")
        raise ModelUnavailable from exc
    if isinstance(result, dict) and isinstance(result.get("raw"), AIMessage):
        trace.record(result["raw"])
    parsed = result.get("parsed") if isinstance(result, dict) else None
    if not isinstance(parsed, ReviewDraft):
        log.error("final_review_missing")
        raise ModelUnavailable
    return parsed
