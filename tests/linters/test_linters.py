import os
import sys
from pathlib import Path

import pytest

from pyreview.linters.application import Linter
from pyreview.linters.infrastructure import _process
from pyreview.linters.infrastructure.ruff import RuffLinter
from pyreview.linters.infrastructure.ty import TyLinter

BROKEN = "import os\nimport requests\n\n\ndef total(x: int) -> int:\n    return missing + x\n"
CLEAN = "def total(x: int) -> int:\n    return x + 1\n"


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "sample.py"
    path.write_text(text)
    return path


def ruff() -> RuffLinter:
    return RuffLinter(select=("E", "F"), timeout_seconds=30)


async def test_ruff_finds_unused_import_and_undefined_name(tmp_path: Path) -> None:
    run = await ruff().run(write(tmp_path, BROKEN))
    assert run.error is None
    assert not run.timed_out
    assert [(i.line, i.column, i.code) for i in run.issues] == [
        (1, 8, "F401"),
        (2, 8, "F401"),
        (6, 12, "F821"),
    ]
    assert all(i.tool == "ruff" and i.message for i in run.issues)


async def test_ty_finds_undefined_name_and_ignores_unresolved_import(tmp_path: Path) -> None:
    run = await TyLinter(timeout_seconds=30).run(write(tmp_path, BROKEN))
    assert run.error is None
    assert [(i.tool, i.line, i.column, i.code) for i in run.issues] == [
        ("ty", 6, 12, "unresolved-reference")
    ]
    assert run.issues[0].message.startswith("Name `missing`")


async def test_ty_ignores_parent_project_config(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.ty.rules]\nunresolved-reference = "ignore"\n')
    (tmp_path / "pkg").mkdir()
    run = await TyLinter(timeout_seconds=30).run(write(tmp_path / "pkg", BROKEN))
    assert [i.code for i in run.issues] == ["unresolved-reference"]


@pytest.mark.parametrize("linter", [ruff(), TyLinter(timeout_seconds=30)])
async def test_clean_file_has_no_issues(tmp_path: Path, linter: Linter) -> None:
    run = await linter.run(write(tmp_path, CLEAN))
    assert run.issues == ()
    assert run.error is None
    assert not run.timed_out


async def test_timeout_kills_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pid_file = tmp_path / "pid"
    script = tmp_path / "slow"
    script.write_text(f"#!/bin/sh\necho $$ > {pid_file}\nexec sleep 30\n")
    script.chmod(0o755)
    monkeypatch.setattr(_process, "find_binary", lambda _: str(script))
    run = await RuffLinter(select=("F",), timeout_seconds=0.5).run(write(tmp_path, CLEAN))
    assert run.timed_out
    assert run.issues == ()
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


@pytest.mark.parametrize("linter", [ruff(), TyLinter(timeout_seconds=30)])
async def test_missing_binary_sets_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, linter: Linter
) -> None:
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python"))
    monkeypatch.setenv("PATH", str(tmp_path))
    run = await linter.run(write(tmp_path, CLEAN))
    assert run.error is not None
    assert run.issues == ()


@pytest.mark.parametrize("redirect", ["", " >&2"])
async def test_oversized_output_kills_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, redirect: str
) -> None:
    pid_file = tmp_path / "pid"
    script = tmp_path / "noisy"
    script.write_text(
        f"#!/bin/sh\necho $$ > {pid_file}\nhead -c 5000000 /dev/zero{redirect}\nexec sleep 30\n"
    )
    script.chmod(0o755)
    monkeypatch.setattr(_process, "find_binary", lambda _: str(script))
    run = await RuffLinter(select=("F",), timeout_seconds=10).run(write(tmp_path, CLEAN))
    assert run.error == "Вывод линтера слишком большой."
    assert not run.timed_out
    assert run.issues == ()
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)
