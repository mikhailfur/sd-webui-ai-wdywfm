# Roadmap ai-wdywfm

Roadmap построен по принципу: сначала безопасный end-to-end vertical slice для Forge Neo, затем качество retrieval и профессиональные функции.

Даты намеренно не фиксируются до первого измеренного prototype. Версии отражают scope, а не обещанный срок.

## Phase 0 — Architecture baseline

Статус: **готово**

- [x] Зафиксировать Forge Neo как единственную целевую платформу.
- [x] Проверить Neo extension hooks и Gradio component ids.
- [x] Изучить локальные CivitAI sidecars и референсное Neo-расширение.
- [x] Спроектировать provider-neutral OpenRouter/LM Studio layer.
- [x] Определить JSON Schema и правило «изменяются только prompts».
- [x] Зафиксировать security/privacy boundaries.
- [x] Подготовить README, архитектуру и roadmap.

Результат: документы, по которым можно начинать реализацию без изменения ключевых продуктовых решений.

## v0.1.0 — Forge Neo skeleton

Статус: **готово**

Цель: расширение безопасно загружается и показывает UI в обеих вкладках.

- [x] Создать package structure, `install.py`, dependency policy.
- [x] Добавить Neo compatibility guard.
- [x] Реализовать `scripts.Script` + `scripts.AlwaysVisible`.
- [x] Захватить prompt/negative components через `on_after_component`.
- [x] Создать одинаковый accordion в txt2img и img2img.
- [x] Реализовать preview и `Apply prompts`.
- [x] Добавить regression test: меняются ровно два поля.
- [x] Добавить Settings section; content logging выключен по умолчанию.

Exit criteria:

- WebUI Neo стартует без patching core;
- обе панели независимы;
- тестовый статический suggestion применяется только к active-tab prompts.

## v0.2.0 — Local model intelligence

Цель: построить нормализованный offline-каталог checkpoint/LoRA.

- [ ] Adapter `sd_models.checkpoints_list`.
- [ ] Adapter `sd_forge_lora.networks.available_networks`.
- [ ] Определение current checkpoint.
- [ ] Parse LoRA references из current prompt.
- [ ] Readers для `.json`, `.api_info.json`, safetensors header.
- [ ] Нормализация trigger words и provenance.
- [ ] SQLite schema/migrations.
- [ ] Fingerprint и incremental refresh.
- [ ] Lazy SHA-256 worker с progress/cancel.
- [ ] Unit tests на все fixtures из `docs/LoRA json exmples/`.

Exit criteria:

- каталог работает без сети;
- повторный scan не хэширует неизменённые файлы;
- абсолютные пути не появляются в export/context.

## v0.3.0 — CivitAI enrichment

Цель: самостоятельно получать полные metadata без зависимости от другого extension.

- [ ] CivitAI client `by-hash`.
- [ ] Fallback `by-version-id`.
- [ ] Model-level lookup `GET /api/v1/models/{modelId}` для полного description/tags.
- [ ] Configurable `civitai.com`/`civitai.red`.
- [ ] Optional API token и environment-variable priority.
- [ ] Timeout/retry/backoff/rate-limit handling.
- [ ] Positive и negative cache TTL.
- [ ] HTML → sanitized plain text.
- [ ] Extract descriptions, trained words, sample prompts, base model.
- [ ] Per-field provenance и stale indicator.
- [ ] UI refresh metadata + offline warning.
- [ ] Contract tests на recorded sanitized responses.

Exit criteria:

- cache-first lookup;
- CivitAI outage не мешает локальной генерации suggestion;
- отсутствующая модель не вызывает бесконечные повторные запросы.

## v0.4.0 — LM Studio text MVP

Цель: полностью локальный Text → Prompt flow.

- [ ] OpenAI-compatible base client.
- [ ] LM Studio connection test и `/v1/models`.
- [ ] Provider capability model.
- [ ] System prompt v1.
- [ ] JSON Schema file v1.
- [ ] Structured Output request.
- [ ] Structural + semantic validation.
- [ ] Context builder с current model и relevant LoRA.
- [ ] Booru/Natural/Auto dialect.
- [ ] Cancel и stale-response protection.
- [ ] Ошибки, regenerate и response preview.

Exit criteria:

- natural request превращается в два валидных prompts;
- неизвестная LoRA не попадает в применяемый prompt;
- рекомендации отображаются, но не изменяют Forge controls.

## v0.5.0 — OpenRouter text support

Цель: cloud-provider parity.

