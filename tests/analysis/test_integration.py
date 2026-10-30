import os
from functools import partial
from pathlib import Path

import pytest

from pyreview.analysis.application.service import ReviewService
from pyreview.linters.infrastructure.ruff import RuffLinter
from pyreview.linters.infrastructure.ty import TyLinter
from pyreview.shared.config import Settings
from pyreview.shared.infrastructure.llm import build_chat_model
from tests.fakes import CONFIG

SAMPLE = Path(__file__).parents[1] / "fixtures" / "samples" / "buggy.py"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("GIGACHAT_CREDENTIALS"), reason="нет GIGACHAT_CREDENTIALS"
    ),
]


async def test_real_gigachat_reviews_buggy_sample() -> None:
    linters = CONFIG.linters
    service = ReviewService(
        CONFIG,
        [
            RuffLinter(linters.ruff_select, linters.timeout_seconds),
            TyLinter(linters.timeout_seconds),
        ],
        partial(build_chat_model, CONFIG.llm, Settings()),
    )

    report = await service.review(SAMPLE.name, SAMPLE.read_bytes())

    print(f"\n{report.usage}\n{report.review.verdict}: {report.review.summary}")
    for f in report.review.findings:
        print(f"  {f.line}-{f.end_line} {f.severity} {f.title}")
    for i in report.lint:
        print(f"  lint {i.tool} {i.line}:{i.column} {i.code}")
    for s in report.reasoning:
        print(f"  #{s.n} {s.at_ms}ms {s.kind} {s.tool or ''} {(s.text or '')[:120]!r}")
    assert report.review.verdict == "issues"
    assert report.review.findings
    assert {"F401"} <= {i.code for i in report.lint}
    assert {s.kind for s in report.reasoning} >= {
        "thought",
        "tool_call",
        "tool_result",
        "conclusion",
    }
    assert all(1 <= f.line <= report.file.lines for f in report.review.findings)
