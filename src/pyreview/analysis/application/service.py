import asyncio
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path, PurePosixPath

import structlog
from langchain_core.language_models import BaseChatModel

from pyreview.analysis.application.agent import ReviewGuard, request_review, run_agent
from pyreview.analysis.application.postprocess import finalize
from pyreview.analysis.application.prompt import user_message
from pyreview.analysis.application.tools import build_tools, format_run
from pyreview.analysis.application.trace import Trace
from pyreview.analysis.domain import ModelInfo, Review, ReviewReport, SourceFile, Usage
from pyreview.linters.application import Linter
from pyreview.shared.config import AppConfig
from pyreview.shared.errors import AnalysisTimeout, FileTooLarge, NotUtf8, UnsupportedFile

log = structlog.get_logger(__name__)
EMPTY_SUMMARY = "Файл пустой — проверять нечего."
MAX_NAME_BYTES = 255


class ReviewService:
    def __init__(
        self,
        config: AppConfig,
        linters: Sequence[Linter],
        model_factory: Callable[[], BaseChatModel],
    ) -> None:
        self._config = config
        self._linters = tuple(lin for lin in linters if getattr(config.linters, lin.name, False))
        self._names = frozenset(lin.name for lin in self._linters)
        self.model_factory = model_factory
        self._model = ModelInfo(provider=config.llm.provider, name=config.llm.model)

    def _source(self, name: str, data: bytes) -> SourceFile:
        name = PurePosixPath(name.replace("\\", "/")).name
        if (
            len(name) <= len(".py")
            or len(name.encode()) > MAX_NAME_BYTES
            or not name.lower().endswith(".py")
            or not name.isprintable()
        ):
            raise UnsupportedFile
        if len(data) > self._config.limits.max_file_bytes:
            raise FileTooLarge
        try:
            return SourceFile(name=name, text=data.decode("utf-8-sig"), size=len(data))
        except UnicodeDecodeError as exc:
            raise NotUtf8 from exc

    async def review(self, name: str, data: bytes) -> ReviewReport:
        trace = Trace(time.monotonic())
        source = self._source(name, data)
        if not source.text.strip():
            review = Review(verdict="ok", summary=EMPTY_SUMMARY, findings=(), dropped=0)
            usage = Usage(tokens=0, tool_calls=0, duration_ms=trace.elapsed_ms(), truncated=False)
            return ReviewReport(source, review, (), (), self._model, usage)
        try:
            async with asyncio.timeout(self._config.limits.analysis_timeout_seconds):
                report = await self._analyse(source, data, trace)
        except TimeoutError as exc:
            log.warning("analysis_timeout", bytes=source.size, lines=source.lines)
            raise AnalysisTimeout from exc
        log.info(
            "review_done",
            bytes=source.size,
            lines=source.lines,
            findings=len(report.review.findings),
            dropped=report.review.dropped,
            lint=len(report.lint),
            tool_calls=report.usage.tool_calls,
            tokens=report.usage.tokens,
            duration_ms=report.usage.duration_ms,
            truncated=report.usage.truncated,
        )
        return report

    async def _analyse(self, source: SourceFile, data: bytes, trace: Trace) -> ReviewReport:
        limits = self._config.limits
        task, shown = user_message(source, limits.max_prompt_chars)
        if shown < source.lines:
            trace.add("thought", f"Листинг в промпте обрезан до {shown} строк из {source.lines}.")
        with tempfile.TemporaryDirectory(prefix="pyreview-") as tmp:
            workspace = Path(tmp)
            (workspace / source.name).write_bytes(data)
            model = self.model_factory()
            tools = build_tools(
                self._linters, workspace, source.name, limits.max_tool_output_chars, trace
            )
            guard = ReviewGuard(trace, limits.max_tool_calls, self._names)
            messages, draft = await run_agent(model, tools, workspace, task, guard)
            draft = draft or await request_review(model, messages, trace)
            for linter in self._linters:
                if linter.name not in trace.runs:
                    trace.runs[linter.name] = run = await linter.run(workspace / source.name)
                    text = f"Запущен сервисом.\n{format_run(run, limits.max_tool_output_chars)}"
                    trace.add("tool_result", text, tool=f"run_{linter.name}")
        lint = sorted(
            (issue for run in trace.runs.values() for issue in run.issues),
            key=lambda i: (i.line, i.column),
        )
        note = f"Показаны первые {limits.max_lint_issues} замечаний линтеров из {len(lint)}."
        capped, lint = len(lint) > limits.max_lint_issues, lint[: limits.max_lint_issues]
        if capped:
            trace.add("thought", note)
        trace.add("conclusion", draft.reasoning)
        review = finalize(draft, source, limits, lint, trace.truncated)
        if capped:
            review = replace(review, summary=f"{review.summary} {note}")
        usage = Usage(trace.tokens, trace.tool_calls, trace.elapsed_ms(), trace.truncated)
        return ReviewReport(source, review, tuple(lint), tuple(trace.steps), self._model, usage)
