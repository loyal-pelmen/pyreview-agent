# Deep Agents — устройство

Справочная заметка: что даёт каркас и как мы его используем. Сверено 29.10.2026 по документации `docs.langchain.com/oss/python/deepagents` через context7, дополнено 30.10.2026 по исходникам `deepagents` 0.7.32. API библиотеки меняется быстро: перед правкой кода агента сверяй сигнатуры заново.

## Сборка

```python
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware import FilesystemMiddleware

agent = create_deep_agent(
    model=chat_model,
    system_prompt=REVIEW_PROMPT,
    tools=[run_ruff, run_ty],
    middleware=[FilesystemMiddleware(backend=FilesystemBackend(root_dir=workdir), tools=["read_file", "ls", "grep"])],
    response_format=ReviewResult,
)
result = await agent.ainvoke({"messages": [HumanMessage(task)]})
```

- `model` принимает объект `BaseChatModel`; строка `provider:model` для GigaChat не существует.
- `system_prompt` дополняет встроенный промпт каркаса о планировании и файлах, а не заменяет его.
- `tools` — функции под `@tool` или `BaseTool`; аргументы описываются моделью pydantic через `args_schema`.
- `response_format` — модель pydantic итога: итог, вердикт, находки, поле рассуждения; результат лежит в `result["structured_response"]`.
- След для цепочки рассуждений — `result["messages"]`: `AIMessage.content` между вызовами, `AIMessage.tool_calls`, `ToolMessage`; коллектор собирает их в шаги с временем от начала и считает вызовы для `limits.max_tool_calls`.
- Новый экземпляр агента на каждый запрос: `root_dir` у каждого свой, состояние между запросами не живёт.

## Бэкенды файлов

| Бэкенд | Что это | Где у нас |
|---|---|---|
| `StateBackend` | виртуальные файлы в состоянии графа, по умолчанию | нет |
| `FilesystemBackend(root_dir=…)` | настоящие файлы под корнем | временный каталог с присланным файлом |
| `LocalShellBackend` | то же плюс инструмент `execute` | нет: оболочка у модели запрещена (`INV-05`) |
| `StoreBackend`, `CompositeBackend` | долгая память, составной | нет: памяти между запросами нет (`INV-01`) |

Allowlist `FilesystemMiddleware(tools=[...])` убирает `write_file`, `edit_file` и `delete`; `read_file` обязателен в списке, иначе `ValueError`. Свои инструменты из `tools=` allowlist не трогает. `FilesystemMiddleware`, переданный в `middleware=`, заменяет встроенный по имени, а не добавляется вторым.

## Субагенты и профили

Словарь `{"name", "description", "system_prompt", "tools", "model", "middleware"}`; главный агент зовёт их инструментом `task(name, …)`. Режим `isolated` по умолчанию — субагент видит только поручение; `fork` наследует разговор. Субагент с именем `general-purpose` заменяет встроенного. Это точка расширения под новый вид проверки: субагент со своим промптом и подмножеством инструментов вместо ветки в главном промпте.

Встроенный `general-purpose` выключается профилем каркаса: `register_harness_profile("giga", HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)))` из `deepagents.profiles`. Ключ профиля — `ls_provider` модели (`openspec/notes/gigachat.md`). Без субагентов инструмента `task` у агента нет. API профилей — бета.

## Middleware

Список `middleware=` встраивается в цикл агента после базового стека; middleware с тем же `.name`, что у встроенного, заменяет его. `FilesystemMiddleware` и `SubAgentMiddleware` профиль исключить не может — `ValueError`. Наш случай — middleware, которое перед отправкой вызовов инструментов оставляет первый, а остальные превращает в `ToolMessage` с отказом: GigaChat не принимает несколько вызовов за ход (`openspec/notes/gigachat.md`).

## Встроенные инструменты

Каркас сам добавляет `write_todos` для плана, файловые инструменты бэкенда и `task` для субагентов. Промпт главного агента не описывает их заново, а говорит, в каком порядке их применять: план → чтение файла → линтеры → логический разбор → структурированный итог.
