<div align="center">

# ai-wdywfm

### AI LLM SD WebUI ヘルパー

**What Do You Want From Me?**

自然言語のアイデア、または画像と編集指示を、Forge Neo に実際にインストールされているチェックポイントと LoRA に合わせた Stable Diffusion プロンプトへ変換します。

[![Forge Neo](https://img.shields.io/badge/Forge-Neo-2563eb?style=for-the-badge)](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo)
[![Gradio 4.40](https://img.shields.io/badge/Gradio-4.40-f97316?style=for-the-badge)](https://www.gradio.app/)
[![OpenRouter](https://img.shields.io/badge/LLM-OpenRouter-7c3aed?style=for-the-badge)](https://openrouter.ai/)
[![LM Studio](https://img.shields.io/badge/LLM-LM_Studio-0f766e?style=for-the-badge)](https://lmstudio.ai/)
[![Status](https://img.shields.io/badge/status-v0.1_MVP-22c55e?style=for-the-badge)](ROADMAP.md)

[English](README.md) · [Русский](README_RU.md) · [한국어](README_KO.md) · **日本語** · [简体中文](README_ZH_CN.md) · [繁體中文](README_ZH_TW.md)

[概要](#概要) · [仕組み](#仕組み) · [アーキテクチャ](#アーキテクチャ) · [ロードマップ](ROADMAP.md) · [プロジェクトを支援](#プロジェクトを支援)

</div>

> [!IMPORTANT]
> 最初の実行可能な MVP を利用できます。Forge Neo UI、LM Studio/OpenRouter の構造化リクエスト、テキスト・画像入力、検証、プロンプトだけを明示的に適用する機能を備えています。メタデータ拡充と高度なモデル検索は今後のロードマップ項目です。

> [!NOTE]
> **検証状況。** 最新の **Stable Diffusion WebUI Forge Neo** で一連の動作を確認済みです。実利用で検証済みのプロバイダーは現在 **OpenRouter** のみです。LM Studio も同じ契約で実装されていますが、エンドツーエンド検証は未完了です。
>
> **推奨・検証済みモデルは `google/gemma-4-31b-it`（Gemma 4 31B）**で、NSFW プロンプト生成にも対応します。ほかのモデルでは、スキーマ準拠、品質、コンテンツポリシーの挙動を保証できません。
>
> 画像生成前に、**生成されたプロンプトを必ず確認・編集**してください。LLM の提案は完成品ではなく下書きです。SDXL プロンプトが初めてなら、[この動画](https://www.youtube.com/watch?v=QdRP9pO89MY)や [CivitAI](https://civitai.com) のモデル別事例も参考にしてください。

## クイックスタート

1. このリポジトリを Forge Neo の `extensions/` ディレクトリへ配置します。
2. Forge Neo を再起動します。
3. `txt2img` または `img2img` で `LLM Prompt Helper · AI WDYWFM` を開きます。
4. LM Studio を `http://127.0.0.1:1234/v1` で起動するか、OpenRouter とセッション専用キーを選びます（`OPENROUTER_API_KEY` 環境変数にも対応）。
5. モデルを更新・選択し、望む結果を説明して `Generate verified draft` を押します。
6. プレビューと読み取り専用の推奨値を確認し、`Apply prompts` を押します。

WebUI の再読み込み後もプロバイダー、URL、モデル、OpenRouter キーは自動復元されます。Windows では保存キーを現在のユーザー用 DPAPI で暗号化します。タイムアウト、画像サイズ、コンテキスト上限は `Settings → AI WDYWFM` で設定できます。

各プロバイダー操作にはリクエスト ID が付き、サニタイズ済みローテーションログ `logs/ai-wdywfm.log` に記録されます。`Diagnostics · sanitized log` で最近のイベントを確認できます。API キー、プロンプト本文、画像は記録されません。

Gemma 4 系 OpenRouter モデルは、脱獄、独自ターンマーカー、推論要求を含まない高速な構造化出力プロファイルを使います。出力は 3072 トークン、Generate 1 回につき補完 1 回までで、構造化 JSON には Response Healing が有効です。

Forge は safetensors ヘッダーをキャッシュします。LoRA サイドカー JSON もサイズと更新時刻を基準にメモリキャッシュされ、関連性の高い詳細カード 8 件だけを送信し、検証用の完全なコンパクト ID 許可リストは保持します。

## 概要

`ai-wdywfm` は **Stable Diffusion WebUI Forge Neo** 専用のプロンプト支援ツールです。初心者は構文を覚える前に希望を説明でき、上級者はモデルを考慮した下書きをすばやく作成できます。

次の情報を組み合わせます。

- 自然言語の依頼
- 任意の参照画像と編集指示
- アクティブな `txt2img` / `img2img` コンテキスト
- インストール済みチェックポイントと LoRA
- ローカルメタデータ、トリガーワード、利用可能な CivitAI の説明
- バージョン管理されたシステムプロンプトと厳格な JSON Schema
- OpenRouter またはローカル LM Studio

### 絶対ルール

LLM 応答後に拡張機能が変更できるのは **Prompt** と **Negative Prompt** だけです。`CFG Scale`、寸法、サンプラー、スケジューラー、ステップ、ノイズ除去強度などは**読み取り専用の推奨値**で、Forge の各コントロールへ出力接続されません。

チェックポイントは自動切替しません。LoRA は ID と別名がローカル Forge Neo レジストリで検証された場合のみ、`<lora:name:weight>` として追加できます。

## 対象ユーザー

| ユーザー | 提供するもの |
|---|---|
| **初心者** | 普通の説明を実用的な正・負プロンプトへ変換します。 |
| **上級者** | 有効なローカル LoRA、トリガーワード、互換性警告を含む下書きを作ります。 |
| **オフライン優先** | クラウド LLM を使わず LM Studio とローカル/キャッシュ済み情報で動作します。 |
| **大量のモデルを所有** | 全説明を送らず、上限付きで順位付けしたコンテキストを構築します。 |

## 仕組み

### テキスト → プロンプト

```text
自然言語のアイデア
  ↓
Forge Neo のチェックポイント + LoRA 一覧
  ↓
ローカルサイドカー / safetensors / CivitAI キャッシュ
  ↓
関連モデルの順位付けと上限付きコンテキスト
  ↓
OpenRouter または LM Studio + 厳格な JSON Schema
  ↓
検証済みプレビュー → 明示的な “Apply prompts”
  ↓
Prompt + Negative Prompt のみ
```

1. `txt2img` または `img2img` で `AI WDYWFM` を開き、希望を普段の言葉で説明します。
2. 現在のチェックポイント、既存プロンプトの LoRA、関連するインストール済みモデルを検出します。
3. 不足メタデータを必要に応じて CivitAI から補完します。
4. LLM の構造化提案をスキーマと現在の Forge レジストリで検証します。
5. プロンプト、推奨値、モデル、警告を確認し、`Apply prompts` を押します。

### 画像 + 指示 → プロンプト

パネルに画像を添付し、変更・維持・削除・スタイル変更を説明します。サニタイズと縮小を施したコピーを、画像対応モデルがローカルモデル情報と共に解析します。同じ検証・明示的適用フローを使い、独自の画像入力により `txt2img` と `img2img` の両方で動作します。

## インターフェース

`AI WDYWFM` パネルは両生成タブで独立表示される `AlwaysVisible` Forge スクリプトです。

| コントロール | 用途 |
|---|---|
| Natural request | 希望する結果や編集を説明 |
| Reference image | 画像対応 LLM への任意入力 |
| Create / Edit | 依頼の意図を選択 |
| Prompt dialect | `Auto`、`Booru tags`、`Natural language` |
| Provider / model | LM Studio/OpenRouter とモデルを選択 |
| Model context preview | 送信されるローカル情報を確認 |
| Generate suggestion | 明示的な LLM リクエストを開始 |
| Prompt preview | 適用前に両プロンプトを確認 |
| Recommendations | CFG、寸法、サンプラー等の読み取り専用値 |
| Apply prompts | アクティブタブのプロンプトだけを置換または追記 |

`Apply prompts` を押すまで既存プロンプトは上書きされません。予定される既定値は `Replace with preview` で、`Append` も明示的に選べます。

## Forge Neo 互換性

対象は [Stable Diffusion WebUI Forge — Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo) の `neo` ブランチ、Gradio `4.40.0`、`modules.scripts`、`modules.script_callbacks`、`modules.shared`、組み込み `extensions-builtin/sd_forge_lora` です。

| タブ | 正プロンプト | 負プロンプト |
|---|---|---|
| txt2img | `txt2img_prompt` | `txt2img_neg_prompt` |
| img2img | `img2img_prompt` | `img2img_neg_prompt` |

Forge のコアファイルは変更しません。Forge Classic、AUTOMATIC1111、reForge などは互換性保証の対象外です。

## モデル対応 CivitAI 連携

CivitAI 対応は内部実装で、**CivitAI Browser Neo は実行時依存ではありません**。情報源をキャッシュ優先で確認します。

1. `<model>.api_info.json`
2. `<model>.json`
3. `.safetensors` の `__metadata__`
4. SQLite キャッシュ
5. `GET /api/v1/model-versions/by-hash/{sha256}`
6. `GET /api/v1/model-versions/{versionId}`
7. `GET /api/v1/models/{modelId}`

モデル ID、種類、ベースモデル系統、ハッシュ、CivitAI ID、トリガーワード、説明、作例プロンプト、フィールド別出典を正規化します。大きなチェックポイントは遅延ハッシュし、全ローカル一覧を保ちながら関連性の高い互換モデルだけをコンテキスト予算内で送ります。

## LLM プロバイダー

### LM Studio — ローカル優先の既定値

- 既定 URL: `http://127.0.0.1:1234/v1`
- OpenAI 互換 `/models`、`/chat/completions`
- 同じ JSON Schema による Structured Output
- 対応モデルで画像入力
- CivitAI キャッシュを使った完全ローカル動作

### OpenRouter

- `https://openrouter.ai/api/v1/chat/completions`
- テキスト・マルチモーダルモデル
- 対応モデルの厳格な Structured Outputs
- リクエスト前の機能フィルタリング
- 推奨シークレット元: `OPENROUTER_API_KEY`

両アダプターは同じプロバイダー中立オブジェクトを生成します。無効・不完全な応答は適用されません。

## 構造化レスポンス契約

正規スキーマは [prompt_suggestion.v1.json](schemas/prompt_suggestion.v1.json) です。

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

Forge に適用できるのは `prompt` と `negative_prompt` だけです。モデル ID、LoRA 重み、サンプラー、スケジューラー、値範囲は現在の Neo レジストリで追加検証します。詳細は [LLM プロトコル](docs/LLM_PROTOCOL.md)を参照してください。

## アーキテクチャ

```text
Forge Neo UI
  ↓
アプリケーションユースケース
  ↓
ドメインモデルとポリシー
  ├── Forge Neo インベントリアダプター
  ├── サイドカー / safetensors リーダー
  ├── CivitAI メタデータアダプター
  ├── OpenRouter / LM Studio アダプター
  └── SQLite キャッシュ
```

主なディレクトリは `scripts/`、`ai_wdywfm/application/`、`domain/`、`infrastructure/`、`prompts/`、`ui/`、`schemas/`、`tests/`、`docs/` です。[アーキテクチャ文書](docs/ARCHITECTURE.md)も参照してください。

## プライバシーとセキュリティ

> [!NOTE]
> リクエストは自動送信されません。ネットワーク接続はユーザーの明示操作後だけ開始します。

- API キーを LLM ペイロード、キャッシュ、ログへ含めません。
- ローカル絶対パスを送信しません。
- CivitAI 情報は命令ではなく信頼できないデータとして扱います。
- クラウドへの画像送信には明示的な同意が必要です。
- 参照画像は検証、縮小、メタデータ削除、再エンコードを行います。
- 未知のモデル、LoRA、Embedding、サンプラー、スケジューラーを拒否します。
- 生成開始、モデル取得、LLM 出力の実行は行いません。
- プロンプト、画像、シークレット、完全な応答を既定ログから除外します。

## MVP 設定

| 設定 | 既定値 | 用途 |
|---|---:|---|
| Provider | `LM Studio` | ローカル優先 |
| LM Studio base URL | `http://127.0.0.1:1234/v1` | ローカルサーバー |
| OpenRouter model | 空 | 明示選択が必要 |
| CivitAI enrichment | On | 不足情報を取得 |
| CivitAI domain | `civitai.com` | `civitai.red` も選択可能 |
| Detailed model cards | `12` | 1 リクエストの上限 |
| Context budget | `12,000 tokens` | ソフト上限 |
| LLM timeout | `120 seconds` | リクエスト制限時間 |
| Image maximum side | `1,536 px` | 画像入力サイズ上限 |
| Cloud image input | Off | OpenRouter 画像への追加同意 |
| Debug logging | Off | 内容とシークレットを除外 |

## MVP 受け入れ基準

- [ ] コア変更なしで起動
- [ ] `txt2img` / `img2img` で独立動作
- [ ] Neo レジストリからチェックポイントと LoRA を検出
- [ ] ローカルサイドカーを正規化
- [ ] キャッシュ優先の SHA-256 CivitAI 検索
- [ ] 両プロバイダーが同じドメインオブジェクトを返す
- [ ] テキスト・画像フローが完走
- [ ] `Apply prompts` はアクティブタブの 2 項目だけ変更
- [ ] 推奨値は生成設定を変更しない
- [ ] 無効な出力を適用できない

## ドキュメント

- [アーキテクチャ](docs/ARCHITECTURE.md)
- [LLM プロトコル](docs/LLM_PROTOCOL.md)
- [ロードマップ](ROADMAP.md)
- [プロンプト例](docs/promptexmaple.md)
- `docs/LoRA json exmples/` — ローカルメタデータ fixtures
- `docs/sd-civitai-browser-neo-main/` — Forge Neo CivitAI 参考資料

外部資料: [Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo)、[OpenRouter Structured Outputs](https://openrouter.ai/docs/guides/features/structured-outputs)、[OpenRouter Image Inputs](https://openrouter.ai/docs/guides/overview/multimodal/image-understanding)、[LM Studio OpenAI compatibility](https://lmstudio.ai/docs/developer/openai-compat)、[LM Studio Structured Output](https://lmstudio.ai/docs/developer/openai-compat/structured-output)、[CivitAI REST API](https://github.com/civitai/civitai/wiki/REST-API-Reference)。

## 初回リリースの対象外

画像の自動生成、チェックポイント自動切替、生成パラメーター自動変更、推奨モデルのダウンロード、LoRA 学習、プロンプト履歴のクラウド同期、エージェント型コマンド実行は対象外です。初回リリースは自律 WebUI オペレーターではなく、予測可能なプロンプト支援ツールです。

## プロジェクトを支援

| 資産 / ネットワーク | アドレス |
|---|---|
| **USDT (TRC-20)** | `TJWZfYHvis7B1uzxhCeenvtzaAFNipzjhz` |
| **LTC** | `LgRVpM8DRrae4ZKeFen39Z5FNXcQfeZtWL` |
| **ETH** | `0x60d1ab93862336241aa77fdf9c7e32e9f9ddf688` |

> [!CAUTION]
> 送金前にアドレスとネットワークを確認してください。暗号資産取引は取り消せません。

---

<div align="center">

**Stable Diffusion WebUI Forge Neo** のために開発。

[先頭へ戻る](#ai-wdywfm)

</div>
