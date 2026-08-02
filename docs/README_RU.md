<div align="center">

<img src="banner.png" alt="WDYWFM — ИИ-помощник по промптам для Forge Neo" width="100%">

# ai-wdywfm

### AI LLM-помощник для SD WebUI

**What Do You Want From Me? / Чего ты от меня хочешь?**

Превращает обычное описание — или изображение с инструкцией по изменению — в промпты Stable Diffusion, адаптированные к checkpoint и LoRA, действительно установленным в Forge Neo.

[![Forge Neo](https://img.shields.io/badge/Forge-Neo-2563eb?style=for-the-badge)](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo)
[![Gradio 4.40](https://img.shields.io/badge/Gradio-4.40-f97316?style=for-the-badge)](https://www.gradio.app/)
[![OpenRouter](https://img.shields.io/badge/LLM-OpenRouter-7c3aed?style=for-the-badge)](https://openrouter.ai/)
[![LM Studio](https://img.shields.io/badge/LLM-LM_Studio-0f766e?style=for-the-badge)](https://lmstudio.ai/)
[![Status](https://img.shields.io/badge/status-v0.1_MVP-22c55e?style=for-the-badge)](ROADMAP.md)

[English](../README.md) · **Русский** · [한국어](README_KO.md) · [日本語](README_JA.md) · [简体中文](README_ZH_CN.md) · [繁體中文](README_ZH_TW.md)

[Обзор](#обзор) · [Как это работает](#как-это-работает) · [Архитектура](#архитектура) · [Roadmap](ROADMAP.md) · [Поддержать проект](#поддержать-проект)

</div>

> [!IMPORTANT]
> Первый исполняемый MVP готов. В нём есть интерфейс Forge Neo, structured-запросы
> к LM Studio и OpenRouter, text/vision-ввод, валидация и явное применение только
> промптов. CivitAI enrichment metadata реализован; продвинутый retrieval остаётся в roadmap.

> [!NOTE]
> **Статус проверки.** Расширение проверено и работает на последней версии
> **Stable Diffusion WebUI Forge Neo**. На данный момент реально проверена работа только
> с провайдером **OpenRouter**; LM Studio реализована по тому же контракту, но пока не
> подтверждена end-to-end на практике.
>
> **Рекомендуемая и проверенная модель — `google/gemma-4-31b-it` (Gemma 4 31B)**, которая
> также поддерживает генерацию NSFW-промптов. Работа с любыми другими LLM/моделями
> **не гарантируется** — соблюдение schema, качество промпта и обработка content policy
> могут заметно отличаться в зависимости от модели и провайдера.
>
> Крайне рекомендуется **перепроверять и при необходимости править сгенерированный
> промпт перед запуском генерации** — воспринимайте ответ LLM как черновик, а не как
> готовый финальный промпт.
>
> Если вы только начинаете разбираться с промптингом для SDXL, рекомендуем посмотреть
> подробный гайд — [это видео](https://www.youtube.com/watch?v=QdRP9pO89MY), а также
> заглянуть в [CivitAI](https://civitai.com) за примерами и техниками
> под конкретные модели.

## Быстрый старт

1. Скачайте архив последнего релиза со страницы
   [github.com/mikhailfur/sd-webui-ai-wdywfm/releases/latest](https://github.com/mikhailfur/sd-webui-ai-wdywfm/releases/latest).
2. Распакуйте архив в каталог `extensions/` Forge Neo так, чтобы папка самого
   расширения (например, `sd-webui-ai-wdywfm`) оказалась непосредственно внутри
   `extensions/`, а не на уровень глубже.
3. Перезапустите Forge Neo — полностью закройте и снова запустите процесс WebUI;
   одной перезагрузки страницы в браузере недостаточно.
4. Откройте `LLM Prompt Helper · AI WDYWFM` внутри `txt2img` или `img2img`.
5. Для локального режима запустите LM Studio на `http://127.0.0.1:1234/v1`;
   либо выберите OpenRouter и укажите ключ только для текущей сессии. Также
   поддерживается переменная окружения `OPENROUTER_API_KEY`.
6. Обновите список моделей, выберите модель, опишите результат и нажмите
   `Generate verified draft`.
7. Проверьте превью и read-only рекомендации, затем нажмите `Apply prompts`.

Выбранный провайдер, URL, модель и ключ OpenRouter автоматически восстанавливаются
после перезапуска WebUI. В Windows ключ шифруется DPAPI для текущего пользователя.
В `Settings → AI WDYWFM` настраиваются только провайдер, URL LM Studio, два timeout
и thinking budget. Остальные параметры используют встроенные значения.

Каждая операция провайдера получает request-id и записывается в rotating-лог
`logs/ai-wdywfm.log`. Последние события можно посмотреть и скопировать в accordion
`Diagnostics · sanitized log`. API-ключи, текст промпта и изображения в лог не попадают.

Для моделей семейства Gemma 4 в OpenRouter применяется быстрый structured-output профиль
без jailbreak, пользовательских turn markers и запрошенного reasoning: reasoning приводил
к медленным и усечённым schema-ответам. Output ограничен 2048 токенами. OpenRouter
Response Healing включён для structured JSON.

Заголовки safetensors кэширует Forge. Sidecar JSON для LoRA дополнительно кэшируются в
памяти с инвалидацией по размеру/mtime; в запрос отправляются только восемь наиболее
релевантных полных карточек, а полный компактный allowlist ID остаётся для проверки.

## Обзор

`ai-wdywfm` — помощник по созданию промптов, разработанный специально для **Stable Diffusion WebUI Forge Neo**. Он позволяет новичкам описывать желаемый результат без предварительного изучения синтаксиса промптов, а опытным пользователям помогает быстрее создавать черновики с учётом доступных моделей.

Помощник объединяет:

- запрос на естественном языке;
- необязательное референсное изображение и инструкцию по изменению;
- контекст активной вкладки `txt2img` или `img2img`;
- установленные checkpoint и LoRA;
- локальные metadata моделей и trigger words;
- полные описания моделей и версий с CivitAI, когда они доступны;
- версионируемый системный промпт и строгую JSON Schema;
- OpenRouter или локальный сервер LM Studio.

### Неизменяемое правило

После ответа LLM расширение может обновлять только:

- **Prompt**;
- **Negative Prompt**.

`CFG Scale`, размеры, sampler, scheduler, sampling steps, denoising strength и другие параметры генерации отображаются как **рекомендации только для чтения**. Они никогда не подключаются как outputs к соответствующим элементам управления Forge.

Checkpoint никогда не переключается автоматически. LoRA может быть добавлена в созданный промпт в виде `<lora:name:weight>` только после проверки её ID и alias по локальному реестру Forge Neo.

## Для кого предназначено расширение?

| Пользователь | Что предоставляет ai-wdywfm |
|---|---|
| **Новичок** | Преобразует обычное описание в готовые positive и negative prompt. |
| **Опытный пользователь** | Создаёт учитывающий модели черновик с корректными локальными LoRA, trigger words и предупреждениями о совместимости. |
| **Пользователь с приоритетом локальной работы** | Работает через LM Studio и локальные/закэшированные metadata без отправки запроса облачной LLM. |
| **Владелец большой коллекции моделей** | Создаёт ограниченный и ранжированный контекст вместо отправки полного описания каждой модели в context window LLM. |

## Как это работает

### Текст → промпт

```text
Идея на естественном языке
        ↓
Инвентарь checkpoint и LoRA из Forge Neo
        ↓
Локальные sidecar / safetensors metadata / CivitAI cache
        ↓
Ранжирование подходящих моделей и ограниченный контекст
        ↓
OpenRouter или LM Studio + строгая JSON Schema
        ↓
Проверенное превью
        ↓
Явное нажатие «Apply prompts»
        ↓
Только Prompt + Negative Prompt
```

1. Откройте accordion `AI WDYWFM` во вкладке `txt2img` или `img2img`.
2. Опишите желаемое изображение обычным языком.
3. Расширение определит текущий checkpoint, уже указанные в промпте LoRA и подходящие установленные модели.
4. Отсутствующие metadata при необходимости дополняются данными CivitAI.
5. Выбранная LLM возвращает структурированное предложение.
6. Ответ проверяется по schema и актуальным реестрам Forge.
7. Просмотрите промпты, рекомендации, выбранные модели и предупреждения.
8. Нажмите `Apply prompts`, чтобы обновить только positive и negative prompt активной вкладки.

### Изображение + инструкция → промпт

1. Прикрепите изображение внутри панели помощника.
2. Опишите, что нужно изменить, сохранить, удалить или стилизовать.
3. Проверенная и уменьшенная копия отправляется модели с поддержкой vision.
4. LLM анализирует изображение вместе с контекстом локальных моделей.
5. Используется тот же процесс проверки и явного применения результата.

Расширение использует собственное поле загрузки изображения, поэтому этот сценарий доступен как в `txt2img`, так и в `img2img` и не зависит от конкретного подрежима img2img.

## Интерфейс

Панель `AI WDYWFM` реализуется как `AlwaysVisible` Forge script и независимо отображается в обеих вкладках генерации.

| Элемент управления | Назначение |
|---|---|
| Natural request | Описание желаемого результата или изменения. |
| Reference image | Необязательное визуальное содержимое для vision-совместимой LLM. |
| Create / Edit | Выбор назначения запроса. |
| Prompt dialect | `Auto`, `Booru tags` или `Natural language`. |
| Provider / model | Выбор LM Studio либо OpenRouter и совместимой модели. |
| Model context preview | Просмотр metadata локальных моделей, которые войдут в запрос. |
| Generate suggestion | Запуск явного запроса к LLM. |
| Prompt preview | Проверка positive и negative prompt до применения. |
| Recommendations | CFG, размер, sampler, scheduler и steps только для чтения. |
| Apply prompts | Замена или добавление только prompt-полей активной вкладки. |

Существующий промпт не перезаписывается до нажатия `Apply prompts`. Планируемый режим по умолчанию — `Replace with preview`; `Append` остаётся отдельной явной альтернативой.

## Совместимость с Forge Neo

Целевое окружение:

- [Stable Diffusion WebUI Forge — Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo), ветка `neo`;
- Gradio `4.40.0`, используемый Forge Neo;
- `modules.scripts`, `modules.script_callbacks` и `modules.shared`;
- встроенный модуль LoRA для Neo: `extensions-builtin/sd_forge_lora`.

Архитектура использует `scripts.AlwaysVisible` и получает официальные компоненты промптов по их Neo ID:

| Вкладка | Positive prompt | Negative prompt |
|---|---|---|
| txt2img | `txt2img_prompt` | `txt2img_neg_prompt` |
| img2img | `img2img_prompt` | `img2img_neg_prompt` |

Core-файлы Forge не изменяются. Forge Classic, AUTOMATIC1111, reForge и другие WebUI не входят в гарантию совместимости.

## Интеграция с CivitAI с учётом моделей

Поддержка CivitAI реализована внутри `ai-wdywfm`; **CivitAI Browser Neo не является runtime dependency**.

Источники metadata обрабатываются с приоритетом cache-first:

1. `<model>.api_info.json`;
2. `<model>.json`;
3. header `__metadata__` файла `.safetensors`;
4. SQLite cache расширения;
5. `GET /api/v1/model-versions/by-hash/{sha256}`;
6. `GET /api/v1/model-versions/{versionId}`;
7. `GET /api/v1/models/{modelId}` для полных описаний и tags на уровне модели.

Нормализованные metadata включают идентификатор и тип модели, семейство base model, hashes, CivitAI ID, группы trigger words, описания модели и версии, sample prompts, negative prompts и происхождение каждого поля.

Hash больших checkpoint вычисляется лениво. Расширение хранит полный локальный инвентарь, но отправляет LLM только компактный каталог и подробные карточки наиболее подходящих совместимых моделей в пределах настраиваемого бюджета контекста.

## LLM-провайдеры

### LM Studio — локальный режим по умолчанию

- Base URL по умолчанию: `http://127.0.0.1:1234/v1`.
- OpenAI-совместимые endpoints `/models` и `/chat/completions`.
- Structured Output на основе того же контракта JSON Schema.
- Vision-сценарий, если выбранная локальная модель поддерживает изображения.
- Возможность полностью локальной работы с закэшированными metadata CivitAI.

### OpenRouter

- Endpoint: `https://openrouter.ai/api/v1/chat/completions`.
- Текстовые и мультимодальные модели.
- Строгий Structured Output для совместимых моделей.
- Проверка возможностей provider/model перед запросом.
- Переменная окружения `OPENROUTER_API_KEY` — предпочтительный источник секрета.

Оба adapter возвращают один и тот же provider-neutral domain object. Невалидные или неполные ответы никогда не применяются.

## Контракт структурированного ответа

Каноническая schema: [prompt_suggestion.v1.json](../schemas/prompt_suggestion.v1.json). Ответ содержит:

```json
{
  "schema_version": "1.0",
  "prompt": "masterpiece, best quality, neon city, night, rain",
  "negative_prompt": "worst quality, blurry, text, watermark",
  "models": {
    "checkpoint_id": null,
    "loras": []
  },
  "recommendations": {
    "sampler": "Euler a",
    "scheduler": "Automatic",
    "sampling_steps": 28,
    "cfg_scale": 5,
    "width": 832,
    "height": 1216,
    "denoising_strength": null
  },
  "summary": "Вертикальная ночная сцена с неоновым освещением.",
  "warnings": []
}
```

К Forge могут применяться только `prompt` и `negative_prompt`. ID моделей, веса LoRA, sampler, scheduler и диапазоны значений проходят дополнительную семантическую проверку по активным реестрам Neo.

Полная спецификация: [LLM Protocol](LLM_PROTOCOL.md).

## Архитектура

```text
Forge Neo UI
    │
    ▼
Сценарии уровня Application
    │
    ▼
Domain-модели и политики
    │
    ├── Adapter инвентаря Forge Neo
    ├── Readers для sidecar / safetensors
    ├── Adapter metadata CivitAI
    ├── Provider adapter OpenRouter
    ├── Provider adapter LM Studio
    └── SQLite cache
```

Планируемая структура проекта:

```text
sd-webui-ai-wdywfm/
├── install.py
├── requirements.txt
├── scripts/
│   └── ai_wdywfm.py
├── ai_wdywfm/
│   ├── application/
│   ├── domain/
│   ├── infrastructure/
│   │   ├── civitai/
│   │   ├── forge_neo/
│   │   ├── providers/
│   │   └── storage/
│   ├── prompts/
│   └── ui/
├── javascript/
│   └── ai_wdywfm.js
├── schemas/
│   └── prompt_suggestion.v1.json
├── tests/
└── docs/
```

Прочитайте полный документ [Архитектура](ARCHITECTURE.md).

## Приватность и безопасность

> [!NOTE]
> Ни один запрос не отправляется автоматически. Сетевое обращение начинается только после явного действия пользователя.

- API keys исключаются из LLM payload, cache и logs.
- Абсолютные локальные пути никогда не отправляются provider.
- Описания CivitAI и metadata моделей считаются недоверенными данными, а не инструкциями.
- Отправка изображения в облако требует явного согласия.
- Перед запросом показывается, будут ли отправлены текст, изображение и metadata моделей.
- Референсные изображения проверяются, уменьшаются, очищаются от metadata и перекодируются.
- Неизвестные checkpoint, LoRA, embedding, sampler и scheduler отклоняются.
- Расширение никогда не запускает генерацию, не скачивает модели и не исполняет созданный LLM текст.
- Содержимое промптов, изображения, секреты и полные ответы provider исключены из logs по умолчанию.

## Конфигурация MVP

| Настройка | По умолчанию | Назначение |
|---|---:|---|
| Default LLM provider | `LM Studio` | Безопасный локальный default. |
| LM Studio base URL | `http://127.0.0.1:1234/v1` | Локальный OpenAI-совместимый сервер. |
| OpenRouter timeout | `60 секунд` | Timeout облачного запроса. |
| LM Studio timeout | `180 секунд` | Timeout локального запроса. |
| Thinking budget | `2 048 токенов` | Оба провайдера; `0` оставляет default модели/provider. |

Это все доступные настройки расширения. Остальные функции используют встроенные defaults.

## Критерии приёмки MVP

- [ ] Forge Neo запускается с расширением без core patches.
- [ ] Помощник независимо работает в `txt2img` и `img2img`.
- [ ] Checkpoint и LoRA обнаруживаются через реестры Neo.
- [ ] Локальные sidecar из `docs/LoRA json exmples/` корректно нормализуются.
- [ ] CivitAI lookup работает по SHA-256 и сохраняет приоритет cache-first.
- [ ] OpenRouter и LM Studio возвращают одинаковый domain object.
- [ ] Текстовый и vision-сценарии работают end-to-end.
- [ ] `Apply prompts` изменяет ровно два поля активной вкладки.
- [ ] Рекомендации никогда не изменяют CFG, dimensions, sampler, scheduler или steps.
- [ ] Невалидный LLM output невозможно применить.

## Документация

- [Архитектура](ARCHITECTURE.md)
- [LLM Protocol](LLM_PROTOCOL.md)
- [Roadmap](ROADMAP.md)
- [Примеры промптов](promptexmaple.md)
- `docs/LoRA json exmples/` — локальные fixtures metadata
- `docs/sd-civitai-browser-neo-main/` — изученная референсная реализация CivitAI для Forge Neo

Внешние материалы:

- [Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo)
- [OpenRouter Structured Outputs](https://openrouter.ai/docs/guides/features/structured-outputs)
- [OpenRouter Image Inputs](https://openrouter.ai/docs/guides/overview/multimodal/image-understanding)
- [LM Studio OpenAI compatibility](https://lmstudio.ai/docs/developer/openai-compat)
- [LM Studio Structured Output](https://lmstudio.ai/docs/developer/openai-compat/structured-output)
- [CivitAI REST API reference](https://github.com/civitai/civitai/wiki/REST-API-Reference)

## Не входит в первую версию

- Автоматическая генерация изображений.
- Автоматическое переключение checkpoint.
- Автоматическое изменение параметров генерации.
- Скачивание рекомендованных моделей.
- Обучение LoRA.
- Облачная синхронизация истории промптов.
- Агентное выполнение команд.

Первая версия намеренно проектируется как предсказуемый помощник по промптам, а не автономный оператор WebUI.

## Поддержать проект

Если `ai-wdywfm` экономит ваше время и вы хотите поддержать его разработку:

| Актив / сеть | Адрес |
|---|---|
| **USDT (TRC-20)** | `TJWZfYHvis7B1uzxhCeenvtzaAFNipzjhz` |
| **LTC** | `LgRVpM8DRrae4ZKeFen39Z5FNXcQfeZtWL` |
| **ETH** | `0x60d1ab93862336241aa77fdf9c7e32e9f9ddf688` |

> [!CAUTION]
> Перед отправкой всегда проверяйте адрес и выбранную сеть. Криптовалютные транзакции необратимы.

---

<div align="center">

Создано для **Stable Diffusion WebUI Forge Neo**.

[Наверх](#ai-wdywfm)

</div>
