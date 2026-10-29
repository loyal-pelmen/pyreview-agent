import tempfile
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from pyreview.analysis.application.service import ReviewService
from pyreview.shared.config import AppConfig
from pyreview.shared.errors import (
    AnalysisTimeout,
    FileTooLarge,
    ModelUnavailable,
    NotUtf8,
    UnsupportedFile,
)
from tests.fakes import CONFIG, FakeLinter, ScriptedModel, call, calls, draft, issue, make_config

SOURCE = (
    b"import os\n\n\ndef first(items):\n    return items[1]\n\n\n"
    b"def total(values=[]):\n    values.append(1)\n    return sum(values)\n"
)
TOOLS = {"think", "run_ruff", "run_ty", "read_file", "ls", "grep"}
BUG = {"severity": "bug", "title": "Ошибка", "detail": "Подробно."}


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return tmp_path


def leftovers(path: Path) -> list[Path]:
    return list(path.iterdir())


def service(
    model: ScriptedModel, *linters: FakeLinter, config: AppConfig = CONFIG
) -> ReviewService:
    return ReviewService(config, linters, lambda: model)


async def test_happy_path(workdir: Path) -> None:
    ruff = FakeLinter("ruff", (issue("ruff", 1, "F401", column=8),))
    ty = FakeLinter("ty", (issue("ty", 1, "unresolved-import"),))
    model = ScriptedModel(
        script=[
            call("think", thought="Посмотрю линтеры."),
            call("run_ruff", path="/sample.py"),
            call("think", text="Читаю файл.", thought="Теперь типы."),
            call("run_ty", path="sample.py"),
            call("read_file", file_path="/sample.py"),
            draft(
                {"line": 3, "quote": "return items[1]", **BUG},
                {"line": 8, "end_line": 9, "quote": "   8 | def total(values=[]):", **BUG},
            ),
        ]
    )

    report = await service(model, ruff, ty).review("pkg/sample.py", SOURCE)

    assert report.file.name == "sample.py"
    assert report.file.lines == 10
    assert [(f.line, f.end_line) for f in report.review.findings] == [(5, None), (8, 9)]
    assert report.review.verdict == "issues"
    assert report.review.dropped == 0
    assert [(i.tool, i.line, i.column) for i in report.lint] == [("ty", 1, 1), ("ruff", 1, 8)]
    assert [(s.kind, s.tool) for s in report.reasoning] == [
        ("thought", None),
        ("tool_call", "run_ruff"),
        ("tool_result", "run_ruff"),
        ("thought", None),
        ("thought", None),
        ("tool_call", "run_ty"),
        ("tool_result", "run_ty"),
        ("tool_call", "read_file"),
        ("tool_result", "read_file"),
        ("conclusion", None),
    ]
    assert [s.n for s in report.reasoning] == list(range(1, 11))
    assert [s.at_ms for s in report.reasoning] == sorted(s.at_ms for s in report.reasoning)
    assert report.reasoning[2].text == "1:8 F401 F401 message"
    assert "return items[1]" in (report.reasoning[8].text or "")
    assert report.reasoning[-1].text == "Проверил линтеры и логику."
    assert report.usage.tool_calls == 3
    assert report.usage.tokens == 90
    assert not report.usage.truncated
    assert report.model.name == CONFIG.llm.model
    assert len(ruff.paths) == len(ty.paths) == 1
    assert set(model.offered[0]) == TOOLS
    assert set(model.offered[-1]) == {*TOOLS, "ReviewDraft"}
    assert leftovers(workdir) == []


async def test_answer_waits_for_linters() -> None:
    ruff = FakeLinter("ruff")
    model = ScriptedModel(
        script=[draft(verdict="ok"), call("run_ruff", path="/sample.py"), draft(verdict="ok")]
    )

    report = await service(model, ruff).review("sample.py", SOURCE)

    assert [s.kind for s in report.reasoning] == ["tool_call", "tool_result", "conclusion"]
    assert "ReviewDraft" not in model.offered[1]
    assert "ReviewDraft" in model.offered[2]
    assert report.review.verdict == "ok"


