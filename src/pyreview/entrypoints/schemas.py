from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from pyreview.analysis.domain import ReasoningStep, Severity, StepKind, Verdict
from pyreview.shared.config import AppConfig


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


_OMIT_NONE = Field(exclude_if=lambda value: value is None)


class ErrorBody(_Out):
    code: str
    message: str


class ErrorResponse(_Out):
    error: ErrorBody


class HealthResponse(_Out):
    status: Literal["ok"] = "ok"


class ModelOut(_Out):
    provider: str
    name: str


class LimitsOut(_Out):
    max_file_bytes: int
    max_findings: int
    analysis_timeout_seconds: float


class ConfigResponse(_Out):
    model: ModelOut
    linters: list[str]
    limits: LimitsOut

    @classmethod
    def from_config(cls, config: AppConfig) -> ConfigResponse:
        return cls(
            model=ModelOut(provider=config.llm.provider, name=config.llm.model),
            linters=[name for name in ("ruff", "ty") if getattr(config.linters, name)],
            limits=LimitsOut.model_validate(config.limits),
        )


class FileOut(_Out):
    name: str
    bytes: int = Field(validation_alias=AliasChoices("bytes", "size"))
    lines: int


class FindingOut(_Out):
    line: int
    end_line: int | None
    severity: Severity
    title: str
    detail: str
    suggestion: str | None


class ReviewOut(_Out):
    verdict: Verdict
    summary: str
    findings: list[FindingOut]
    dropped: int


class LintOut(_Out):
    tool: str
    line: int
    column: int
    code: str
    message: str


class StepOut(_Out):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": "Ключ без значения для вида шага опускается: text и truncated — "
            "у шагов с текстом, tool — у tool_call и tool_result, args — только у tool_call."
        },
    )

    n: int
    at_ms: int
    kind: StepKind
    text: Annotated[str | None, _OMIT_NONE] = None
    tool: Annotated[str | None, _OMIT_NONE] = None
    args: Annotated[dict[str, object] | None, _OMIT_NONE] = None
    truncated: Annotated[bool | None, _OMIT_NONE] = None

    @model_validator(mode="before")
    @classmethod
    def _meaningful_only(cls, step: object) -> object:
        if not isinstance(step, ReasoningStep):
            return step
        return {
            "n": step.n,
            "at_ms": step.at_ms,
            "kind": step.kind,
            "text": step.text,
            "tool": step.tool,
            "args": step.args if step.kind == "tool_call" else None,
            "truncated": step.truncated if step.text is not None else None,
        }


class UsageOut(_Out):
    tokens: int
    tool_calls: int
    duration_ms: int
    truncated: bool


class ReviewResponse(_Out):
    file: FileOut
    review: ReviewOut
    lint: list[LintOut]
    reasoning: list[StepOut]
    model: ModelOut
    usage: UsageOut
