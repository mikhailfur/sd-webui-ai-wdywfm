# Roadmap ai-wdywfm

Документ переписан **2026-07-29** по факту кода в `ai_wdywfm/`, `scripts/ai_wdywfm.py`, `schemas/` и `tests/`, а не
по изначальному замыслу. Предыдущая версия roadmap была написана до реализации и почти везде помечала
базовые фичи как "не начато", хотя они давно реализованы и покрыты тестами. Актуальный порядок:

1. Что уже работает в репозитории сегодня (де-факто), с указанием файлов.
2. Расхождения между `docs/ARCHITECTURE.md`/`docs/LLM_PROTOCOL.md`/`README.md` и реальным кодом — эти документы
   местами описывают ещё не реализованный CivitAI/SQLite слой как уже существующий.
3. План оставшейся работы, включая четыре продуктовые задачи, добавленные в этот пересмотр:
   web-search tool для LLM, "ленивая" передача метаданных LoRA по запросу модели, отдельный CivitAI LoRA
   recommender и более информативное логирование/дебаг.

Даты по-прежнему не фиксируются. Версии отражают scope, а не обещанный срок.

---

## Часть 1. Что уже реализовано (де-факто)

### Forge Neo интеграция
- `scripts/ai_wdywfm.py` регистрирует `scripts.Script` + `AlwaysVisible`, ловит `txt2img_prompt` /
  `txt2img_neg_prompt` / `img2img_prompt` / `img2img_neg_prompt` через `on_after_component`, вызывает
  `ai_wdywfm.ui.settings.register_settings()` на `on_ui_settings`.
- `ai_wdywfm/infrastructure/forge_neo/inventory.py::compatibility()` — guard по версии Gradio и наличию
  `modules_forge`, без падения WebUI на несовместимом рантайме.
- Панель одинаково рендерится в обеих вкладках (`ai_wdywfm/ui/panel.py::build_panel`), обновляет только
  `prompt_preview`/`negative_preview` → `Apply prompts` пишет исключительно в захваченные positive/negative
  компоненты. Регрессия покрыта `tests/test_apply_prompts.py`.

### Локальный inventory checkpoint/LoRA
- `build_inventory()` читает `modules.sd_models.checkpoints_list` и `networks.available_networks` (Forge's
  built-in LoRA module), определяет текущий checkpoint по `shared.opts.sd_model_checkpoint`.
- Для каждой LoRA подтягивается **собственный Forge user-metadata `.json`** рядом с `.safetensors`
  (`activation text`, `preferred weight`) — это не CivitAI `api_info.json`/`.civitai.json` sidecar, а формат
  extra-networks card, который создаёт сам Forge/webui.
- Простая lexical-релевантность: `_rank_lora_cards()` скорит карточки по вхождению термов запроса в
  id/alias/activation words и сортирует детальные карточки; отправляется compact summary **всех** моделей +
  top-8 detailed cards (`MAX_DETAILED_LORAS`), лимит компакт-списка настраивается (`wdywfm_inventory_limit`).
- `lru_cache` на чтение sidecar `.json` с инвалидацией по `(mtime_ns, size)`, метрики hits/misses логируются.
- `unload_sd_checkpoint()` — best-effort выгрузка SD/SDXL из VRAM на время LLM-запроса к LM Studio
  (`wdywfm_sdxl_auto_unload`), симметричный LM Studio JIT-load/idle-TTL unload (`wdywfm_lmstudio_auto_unload`,
  `wdywfm_lmstudio_unload_ttl`) — этого не было в изначальном плане вообще, добавлено по месту.
- Покрыто `tests/test_inventory.py`.

### LLM providers (LM Studio + OpenRouter)
- `ai_wdywfm/infrastructure/providers/openai_compatible.py::OpenAICompatibleClient` — общий клиент:
  `/models`, `/chat/completions`, `response_format: json_schema` (strict), background-thread hard timeout,
  URL allowlisting (loopback-only для LM Studio, `https://openrouter.ai` для OpenRouter), маппинг ошибок
  (timeout/HTTP/connection) в `ProviderError` с деталями из тела ответа.
  провайдер-специфика: `provider.require_parameters` + OpenRouter Response Healing plugin, LM Studio `ttl`
  для авто-unload.
- Специальный "быстрый" профиль для Gemma 4 (`providers/gemma4.py`): без jailbreak/turn markers, без
  reasoning, `max_tokens=3072`, один completion без repair-запроса. Покрыт `tests/test_gemma4.py`.
