<div align="center">

# ai-wdywfm

### AI LLM SD WebUI 助手

**What Do You Want From Me?**

將自然語言構想，或圖片與編輯說明，轉換為配合 Forge Neo 中實際安裝之 checkpoint 與 LoRA 的 Stable Diffusion 提示詞。

[![Forge Neo](https://img.shields.io/badge/Forge-Neo-2563eb?style=for-the-badge)](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo)
[![Gradio 4.40](https://img.shields.io/badge/Gradio-4.40-f97316?style=for-the-badge)](https://www.gradio.app/)
[![OpenRouter](https://img.shields.io/badge/LLM-OpenRouter-7c3aed?style=for-the-badge)](https://openrouter.ai/)
[![LM Studio](https://img.shields.io/badge/LLM-LM_Studio-0f766e?style=for-the-badge)](https://lmstudio.ai/)
[![Status](https://img.shields.io/badge/status-v0.1_MVP-22c55e?style=for-the-badge)](ROADMAP.md)

[English](README.md) · [Русский](README_RU.md) · [한국어](README_KO.md) · [日本語](README_JA.md) · [简体中文](README_ZH_CN.md) · **繁體中文**

[概覽](#概覽) · [運作方式](#運作方式) · [架構](#架構) · [路線圖](ROADMAP.md) · [支持專案](#支持專案)

</div>

> [!IMPORTANT]
> 首個可執行的 MVP 已提供，包含 Forge Neo 介面、LM Studio/OpenRouter 結構化請求、文字與視覺輸入、驗證，以及僅對提示詞的明確套用。中繼資料強化與進階模型檢索仍屬路線圖工作。

> [!NOTE]
> **驗證狀態。** 已在最新版 **Stable Diffusion WebUI Forge Neo** 完成端對端驗證。目前僅 **OpenRouter** 經實際使用驗證；LM Studio 依同一契約實作，但尚未完成端對端確認。
>
> **建議且已驗證的模型是 `google/gemma-4-31b-it`（Gemma 4 31B）**，亦支援 NSFW 提示詞。其他模型的結構描述遵循度、提示詞品質與內容政策行為均不保證。
>
> 強烈建議在生成圖片前**檢查並編輯生成的提示詞**。所有 LLM 建議都應視為草稿。初次接觸 SDXL 提示詞時，可參考[此影片](https://www.youtube.com/watch?v=QdRP9pO89MY)與 [CivitAI](https://civitai.com) 的模型專屬技巧及範例。

## 快速開始

1. 從 [github.com/mikhailfur/sd-webui-ai-wdywfm/releases/latest](https://github.com/mikhailfur/sd-webui-ai-wdywfm/releases/latest) 下載最新版本的 zip 壓縮檔。
2. 將壓縮檔解壓縮到 Forge Neo 的 `extensions/` 目錄，使擴充功能本身的資料夾（例如 `sd-webui-ai-wdywfm`）直接位於 `extensions/` 之下，而不是巢狀在更深一層的資料夾中。
3. 重新啟動 Forge Neo（需完全關閉並重新啟動 WebUI 處理程序，僅重新整理瀏覽器頁面並不足夠）。
4. 在 `txt2img` 或 `img2img` 開啟 `LLM Prompt Helper · AI WDYWFM`。
5. 在 `http://127.0.0.1:1234/v1` 啟動 LM Studio，或選擇 OpenRouter 並提供僅限工作階段的金鑰（亦支援 `OPENROUTER_API_KEY` 環境變數）。
6. 重新整理/選擇模型，描述目標，再按 `Generate verified draft`。
7. 檢查預覽與唯讀建議，然後按 `Apply prompts`。

重新載入 WebUI 後，提供者、URL、模型及 OpenRouter 金鑰會自動還原。Windows 上的已儲存金鑰使用目前使用者的 DPAPI 加密。逾時、圖片尺寸與上下文限制可在 `Settings → AI WDYWFM` 設定。

每項提供者操作都有請求 ID，並寫入已淨化的輪替日誌 `logs/ai-wdywfm.log`。可於 `Diagnostics · sanitized log` 查看近期事件。API 金鑰、提示詞文字與圖片絕不寫入此日誌。

Gemma 4 系列 OpenRouter 模型使用快速結構化輸出設定，不含越獄、自訂回合標記或推理要求。輸出上限為 3072 token，每次 Generate 最多一次 completion；結構化 JSON 啟用 Response Healing。

Forge 會快取 safetensors 標頭。LoRA sidecar JSON 也依檔案大小與修改時間快取於記憶體；只傳送最相關的 8 張詳細 LoRA 卡，同時保留完整精簡 ID 允許清單供驗證。

## 概覽

`ai-wdywfm` 是專為 **Stable Diffusion WebUI Forge Neo** 建置的提示詞助手。初學者不必先學提示詞語法即可描述需求，熟練使用者則能更快建立能感知模型的草稿。

助手結合以下資訊：

- 自然語言請求；
- 選用的參考圖片與編輯說明；
- 目前 `txt2img` 或 `img2img` 上下文；
- 已安裝的 checkpoint 與 LoRA；
- 本機模型中繼資料、觸發詞與可用的 CivitAI 說明；
- 具版本的系統提示詞與嚴格 JSON Schema；
- OpenRouter 或本機 LM Studio。

### 不可違背的規則

LLM 回應後，擴充功能只能更新 **Prompt** 與 **Negative Prompt**。`CFG Scale`、尺寸、採樣器、排程器、採樣步數、去雜訊強度等僅顯示為**唯讀建議**，不會連接到 Forge 控制項的輸出。

Checkpoint 不會自動切換。只有 ID 與別名通過本機 Forge Neo 登錄驗證後，LoRA 才能以 `<lora:name:weight>` 加入提示詞。

## 適用對象

| 使用者 | ai-wdywfm 提供的功能 |
|---|---|
| **初學者** | 將一般描述轉換為可用的正向與負向提示詞。 |
| **進階使用者** | 產生含有效本機 LoRA、觸發詞及相容性警告的模型感知草稿。 |
| **離線優先使用者** | 使用 LM Studio 與快取/本機資料，不必傳送請求至雲端 LLM。 |
| **大型模型收藏者** | 建立有界且排序過的上下文，而非傳送所有完整模型說明。 |

## 運作方式

### 文字 → 提示詞

```text
自然語言構想
  ↓
Forge Neo checkpoint + LoRA 清單
  ↓
本機 sidecar / safetensors / CivitAI 快取
  ↓
相關模型排序與有界上下文
  ↓
OpenRouter 或 LM Studio + 嚴格 JSON Schema
  ↓
已驗證預覽 → 明確的 “Apply prompts”
  ↓
僅 Prompt + Negative Prompt
```

1. 在 `txt2img` 或 `img2img` 開啟 `AI WDYWFM`，以日常語言描述所需圖片。
2. 擴充功能偵測目前 checkpoint、提示詞中已有的 LoRA 與相關已安裝模型。
3. 可選擇從 CivitAI 補充缺少的中繼資料。
4. LLM 傳回結構化建議，並依 schema 與目前 Forge 登錄進行驗證。
5. 檢查提示詞、建議、模型與警告，再按 `Apply prompts`。

### 圖片 + 說明 → 提示詞

在助手面板附加圖片，說明要變更、保留、移除或重新設計的內容。經淨化與縮放的副本會交由支援視覺的模型，連同本機模型上下文一起分析，之後使用相同的驗證和明確套用流程。擴充功能擁有獨立圖片輸入，因此在 `txt2img` 與 `img2img` 均可使用。

## 介面

`AI WDYWFM` 面板是於兩個生成分頁獨立呈現的 `AlwaysVisible` Forge 指令碼。

| 控制項 | 用途 |
|---|---|
| Natural request | 描述目標結果或編輯內容 |
| Reference image | 視覺 LLM 的選用輸入 |
| Create / Edit | 選擇請求意圖 |
| Prompt dialect | `Auto`、`Booru tags` 或 `Natural language` |
| Provider / model | 選擇 LM Studio/OpenRouter 及模型 |
| Model context preview | 查看將包含的本機模型資料 |
| Generate suggestion | 發起明確的 LLM 請求 |
| Prompt preview | 套用前檢查正向與負向提示詞 |
| Recommendations | CFG、尺寸、採樣器、排程器、步數的唯讀值 |
| Apply prompts | 僅取代或附加目前分頁的提示詞欄位 |

使用者按下 `Apply prompts` 前不會覆寫原提示詞。規劃的預設模式是 `Replace with preview`，`Append` 則是明確的替代選項。

## Forge Neo 相容性

目標環境為 [Stable Diffusion WebUI Forge — Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo) 的 `neo` 分支、Gradio `4.40.0`、`modules.scripts`、`modules.script_callbacks`、`modules.shared` 與內建 `extensions-builtin/sd_forge_lora`。

| 分頁 | 正向提示詞 | 負向提示詞 |
|---|---|---|
| txt2img | `txt2img_prompt` | `txt2img_neg_prompt` |
| img2img | `img2img_prompt` | `img2img_neg_prompt` |

不會修改 Forge 核心檔案。Forge Classic、AUTOMATIC1111、reForge 等不在相容性保證範圍內。

## 模型感知 CivitAI 整合

CivitAI 支援內建於 `ai-wdywfm`，**執行階段不依賴 CivitAI Browser Neo**。中繼資料來源依快取優先順序解析：

1. `<model>.api_info.json`
2. `<model>.json`
3. `.safetensors` 的 `__metadata__`
4. SQLite 快取
5. `GET /api/v1/model-versions/by-hash/{sha256}`
6. `GET /api/v1/model-versions/{versionId}`
7. `GET /api/v1/models/{modelId}`

正規化內容包含模型身分、類型、基礎模型系列、雜湊、CivitAI ID、觸發詞、說明、範例提示詞與欄位層級來源。大型 checkpoint 延遲計算雜湊；系統保留完整本機清單，但只在上下文預算內傳送最相關的相容模型。

## LLM 提供者

### LM Studio — 本機優先預設值

- 預設 URL：`http://127.0.0.1:1234/v1`
- OpenAI 相容 `/models` 與 `/chat/completions`
- 使用同一 JSON Schema 的 Structured Output
- 所選模型支援時可使用視覺輸入
- 搭配已快取的 CivitAI 資料可完全於本機運作

### OpenRouter

- `https://openrouter.ai/api/v1/chat/completions`
- 文字及多模態模型
- 相容模型上的嚴格 Structured Outputs
- 請求前進行功能篩選
- 建議的金鑰來源：`OPENROUTER_API_KEY`

兩個適配器產生相同的提供者中立領域物件。無效或不完整的回應絕不套用。

## 結構化回應契約

標準 schema 為 [prompt_suggestion.v1.json](schemas/prompt_suggestion.v1.json)：

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

只有 `prompt` 與 `negative_prompt` 可套用至 Forge。模型 ID、LoRA 權重、採樣器、排程器與值範圍還會依即時 Neo 登錄進行語意驗證。詳見 [LLM 協定](docs/LLM_PROTOCOL.md)。

## 架構

```text
Forge Neo UI
  ↓
應用程式使用案例
  ↓
領域模型與政策
  ├── Forge Neo 清單適配器
  ├── sidecar / safetensors 讀取器
  ├── CivitAI 中繼資料適配器
  ├── OpenRouter / LM Studio 適配器
  └── SQLite 快取
```

主要目錄包括 `scripts/`、`ai_wdywfm/application/`、`domain/`、`infrastructure/`、`prompts/`、`ui/`、`schemas/`、`tests/` 與 `docs/`。請閱讀完整[架構文件](docs/ARCHITECTURE.md)。

## 隱私與安全

> [!NOTE]
> 請求不會自動傳送。只有使用者明確操作後才會開始網路存取。

- API 金鑰不會進入 LLM payload、快取或日誌。
- 本機絕對路徑不會傳送給提供者。
- CivitAI 資料視為不受信任的資料，而非指令。
- 雲端圖片上傳需要明確同意。
- 參考圖片會經驗證、縮放、移除中繼資料並重新編碼。
- 未知的模型、LoRA、embedding、採樣器或排程器會被拒絕。
- 擴充功能不會啟動生成、下載模型或執行 LLM 輸出文字。
- 預設日誌不含提示詞、圖片、金鑰或完整提供者回應。

## MVP 設定

| 設定 | 預設值 | 用途 |
|---|---:|---|
| Provider | `LM Studio` | 本機優先預設值 |
| LM Studio base URL | `http://127.0.0.1:1234/v1` | 本機伺服器 |
| OpenRouter model | 空白 | 需要明確選擇 |
| CivitAI enrichment | 開啟 | 取得缺少的資料 |
| CivitAI domain | `civitai.com` | 可選擇 `civitai.red` |
| Detailed model cards | `12` | 每次請求上限 |
| Context budget | `12,000 tokens` | 軟性上限 |
| LLM timeout | `120 seconds` | 請求逾時 |
| Image maximum side | `1,536 px` | 視覺輸入尺寸限制 |
| Cloud image input | 關閉 | OpenRouter 圖片額外同意 |
| Debug logging | 關閉 | 仍排除內容與金鑰 |

## MVP 驗收條件

- [ ] 無需修改核心即可啟動
- [ ] 在 `txt2img` / `img2img` 獨立運作
- [ ] 從 Neo 登錄發現 checkpoint 與 LoRA
- [ ] 正確正規化本機 sidecar
- [ ] 依 SHA-256 查詢 CivitAI 且快取優先
- [ ] 兩個提供者傳回相同領域物件
- [ ] 文字與視覺流程端對端通過
- [ ] `Apply prompts` 僅修改目前分頁的兩個欄位
- [ ] 建議不會變更生成設定
- [ ] 無效輸出無法套用

## 文件

- [架構](docs/ARCHITECTURE.md)
- [LLM 協定](docs/LLM_PROTOCOL.md)
- [路線圖](ROADMAP.md)
- [提示詞範例](docs/promptexmaple.md)
- `docs/LoRA json exmples/` — 本機中繼資料範例
- `docs/sd-civitai-browser-neo-main/` — Forge Neo CivitAI 參考

外部資料：[Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo)、[OpenRouter Structured Outputs](https://openrouter.ai/docs/guides/features/structured-outputs)、[OpenRouter Image Inputs](https://openrouter.ai/docs/guides/overview/multimodal/image-understanding)、[LM Studio OpenAI compatibility](https://lmstudio.ai/docs/developer/openai-compat)、[LM Studio Structured Output](https://lmstudio.ai/docs/developer/openai-compat/structured-output)、[CivitAI REST API](https://github.com/civitai/civitai/wiki/REST-API-Reference)。

## 首個版本不包含

自動圖片生成、自動切換 checkpoint、自動變更生成參數、下載建議模型、LoRA 訓練、提示詞歷史雲端同步，以及代理式命令執行。首個版本刻意維持為可預測的提示詞助手，而非自主 WebUI 操作員。

## 支持專案

| 資產 / 網路 | 位址 |
|---|---|
| **USDT (TRC-20)** | `TJWZfYHvis7B1uzxhCeenvtzaAFNipzjhz` |
| **LTC** | `LgRVpM8DRrae4ZKeFen39Z5FNXcQfeZtWL` |
| **ETH** | `0x60d1ab93862336241aa77fdf9c7e32e9f9ddf688` |

> [!CAUTION]
> 轉帳前務必核對位址與所選網路。加密貨幣交易無法撤銷。

---

<div align="center">

為 **Stable Diffusion WebUI Forge Neo** 建置。

[返回頂端](#ai-wdywfm)

</div>
