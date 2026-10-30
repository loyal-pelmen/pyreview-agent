from typing import Literal

from pydantic import BaseModel, Field


class DraftFinding(BaseModel):
    """Одна настоящая проблема в коде с точной строкой из пронумерованного листинга."""

    line: int = Field(description="Номер строки из листинга, где начинается проблема")
    end_line: int = Field(
        default=0, description="Номер последней строки проблемы или 0, если строка одна"
    )
    quote: str = Field(description="Точный текст кода строки line из листинга, без номера")
    severity: Literal["bug", "warning", "nit"] = Field(
        description="bug — ошибка в поведении, warning — риск ошибки, nit — мелочь"
    )
    title: str = Field(description="Коротко, что не так, на русском")
    detail: str = Field(description="Почему это ошибка и к чему приведёт, на русском")
    suggestion: str = Field(default="", description="Предлагаемая правка или пустая строка")


class ReviewDraft(BaseModel):
    """Итоговое ревью файла. Вызови один раз, когда разбор закончен."""

    reasoning: str = Field(description="Краткий итог рассуждений: что проверил и к чему пришёл")
    verdict: Literal["ok", "issues"] = Field(
        description="ok — настоящих проблем нет, issues — есть находки"
    )
    summary: str = Field(description="Итог ревью на 2–5 предложений, на русском")
    findings: list[DraftFinding] = Field(
        default_factory=list,
        description="Только логические ошибки, которых нет в выводе ruff и ty: строки и проблемы, "
        "уже указанные линтерами, сюда не попадают",
    )