- Тексто-визуальный запрос: `image_url` content part добавляется после текстового (совместимость с
  OpenRouter), `ai_wdywfm/infrastructure/images.py` валидирует Pillow-декодом, лимит 32 MP, ресайз до
  `wdywfm_image_max_side`, конвертация в RGB и **пере-кодирование в JPEG** (EXIF отбрасывается тем самым как
  побочный эффект пере-энкода, отдельного explicit-strip шага нет).
- Секреты: env `OPENROUTER_API_KEY` имеет приоритет над введённым ключом только если поле пустое; на Windows
  ключ шифруется DPAPI (`ai_wdywfm/infrastructure/provider_state.py`), сохраняется в `data/provider_state.v1.json`
  с миграцией из старого пути `data_path/ai-wdywfm/`.
- Cancel — через Gradio `cancels=[generate_event]`, отменённый поздний ответ не обновляет UI (естественно
  для Gradio queue, отдельного request-generation counter не реализовано).
- Покрыто `tests/test_provider_client.py`, `tests/test_provider_state.py`, `tests/test_generation_repair.py`.

### Validation
- `ai_wdywfm/domain/validation.py` — двухступенчатая проверка: `parse_suggestion()` (структурная, по
  `schemas/prompt_suggestion.v1.json`) и `semantic_validate()` (checkpoint/LoRA id из allowlist, sampler/
  scheduler из живых списков Forge, диапазоны steps/cfg/width/height, обнуление `denoising_strength` в
  txt2img, вычищение `<lora:unknown:...>` из применяемого prompt с warning).
- `ai_wdywfm/application/generate_suggestion.py::_normalize_lora_weights()` — backend всегда сам
  пересобирает вес LoRA (принимает numeric-string, откатывается на `preferred_weight` или `0.7` при
  `null`/`0`/мусоре), LLM не может протащить произвольный вес как строку.
- Покрыто `tests/test_validation.py`.

### Логирование и диагностика
- `ai_wdywfm/infrastructure/diagnostics.py` — единый логгер `ai_wdywfm`, rotating file (`logs/ai-wdywfm.log`,
  2 MB × 3 backups) + stream handler, redaction-фильтр на `sk-or-v1-*`/`Authorization: Bearer`/`api_key=`.
  Уровень: `INFO` по умолчанию, `DEBUG` через `wdywfm_debug_logging` или `WDYWFM_DEBUG=1`.
- По всему пайплайну проставлен `request=<12-hex>` и структурные `key=value` токены: `ui.generate` →
  `inventory.ok` → `completion.start`/`http.start`/`http.response`/`completion.shape`/`completion.usage` →
  `completion.json_ok`/`http.timeout`/`http.error` → `validated`/`failed`/`crashed`. Есть `duration=%.3fs`
  на большинстве шагов и token usage (`prompt_tokens`/`completion_tokens`/`reasoning_tokens`) когда провайдер
  их отдаёт.
- В панели есть аккордеон "Diagnostics" с кнопкой обновления и `read_log_tail()` (последние 160 строк /
  192 KB). Покрыто `tests/test_diagnostics.py`.
- Это уже полезный лог, но он **строчный key=value, единого уровня verbosity, без категоризации ошибок и
  без деталей по конкретной LoRA/checkpoint, которые validation отклонила** — см. Phase E ниже.

### UI
- Единая панель в обеих вкладках: natural request, reference image, Create/Edit, dialect (`Auto`/`Booru`/
  `Natural`), выбор provider/model/base_url/api key, кнопки `Test connection`/`Generate`/`Cancel`/`Apply`,
  превью prompt/negative, summary, warnings, read-only recommendations card, model status, activity log,
  diagnostics tail. `ai_wdywfm/ui/presenters.py` рендерит markdown/HTML для summary/warnings/recommendations.

### Тесты
`tests/` — 9 файлов: apply_prompts, civitai_phase_a, diagnostics, gemma4, generation_repair, inventory,
provider_client, provider_state, validation. Phase A покрыта fixture/contract/integration-тестами; тестов
на web search и recommender пока нет, потому что Phase C/D ещё не реализованы.

---

## Часть 2. Расхождения между документацией и кодом на момент пересмотра

Расхождение закрыто реализацией **Phase A**. В коде появились `infrastructure/civitai/`,
`infrastructure/storage/`, bounded safetensors-header reader, потоковый lazy SHA-256 и HTTP-клиент с
allowlist для `civitai.com`/`civitai.red`. Forge user-metadata `.json`, CivitAI sidecar, safetensors metadata,
SQLite snapshot и сетевой ответ теперь сводятся в один `ModelMetadata` с provenance по полям.

