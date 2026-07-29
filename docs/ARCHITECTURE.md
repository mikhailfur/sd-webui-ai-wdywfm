# Архитектура ai-wdywfm

## 1. Цель и архитектурные ограничения

`ai-wdywfm` формирует Stable Diffusion prompt на основе:

- natural-language запроса;
- необязательного reference image;
- текущего режима `txt2img`/`img2img`;
- текущего и установленных checkpoint;
- установленных LoRA;
- локальных и CivitAI metadata;
- правил выбранного prompt dialect.

Архитектура обязана сохранять следующие инварианты:

1. Поддерживается именно Forge Neo и его Gradio 4 UI.
2. Core-файлы Forge не изменяются.
3. LLM получает только подготовленный bounded context, а не прямой доступ к файловой системе.
4. LLM output не считается доверенным до schema и semantic validation.
5. В основные компоненты Forge выводятся только `prompt` и `negative_prompt`.
6. Все остальные значения отображаются read-only.
7. Сетевые ошибки не ломают локальный каталог и не блокируют запуск WebUI.
8. CivitAI Browser Neo может быть установлен рядом, но не является dependency.

## 2. Контекст системы

```text
                         ┌───────────────────┐
                         │ CivitAI REST API  │
                         └─────────▲─────────┘
                                   │ metadata enrichment
┌──────────────┐   request   ┌─────┴──────────────┐   structured request
│ Forge Neo UI ├────────────►│ ai-wdywfm backend ├──────────────────────┐
│ txt2img/i2i  │◄────────────┤                    │                      │
└──────────────┘ prompt only └─────┬──────────────┘                      │
                                   │                                     │
                          scan/read│                                     │
                    ┌──────────────▼────────────┐              ┌─────────▼─────────┐
                    │ Forge model registries + │              │ OpenRouter or     │
                    │ local sidecars/cache     │              │ LM Studio         │
                    └───────────────────────────┘              └───────────────────┘
```

## 3. Интеграция с Forge Neo

### 3.1 Регистрация

Точка входа `scripts/ai_wdywfm.py`:

- наследует `modules.scripts.Script`;
- `show(is_img2img)` возвращает `scripts.AlwaysVisible`;
- `ui(is_img2img)` создаёт accordion для конкретной вкладки;
- `modules.script_callbacks.on_ui_settings` регистрирует настройки;
- `modules.script_callbacks.on_after_component` захватывает только необходимые компоненты по точным `elem_id`;
- `on_before_reload` корректно останавливает workers и закрывает storage.

Целевые prompt components:

| Вкладка | Positive | Negative |
|---|---|---|
| txt2img | `txt2img_prompt` | `txt2img_neg_prompt` |
| img2img | `img2img_prompt` | `img2img_neg_prompt` |

`Apply prompts` возвращает два значения только в эти два Gradio outputs. Компоненты `*_cfg_scale`, `*_width`, `*_height`, `*_sampling`, `*_steps` и scheduler намеренно не сохраняются в набор outputs.

### 3.2 Получение моделей

Checkpoint читаются из `modules.sd_models.checkpoints_list`. Для каждого `CheckpointInfo` используются публичные поля, доступные в Neo:

- `filename`;
- `name`, `title`, `name_for_extra`;
- `sha256`/`shorthash`, если уже рассчитаны;
- `metadata`;
- признак текущего checkpoint из `shared.opts.sd_model_checkpoint`.

LoRA читаются из `extensions-builtin/sd_forge_lora/networks.available_networks`. Перед ручным refresh допускается вызов `networks.list_available_networks()`, но не на каждый UI event.

Импорт LoRA adapter выполняется лениво. Если Neo-модуль недоступен, UI показывает несовместимость и не падает при startup.

### 3.3 Почему не DOM-only

JavaScript полезен для UX, но не должен быть единственным способом записи prompt:

- DOM selectors хрупки при изменениях темы;
- прямое изменение textarea может рассинхронизировать Gradio state;
- Python event с Gradio outputs сохраняет штатную модель событий.

JS используется для badge, copy, preview diff и небольших улучшений. Запись в prompt выполняет Gradio event.

## 4. Слои

```text
UI / Forge adapter
        │
Application use cases
        │
Domain model + policies
        │
Infrastructure adapters
  ├─ Forge Neo inventory
  ├─ sidecar/safetensors readers
  ├─ CivitAI client
  ├─ OpenRouter client
  ├─ LM Studio client
  └─ SQLite cache
```

### 4.1 Domain

Не импортирует Gradio, Forge, requests или provider SDK.

Основные сущности:

- `GenerationIntent`: mode, natural request, optional image descriptor;
- `InstalledModel`: stable local id, kind, alias, path fingerprint;
- `ModelMetadata`: base model, trigger words, descriptions, examples, provenance;
- `ModelCandidate`: model + relevance + compatibility + reason;
- `PromptSuggestion`: проверенный provider-neutral ответ;
- `ReadOnlyRecommendations`;
- `ProviderCapabilities`;
- `ContextBudget`.

