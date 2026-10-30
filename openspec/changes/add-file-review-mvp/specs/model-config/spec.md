## Purpose

Модель, линтеры и пределы задаются `config.json` и читаются при старте, секреты GigaChat — только из окружения, чтобы менять модель и пороги без правки кода.

## ADDED Requirements

### Requirement: Секции и ключи `config.json`
Приложение MUST читать при старте `config.json` с секциями `llm`, `linters`, `limits` и ключами из `FR-C-01` и отказываться подниматься при отсутствующем файле, лишнем, пропущенном или неверном ключе, называя поле.

Трассировка: `FR-C-01`, `FR-C-02`, `INV-06`; блок приёмки 5.

#### Scenario: Неверное значение
- **WHEN** в `config.json` `limits.max_findings = 0`
- **THEN** приложение не поднимается, ошибка называет `limits.max_findings`

#### Scenario: Лишний ключ
- **WHEN** в секции `llm` есть неизвестный ключ
- **THEN** приложение не поднимается, ошибка называет этот ключ

#### Scenario: Свой путь к конфигу
- **WHEN** задан `CONFIG_PATH` на другой файл
- **THEN** приложение читает его вместо `config.json` в рабочем каталоге

### Requirement: Смена модели без правки кода
Смена `llm.model` в конфиге и перезапуск MUST менять модель анализа и `model.name` в ответе ревью и в `GET /api/v1/config`.

Трассировка: `FR-C-04`; блок приёмки 5.

#### Scenario: Другая модель
- **WHEN** `llm.model` изменён на `GigaChat-2-Pro` и приложение перезапущено
- **THEN** `GET /api/v1/config` и ответ ревью показывают `GigaChat-2-Pro`

### Requirement: Один провайдер
Приложение MUST принимать в `llm.provider` только `gigachat` и отвергать при старте другое значение с перечнем поддерживаемых.

Трассировка: `FR-C-05`; блок приёмки 5.

#### Scenario: Неизвестный провайдер
- **WHEN** `llm.provider = "openai"`
- **THEN** приложение не поднимается, ошибка называет `llm.provider` и допустимое `gigachat`

### Requirement: Секреты только в окружении
Ключ GigaChat MUST приходить из `GIGACHAT_CREDENTIALS`, область — из `GIGACHAT_SCOPE`, bundle сертификатов — из `GIGACHAT_CA_BUNDLE_FILE`; значения не попадают в `config.json`, промпт, ответ API и лог.

Трассировка: `INV-02`; блоки приёмки 5, 6.

#### Scenario: Ключа нет
- **WHEN** `GIGACHAT_CREDENTIALS` не задан
- **THEN** приложение поднимается, `GET /healthz` отвечает `200`, а ревью отвечает `502 model_unavailable`