`README.md` и `docs/ARCHITECTURE.md` актуализированы по фактической реализации: сеть вызывается только во
время явного Generate для shortlist, lookup выполняется cache-first, а CivitAI failure оставляет локальную
генерацию рабочей. Следующие зависимости Phase A — Phase B (ленивая передача metadata) и Phase D
(recommender) — теперь разблокированы.

Проверка закрытия: `tests/test_civitai_phase_a.py` покрывает все шесть JSON-fixtures, SQLite migrations/cache,
safetensors header, retry/allowlist/env-token, negative cache и streaming SHA-256.

---

## Часть 3. План оставшейся работы

### Phase A — CivitAI enrichment (было v0.3.0, выполнено)

Цель: получать полные metadata (описание, trigger words, sample prompts, base model) для локальных
checkpoint/LoRA без стороннего расширения.

- [x] `infrastructure/civitai/client.py`: `GET /api/v1/model-versions/by-hash/{sha256}`, fallback
      `by-version-id`, `GET /api/v1/models/{modelId}` для полного description/tags.
- [x] Configurable domain `civitai.com`/`civitai.red`, allowlist проверка URL как уже сделано для
      OpenRouter/LM Studio в `openai_compatible.py::_validated_url`.
- [x] Optional Bearer token, приоритет у env-переменной (`CIVITAI_API_TOKEN`, затем `CIVITAI_TOKEN`).
- [x] Timeout/retry только на `429`/`5xx`/transport errors, exponential backoff + `Retry-After`, negative
      cache на `404`.
- [x] `infrastructure/civitai/sidecars.py`: чтение `X.api_info.json`, `X.json` (CivitAI-формат, отдельно от
      уже существующего Forge user-metadata), safetensors `__metadata__` header как последний fallback.
- [x] Нормализация в единый `ModelMetadata` с provenance по полю (identity/triggers/description/base_model),
      как описано в `docs/ARCHITECTURE.md` §6.4 — реализовать буквально то, что уже спроектировано там.
- [x] `infrastructure/storage/sqlite_cache.py`: таблицы `local_models`, `metadata_snapshots`,
      `field_provenance`, `fetch_state`, `schema_migrations`; путь `data/ai-wdywfm/cache.sqlite3`.
- [x] Lazy SHA-256 (поток блоками, cooperative cancel, ограниченный пул воркеров), считается только когда хэша нет
      локально и модель попала в shortlist.
- [x] HTML → sanitized plain text для description/sample prompts.
- [x] Unit-тесты на все фикстуры из `docs/LoRA json exmples/`.
- [x] UI: индикатор "metadata: local / cached / stale / offline" для выбранных LoRA.

Exit criteria: cache-first lookup; недоступность CivitAI не блокирует локальную генерацию; отсутствующая
модель не вызывает бесконечные повторные запросы; сеть не трогается на импорте расширения.

### Phase B — Ленивая передача метаданных LoRA по запросу модели (новое)

Сегодня pipeline отправляет **всем моделям одинаково**: compact summary всех LoRA + заранее выбранные (по
Python-эвристике) top-8 detailed cards с activation words/preferred weight. Это не "передаётся всё" в
смысле полных CivitAI-описаний (их пока не существует, см. Phase A), но и не даёт модели самой решать, какие
карточки ей нужны — выбор top-8 делает `_rank_lora_cards()`, а не LLM.

Цель: перейти на compact-каталог из **только `id` + `alias` + короткое (≤140 символов) описание**, без
activation words/preferred weight/base_model в первом сообщении, и дать модели инструмент, которым она сама
запрашивает подробности по конкретным id, которые сочла релевантными.

- [ ] Определить минимальную compact-карточку: `{id, alias, short_description}`. `short_description` —
      первая строка sanitized CivitAI description (Phase A) или activation words, сокращённые до лимита, если
      CivitAI-описания ещё нет.
- [ ] Спроектировать tool-calling contract поверх текущего `OpenAICompatibleClient.complete()`: функция
      `get_lora_details(ids: string[])`, возвращающая полные карточки (activation words, preferred weight,
      base model, CivitAI description/sample prompts после Phase A) только для запрошенных id.
- [ ] Bounded tool loop: максимум N раундов (например 2), максимум M id за раунд, hard timeout остаётся
      общим на весь request; не даём модели зациклиться на бесконечных вызовах.
