# 0009 — MVP: ревью одного файла `.py` агентом

Тип: фича
Статус: в работе, 30.10.2026

## Задача

Собрать флоу «перетащил `.py` → получил ревью и цепочку рассуждений» целиком: приём и проверка файла, адаптеры `ruff` и `ty` и инструменты `run_ruff`, `run_ty`, агент Deep Agents на GigaChat со структурированным ответом, `POST /api/v1/review`, `GET /api/v1/config`, `GET /healthz`, страница в `frontend/`. Шаги 1–5 плана `openspec/notes/mvp-plan.md` делаются одним изменением OpenSpec `add-file-review-mvp`, а не пятью: части пишутся параллельно против общих контрактов в `src/pyreview/shared/`, `linters/domain.py`, `linters/application.py`, `analysis/domain.py`.

## Контекст

Решения уже приняты записями [0002](0002-deep-agents-with-gigachat.md), [0003](0003-linters-as-agent-tools.md), [0006](0006-web-page-with-file-upload.md)–[0008](0008-model-config-in-json.md); контракт — `openspec/notes/api-contract.md`, требования — `Rules/REQUIREMENTS.md`, блоки приёмки 1–6. Пакет называется `pyreview`. Живой прогон на GigaChat-2-Max показал ограничения модели, записанные в `openspec/notes/gigachat.md`, и особенности каркаса из `openspec/notes/deepagents.md`; решения внутри изменения — в `design.md` изменения.

## Что не делаем

- Шаг 6 плана: прогон на наборе файлов с известными багами, настройка промпта и разметка `integration` — отдельным изменением.
- Потоковая лента рассуждений (запись 0007), `FR-V-06`, `FR-R-06`, субагенты, второй провайдер модели.
- Всё из Out of scope `openspec/config.yaml`: хранение, несколько файлов, GitHub, правка кода за пользователя, фреймворки на фронте.
- Инварианты `INV-*` не меняются.

## Что готово когда

- `openspec validate add-file-review-mvp --strict` проходит, задачи реализации в `tasks.md` закрыты.
- `make lint` и `make test` зелёные; тесты с фейком модели покрывают `400`, `413`, `422`, `502`, `504`, два вызова за ход и превышение `limits.max_tool_calls`.
- Живая проверка по критерию готовности MVP из `openspec/notes/mvp-plan.md` пройдена вручную; после неё статус — «выполнено».
