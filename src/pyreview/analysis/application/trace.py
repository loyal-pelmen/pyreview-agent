import re
import time

from langchain_core.messages import AIMessage

from pyreview.analysis.application.schema import ReviewDraft
from pyreview.analysis.domain import ReasoningStep, StepKind
from pyreview.linters.domain import LintRun

STEP_CHARS = 2000
THINK = "think"
STRUCTURED = ReviewDraft.__name__
THINK_MARK = re.compile(r"(?im)^\s*think\s*:\s*|(?<=[.!?])\s+think\s*:\s*")
TAIL = re.compile(r"(?ims)^\s*(?:итоговое ревью|reasoning|verdict|summary)\s*:.*")


def thoughts(text: str) -> list[str]:
    return [p for part in THINK_MARK.split(TAIL.sub("", text)) if (p := part.strip())]


class Trace:
    def __init__(self, started: float) -> None:
        self.started = started
        self.steps: list[ReasoningStep] = []
        self.runs: dict[str, LintRun] = {}
        self.tokens = 0
        self.tool_calls = 0
        self.thoughts = 0
        self.truncated = False

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started) * 1000)

    def add(
        self,
        kind: StepKind,
        text: str | None = None,
        tool: str | None = None,
        args: dict[str, object] | None = None,
    ) -> None:
        clipped = text[:STEP_CHARS] if text is not None else None
        self.steps.append(
            ReasoningStep(
                n=len(self.steps) + 1,
                at_ms=self.elapsed_ms(),
                kind=kind,
                text=clipped,
                tool=tool,
                args=args or {},
                truncated=clipped != text,
            )
        )

    def record(self, message: AIMessage) -> None:
        self.tokens += (message.usage_metadata or {}).get("total_tokens", 0)
        for thought in thoughts(message.text):
            self.add("thought", thought)
        for call in message.tool_calls:
            if call["name"] == THINK:
                self.add("thought", str(call["args"].get("thought", "")))
            elif call["name"] != STRUCTURED:
                self.add("tool_call", tool=call["name"], args=call["args"])