async def test_linter_not_called_by_model_is_run_by_service() -> None:
    ruff = FakeLinter("ruff", (issue("ruff", 2, "E303"),))
    ty = FakeLinter("ty", (issue("ty", 1, "invalid-return-type"),))
    model = ScriptedModel(
        script=[
            call("run_ruff", path="/sample.py"),
            AIMessage("Готово."),
            draft(verdict="ok"),
            draft(verdict="ok"),
        ]
    )

    report = await service(model, ruff, ty).review("sample.py", SOURCE)

    assert [(i.tool, i.line) for i in report.lint] == [("ty", 1), ("ruff", 2)]
    assert [(s.kind, s.tool) for s in report.reasoning] == [
        ("tool_call", "run_ruff"),
        ("tool_result", "run_ruff"),
        ("thought", None),
        ("tool_result", "run_ty"),
        ("conclusion", None),
    ]
    assert (report.reasoning[3].text or "").startswith("Запущен сервисом.")
    assert len(ty.paths) == 1


async def test_parallel_calls_are_trimmed() -> None:
    ruff = FakeLinter("ruff")
    model = ScriptedModel(
        script=[
            calls(("think", {"thought": "Сразу два."}), ("run_ruff", {"path": "/sample.py"})),
            call("run_ruff", path="/sample.py"),
            draft(verdict="ok"),
        ]
    )

    report = await service(model, ruff).review("sample.py", SOURCE)

    kinds = [s.kind for s in report.reasoning]
    assert kinds == ["thought", "tool_call", "tool_result", "conclusion"]
    assert report.usage.tool_calls == 1
    assert len(ruff.paths) == 1


async def test_tool_limit_stops_tools_and_falls_back() -> None:
    ruff = FakeLinter("ruff")
    model = ScriptedModel(
        script=[
            call("think", thought="Начну с ruff."),
            call("run_ruff", path="./sample.py"),
            call("run_ruff", path="sample.py"),
            AIMessage("Готово, ошибок нет."),
            draft(verdict="ok"),
            draft(verdict="ok"),
        ]
    )

    report = await service(model, ruff, config=make_config(max_tool_calls=2)).review(
        "sample.py", SOURCE
    )

    assert report.usage.truncated
    assert report.usage.tool_calls == 1
    assert len(ruff.paths) == 1
    assert "пределу в 2 вызовов" in report.review.summary
    assert model.offered[-2] == model.offered[-1] == ["ReviewDraft"]
    results = [s.text for s in report.reasoning if s.kind == "tool_result"]
    assert "Лимит вызовов" in (results[-1] or "")


async def test_wrong_path_is_refused() -> None:
    ruff = FakeLinter("ruff")
    model = ScriptedModel(
        script=[
            call("run_ruff", path="/etc/passwd"),
            call("run_ruff", path="/sample.py"),
            draft(verdict="ok"),
        ]
    )

    report = await service(model, ruff).review("sample.py", SOURCE)

    assert (report.reasoning[1].text or "").startswith("Отказ")
    assert len(ruff.paths) == 1


async def test_disabled_linter_is_not_offered() -> None:
    ruff, ty = FakeLinter("ruff"), FakeLinter("ty")
    config = CONFIG.model_copy(update={"linters": CONFIG.linters.model_copy(update={"ty": False})})
    model = ScriptedModel(script=[call("run_ruff", path="/sample.py"), draft(verdict="ok")])

    report = await service(model, ruff, ty, config=config).review("sample.py", SOURCE)

    assert "run_ty" not in model.offered[0]
    assert ty.paths == []
    assert [s.tool for s in report.reasoning if s.kind == "tool_result"] == ["run_ruff"]


@pytest.mark.parametrize(
    ("name", "data", "error"),
    [
        ("sample.txt", SOURCE, UnsupportedFile),
        (".py", SOURCE, UnsupportedFile),
        ("dir/", SOURCE, UnsupportedFile),
        ("sample.py", b"x" * (CONFIG.limits.max_file_bytes + 1), FileTooLarge),
        ("sample.py", "привет".encode("cp1251"), NotUtf8),
        ("a" * 297 + ".py", SOURCE, UnsupportedFile),
        ("я" * 127 + ".py", SOURCE, UnsupportedFile),
        ("bad\x00.py", SOURCE, UnsupportedFile),
    ],
)
async def test_rejected_files(name: str, data: bytes, error: type[Exception]) -> None:
    model = ScriptedModel(script=[])
    with pytest.raises(error):
        await service(model).review(name, data)
    assert model.offered == []


