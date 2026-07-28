<div align="center">

<img src="banner.png" alt="WDYWFM — Forge Neo용 AI 프롬프트 도우미" width="100%">

# ai-wdywfm

### AI LLM SD WebUI 도우미

**What Do You Want From Me?**

자연어 아이디어 또는 이미지와 편집 지시를 Forge Neo에 실제로 설치된 체크포인트와 LoRA에 맞는 Stable Diffusion 프롬프트로 변환합니다.

[![Forge Neo](https://img.shields.io/badge/Forge-Neo-2563eb?style=for-the-badge)](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo)
[![Gradio 4.40](https://img.shields.io/badge/Gradio-4.40-f97316?style=for-the-badge)](https://www.gradio.app/)
[![OpenRouter](https://img.shields.io/badge/LLM-OpenRouter-7c3aed?style=for-the-badge)](https://openrouter.ai/)
[![LM Studio](https://img.shields.io/badge/LLM-LM_Studio-0f766e?style=for-the-badge)](https://lmstudio.ai/)
[![Status](https://img.shields.io/badge/status-v0.1_MVP-22c55e?style=for-the-badge)](ROADMAP.md)

[English](../README.md) · [Русский](README_RU.md) · **한국어** · [日本語](README_JA.md) · [简体中文](README_ZH_CN.md) · [繁體中文](README_ZH_TW.md)

[개요](#개요) · [작동 방식](#작동-방식) · [아키텍처](#아키텍처) · [로드맵](ROADMAP.md) · [프로젝트 후원](#프로젝트-후원)

</div>

> [!IMPORTANT]
> 최초 실행 가능한 MVP가 제공됩니다. Forge Neo UI, LM Studio/OpenRouter 구조화 요청, 텍스트·비전 입력, 검증, 명시적인 프롬프트 전용 적용을 지원합니다. 메타데이터 보강과 고급 모델 검색은 로드맵에 남아 있습니다.

> [!NOTE]
> **검증 상태.** 최신 **Stable Diffusion WebUI Forge Neo**에서 전체 흐름의 작동을 확인했습니다. 현재 실제 사용으로 검증된 제공자는 **OpenRouter**뿐입니다. LM Studio도 같은 계약으로 구현됐지만 아직 전체 흐름은 검증되지 않았습니다.
>
> **권장·검증 모델은 `google/gemma-4-31b-it`(Gemma 4 31B)**이며 NSFW 프롬프트도 지원합니다. 다른 모델은 스키마 준수, 품질, 콘텐츠 정책 동작을 보장하지 않습니다.
>
> 이미지 생성 전 **생성된 프롬프트를 검토하고 편집**하십시오. 모든 LLM 제안은 최종본이 아닌 초안입니다. SDXL 프롬프팅이 처음이라면 [이 영상](https://www.youtube.com/watch?v=QdRP9pO89MY)과 [CivitAI](https://civitai.com)의 모델별 예시를 참고하십시오.

## 빠른 시작

1. [github.com/mikhailfur/sd-webui-ai-wdywfm/releases/latest](https://github.com/mikhailfur/sd-webui-ai-wdywfm/releases/latest)에서 최신 릴리스 zip 압축 파일을 다운로드합니다.
2. 압축을 Forge Neo의 `extensions/` 디렉터리에 풉니다. 확장 프로그램 자체 폴더(예: `sd-webui-ai-wdywfm`)가 `extensions/` 바로 아래에 오도록 하고, 한 단계 더 깊은 폴더 안에 들어가지 않도록 주의합니다.
3. Forge Neo를 다시 시작합니다(WebUI 프로세스를 완전히 종료한 뒤 다시 실행해야 합니다. 브라우저 탭 새로고침만으로는 충분하지 않습니다).
4. `txt2img` 또는 `img2img`에서 `LLM Prompt Helper · AI WDYWFM`을 엽니다.
5. LM Studio를 `http://127.0.0.1:1234/v1`에서 시작하거나 OpenRouter와 세션 전용 키를 선택합니다(`OPENROUTER_API_KEY` 환경 변수도 지원).
6. 모델을 새로고침/선택하고 결과를 설명한 뒤 `Generate verified draft`를 클릭합니다.
7. 미리보기와 읽기 전용 권장사항을 확인하고 `Apply prompts`를 클릭합니다.

WebUI를 다시 불러오면 제공자, URL, 모델, OpenRouter 키가 자동 복원됩니다. Windows에서는 저장 키를 현재 사용자용 DPAPI로 암호화합니다. 시간 제한, 이미지 크기, 컨텍스트 제한은 `Settings → AI WDYWFM`에서 설정합니다.

모든 제공자 작업에는 요청 ID가 있으며 정제된 순환 로그 `logs/ai-wdywfm.log`에 기록됩니다. 패널의 `Diagnostics · sanitized log`에서 최근 이벤트를 확인할 수 있습니다. API 키, 프롬프트, 이미지는 기록하지 않습니다.

Gemma 4 계열 OpenRouter 모델은 탈옥, 사용자 지정 턴 마커, 추론 요청이 없는 빠른 구조화 출력 프로필을 사용합니다. 출력은 3072토큰, Generate당 완성 요청은 한 번으로 제한되며 구조화 JSON에 Response Healing을 사용합니다.

Forge는 safetensors 헤더를 캐시합니다. LoRA 사이드카 JSON도 파일 크기/수정 시간 기준으로 메모리 캐시되며, 관련성 높은 상세 카드 8개만 전송하고 전체 압축 ID 허용 목록은 검증용으로 유지합니다.

## 개요

`ai-wdywfm`은 **Stable Diffusion WebUI Forge Neo** 전용 프롬프트 도우미입니다. 초보자는 문법을 먼저 배우지 않고 원하는 것을 설명할 수 있고, 숙련자는 모델을 고려한 초안을 빠르게 만들 수 있습니다.

다음 정보를 결합합니다.

- 자연어 요청
- 선택적 참조 이미지와 편집 지시
- 활성 `txt2img`/`img2img` 컨텍스트
- 설치된 체크포인트와 LoRA
- 로컬 메타데이터, 트리거 단어, 사용 가능한 CivitAI 설명
- 버전 지정 시스템 프롬프트와 엄격한 JSON Schema
- OpenRouter 또는 로컬 LM Studio

### 절대 규칙

LLM 응답 후 확장 프로그램이 변경할 수 있는 것은 **Prompt**와 **Negative Prompt**뿐입니다. `CFG Scale`, 크기, 샘플러, 스케줄러, 단계, 디노이즈 강도 등은 **읽기 전용 권장사항**이며 Forge 컨트롤에 출력으로 연결되지 않습니다.

체크포인트는 자동 전환하지 않습니다. LoRA는 ID와 별칭이 로컬 Forge Neo 레지스트리에서 검증된 경우에만 `<lora:name:weight>`로 추가할 수 있습니다.

## 대상 사용자

| 사용자 | 제공 기능 |
|---|---|
| **초보자** | 일반 설명을 사용 가능한 긍정/부정 프롬프트로 변환합니다. |
| **숙련 사용자** | 유효한 로컬 LoRA, 트리거 단어, 호환성 경고가 포함된 초안을 만듭니다. |
| **오프라인 우선 사용자** | 클라우드 LLM 없이 LM Studio와 캐시/로컬 메타데이터로 작동합니다. |
| **대규모 수집가** | 모든 설명을 보내지 않고 제한되고 순위화된 컨텍스트를 구성합니다. |

## 작동 방식

### 텍스트 → 프롬프트

```text
자연어 아이디어
  ↓
Forge Neo 체크포인트 + LoRA 인벤토리
  ↓
로컬 사이드카 / safetensors / CivitAI 캐시
  ↓
관련 모델 순위화 및 제한된 컨텍스트
  ↓
OpenRouter 또는 LM Studio + 엄격한 JSON Schema
  ↓
검증된 미리보기 → 명시적인 “Apply prompts”
  ↓
Prompt + Negative Prompt만 적용
```

1. `txt2img` 또는 `img2img`에서 `AI WDYWFM`을 엽니다.
2. 원하는 이미지를 일상 언어로 설명합니다.
3. 현재 체크포인트, 프롬프트의 LoRA, 관련 설치 모델을 감지합니다.
4. 누락 메타데이터를 선택적으로 CivitAI에서 보강합니다.
5. LLM의 구조화 제안을 스키마와 실시간 Forge 레지스트리에 맞춰 검증합니다.
6. 프롬프트, 권장사항, 모델, 경고를 검토하고 `Apply prompts`를 누릅니다.

### 이미지 + 지시 → 프롬프트

도우미 패널에 이미지를 첨부하고 변경·유지·제거·스타일 변경 내용을 설명합니다. 정제되고 크기가 조절된 사본을 비전 모델이 로컬 모델 컨텍스트와 함께 분석하며, 같은 검증과 명시적 적용 흐름을 사용합니다. 자체 이미지 입력 덕분에 `txt2img`와 `img2img` 모두에서 작동합니다.

## 인터페이스

`AI WDYWFM` 패널은 두 생성 탭에서 독립적으로 렌더링되는 `AlwaysVisible` Forge 스크립트입니다.

| 컨트롤 | 용도 |
|---|---|
| Natural request | 원하는 결과 또는 편집 설명 |
| Reference image | 비전 LLM용 선택적 입력 |
| Create / Edit | 요청 의도 선택 |
| Prompt dialect | `Auto`, `Booru tags`, `Natural language` |
| Provider / model | LM Studio/OpenRouter 및 모델 선택 |
| Model context preview | 포함될 로컬 메타데이터 확인 |
| Generate suggestion | 명시적 LLM 요청 시작 |
| Prompt preview | 적용 전 두 프롬프트 검토 |
| Recommendations | CFG, 크기, 샘플러, 스케줄러, 단계의 읽기 전용 값 |
| Apply prompts | 활성 탭의 프롬프트 필드만 교체 또는 추가 |

`Apply prompts` 전에는 기존 프롬프트를 덮어쓰지 않습니다. 예정 기본값은 `Replace with preview`이며 `Append`도 명시적으로 선택할 수 있습니다.

## Forge Neo 호환성

대상은 [Stable Diffusion WebUI Forge — Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo)의 `neo` 브랜치, Gradio `4.40.0`, `modules.scripts`, `modules.script_callbacks`, `modules.shared`, 내장 `extensions-builtin/sd_forge_lora`입니다.

| 탭 | 긍정 프롬프트 | 부정 프롬프트 |
|---|---|---|
| txt2img | `txt2img_prompt` | `txt2img_neg_prompt` |
| img2img | `img2img_prompt` | `img2img_neg_prompt` |

Forge 코어 파일은 패치하지 않습니다. Forge Classic, AUTOMATIC1111, reForge 등은 호환성 보장 범위 밖입니다.

## 모델 인식 CivitAI 통합

CivitAI 지원은 내부 구현이며 **CivitAI Browser Neo는 런타임 의존성이 아닙니다**. 소스는 캐시 우선으로 확인합니다.

1. `<model>.api_info.json`
2. `<model>.json`
3. `.safetensors` `__metadata__`
4. SQLite 캐시
5. `GET /api/v1/model-versions/by-hash/{sha256}`
6. `GET /api/v1/model-versions/{versionId}`
7. `GET /api/v1/models/{modelId}`

모델 ID·유형·기본 계열·해시·CivitAI ID·트리거 단어·설명·예시 프롬프트·필드별 출처를 정규화합니다. 대형 체크포인트는 지연 해시하고, 전체 로컬 인벤토리를 유지하면서 관련성 높은 호환 모델만 컨텍스트 예산 안에서 전송합니다.

## LLM 제공자

### LM Studio — 로컬 우선 기본값

- 기본 URL `http://127.0.0.1:1234/v1`
- OpenAI 호환 `/models`, `/chat/completions`
- 동일 JSON Schema의 Structured Output
- 지원 모델의 비전 입력
- 캐시된 CivitAI 메타데이터로 완전 로컬 작동

### OpenRouter

- `https://openrouter.ai/api/v1/chat/completions`
- 텍스트 및 멀티모달 모델
- 호환 모델의 엄격한 Structured Outputs
- 요청 전 기능 필터링
- 권장 비밀 정보 소스: `OPENROUTER_API_KEY`

두 어댑터는 동일한 제공자 중립 객체를 만듭니다. 유효하지 않거나 불완전한 응답은 적용하지 않습니다.

## 구조화 응답 계약

표준 스키마는 [prompt_suggestion.v1.json](../schemas/prompt_suggestion.v1.json)입니다.

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

Forge에는 `prompt`와 `negative_prompt`만 적용합니다. 모델 ID, LoRA 가중치, 샘플러, 스케줄러, 값 범위는 실시간 Neo 레지스트리로 추가 검증합니다. 전체 내용은 [LLM 프로토콜](LLM_PROTOCOL.md)을 참조하십시오.

## 아키텍처

```text
Forge Neo UI
  ↓
애플리케이션 유스케이스
  ↓
도메인 모델 및 정책
  ├── Forge Neo 인벤토리 어댑터
  ├── 사이드카 / safetensors 리더
  ├── CivitAI 메타데이터 어댑터
  ├── OpenRouter / LM Studio 어댑터
  └── SQLite 캐시
```

프로젝트의 주요 디렉터리는 `scripts/`, `ai_wdywfm/application/`, `domain/`, `infrastructure/`, `prompts/`, `ui/`, `schemas/`, `tests/`, `docs/`입니다. 전체 [아키텍처 문서](ARCHITECTURE.md)를 참조하십시오.

## 개인정보 보호 및 보안

> [!NOTE]
> 요청은 자동 전송되지 않습니다. 네트워크 접근은 명시적 사용자 동작 후에만 시작됩니다.

- API 키는 LLM 페이로드, 캐시, 로그에서 제외합니다.
- 절대 로컬 경로는 전송하지 않습니다.
- CivitAI 메타데이터는 지시가 아닌 신뢰할 수 없는 데이터로 취급합니다.
- 클라우드 이미지 업로드에는 명시적 동의가 필요합니다.
- 참조 이미지는 검증, 크기 조절, 메타데이터 제거, 재인코딩합니다.
- 알 수 없는 모델·LoRA·임베딩·샘플러·스케줄러는 거부합니다.
- 생성 시작, 모델 다운로드, LLM 출력 실행을 하지 않습니다.
- 프롬프트, 이미지, 비밀 정보, 전체 제공자 응답은 기본 로그에서 제외합니다.

## MVP 설정

| 설정 | 기본값 | 용도 |
|---|---:|---|
| Provider | `LM Studio` | 로컬 우선 기본값 |
| LM Studio base URL | `http://127.0.0.1:1234/v1` | 로컬 서버 |
| OpenRouter model | 비어 있음 | 명시적 선택 필요 |
| CivitAI enrichment | 켬 | 누락 메타데이터 가져오기 |
| CivitAI domain | `civitai.com` | `civitai.red` 선택 가능 |
| Detailed model cards | `12` | 요청당 최대 카드 |
| Context budget | `12,000 tokens` | 소프트 제한 |
| LLM timeout | `120 seconds` | 요청 제한 시간 |
| Image maximum side | `1,536 px` | 비전 입력 크기 제한 |
| Cloud image input | 끔 | OpenRouter 이미지 추가 동의 |
| Debug logging | 끔 | 콘텐츠와 비밀 정보 제외 |

## MVP 승인 기준

- [ ] 코어 패치 없이 시작
- [ ] `txt2img`/`img2img`에서 독립 작동
- [ ] Neo 레지스트리에서 체크포인트와 LoRA 검색
- [ ] 로컬 사이드카 정규화
- [ ] 캐시 우선 SHA-256 CivitAI 조회
- [ ] 두 제공자가 같은 도메인 객체 반환
- [ ] 텍스트·비전 전체 흐름 통과
- [ ] `Apply prompts`가 활성 탭의 두 필드만 변경
- [ ] 권장사항이 생성 설정을 변경하지 않음
- [ ] 유효하지 않은 출력 적용 불가

## 문서

- [아키텍처](ARCHITECTURE.md)
- [LLM 프로토콜](LLM_PROTOCOL.md)
- [로드맵](ROADMAP.md)
- [프롬프트 예시](promptexmaple.md)
- `docs/LoRA json exmples/` — 로컬 메타데이터 픽스처
- `docs/sd-civitai-browser-neo-main/` — Forge Neo CivitAI 참조

외부 참조: [Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo), [OpenRouter Structured Outputs](https://openrouter.ai/docs/guides/features/structured-outputs), [OpenRouter Image Inputs](https://openrouter.ai/docs/guides/overview/multimodal/image-understanding), [LM Studio OpenAI compatibility](https://lmstudio.ai/docs/developer/openai-compat), [LM Studio Structured Output](https://lmstudio.ai/docs/developer/openai-compat/structured-output), [CivitAI REST API](https://github.com/civitai/civitai/wiki/REST-API-Reference).

## 첫 릴리스 범위 밖

자동 이미지 생성, 체크포인트 전환, 생성 매개변수 변경, 권장 모델 다운로드, LoRA 학습, 프롬프트 기록 클라우드 동기화, 에이전트식 명령 실행은 포함하지 않습니다. 첫 릴리스는 자율 WebUI 운영자가 아니라 예측 가능한 프롬프트 도우미입니다.

## 프로젝트 후원

| 자산 / 네트워크 | 주소 |
|---|---|
| **USDT (TRC-20)** | `TJWZfYHvis7B1uzxhCeenvtzaAFNipzjhz` |
| **LTC** | `LgRVpM8DRrae4ZKeFen39Z5FNXcQfeZtWL` |
| **ETH** | `0x60d1ab93862336241aa77fdf9c7e32e9f9ddf688` |

> [!CAUTION]
> 보내기 전에 주소와 네트워크를 확인하십시오. 암호화폐 거래는 되돌릴 수 없습니다.

---

<div align="center">

**Stable Diffusion WebUI Forge Neo**용으로 제작되었습니다.

[맨 위로](#ai-wdywfm)

</div>
