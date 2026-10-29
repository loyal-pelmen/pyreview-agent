# Контракт страницы и бэкенда

Единственное описание HTTP-контракта между `frontend/` и бэкендом. Правка контракта затрагивает обе части в одном изменении (`Rules/RULES.md`). Составлен 29.10.2026 по записям 0006–0008.

## Общее

- Префикс `/api/v1`, JSON в UTF-8. Страница отдаётся с корня тем же приложением, поэтому запросы идут на тот же origin без CORS.
- Ошибка — конверт `{"error": {"code": "<латиницей>", "message": "<на русском>"}}` с подходящим HTTP-кодом.
- Заголовок `X-Request-Id` в ответе — идентификатор запроса из лога.

## `GET /healthz`

`200` с `{"status": "ok"}` без обращения к GigaChat и линтерам.

## `GET /api/v1/config`

`200` с несекретной частью конфига:

```json
{
  "model": {"provider": "gigachat", "name": "GigaChat-2"},
  "linters": ["ruff", "ty"],
  "limits": {"max_file_bytes": 200000, "max_findings": 30, "analysis_timeout_seconds": 300}
}
```

Страница берёт отсюда предел размера для проверки до отправки и имя модели для подвала.

## `POST /api/v1/review`

Запрос — `multipart/form-data` с одним полем `file`: имя файла с расширением `.py`, содержимое в UTF-8, размер не больше `limits.max_file_bytes`.

Ответ `200`:

```json
{
  "file": {"name": "app.py", "bytes": 4210, "lines": 120},
  "review": {
    "verdict": "issues",
    "summary": "Итог на 2–5 предложений.",
    "findings": [
      {
        "line": 42, "end_line": 44, "severity": "bug",
        "title": "Коротко, что не так",
        "detail": "Объяснение на русском.",
        "suggestion": "Предлагаемая правка или null"
      }
    ],
    "dropped": 0
  },
  "lint": [
    {"tool": "ruff", "line": 3, "column": 8, "code": "F401", "message": "`os` imported but unused"},
    {"tool": "ty", "line": 17, "column": 12, "code": "invalid-argument-type", "message": "…"}
  ],
  "reasoning": [
    {"n": 1, "at_ms": 0, "kind": "thought", "text": "Сначала посмотрю, что скажут линтеры."},
    {"n": 2, "at_ms": 120, "kind": "tool_call", "tool": "run_ruff", "args": {"path": "app.py"}},
    {"n": 3, "at_ms": 980, "kind": "tool_result", "tool": "run_ruff", "text": "3:8 F401 …", "truncated": false},
    {"n": 4, "at_ms": 6400, "kind": "conclusion", "text": "Главная проблема — незакрытый файл в строке 42."}
  ],
  "model": {"provider": "gigachat", "name": "GigaChat-2"},
  "usage": {"tokens": 5120, "tool_calls": 3, "duration_ms": 6800, "truncated": false}
}
```

- `review.verdict` — `ok` или `issues`. `severity` — `bug`, `warning`, `nit`. `end_line` и `suggestion` могут быть `null`.
- `review.findings` отсортированы по строке; строка всегда в диапазоне `1..file.lines`. Находки без строки или вне диапазона учтены в `review.dropped` и упомянуты в `summary`.
- `lint` — список из инструментов, а не пересказ модели, отсортированный по строке и столбцу и обрезанный до `limits.max_lint_issues`; обрезка видна шагом рассуждений и фразой в `summary`. Пустой список — линтеры ничего не нашли или выключены в конфиге.
- `reasoning[].kind` — `thought`, `tool_call`, `tool_result`, `conclusion`. `text` обрезается до 2000 символов с `truncated: true`.
- `usage.truncated` — `true`, если анализ оборван по `limits.max_tool_calls`; `summary` тогда говорит об этом.

Ошибки:

| Код | `error.code` | Когда |
|---|---|---|
| `400` | `unsupported_file` | расширение не `.py`, нет поля `file`, больше одного файла, лишние поля формы, имя файла длиннее 255 байт или с непечатными символами |
| `413` | `file_too_large` | размер больше `limits.max_file_bytes` |
| `422` | `not_utf8` | содержимое не декодируется как UTF-8 |
| `502` | `model_unavailable` | GigaChat не ответил или отверг запрос |
| `504` | `analysis_timeout` | анализ не уложился в `limits.analysis_timeout_seconds` |
| `500` | `internal` | остальное; подробности только в логе по `X-Request-Id` |

## Статика

`GET /` отдаёт `frontend/index.html`, `GET /styles.css` и `GET /app.js` — соответствующие файлы. Кэширование — `no-cache`, чтобы правка файла была видна без сборки.
