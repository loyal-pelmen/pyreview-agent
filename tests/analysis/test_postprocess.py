import ast
from typing import Any

import pytest

from pyreview.analysis.application.postprocess import finalize
from pyreview.analysis.application.prompt import user_message
from pyreview.analysis.application.schema import DraftFinding, ReviewDraft
from pyreview.analysis.domain import Review, Severity, SourceFile
from pyreview.linters.domain import LintIssue
from tests.fakes import issue, make_config

SOURCE = SourceFile(name="a.py", text="a = 1\nb = 2\nc = 3\nb = 2\n", size=24)


def found(line: int, quote: str = "", severity: Severity = "bug", **extra: Any) -> DraftFinding:
    base = {"line": line, "quote": quote, "severity": severity, "title": "t", "detail": "d"}
    return DraftFinding.model_validate(base | extra)


def review(
    *findings: DraftFinding,
    max_findings: int = 30,
    truncated: bool = False,
    lint: tuple[LintIssue, ...] = (),
    verdict: str = "ok",
    source: SourceFile = SOURCE,
) -> Review:
    draft = ReviewDraft.model_validate(
        {"reasoning": "r", "verdict": verdict, "summary": "Итог.", "findings": findings}
    )
    limits = make_config(max_findings=max_findings, max_tool_calls=20).limits
    return finalize(draft, source, limits, lint, truncated)


def test_quote_realigns_to_nearest_line() -> None:
    result = review(found(1, "c = 3"), found(5, "b = 2"), found(1, "   2 | b = 2"))
    assert [f.line for f in result.findings] == [2, 3, 4]
    assert result.verdict == "issues"


def test_unknown_quote_keeps_line_in_range_and_drops_outside() -> None:
    result = review(found(2, "nope"), found(9, "nope"), found(0))
    assert [f.line for f in result.findings] == [2]
    assert result.dropped == 2
    assert "Не показано находок: 2" in result.summary


def test_end_line_shifted_clamped_or_cleared() -> None:
    result = review(
        found(1, "b = 2", end_line=2), found(3, end_line=99), found(4, end_line=1, suggestion="")
    )
    assert [(f.line, f.end_line) for f in result.findings] == [(2, 3), (3, 4), (4, None)]
    assert result.findings[2].suggestion is None


def test_max_findings_cap_and_truncation_note() -> None:
    result = review(found(4), found(1), found(3), max_findings=2, truncated=True)
    assert [f.line for f in result.findings] == [1, 3]
    assert result.dropped == 1
    assert "пределу в 20 вызовов" in result.summary


@pytest.mark.parametrize(
    ("severities", "model_verdict", "expected"),
    [
        ((), "issues", "ok"),
        (("nit", "nit"), "issues", "ok"),
        (("nit", "warning"), "ok", "issues"),
        (("bug",), "ok", "issues"),
    ],
)
def test_verdict_follows_kept_severities(
    severities: tuple[Severity, ...], model_verdict: str, expected: str
) -> None:
    findings = [found(n, severity=s) for n, s in enumerate(severities, 1)]
    assert review(*findings, verdict=model_verdict).verdict == expected


def test_findings_repeating_linters_are_removed_and_counted() -> None:
    mentioned = found(3, "c = 3", detail="F841: значение не используется")
    lint = (issue("ruff", 3, "F841"),)
    result = review(found(1), found(3, "c = 3", "warning"), mentioned, found(3, "c = 3"), lint=lint)
    assert [(f.line, f.severity) for f in result.findings] == [(1, "bug"), (3, "bug")]
    assert result.findings[1].detail == "D"
    assert result.dropped == 0
    assert "Повторы замечаний линтеров убраны: 2." in result.summary
    assert "Не показано" not in result.summary


def test_lines_split_like_python_tokenizer() -> None:
    text = "a = 1\n\x0c\n# x\u2028y\x1cz\x85w\x0bq\r\nb = c\rd = 4\n"
    source = SourceFile(name="f.py", text=text, size=len(text.encode()))
    tree = ast.parse(text)
    assert source.lines == tree.body[-1].lineno == 5
    listing, shown = user_message(source, 10_000)
    assert shown == 5
    assert "    4 | b = c" in listing.split("\n")
    result = review(found(1, "b = c"), found(6), source=source)
    assert [f.line for f in result.findings] == [tree.body[1].lineno] == [4]
    assert result.dropped == 1
