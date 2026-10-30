import re
from collections.abc import Sequence

from pyreview.analysis.application.schema import DraftFinding, ReviewDraft
from pyreview.analysis.domain import Finding, Review, SourceFile, source_lines
from pyreview.linters.domain import LintIssue
from pyreview.shared.config import LimitsConfig

LINE_PREFIX = re.compile(r"^\s*\d+\s*\|\s?")


def _cap(text: str) -> str:
    text = text.strip()
    return text[:1].upper() + text[1:]


def _align(finding: DraftFinding, lines: list[str]) -> int | None:
    quote = next((q.strip() for q in source_lines(finding.quote) if q.strip()), "")
    quote = LINE_PREFIX.sub("", quote).strip()
    hits = [n for n, text in enumerate(lines, 1) if quote and quote in text]
    if hits:
        return min(hits, key=lambda n: abs(n - finding.line))
    return finding.line if 1 <= finding.line <= len(lines) else None


def _finding(draft: DraftFinding, line: int, total: int) -> Finding:
    end = min(draft.end_line + line - draft.line, total) if draft.end_line else None
    return Finding(
        line=line,
        end_line=end if end and end > line else None,
        severity=draft.severity,
        title=_cap(draft.title),
        detail=_cap(draft.detail),
        suggestion=draft.suggestion or None,
    )


def _repeats(finding: Finding, lint: Sequence[LintIssue]) -> bool:
    text = f"{finding.title} {finding.detail}".lower()
    return any(
        i.line == finding.line and (finding.severity != "bug" or i.code.lower() in text)
        for i in lint
    )


def finalize(
    draft: ReviewDraft,
    source: SourceFile,
    limits: LimitsConfig,
    lint: Sequence[LintIssue],
    truncated: bool,
) -> Review:
    lines, max_findings = source_lines(source.text), limits.max_findings
    placed = [(f, _align(f, lines)) for f in draft.findings]
    kept = sorted(
        (_finding(f, line, len(lines)) for f, line in placed if line is not None),
        key=lambda f: f.line,
    )
    unique = [f for f in kept if not _repeats(f, lint)]
    repeats = len(kept) - len(unique)
    dropped = len(draft.findings) - len(kept) + len(unique[max_findings:])
    kept = unique[:max_findings]
    summary = _cap(draft.summary)
    if repeats:
        summary += f" Повторы замечаний линтеров убраны: {repeats}."
    if dropped:
        summary += (
            f" Не показано находок: {dropped} — без строки в файле или сверх предела "
            f"в {max_findings}."
        )
    if truncated:
        summary += (
            f" Анализ остановлен по пределу в {limits.max_tool_calls} вызовов инструментов "
            "вместе с записью мыслей, ревью может быть неполным."
        )
    return Review(
        verdict="issues" if any(f.severity != "nit" for f in kept) else "ok",
        summary=summary,
        findings=tuple(kept),
        dropped=dropped,
    )