- [ ] Backend не доверяет id из вызова инструмента больше, чем текущим `models.loras[].id` — те же
      allowlist-проверки, что уже есть в `semantic_validate()`.
- [ ] Fallback для моделей/провайдеров без tool calling (часть локальных LM Studio моделей его не
      поддерживает в structured-output режиме): вернуться к текущему статическому top-N поведению, не ронять
      функциональность.
- [ ] Обновить `docs/LLM_PROTOCOL.md` до v2 с описанием tool-calling round trip.
- [ ] Логирование раундов инструмента (см. Phase E) — сколько вызовов, сколько id, что было отклонено как
      неизвестный id.
- [ ] Тесты: обрыв цикла по лимиту раундов, галлюцинированный id из tool-вызова отклоняется и не ломает
      основной ответ, fallback-путь для моделей без tool calling не регрессирует существующее поведение.

Exit criteria: при большой коллекции LoRA (500+) первое сообщение к LLM меньше по объёму, чем сейчас
(top-8 полных карточек всегда занимают место, даже если не нужны половине из них); суммарный объём данных о
модели, попадающих в LLM за один Generate, не выше текущего в худшем случае.

### Phase C — Web search tool для LLM (новое)

Цель: дать LLM возможность самостоятельно уходить в веб-поиск за фактами, которых нет в локальных
метаданных — например, канонiчная внешность/атрибуты персонажа из франшизы, чтобы промпт был точнее, а не
галлюцинировался моделью из общих знаний.

- [ ] Абстракция search-провайдера (Protocol, аналогично `LlmProvider`/`MetadataProvider` в
      `docs/ARCHITECTURE.md` §4.3): минимум одна реализация — либо нативный OpenRouter `:online`/web plugin
      (требует ресёрча текущего API OpenRouter), либо внешний search API (Brave Search / Tavily / SerpAPI) с
      пользовательским ключом для LM Studio, у которого своего web-доступа нет.