- [ ] OpenRouter authentication.
- [ ] Model listing и capability filtering.
- [ ] Structured Outputs с required parameters.
- [ ] Usage/cost metadata, когда доступны.
- [ ] Cloud data disclosure перед запросом.
- [ ] Env-first API key и redaction tests.
- [ ] Provider error mapping: auth, credits, rate limit, model/provider.
- [ ] Connection/provider diagnostics.

Exit criteria:

- один и тот же domain request работает через LM Studio и OpenRouter;
- secrets отсутствуют в logs/cache;
- cloud request невозможен без явного действия пользователя.

## v0.6.0 — Vision flow

Цель: Image + Instruction → Prompt в txt2img и img2img.

- [ ] Собственный `gr.Image`/upload component в обеих панелях.
- [ ] Decode limits и image validation.
- [ ] EXIF/metadata stripping.
- [ ] Resize/re-encode policy.
- [ ] Vision capability check.
- [ ] Multipart OpenAI-compatible message builder.
- [ ] Create/Edit intent templates.
- [ ] OpenRouter vision flow.
- [ ] LM Studio vision flow.
- [ ] Image privacy preview/consent.
- [ ] End-to-end tests PNG/JPEG/WebP и oversized/corrupt input.

Exit criteria:

- image flow одинаково доступен в обеих вкладках;
- text-only model отклоняется до отправки;
- исходный файл не изменяется и не сохраняется extension.

## v0.7.0 — Retrieval and context budgeting

Цель: качественная работа с большими model collections.

- [ ] Compatibility map для SD1.x, SD2.x, SDXL, Pony, Illustrious, NoobAI, FLUX и поддерживаемых Neo families.
- [ ] Lexical index по names/triggers/tags/descriptions.
- [ ] Deterministic relevance scoring.
- [ ] Двухуровневый context: compact catalog + detailed cards.
- [ ] Token estimator per provider family.
- [ ] Настраиваемые budget и top-N.
- [ ] UI «что будет отправлено».
- [ ] Benchmark fixtures для 100/1 000/10 000 LoRA.
- [ ] Optional two-step vision caption → retrieval → final suggestion.

Exit criteria:

- request не превышает заданный budget;
- current/explicit models никогда не теряются при truncation;
- одинаковый input создаёт одинаковый shortlist.

## v0.8.0 — Professional workflow

Цель: ускорить итерации опытных пользователей.

- [ ] Replace/Append с визуальным diff.
- [ ] Несколько variants за запрос.
- [ ] Lock fragments, которые нельзя переписывать.
- [ ] Presets и custom system additions с безопасным разделением ролей.
- [ ] Prompt lint: duplicate/conflicting tags, неизвестные extra networks.
- [ ] Architecture-aware recommendations.
- [ ] Copy as style/preset.
- [ ] Opt-in local history без изображений и secrets.
- [ ] Export/import settings с secret stripping.

## v0.9.0 — Hardening and release candidate

- [ ] Полная test matrix на поддерживаемой Neo revision.
- [ ] Windows/Linux path tests.
- [ ] Gradio queue/concurrency soak tests.
- [ ] Security review: prompt injection, path traversal, SSRF, oversized inputs.
- [ ] Cache corruption recovery и migrations rollback strategy.
- [ ] Accessibility и keyboard navigation.
- [ ] Localization foundation: RU/EN.
- [ ] Performance profiling startup/scan/hash/context.
- [ ] User documentation и troubleshooting.
- [ ] Automated compatibility smoke test against Neo updates.

## v1.0.0 — Stable

Условия:

- Text и Vision flows стабильны на OpenRouter и LM Studio.
- CivitAI enrichment полностью встроен.
- Нет core patches.
- Нет известных случаев изменения generation controls кроме prompts.
- Cache migrations протестированы.
- Privacy disclosure и secret handling документированы.
- Указан поддерживаемый диапазон Forge Neo revisions.

## После v1.0 — возможные направления

Не входят в текущие обязательства:

- другие OpenAI-compatible endpoints;
- embeddings/hybrid retrieval;
- community prompt packs;
- optional integration с CivitAI Browser Neo cache;
- командная библиотека prompts;
- controlled one-click application отдельных рекомендаций.

Последний пункт может появиться только как отдельная opt-in функция. Базовый `Generate suggestion` по-прежнему никогда не меняет CFG, dimensions, sampler или steps.

## Сквозные workstreams

В каждой фазе обязательны:

- tests вместе с кодом;
- migration/compatibility notes;
- отсутствие secrets и prompt content в default logs;
- cancel/timeout behavior;
- обновление README и architecture decisions;
- проверка инварианта prompt-only mutation.