async def test_longest_name_is_reviewed(workdir: Path) -> None:
    name = "a" * 252 + ".py"
    ruff = FakeLinter("ruff")
    model = ScriptedModel(script=[call("run_ruff", path=f"/{name}"), draft(verdict="ok")])

    report = await service(model, ruff).review(name, SOURCE)

    assert report.file.name == name
    assert ruff.paths[0].name == name
    assert leftovers(workdir) == []


async def test_lint_list_is_capped() -> None:
    ruff = FakeLinter("ruff", tuple(issue("ruff", n, "E501") for n in (3, 1, 2)))
    model = ScriptedModel(script=[call("run_ruff", path="/sample.py"), draft(verdict="ok")])

    report = await service(model, ruff, config=make_config(max_lint_issues=2)).review(
        "sample.py", SOURCE
    )

    note = "Показаны первые 2 замечаний линтеров из 3."
    assert [i.line for i in report.lint] == [1, 2]
    assert [(s.kind, s.text) for s in report.reasoning[-2:]] == [
        ("thought", note),
        ("conclusion", "Проверил линтеры и логику."),
    ]
    assert note in report.review.summary


async def test_empty_file_skips_model() -> None:
    model = ScriptedModel(script=[])

    report = await service(model, FakeLinter("ruff")).review("SAMPLE.PY", b"\xef\xbb\xbf \n\n")

    assert report.review.verdict == "ok"
    assert report.review.summary == "Файл пустой — проверять нечего."
    assert report.review.findings == report.lint == report.reasoning == ()
    assert model.offered == []


async def test_model_error_maps_to_unavailable(workdir: Path) -> None:
    model = ScriptedModel(script=[], error=RuntimeError("401 secret"))

    with pytest.raises(ModelUnavailable) as exc:
        await service(model, FakeLinter("ruff")).review("sample.py", SOURCE)

    assert "secret" not in exc.value.message
    assert leftovers(workdir) == []


async def test_model_without_answer_is_unavailable() -> None:
    model = ScriptedModel(script=[AIMessage("Не знаю."), AIMessage("Всё ещё не знаю.")])

    with pytest.raises(ModelUnavailable):
        await service(model).review("sample.py", SOURCE)


async def test_slow_model_times_out(workdir: Path) -> None:
    model = ScriptedModel(script=[draft(verdict="ok")], delay=1)
    config = make_config(analysis_timeout_seconds=0.05)

    with pytest.raises(AnalysisTimeout):
        await service(model, config=config).review("sample.py", SOURCE)

    assert leftovers(workdir) == []


async def test_long_file_is_truncated_in_prompt() -> None:
    model = ScriptedModel(script=[draft(verdict="ok")])
    source = b"".join(f"x_{n} = {n}\n".encode() for n in range(200))

    report = await service(model, config=make_config(max_prompt_chars=500)).review("big.py", source)

    assert report.reasoning[0].kind == "thought"
    assert "из 200" in (report.reasoning[0].text or "")


LONE_BUG = {"line": 1, "quote": "", "severity": "bug", "title": "Ошибка", "detail": "Подробно."}


@pytest.mark.parametrize("first", ["ok", "issues"])
async def test_fallback_without_findings_is_asked_again(first: str) -> None:
    ruff = FakeLinter("ruff")
    model = ScriptedModel(
        script=[
            call("run_ruff", path="/sample.py"),
            AIMessage("Разобрал."),
            draft(verdict=first),
            draft(LONE_BUG),
        ]
    )

    report = await service(model, ruff).review("sample.py", SOURCE)

    assert report.review.verdict == "issues"
    assert [f.title for f in report.review.findings] == ["Ошибка"]
    assert model.script == []
