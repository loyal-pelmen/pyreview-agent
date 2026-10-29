from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from pyreview.analysis.domain import (
    Finding,
    ModelInfo,
    ReasoningStep,
    Review,
    ReviewReport,
    SourceFile,
    Usage,
)
from pyreview.entrypoints.app import create_app
from pyreview.linters.domain import LintIssue
from pyreview.shared.config import AppConfig

CONFIG = AppConfig.model_validate(
    {
        "llm": {
            "provider": "gigachat",
            "model": "GigaChat-2-Max",
            "temperature": 0.1,
            "max_tokens": 4000,
            "timeout_seconds": 120,
        },
        "linters": {"ruff": True, "ty": False, "timeout_seconds": 30, "ruff_select": ["E"]},
        "limits": {
            "max_file_bytes": 100,
            "max_findings": 30,
            "max_tool_calls": 20,
            "analysis_timeout_seconds": 300,
            "max_prompt_chars": 60000,
            "max_tool_output_chars": 4000,
            "max_lint_issues": 200,
        },
    }
)

REPORT = ReviewReport(
    file=SourceFile(name="app.py", text="import os\nprint(1)\n", size=19),
    review=Review(
        verdict="issues",
        summary="Итог.",
        findings=(Finding(1, None, "nit", "Лишний импорт", "Не используется.", None),),
        dropped=0,
    ),
    lint=(LintIssue("ruff", 1, 8, "F401", "`os` imported but unused"),),
    reasoning=(
        ReasoningStep(1, 0, "thought", text="Посмотрю линтеры."),
        ReasoningStep(2, 10, "tool_call", tool="run_ruff", args={"path": "app.py"}),
        ReasoningStep(3, 90, "tool_result", text="1:8 F401", tool="run_ruff"),
        ReasoningStep(4, 120, "conclusion", text="Лишний импорт."),
    ),
    model=ModelInfo("gigachat", "GigaChat-2-Max"),
    usage=Usage(tokens=100, tool_calls=1, duration_ms=150, truncated=False),
)


@dataclass(frozen=True, slots=True)
class FakeService:
    outcome: ReviewReport | Exception = REPORT
    calls: list[tuple[str, bytes]] = field(default_factory=list)

    async def review(self, name: str, data: bytes) -> ReviewReport:
        self.calls.append((name, data))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


type ClientFactory = Callable[..., AbstractAsyncContextManager[AsyncClient]]


@pytest.fixture
def make_client(tmp_path: Path) -> ClientFactory:
    @asynccontextmanager
    async def factory(
        service: FakeService | None = None, frontend_dir: Path = tmp_path
    ) -> AsyncGenerator[AsyncClient]:
        app = create_app(CONFIG, service or FakeService(), frontend_dir)
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    return factory