### 4.2 Application

Use cases:

- `RefreshModelInventory`;
- `EnrichModelMetadata`;
- `BuildPromptContext`;
- `GeneratePromptSuggestion`;
- `ValidateSuggestion`;
- `ApplyPromptFields`;
- `ClearMetadataCache`;
- `TestProviderConnection`.

Application orchestrates adapters, но не знает HTTP details.

### 4.3 Infrastructure

Каждый внешний источник реализует узкий Protocol:

```python
class LlmProvider(Protocol):
    def capabilities(self) -> ProviderCapabilities: ...
    def list_models(self) -> list[ProviderModel]: ...
    def generate(self, request: PromptRequest) -> RawLlmResponse: ...

class MetadataProvider(Protocol):
    def get_by_hash(self, sha256: str) -> ModelMetadata | None: ...
    def get_by_version_id(self, version_id: int) -> ModelMetadata | None: ...
```

OpenRouter и LM Studio возвращают один и тот же `RawLlmResponse`; CivitAI и sidecar readers возвращают один `ModelMetadata`.

## 5. Файловая структура

```text
ai_wdywfm/
├── application/
│   ├── build_context.py
│   ├── generate_suggestion.py
│   ├── refresh_inventory.py
│   └── validate_suggestion.py
├── domain/
│   ├── models.py
│   ├── policies.py
│   ├── ports.py
│   └── errors.py
├── infrastructure/
│   ├── civitai/
│   │   ├── client.py
│   │   ├── normalizer.py
│   │   └── sidecars.py
│   ├── forge_neo/
│   │   ├── components.py
│   │   ├── checkpoints.py
│   │   └── loras.py
│   ├── providers/
│   │   ├── base_openai_compat.py
│   │   ├── openrouter.py
│   │   └── lmstudio.py
│   ├── storage/
│   │   ├── migrations.py
│   │   └── sqlite_cache.py
│   └── images.py
├── prompts/
│   ├── system_v1.txt
│   ├── dialect_booru_v1.txt
│   └── dialect_natural_v1.txt
└── ui/
    ├── panel.py
    ├── presenters.py
    └── settings.py
```

Phase A реализована в `application/enrich_metadata.py`, `application/inventory_enrichment.py`,
`infrastructure/civitai/{client,normalizer,sidecars}.py`, `infrastructure/hashing.py` и
`infrastructure/storage/sqlite_cache.py`. Остальные имена в дереве выше фиксируют целевое разбиение
последующих фаз; текущие provider adapters объединены в `providers/openai_compatible.py`, а Forge inventory
— в `forge_neo/inventory.py`.

## 6. Model inventory и metadata pipeline

### 6.1 Scan

Scan не читает tensor payload. Он получает список файлов из реестров Forge, `stat` и уже загруженные Forge metadata.

Fingerprint:

```text
normalized model kind + relative path + file size + mtime_ns
```

Абсолютный путь хранится только локально и не включается в LLM context.

### 6.2 Lazy hashing

SHA-256 больших checkpoint дорог. Полный hash считается, только если:

- его нет в Forge/sidecar/cache;
- model попал в релевантный shortlist;
- включён CivitAI enrichment.

Hash вычисляется потоково блоками, с отменой и ограниченным числом workers. Результат привязывается к fingerprint; изменение size/mtime инвалидирует его.

### 6.3 Sidecar resolution

Для `X.safetensors` проверяются:

- `X.api_info.json`;
- `X.json`;
- при необходимости header самого safetensors.

Также должна поддерживаться ситуация, когда sidecar сохранён рядом под normalized filename. Поиск не выходит за разрешённые model roots.

### 6.4 Normalization

Разные источники сводятся в один объект:

```json
{
  "local_id": "lora:yoru",
  "kind": "lora",
  "display_name": "Yoru",
  "base_model": "Illustrious",
  "civitai": {
    "model_id": 2054132,
    "version_id": 2324610,
    "sha256": "E60C..."
  },
  "trigger_word_groups": [],
  "description_text": null,
  "sample_prompts": [],
  "provenance": {
    "identity": "sidecar",
    "triggers": "safetensors",
    "description": "civitai_cache"
  }
}
```

Приоритет поля задаётся отдельно, а не заменой всего объекта:

| Поле | Приоритет |
|---|---|
| Identity/hash/id | matching local sidecar → Forge hash → CivitAI |
| Trigger words | safetensors + local activation text + CivitAI, с объединением |
| Description | fresh CivitAI cache → api_info sidecar → отсутствует |
| Base model | api_info root → CivitAI → local sidecar → safetensors inference |
| Examples | api_info/CivitAI sample prompts |