- [ ] Общий tool-calling loop с Phase B — тот же bounded round-trip механизм в `OpenAICompatibleClient`.
- [ ] Настройка **выключена по умолчанию**, явный disclosure в UI ("этот запрос может обратиться к
      стороннему поисковому провайдеру") по аналогии с уже существующим `cloud_image_consent` для
      OpenRouter vision.
- [ ] Санитизация результатов поиска: те же правила, что и для CivitAI description в
      `docs/LLM_PROTOCOL.md` §5 — untrusted quoted data, инструкции внутри игнорируются, HTML → plain text,
      лимит длины сниппета, лимит числа результатов и вызовов на один Generate.
- [ ] Не кэшировать произвольный веб-контент постоянно (или короткий TTL, явно документированный); секреты
      (search API key) исключены из логов теми же паттернами redaction, что уже покрывают OpenRouter/CivitAI
      ключи.
- [ ] Логирование: длина/хэш запроса и количество результатов на INFO, полный текст запроса и сниппетов
      только под `wdywfm_debug_logging`.
- [ ] Тесты: prompt injection через результат поиска не меняет system-правила; лимит вызовов соблюдается;
      выключенный по умолчанию флаг действительно блокирует любой сетевой вызов поиска.

Exit criteria: без явного включения настройки ни один байт не уходит к поисковому провайдеру; при включении
и одном раунде поиска итоговый JSON всё ещё проходит ту же schema+semantic validation, что и обычный ответ.

### Phase D — Отдельный CivitAI LoRA recommender (новое)

Цель: независимая от Generate suggestion фича — "порекомендуй LoRA с CivitAI (включая civitai.red) под
описание", результат read-only (ссылки/id), без автозагрузки и без влияния на bounded context основного
prompt-flow.

- [ ] Зависит от HTTP-слоя Phase A (allowlist домена, retry/backoff, redaction, timeout) — переиспользовать,
      не дублировать клиент.
- [ ] Новый endpoint-класс: `GET /api/v1/models?query=&types=LORA&sort=&baseModel=&nsfw=` (CivitAI search
      API) с пагинацией и лимитом результатов на страницу.
- [ ] Ранжирование: базовые CivitAI-сигналы (downloads/rating/updatedAt) + опциональный LLM re-rank под
      конкретный запрос пользователя (использует тот же provider-neutral `OpenAICompatibleClient`, но
      отдельный, более лёгкий, non-structured или отдельный узкий JSON Schema под "список рекомендаций").
- [ ] Явный non-goal: никакой автозагрузки/автоустановки модели — только имя, автор, base model, превью-
      ссылка, model/version id, прямая ссылка на страницу CivitAI. Совпадает с уже принятым в проекте
      принципом "read-only recommendations" (`docs/ARCHITECTURE.md` §16), только применённым к новой
      поверхности, а не к списку generation params.
- [ ] Настройки: включить/выключить фичу, домен `civitai.com`/`civitai.red` (переиспользовать выбор из
      Phase A), NSFW-фильтр passthrough, число результатов на страницу.
- [ ] UI: отдельный sub-accordion "LoRA recommender (CivitAI)", вне основного Generate-flow, чтобы не
      раздувать context budget генерации промпта.
- [ ] Тесты: contract-тесты на записанные sanitized ответы CivitAI search API, обработка пустого результата,
      429/5xx graceful degradation (recommender показывает "CivitAI недоступен", не роняет остальной UI).

Exit criteria: recommender работает и логируется независимо от Generate suggestion; отключение фичи не
трогает остальной pipeline; ни один найденный LoRA не может быть автоматически подключён к промпту без
явного действия пользователя (copy id / open link).

### Phase E — Более информативное логирование и диагностика (новое)

Текущее логирование (см. Часть 1) уже structured key=value с `request_id`, таймингами и redaction — это
базовый уровень, а не "с нуля". Но пользовательский запрос — сделать его "подробнее, понятнее и удобнее для
дебага" — обоснован конкретными пробелами:

- [ ] **Единый уровень verbosity сегодня** (`wdywfm_debug_logging` — только on/off) → добавить
      уровни/категории по подсистеме (`provider.http`, `inventory`, `validation`, `ui`), настраиваемые
      отдельно, чтобы не включать DEBUG сразу на весь пайплайн ради одного узкого вопроса.
- [ ] **Validation сегодня логирует только агрегаты** (`warnings=%d` в `generate_suggestion`/`panel._generate`)
      → добавить построчные DEBUG-записи по каждому отклонённому/нормализованному полю с кодом причины
      (`lora.unknown_id`, `lora.weight_normalized`, `sampler.unknown`, `checkpoint.unknown`,
      `dimension.out_of_range`), опираясь на то, что `_normalize_lora_weights()` и `semantic_validate()` уже
      знают точную причину — просто не пишут её в лог, только в `warnings[]`, который видит только UI.
- [ ] **Нет видимости в отправленный envelope** — при DEBUG логировать redacted-версию envelope (без
      текста prompt, но со списком id моделей, что реально попали в compact/detailed context) — сейчас в
      логах видно только количество моделей в inventory, а не то, что конкретно ушло в LLM после ranking.
- [ ] **Нет единого поля категории ошибки** — `docs/ARCHITECTURE.md` §13 уже определяет таксономию (provider
      unavailable / auth-credits / no vision / no structured output / civitai offline / metadata not found /
      invalid response / cancelled), но в коде это не проставляется как стабильный `error_category=` тег;
      сейчас лог пишет `kind=%s` с именем Python-исключения, что не совпадает с пользовательской категорией
      из UI-сообщения. Свести к одному словарю, чтобы лог и текст ошибки в UI совпадали.
- [ ] **Diagnostics-панель — просто хвост файла** → добавить фильтр по `request=`/уровню прямо в UI, не
      только "показать последние 160 строк".
- [ ] Опциональный JSONL-режим вывода лога (по отдельному флагу) для удобного `jq`/парсинга, при этом
      человекочитаемый key=value остаётся форматом по умолчанию.
- [ ] Логирование round-trip'ов Phase B/C (tool calls) закладывается сразу в этом же формате — не отдельная
      незадокументированная ветка логов.
- [ ] Тесты: redaction всё ещё отрабатывает на новых полях; JSONL-режим не ломает `read_log_tail()`.

Exit criteria: по одному `request_id` в логе можно восстановить полную историю решения — что было в
inventory, что ушло в LLM, что и почему validation изменила/отклонила, — без включения debug-логирования
содержимого prompt/secrets.

### Phase F — Retrieval и context budgeting (было v0.7.0, частично готово)

Сегодня уже есть: настраиваемый `wdywfm_inventory_limit`, top-8 detailed cards, простой lexical score по
query+current_prompt. Не готово:

- [ ] Compatibility map для SD1.x/SD2.x/SDXL/Pony/Illustrious/NoobAI/FLUX — сейчас base_model попадает в
      карточку как текст, но не используется для фильтрации явно несовместимых моделей.
- [ ] Token estimator per provider family вместо текущего лимита по количеству карточек.
- [ ] UI "что будет отправлено" — показать пользователю фактический compact/detailed набор перед отправкой
      (актуально ещё сильнее после Phase B, где выбор частично уходит к самой модели через tool calls).
- [ ] Benchmark fixtures для 100/1 000/10 000 LoRA — сейчас ranking не измерялся на большой коллекции.
- [ ] Опциональный двухшаговый vision caption → retrieval → final suggestion для image-flow (сейчас vision
      LLM получает тот же compact inventory, что и text-flow, без промежуточного caption-шага).

### Phase G — Professional workflow (было v0.8.0, не начато)

- [ ] Replace/Append с визуальным diff (сейчас `apply_mode` есть, но без визуального сравнения before/after).
- [ ] Несколько variants за один Generate.
- [ ] Lock fragments, которые нельзя переписывать при повторной генерации.
- [ ] Presets и custom system additions с безопасным разделением ролей (не дать пользовательскому тексту
      переопределить protocol-правила).
- [ ] Prompt lint: дубли/конфликтующие теги, неизвестные extra networks за пределами LoRA.
- [ ] Architecture-aware рекомендации (зависит от Phase F compatibility map).
- [ ] Copy as style/preset.
- [ ] Opt-in локальная история suggestions без изображений и секретов.
- [ ] Export/import настроек с secret stripping.

### Phase H — Hardening и release candidate (было v0.9.0, не начато)

- [ ] Полная test matrix на поддерживаемой Neo revision.
- [ ] Windows/Linux path tests (сейчас DPAPI-шифрование ключа — Windows-only ветка без Linux fallback теста).
- [ ] Gradio queue/concurrency soak tests (несколько параллельных Generate в двух вкладках одновременно).
- [ ] Security review: prompt injection (актуальнее после Phase C), path traversal в CivitAI sidecar
      resolution (Phase A), SSRF через настраиваемый LM Studio/CivitAI URL, oversized inputs.
- [ ] Cache corruption recovery и migration rollback для SQLite (после Phase A).
- [ ] Accessibility и keyboard navigation панели.
- [ ] Localization foundation: сейчас есть только переводы README (RU/JA/KO/ZH), сам UI не локализован.
- [ ] Performance profiling: startup/scan/hash/context.
- [ ] Automated compatibility smoke test против обновлений Neo.

## v1.0.0 — Stable

Условия (обновлено под факт):

- Text и Vision flows стабильны на OpenRouter и LM Studio — **уже выполнено сегодня**, остаётся не сломать.
- CivitAI enrichment полностью встроен (Phase A) — **выполнено**.
- Ленивая передача метаданных LoRA работает с fallback на модели без tool calling (Phase B) — **не выполнено**.
- Нет core patches — **уже выполнено**.
- Нет известных случаев изменения generation controls кроме prompts — **уже выполнено и покрыто тестом**.
- Cache migrations и corruption recovery протестированы (Phase A) — **выполнено**.
- Privacy disclosure и secret handling документированы — **частично**: OpenRouter/vision consent есть,
  web-search consent (Phase C) и CivitAI recommender consent (Phase D) ещё нет.
- Логи достаточны для дебага реального инцидента без включения content-логирования (Phase E).
- Указан поддерживаемый диапазон Forge Neo revisions.

## После v1.0 — возможные направления

Не входят в текущие обязательства:

- другие OpenAI-compatible endpoints;
- embeddings/hybrid retrieval;
- community prompt packs;
- optional integration с CivitAI Browser Neo cache;
- командная библиотека prompts;
- controlled one-click application отдельных рекомендаций (по-прежнему только opt-in, `Generate suggestion`
  никогда не меняет CFG, dimensions, sampler или steps).

## Сквозные workstreams

В каждой фазе обязательны:

- tests вместе с кодом (см. существующий `tests/` как образец покрытия);
- обновление `docs/ARCHITECTURE.md`/`docs/LLM_PROTOCOL.md`/`README.md`, когда фаза меняет то, что эти
  документы уже утверждают как факт (в первую очередь — снять несоответствие по CivitAI из Части 2 после
  Phase A);
- отсутствие secrets и prompt content в default logs (redaction-фильтр в `diagnostics.py` — не обходить
  добавлением логов в обход `get_logger()`);
- cancel/timeout behavior для любого нового сетевого вызова (search, CivitAI, tool calls);
- проверка инварианта prompt-only mutation при любом новом UI-элементе.
