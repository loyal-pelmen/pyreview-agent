## Purpose

HTTP-контракт между страницей и бэкендом: эндпоинт ревью, несекретный конфиг, живость, единый конверт ошибки и отдача страницы. Форма тел — `openspec/notes/api-contract.md`.

## ADDED Requirements

### Requirement: `POST /api/v1/review`
Бэкенд MUST принимать `POST /api/v1/review` с `multipart/form-data` и полем `file` и отвечать `200` с JSON из полей `file`, `review`, `lint`, `reasoning`, `model`, `usage` по `openspec/notes/api-contract.md`; ошибки — `400 unsupported_file`, `413 file_too_large`, `422 not_utf8`, `502 model_unavailable`, `504 analysis_timeout`, `500 internal`.

Трассировка: `FR-V-01`, `INV-07`; блок приёмки 4.

#### Scenario: Успешный ответ
- **WHEN** страница отправляет допустимый `app.py`
- **THEN** ответ `200` содержит все шесть полей, `model.name` совпадает с `llm.model`, `usage.tool_calls` равен числу шагов `tool_call`

#### Scenario: Непредвиденная ошибка
- **WHEN** при анализе падает непредусмотренное исключение
- **THEN** ответ `500` с `error.code = "internal"` и сообщением на русском без трассировки

### Requirement: Конверт ошибки и идентификатор запроса
Любая ошибка MUST отдаваться конвертом `{"error": {"code", "message"}}` с кодом латиницей и сообщением на русском, а каждый ответ — нести заголовок `X-Request-Id`.

Трассировка: `INV-07`, `NFR-03`; блок приёмки 6.

#### Scenario: Ошибка в конверте
- **WHEN** запрос отклонён с `413`
- **THEN** тело — `{"error": {"code": "file_too_large", "message": "…"}}`, заголовок `X-Request-Id` есть

#### Scenario: Лог без содержимого
- **WHEN** запрос обработан
- **THEN** в логе есть идентификатор запроса, размер, число строк, модель, число вызовов, число находок и длительность, а текста файла и ревью нет

### Requirement: `GET /api/v1/config`
Бэкенд MUST отдавать `GET /api/v1/config` с `200`: `model` (`provider`, `name`), список включённых линтеров и `limits` с `max_file_bytes`, `max_findings`, `analysis_timeout_seconds` — без секретов.

Трассировка: `FR-C-03`, `INV-02`; блок приёмки 5.

#### Scenario: Несекретный конфиг
- **WHEN** страница запрашивает `GET /api/v1/config`
- **THEN** ответ содержит имя модели и предел размера файла и не содержит значений переменных `GIGACHAT_*`

### Requirement: `GET /healthz` и статика
Бэкенд MUST отвечать на `GET /healthz` `200` с `{"status": "ok"}` без обращения к GigaChat и линтерам и отдавать страницу с `GET /`, `GET /styles.css`, `GET /app.js` с `Cache-Control: no-cache`.

Трассировка: `NFR-04`, `INV-09`; блоки приёмки 4, 6.

#### Scenario: Живость без модели
- **WHEN** GigaChat недоступен
- **THEN** `GET /healthz` отвечает `200`

#### Scenario: Страница с корня
- **WHEN** браузер открывает `http://127.0.0.1:8000/`
- **THEN** приходит `index.html` с того же origin, что и API
