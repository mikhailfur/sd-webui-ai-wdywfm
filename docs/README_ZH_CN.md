<div align="center">

<img src="banner.png" alt="WDYWFM — Forge Neo AI 提示词助手" width="100%">

# ai-wdywfm

### AI LLM SD WebUI 助手

**What Do You Want From Me?**

将自然语言创意，或图片与编辑说明，转换为适配 Forge Neo 中实际安装的检查点和 LoRA 的 Stable Diffusion 提示词。

[![Forge Neo](https://img.shields.io/badge/Forge-Neo-2563eb?style=for-the-badge)](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo)
[![Gradio 4.40](https://img.shields.io/badge/Gradio-4.40-f97316?style=for-the-badge)](https://www.gradio.app/)
[![OpenRouter](https://img.shields.io/badge/LLM-OpenRouter-7c3aed?style=for-the-badge)](https://openrouter.ai/)
[![LM Studio](https://img.shields.io/badge/LLM-LM_Studio-0f766e?style=for-the-badge)](https://lmstudio.ai/)
[![Status](https://img.shields.io/badge/status-v0.1_MVP-22c55e?style=for-the-badge)](ROADMAP.md)

[English](../README.md) · [Русский](README_RU.md) · [한국어](README_KO.md) · [日本語](README_JA.md) · **简体中文** · [繁體中文](README_ZH_TW.md)

[概述](#概述) · [工作原理](#工作原理) · [架构](#架构) · [路线图](ROADMAP.md) · [支持项目](#支持项目)

</div>

> [!IMPORTANT]
> 首个可运行的 MVP 已发布，包含 Forge Neo 界面、LM Studio/OpenRouter 结构化请求、文本与视觉输入、验证，以及仅对提示词的显式应用。元数据增强和高级模型检索仍在路线图中。

> [!NOTE]
> **验证状态。** 已在最新的 **Stable Diffusion WebUI Forge Neo** 上完成端到端验证。目前仅 **OpenRouter** 经过实际使用验证；LM Studio 按相同契约实现，但尚未完成端到端确认。
>
> **推荐且已验证的模型为 `google/gemma-4-31b-it`（Gemma 4 31B）**，它也支持生成 NSFW 提示词。其他模型的模式遵循度、提示词质量和内容政策行为均不作保证。
>
> 强烈建议在生成图片前**检查并编辑生成的提示词**。请将所有 LLM 建议视为草稿。若刚接触 SDXL 提示词，可参考[此视频](https://www.youtube.com/watch?v=QdRP9pO89MY)和 [CivitAI](https://civitai.com) 上针对不同模型的技巧与示例。

## 快速开始

1. 从 [github.com/mikhailfur/sd-webui-ai-wdywfm/releases/latest](https://github.com/mikhailfur/sd-webui-ai-wdywfm/releases/latest) 下载最新版本的 zip 压缩包。
2. 将压缩包解压到 Forge Neo 的 `extensions/` 目录，使扩展自身的文件夹（例如 `sd-webui-ai-wdywfm`）直接位于 `extensions/` 下，而不是嵌套在更深一层的文件夹中。
3. 重启 Forge Neo（需要完全关闭并重新启动 WebUI 进程，仅刷新浏览器页面是不够的）。
4. 在 `txt2img` 或 `img2img` 中打开 `LLM Prompt Helper · AI WDYWFM`。
5. 在 `http://127.0.0.1:1234/v1` 启动 LM Studio，或选择 OpenRouter 并提供仅限会话的密钥（也支持 `OPENROUTER_API_KEY` 环境变量）。
6. 刷新/选择模型，描述目标，然后点击 `Generate verified draft`。
7. 检查预览和只读建议，再点击 `Apply prompts`。

重新加载 WebUI 后会自动恢复提供商、URL、模型和 OpenRouter 密钥。Windows 上保存的密钥使用当前用户的 DPAPI 加密。超时、图片尺寸和上下文限制位于 `Settings → AI WDYWFM`。

每次提供商操作都有请求 ID，并写入经过清理的轮转日志 `logs/ai-wdywfm.log`。可在面板的 `Diagnostics · sanitized log` 中查看近期事件。API 密钥、提示词正文和图片绝不会写入该日志。

Gemma 4 系列 OpenRouter 模型使用快速结构化输出配置，不包含越狱、定制轮次标记或推理请求。输出上限为 3072 token，每次 Generate 最多发起一次补全；结构化 JSON 响应启用 Response Healing。

Forge 会缓存 safetensors 头。LoRA sidecar JSON 也按文件大小和修改时间在内存中缓存；只发送最相关的 8 张详细 LoRA 卡，同时保留完整的紧凑 ID 白名单用于验证。

## 概述

`ai-wdywfm` 是专为 **Stable Diffusion WebUI Forge Neo** 构建的提示词助手。初学者无需先学习提示词语法即可描述需求，熟练用户则能更快起草能够感知模型的提示词。

助手会结合：

- 自然语言请求；
- 可选的参考图片和编辑说明；
- 当前 `txt2img` 或 `img2img` 上下文；
- 已安装的检查点与 LoRA；
- 本地模型元数据、触发词和可用的 CivitAI 说明；
- 带版本的系统提示词与严格 JSON Schema；
- OpenRouter 或本地 LM Studio。

### 不可违背的规则

LLM 响应后，扩展只能更新 **Prompt** 和 **Negative Prompt**。`CFG Scale`、尺寸、采样器、调度器、采样步数、去噪强度等仅显示为**只读建议**，不会连接到 Forge 控件的输出。

检查点不会自动切换。只有在 ID 和别名通过本地 Forge Neo 注册表验证后，LoRA 才能以 `<lora:name:weight>` 形式加入提示词。

## 适用人群

| 用户 | ai-wdywfm 提供的功能 |
|---|---|
| **初学者** | 将普通描述转换为可用的正向和负向提示词。 |
| **高级用户** | 生成含有效本地 LoRA、触发词和兼容性警告的模型感知草稿。 |
| **离线优先用户** | 使用 LM Studio 和缓存/本地元数据，无需将请求发送到云端 LLM。 |
| **大型模型收藏者** | 构建有界且有排序的上下文，而非发送所有完整模型说明。 |

## 工作原理

### 文本 → 提示词

```text
自然语言创意
  ↓
Forge Neo 检查点 + LoRA 清单
  ↓
本地 sidecar / safetensors / CivitAI 缓存
  ↓
相关模型排序与有界上下文
  ↓
OpenRouter 或 LM Studio + 严格 JSON Schema
  ↓
验证后的预览 → 显式 “Apply prompts”
  ↓
仅 Prompt + Negative Prompt
```

1. 在 `txt2img` 或 `img2img` 中打开 `AI WDYWFM`，用日常语言描述想要的图片。
2. 扩展检测当前检查点、提示词中已有的 LoRA 和相关已安装模型。
3. 可选择从 CivitAI 补全缺失元数据。
4. LLM 返回结构化建议，并根据模式与当前 Forge 注册表进行验证。
5. 检查提示词、建议、模型和警告，再点击 `Apply prompts`。

### 图片 + 说明 → 提示词

在助手面板中附加图片，并说明要更改、保留、移除或重新设计的内容。经清理和缩放的副本会发送给支持视觉的模型，与本地模型上下文一起分析。之后使用相同的验证和显式应用流程。扩展拥有独立图片输入，因此在 `txt2img` 和 `img2img` 中均可使用。

## 界面

`AI WDYWFM` 面板是一个在两个生成标签页中独立渲染的 `AlwaysVisible` Forge 脚本。

| 控件 | 用途 |
|---|---|
| Natural request | 描述目标结果或编辑内容 |
| Reference image | 供视觉 LLM 使用的可选输入 |
| Create / Edit | 选择请求意图 |
| Prompt dialect | `Auto`、`Booru tags` 或 `Natural language` |
| Provider / model | 选择 LM Studio/OpenRouter 及模型 |
| Model context preview | 查看将包含的本地模型元数据 |
| Generate suggestion | 发起显式 LLM 请求 |
| Prompt preview | 应用前检查正向和负向提示词 |
| Recommendations | CFG、尺寸、采样器、调度器、步数的只读值 |
| Apply prompts | 仅替换或追加当前标签页的提示词字段 |

在用户点击 `Apply prompts` 前不会覆盖原提示词。计划的默认模式是 `Replace with preview`，`Append` 是显式备选项。

## Forge Neo 兼容性

目标环境为 [Stable Diffusion WebUI Forge — Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo) 的 `neo` 分支、Gradio `4.40.0`、`modules.scripts`、`modules.script_callbacks`、`modules.shared` 及内置的 `extensions-builtin/sd_forge_lora`。

| 标签页 | 正向提示词 | 负向提示词 |
|---|---|---|
| txt2img | `txt2img_prompt` | `txt2img_neg_prompt` |
| img2img | `img2img_prompt` | `img2img_neg_prompt` |

不会修改 Forge 核心文件。Forge Classic、AUTOMATIC1111、reForge 等不在兼容性保证范围内。

## 感知模型的 CivitAI 集成

CivitAI 支持内置于 `ai-wdywfm`，**运行时不依赖 CivitAI Browser Neo**。元数据源按缓存优先顺序解析：

1. `<model>.api_info.json`
2. `<model>.json`
3. `.safetensors` 的 `__metadata__`
4. SQLite 缓存
5. `GET /api/v1/model-versions/by-hash/{sha256}`
6. `GET /api/v1/model-versions/{versionId}`
7. `GET /api/v1/models/{modelId}`

标准化内容包括模型身份、类型、基础模型系列、哈希、CivitAI ID、触发词、说明、示例提示词和字段级来源。大型检查点延迟计算哈希；系统保留完整本地清单，但只在上下文预算内发送最相关的兼容模型。

## LLM 提供商

### LM Studio — 本地优先默认项

- 默认 URL：`http://127.0.0.1:1234/v1`
- OpenAI 兼容的 `/models` 和 `/chat/completions`
- 使用相同 JSON Schema 的 Structured Output
- 所选模型支持时可使用视觉输入
- 借助缓存的 CivitAI 元数据可完全在本地运行

### OpenRouter

- `https://openrouter.ai/api/v1/chat/completions`
- 文本及多模态模型
- 兼容模型上的严格 Structured Outputs
- 请求前进行能力筛选
- 推荐的密钥来源：`OPENROUTER_API_KEY`

两个适配器生成相同的提供商无关领域对象。无效或不完整响应绝不会应用。

## 结构化响应契约

规范模式为 [prompt_suggestion.v1.json](../schemas/prompt_suggestion.v1.json)：

```json
{
  "schema_version": "1.0",
  "prompt": "masterpiece, best quality, neon city, night, rain",
  "negative_prompt": "worst quality, blurry, text, watermark",
  "models": { "checkpoint_id": null, "loras": [] },
  "recommendations": {
    "sampler": "Euler a", "scheduler": "Automatic",
    "sampling_steps": 28, "cfg_scale": 5,
    "width": 832, "height": 1216, "denoising_strength": null
  },
  "summary": "Vertical neon-lit night scene.",
  "warnings": []
}
```

只有 `prompt` 和 `negative_prompt` 可应用到 Forge。模型 ID、LoRA 权重、采样器、调度器和值范围还会根据实时 Neo 注册表进行语义验证。详见 [LLM 协议](LLM_PROTOCOL.md)。

## 架构

```text
Forge Neo UI
  ↓
应用用例
  ↓
领域模型与策略
  ├── Forge Neo 清单适配器
  ├── sidecar / safetensors 读取器
  ├── CivitAI 元数据适配器
  ├── OpenRouter / LM Studio 适配器
  └── SQLite 缓存
```

主要目录包括 `scripts/`、`ai_wdywfm/application/`、`domain/`、`infrastructure/`、`prompts/`、`ui/`、`schemas/`、`tests/` 和 `docs/`。请阅读完整的[架构文档](ARCHITECTURE.md)。

## 隐私与安全

> [!NOTE]
> 请求不会自动发送。只有用户明确操作后才会开始网络访问。

- API 密钥不进入 LLM 载荷、缓存或日志。
- 绝对本地路径不会发送给提供商。
- CivitAI 信息视为不可信数据，而非指令。
- 云端图片上传需要明确同意。
- 参考图片会经过验证、缩放、去除元数据和重新编码。
- 未知的模型、LoRA、嵌入、采样器或调度器会被拒绝。
- 扩展不会启动生成、下载模型或执行 LLM 输出文本。
- 默认日志不含提示词、图片、密钥或完整提供商响应。

## MVP 配置

| 设置 | 默认值 | 用途 |
|---|---:|---|
| Provider | `LM Studio` | 本地优先默认项 |
| LM Studio base URL | `http://127.0.0.1:1234/v1` | 本地服务器 |
| OpenRouter model | 空 | 需要明确选择 |
| CivitAI enrichment | 开 | 获取缺失元数据 |
| CivitAI domain | `civitai.com` | 可选择 `civitai.red` |
| Detailed model cards | `12` | 每次请求的上限 |
| Context budget | `12,000 tokens` | 软上限 |
| LLM timeout | `120 seconds` | 请求超时 |
| Image maximum side | `1,536 px` | 视觉输入尺寸限制 |
| Cloud image input | 关 | OpenRouter 图片额外同意 |
| Debug logging | 关 | 仍排除内容和密钥 |

## MVP 验收标准

- [ ] 无需修改核心即可启动
- [ ] 在 `txt2img` / `img2img` 中独立运行
- [ ] 从 Neo 注册表发现检查点和 LoRA
- [ ] 正确标准化本地 sidecar
- [ ] 按 SHA-256 查询 CivitAI 且缓存优先
- [ ] 两个提供商返回相同领域对象
- [ ] 文本与视觉流程端到端通过
- [ ] `Apply prompts` 只修改当前标签页的两个字段
- [ ] 建议不会更改生成设置
- [ ] 无效输出无法应用

## 文档

- [架构](ARCHITECTURE.md)
- [LLM 协议](LLM_PROTOCOL.md)
- [路线图](ROADMAP.md)
- [提示词示例](promptexmaple.md)
- `docs/LoRA json exmples/` — 本地元数据样本
- `docs/sd-civitai-browser-neo-main/` — Forge Neo CivitAI 参考

外部资料：[Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo)、[OpenRouter Structured Outputs](https://openrouter.ai/docs/guides/features/structured-outputs)、[OpenRouter Image Inputs](https://openrouter.ai/docs/guides/overview/multimodal/image-understanding)、[LM Studio OpenAI compatibility](https://lmstudio.ai/docs/developer/openai-compat)、[LM Studio Structured Output](https://lmstudio.ai/docs/developer/openai-compat/structured-output)、[CivitAI REST API](https://github.com/civitai/civitai/wiki/REST-API-Reference)。

## 首个版本不包含

自动图片生成、自动切换检查点、自动修改生成参数、下载推荐模型、LoRA 训练、提示词历史云同步和代理式命令执行。首个版本有意保持为可预测的提示词助手，而不是自主 WebUI 操作员。

## 支持项目

| 资产 / 网络 | 地址 |
|---|---|
| **USDT (TRC-20)** | `TJWZfYHvis7B1uzxhCeenvtzaAFNipzjhz` |
| **LTC** | `LgRVpM8DRrae4ZKeFen39Z5FNXcQfeZtWL` |
| **ETH** | `0x60d1ab93862336241aa77fdf9c7e32e9f9ddf688` |

> [!CAUTION]
> 转账前务必核对地址和所选网络。加密货币交易不可撤销。

---

<div align="center">

为 **Stable Diffusion WebUI Forge Neo** 构建。

[返回顶部](#ai-wdywfm)

</div>
