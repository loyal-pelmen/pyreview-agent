## 1. shared

- [x] 1.1 Снять фикстуры вывода `ruff` и `ty` на файле с известными ошибками и пример ответа модели в `tests/fixtures/`
- [x] 1.2 `AppConfig`, `Settings`, `load_config` с ключами `FR-C-01` и `extra="forbid"`
- [x] 1.3 `AppError` и ошибки `unsupported_file`, `file_too_large`, `not_utf8`, `model_unavailable`, `analysis_timeout`
- [x] 1.4 `build_chat_model(llm, settings)`: `GigaChat` из конфига и окружения, `allow_any_tool_choice_fallback=True`, bundle сертификатов из `GIGACHAT_CA_BUNDLE_FILE`
- [x] 1.5 Структурный лог с идентификатором запроса без текста файла
- [x] 1.6 Проверка: `uv run ty check src/pyreview/shared` и тесты конфига на неверное поле зелёные

## 2. linters

- [x] 2.1 Доменные `LintIssue`, `LintRun` и порт `Linter`
- [x] 2.2 `RuffLinter(select, timeout_seconds)`: запуск с фиксированными аргументами, разбор вывода в `LintIssue`, таймаут в `LintRun.timed_out`
- [x] 2.3 `TyLinter(timeout_seconds)`: запуск, разбор вывода, таймаут
- [x] 2.4 Проверка: тесты адаптеров на фикстурах и на таймауте зелёные

## 3. analysis

- [x] 3.1 Инструмент `run_ruff` с моделью аргументов `{path}`, проверкой пути и обрезкой до `limits.max_tool_output_chars`; тест на неверный аргумент и чужой путь
- [x] 3.2 Инструмент `run_ty` так же; тест на неверный аргумент и таймаут
- [x] 3.3 Промпт на русском, пронумерованный листинг с обрезкой до `limits.max_prompt_chars`, модель структурированного ответа с описаниями полей
- [x] 3.4 Middleware: один вызов инструмента за ход, отказ по лишним, счётчик `limits.max_tool_calls`
- [x] 3.5 Сборка агента: `FilesystemMiddleware` с allowlist чтения над каталогом запроса, `HarnessProfile` без `general-purpose`, выключенный линтер не в инструментах
- [x] 3.6 Коллектор шагов `reasoning` из следа с `at_ms` и обрезкой до 2000 символов
- [x] 3.7 Выравнивание строк по цитате, отбрасывание вне диапазона в `dropped`, предел `limits.max_findings`, вердикт
- [x] 3.8 `ReviewService.review(name, data)`: проверка файла, временный каталог с удалением в `finally`, пустой файл без модели, `ModelUnavailable`, `AnalysisTimeout`
- [x] 3.9 Проверка: тесты сервиса с фейком модели на два вызова за ход, превышение `max_tool_calls`, `502` и `504` зелёные

## 4. entrypoints

- [x] 4.1 FastAPI-приложение, сборка зависимостей из `AppConfig` и `Settings`, обработчик `AppError` в конверт, `X-Request-Id`
- [x] 4.2 `POST /api/v1/review` по контракту
- [x] 4.3 `GET /api/v1/config` и `GET /healthz`
- [x] 4.4 Отдача `frontend/` с корня с `Cache-Control: no-cache`
- [x] 4.5 Проверка: тесты API через `httpx.AsyncClient` на `200`, `400`, `413`, `422`, `502`, `504` зелёные

## 5. frontend

- [x] 5.1 `index.html` и `styles.css`: зона перетаскивания, разметка результата, две темы через переменные CSS
- [x] 5.2 `app.js`: загрузка `/api/v1/config`, проверка расширения и размера до отправки, отправка `multipart/form-data`
- [x] 5.3 `app.js`: состояния пусто, файл над зоной, отправка, результат, ошибка
- [x] 5.4 `app.js`: код с номерами строк и подсветкой, находки ревью и линтеров, клик к строке, сворачиваемая лента, модель в подвале, код как текст
- [x] 5.5 Режим `?demo` с примером ответа по контракту в `frontend/fixtures/sample-response.json`
- [x] 5.6 Проверка: чек-лист состояний пройден руками на `/?demo`, `.txt` отклоняется до отправки

## 6. tests

- [x] 6.1 Фейк модели с заданной последовательностью вызовов инструментов и структурированного ответа
- [x] 6.2 Тест: временный каталог удалён при `200` и при ошибке, параллельные запросы не делят каталог
- [x] 6.3 Проверка: `make lint` и `make test` зелёные
- [x] 6.4 Живой прогон по критерию готовности MVP из `openspec/notes/mvp-plan.md` с ключом GigaChat
- [x] 6.5 Ветка, PR с типом задачи и ссылкой на запись 0009, зелёный CI
