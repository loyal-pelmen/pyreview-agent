import re
from dataclasses import dataclass, field
from typing import Literal

from pyreview.linters.domain import LintIssue

type Severity = Literal["bug", "warning", "nit"]
type Verdict = Literal["ok", "issues"]
type StepKind = Literal["thought", "tool_call", "tool_result", "conclusion"]

LINE_BREAK = re.compile(r"\r\n|\r|\n")


def source_lines(text: str) -> list[str]:
    lines = LINE_BREAK.split(text)
    return lines[:-1] if lines[-1] == "" else lines


@dataclass(frozen=True, slots=True)
class SourceFile:
    name: str
    text: str
    size: int

    @property
    def lines(self) -> int:
        return len(source_lines(self.text))


@dataclass(frozen=True, slots=True)
class Finding:
    line: int
    end_line: int | None
    severity: Severity
    title: str
    detail: str
    suggestion: str | None


@dataclass(frozen=True, slots=True)
class Review:
    verdict: Verdict
    summary: str
    findings: tuple[Finding, ...]
    dropped: int


@dataclass(frozen=True, slots=True)
class ReasoningStep:
    n: int
    at_ms: int
    kind: StepKind
    text: str | None = None
    tool: str | None = None
    args: dict[str, object] = field(default_factory=dict)
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class Usage:
    tokens: int
    tool_calls: int
    duration_ms: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class ModelInfo:
    provider: str
    name: str


@dataclass(frozen=True, slots=True)
class ReviewReport:
    file: SourceFile
    review: Review
    lint: tuple[LintIssue, ...]
    reasoning: tuple[ReasoningStep, ...]
    model: ModelInfo
    usage: Usage
