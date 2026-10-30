import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.language_models import BaseChatModel, LangSmithParams
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from pyreview.linters.domain import LintIssue, LintRun
from pyreview.shared.config import AppConfig, load_config

CONFIG = load_config(Path(__file__).parents[1] / "config.json")


def make_config(**limits: Any) -> AppConfig:
    return CONFIG.model_copy(update={"limits": CONFIG.limits.model_copy(update=limits)})


def calls(*pairs: tuple[str, dict[str, Any]], text: str = "") -> AIMessage:
    tool_calls = [{"name": n, "args": a, "id": uuid4().hex, "type": "tool_call"} for n, a in pairs]
    usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    return AIMessage(text, tool_calls=tool_calls, usage_metadata=usage)


def call(name: str, text: str = "", **args: Any) -> AIMessage:
    return calls((name, args), text=text)


def draft(*findings: dict[str, Any], verdict: str = "issues") -> AIMessage:
    return call(
        "ReviewDraft",
        reasoning="Проверил линтеры и логику.",
        verdict=verdict,
        summary="Итог ревью.",
        findings=list(findings),
    )


class ScriptedModel(BaseChatModel):
    script: list[AIMessage]
    delay: float = 0
    error: Exception | None = None
    offered: list[list[str]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _get_ls_params(self, stop: list[str] | None = None, **kwargs: Any) -> LangSmithParams:
        return LangSmithParams(ls_provider="giga", ls_model_name="scripted", ls_model_type="chat")

    def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> ScriptedModel:
        self.offered.append([getattr(t, "name", getattr(t, "__name__", "")) for t in tools])
        return self

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> ChatResult:
        if self.error:
            raise self.error
        return ChatResult(generations=[ChatGeneration(message=self.script.pop(0))])

    async def _agenerate(
        self, messages: list[BaseMessage], *args: Any, **kwargs: Any
    ) -> ChatResult:
        await asyncio.sleep(self.delay)
        return self._generate(messages)


@dataclass(frozen=True, slots=True)
class FakeLinter:
    name: str
    issues: tuple[LintIssue, ...] = ()
    paths: list[Path] = field(default_factory=list)

    async def run(self, path: Path) -> LintRun:
        self.paths.append(path)
        return LintRun(tool=self.name, issues=self.issues)


def issue(tool: str, line: int, code: str, column: int = 1) -> LintIssue:
    return LintIssue(tool=tool, line=line, column=column, code=code, message=f"{code} message")
