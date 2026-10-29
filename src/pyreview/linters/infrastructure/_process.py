import asyncio
import shutil
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

from pyreview.linters.domain import LintIssue, LintRun

OUTPUT_LIMIT = 4 * 1024 * 1024


def find_binary(name: str) -> str | None:
    local = Path(sys.executable).parent / name
    return str(local) if local.is_file() else shutil.which(name)


async def read_capped(
    process: asyncio.subprocess.Process, stream: asyncio.StreamReader
) -> bytes | None:
    try:
        await stream.readexactly(OUTPUT_LIMIT + 1)
    except asyncio.IncompleteReadError as exc:
        return exc.partial
    if process.returncode is None:
        process.kill()
    return None


async def run_linter(
    tool: str,
    args: list[str],
    path: Path,
    timeout_seconds: float,
    parse: Callable[[str], list[LintIssue]],
    env: Mapping[str, str] | None = None,
) -> LintRun:
    binary = find_binary(tool)
    if binary is None:
        return LintRun(tool, (), error=f"{tool} не найден рядом с интерпретатором и в PATH")
    process = await asyncio.create_subprocess_exec(
        binary,
        *args,
        "--",
        path.name,
        cwd=path.parent,
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr, _ = await asyncio.wait_for(
            asyncio.gather(
                read_capped(process, cast(asyncio.StreamReader, process.stdout)),
                read_capped(process, cast(asyncio.StreamReader, process.stderr)),
                process.wait(),
            ),
            timeout_seconds,
        )
    except TimeoutError:
        return LintRun(tool, (), timed_out=True)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    if stdout is None or stderr is None:
        return LintRun(tool, (), error="Вывод линтера слишком большой.")
    if process.returncode not in (0, 1):
        message = stderr.decode(errors="replace").strip()[:500]
        return LintRun(tool, (), error=message or f"{tool} завершился с кодом {process.returncode}")
    try:
        issues = parse(stdout.decode(errors="replace"))
    except (ValueError, KeyError, TypeError) as exc:
        return LintRun(tool, (), error=f"не удалось разобрать вывод {tool}: {exc}")
    return LintRun(tool, tuple(sorted(issues, key=lambda issue: (issue.line, issue.column))))
