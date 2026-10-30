from collections.abc import Sequence
from pathlib import Path

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from pyreview.analysis.application.trace import THINK, Trace
from pyreview.linters.application import Linter
from pyreview.linters.domain import LintRun

DESCRIPTIONS = {
    "ruff": "Запустить линтер ruff над присланным файлом. Возвращает замечания построчно "
    "в виде «строка:столбец код сообщение».",
    "ty": "Запустить проверку типов ty над присланным файлом. Возвращает замечания построчно "
    "в виде «строка:столбец код сообщение».",
}


class PathArgs(BaseModel):
    """Аргументы запуска линтера."""

    path: str = Field(description="Путь к присланному файлу, например /app.py")


class ThinkArgs(BaseModel):
    """Аргументы записи мысли."""

    thought: str = Field(description="Короткая мысль: что делаешь, почему и что увидел")


@tool(THINK, args_schema=ThinkArgs)
async def think(thought: str) -> str:
    """Записать мысль перед каждым действием и после каждого результата инструмента."""
    return "Мысль записана." if thought.strip() else "Мысль пустая, сформулируй её."


def format_run(run: LintRun, max_chars: int) -> str:
    if run.timed_out:
        return f"{run.tool} не завершился за отведённое время."
    if run.error:
        return f"{run.tool} завершился с ошибкой: {run.error}"
    text = "\n".join(f"{i.line}:{i.column} {i.code} {i.message}" for i in run.issues)
    if not text:
        return "замечаний нет"
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}\n… вывод обрезан: показано {max_chars} из {len(text)} символов"


def _lint_tool(
    linter: Linter, workspace: Path, file_name: str, max_chars: int, trace: Trace
) -> BaseTool:
    async def run(path: str) -> str:
        if path.strip().removeprefix("./").removeprefix("/") != file_name:
            return f"Отказ: проверять можно только присланный файл /{file_name}."
        trace.runs[linter.name] = result = await linter.run(workspace / file_name)
        return format_run(result, max_chars)

    name, description = f"run_{linter.name}", DESCRIPTIONS[linter.name]
    return tool(name, description=description, args_schema=PathArgs)(run)


def build_tools(
    linters: Sequence[Linter], workspace: Path, file_name: str, max_chars: int, trace: Trace
) -> list[BaseTool]:
    return [think, *(_lint_tool(lin, workspace, file_name, max_chars, trace) for lin in linters)]