Trigger words объединяются без учёта регистра с сохранением исходного порядка и групп. HTML descriptions преобразуются в plain text.

### 6.5 CivitAI client

Минимальные endpoints:

```text
GET /api/v1/model-versions/by-hash/{sha256}
GET /api/v1/model-versions/{version_id}
GET /api/v1/models/{model_id}
```

Version response используется для точного сопоставления локального файла, trigger words и version-level description. Model response дополняет его полным model-level description, tags и общими сведениями автора. Данные двух ответов merge-ятся с раздельным provenance; model-level текст не должен затирать более специфичное version-level поле.

Требования клиента:

- configurable allowlisted base domain;
- optional Bearer API token;
- connect/read timeout;
- retry только для `429`, `5xx` и transport errors;
- exponential backoff с jitter и учётом `Retry-After`;
- concurrency limit;
- negative cache для `404`;
- запись cache только после schema-lite проверки JSON;
- отсутствие сетевых вызовов во время импорта расширения.

### 6.6 Storage

SQLite выбран вместо набора изменяемых JSON:

- atomic transactions;
- безопаснее при параллельных UI events;
- быстрый поиск и invalidation;
- входит в стандартную библиотеку Python.

Реализованные таблицы (schema migration выполняется при первом обращении к cache):

- `local_models`;
- `metadata_snapshots`;
- `field_provenance`;
- `fetch_state`;
- `schema_migrations`.

DB размещается в Forge `data_path/ai-wdywfm/cache.sqlite3`. API keys и изображения в DB не сохраняются.

## 7. Context builder и выбор моделей

Отправка полного описания каждой установленной модели не масштабируется. Pipeline:

1. Собрать полный локальный inventory.
2. Определить текущий checkpoint и LoRA, уже присутствующие в current prompt.
3. Отфильтровать явно несовместимые base-model families.
4. Выполнить lexical ranking по name, trigger words, tags и sanitized description.
5. Всегда включить текущий checkpoint и явно используемые LoRA.
6. Добавить top-N кандидатов с полными карточками.
7. Остальные передать компактно: alias, kind, base model, основные triggers.
8. Урезать context детерминированно до budget, не разрезая JSON object.

Для image-only запроса возможны две стратегии:

- MVP: text instruction участвует в ranking, а vision LLM выбирает из compact inventory;
- позже: отдельный дешёвый vision-caption step, затем local retrieval и финальный request.

Пользователь видит, какие model cards попадут в запрос.

## 8. Request pipeline

```text
UI click
  → validate input
  → snapshot active-tab values
  → refresh lightweight inventory
  → resolve/enrich relevant metadata
  → sanitize and budget context
  → resize/strip image copy if present
  → build provider-neutral request
  → provider adapter
  → parse JSON
  → JSON Schema validation
  → semantic validation against Forge inventory
  → render preview + read-only recommendations
  → explicit Apply prompts
  → update only positive and negative components
```

Операция имеет `request_id` и cancellation token. Поздний ответ отменённого запроса не обновляет UI.

## 9. Provider architecture

Общая реализация `OpenAICompatibleClient` отвечает за:

- `/models`;
- `/chat/completions`;
- text/image content parts;
- timeout, cancellation и error mapping;
- извлечение `choices[0].message.content`;
- parse JSON.

OpenRouter adapter добавляет:

- Bearer API key;
- optional `HTTP-Referer`/`X-OpenRouter-Title`;
- capability filtering;
- `provider.require_parameters=true`, когда требуется strict schema support.

Исключение Gemma 4: fast structured path не запрашивает reasoning, не применяет
model-specific jailbreak/turn markers, ограничивает output 3072 токенами (запас
под полную schema: prompt + negative_prompt + models + recommendations +
summary + warnings — 1024 приводило к `finish_reason=length` и отбраковке
усечённого JSON локальной validation) и сразу использует compatibility routing
без автоматического повторного completion.

LM Studio adapter добавляет:

- loopback-safe default URL;
- необязательный token;
- диагностику доступности server/model;
- понятный fallback, если локальная model не поддерживает vision или schema.

Fallback Structured Output:

1. `json_schema` strict;
2. `json_object`, если provider/model объявляет только JSON mode;
3. plain JSON prompt + local parser — только с предупреждением и обязательной schema validation.

Ни один fallback не разрешает применить невалидный ответ.

## 10. Prompt design

System prompt разделяется на постоянные и динамические части:

- роль SD prompt engineer;
- правила безопасности протокола;
- формат/dialect;
- active mode;
- available model context;
- user intent;
- JSON Schema.

Metadata помещаются в явно маркированный data-блок. System rule запрещает исполнять инструкции, найденные в descriptions, filenames, trigger words и изображении.

