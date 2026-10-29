from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LintIssue:
    tool: str
    line: int
    column: int
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class LintRun:
    tool: str
    issues: tuple[LintIssue, ...]
    timed_out: bool = False
    error: str | None = None