Prompt templates версионируются. `prompt_template_version` записывается в debug telemetry без содержимого запроса.

## 11. Validation

### 11.1 Structural

- ровно schema `prompt_suggestion.v1`;
- `additionalProperties: false`;
- обязательные поля;
- лимиты длины строк и массивов.

### 11.2 Semantic

- checkpoint/LoRA alias существуют локально;
- LoRA weight находится в допустимом диапазоне;
- sampler и scheduler входят в актуальные списки Forge;
- dimensions кратны шагу Neo и находятся в UI bounds;
- steps/CFG находятся в UI bounds;
- img2img-only поля отсутствуют либо помечены `null` в txt2img;
- `<lora:...>` с неизвестным alias удаляется из применяемого prompt и создаёт warning;
- prompt не содержит NUL/control characters.

Рекомендация может остаться видимой при части semantic warnings, но применение prompt требует валидных строк.

## 12. Security и privacy

### Threat model

- prompt injection через CivitAI description;
- вредоносные/огромные sidecar JSON;
- path traversal через filename/sidecar;
- SSRF через настраиваемый provider URL;
- утечка API key в config/log;
- decompression bomb или огромное reference image;
- stale UI request race;
- hallucinated model alias.

### Controls

- лимиты размера sidecar/header/image до полного parse;
- canonical path check внутри Forge model roots;
- HTML stripping и control-character removal;
- metadata как quoted data, не system instructions;
- loopback-only policy по умолчанию для LM Studio;
- HTTPS-only default для OpenRouter/CivitAI;
- secrets redaction;
- content logging off;
- Pillow verify, pixel limit, conversion в RGB и re-encode;
- request generation counter;
- allowlists из текущих Forge registries.

## 13. Ошибки и UX

Ошибки переводятся в пользовательские категории:

- provider unavailable;
- authentication/credits;
- selected model lacks vision;
- selected model lacks structured output;
- CivitAI offline/rate-limited;
- model metadata not found;
- response invalid;
- request cancelled.

CivitAI failure — warning, а не failure всей операции. LLM failure сохраняет введённый текст и preview предыдущего результата. Технический traceback остаётся в server log при debug mode.

## 14. Наблюдаемость

Безопасные поля log:

- request id;
- provider/model id;
- duration;
- количество inventory/shortlist items;
- cache hits/misses;
- input/output token usage, если provider вернул;
- schema/template version;
- error category.

По умолчанию не логируются:

- prompts;
- descriptions;
- изображения/base64;
- API keys;
- абсолютные пути;
- полный provider response.

## 15. Тестовая стратегия

### Unit

- normalizers на всех JSON из `docs/LoRA json exmples/`;
- trigger-word merge;
- safetensors header reader на минимальном fixture;
- compatibility mapping;
- ranking и deterministic budgeting;
- schema и semantic validation;
- prompt apply policy.

### Contract

- recorded sanitized CivitAI responses;
- OpenRouter-compatible response fixtures;
- LM Studio-compatible response fixtures;
- error/timeout/429/invalid JSON.

### Integration

- импорт extension modules под Neo stubs;
- реальная Neo installation: registry scan;
- Gradio event outputs;
- text flow и vision flow.

### Critical UI regression

После `Apply prompts` snapshot всех основных controls сравнивается с состоянием до операции:

```text
allowed changed: prompt, negative_prompt
must not change: checkpoint, CFG, width, height, sampler, scheduler, steps,
                 seed, denoising strength, batch settings
```

## 16. Зафиксированные решения

| Решение | Причина |
|---|---|
| AlwaysVisible Script в обеих вкладках | Нативный lifecycle и правильный active-tab context |
| Собственный image input | Одинаковая работа в txt2img и всех img2img modes |
| Python/Gradio apply | Синхронное состояние вместо хрупкой DOM-записи |
| Provider-neutral domain model | Один pipeline для OpenRouter и LM Studio |
| SQLite cache | Transactions, concurrency, indexing |
| Lazy SHA-256 | Не блокировать startup на больших checkpoint |
| Bounded two-tier model context | Полезность без переполнения context window |
| Strict schema + semantic validation | LLM output недоверенный |
| Read-only recommendations | Явное требование продукта и защита пользователя |
| No core patches | Обновляемость Forge Neo |

## 17. Открытые вопросы до реализации

- Какой prompt dialect выбрать default для разных base families: auto-mapping или пользовательский preset?
- Нужен ли отдельный CivitAI API token UI или только environment variable?
- Сохранять ли локальную историю suggestions, и если да — opt-in ли она?
- Должен ли `Append` добавлять negative prompt или заменять его?
- Какой максимальный context budget безопасен для локальных 7B-моделей?

Открытые вопросы не блокируют Phase 1: для MVP используются `Auto`, env-first secrets, history off, явный apply mode и configurable budget.
