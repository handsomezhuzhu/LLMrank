# Verified Model Data (May 2026)

> **Data Sources:**
> - Arena AI (arena.ai/leaderboard) — Bradley-Terry ratings, scraped May 2, 2026
> - Artificial Analysis (artificialanalysis.ai) — Intelligence Index, scraped May 2, 2026
> - litellm GitHub database — Pricing data
> - Official vendor documentation — Capabilities verification

## Scoring Formula

| Dimension | Weight | Source | Normalization |
|-----------|--------|--------|---------------|
| Arena | 20% | arena.ai | `(rating - 1350) / 200 * 100` |
| AI Index | 20% | artificialanalysis.ai | `(score - 40) / 25 * 100` (below 40 = 0) |
| Ecosystem | 15% | Manual | 0-100 based on official AI products |
| Price | 15% | litellm/vendor docs | `100 / (1 + log10(price/cheapest))`, output $/1M tokens |
| Multimodal | 15% | Official docs | Text=25, Thinking=25, Vision=25, Generation=25 (model-native only) |
| Context | 10% | litellm/vendor docs | `min(100, tokens / 1M * 100)` |

**Cheapest output price:** $0.28/1M tokens (DeepSeek V4 Flash)

---

## Ranked Models

| # | Model | Vendor | Arena | AI Index | Eco | Price $/M | Multi | Context | Total |
|---|-------|--------|-------|----------|-----|-----------|-------|---------|-------|
| 1 | GPT-5.5 High | OpenAI | 1487.6 | 60.24 | 96 | $30.00 | 75 | 1M | 70.6 |
| 2 | Gemini 3.1 Pro | Google | 1492.6 | 57.18 | 94 | $12.00 | 75 | 1M | 69.0 |
| 3 | Claude Opus 4.7 | Anthropic | 1502.7 | 57.28 | 88 | $25.00 | 75 | 976K | 68.6 |
| 4 | GPT-5.4 High | OpenAI | 1476.8 | 56.8 | 96 | $15.00 | 75 | 1M | 67.3 |
| 5 | Gemini 3 Flash | Google | 1473.6 | 46.43 | 94 | $0.40 | 75 | 1M | 65.9 |
| 6 | Claude Opus 4.6 | Anthropic | 1502.0 | 52.95 | 88 | $25.00 | 75 | 976K | 65.1 |
| 7 | Claude Sonnet 4.6 | Anthropic | 1463.2 | 51.72 | 88 | $15.00 | 75 | 976K | 60.7 |
| 8 | Grok 4.3 | xAI | 1455.7 | 53.2 | 58 | $25.00 | 75 | 1M | 56.2 |
| 9 | Grok 4.20 | xAI | 1479.6 | 49.33 | 58 | $25.00 | 75 | 1M | 55.5 |
| 10 | DeepSeek V4 Pro | DeepSeek | 1463.0 | 51.51 | 45 | $0.87 | 50 | 1M | 54.8 |
| 11 | DeepSeek V4 Flash | DeepSeek | 1438.8 | 46.52 | 45 | $0.28 | 50 | 1M | 53.3 |
| 12 | Gemini 2.5 Pro | Google | 1447.7 | 34.63 | 94 | $5.00 | 75 | 1M | 51.7 |
| 13 | MiMo V2.5 | Xiaomi | 1463.3 | 49.03 | 12 | $2.00 | 75 | 1M | 49.7 |
| 14 | GPT-5.1 High | OpenAI | 1454.6 | 47.7 | 96 | $10.00 | 75 | 125K | 49.4 |
| 15 | MiMo V2.5 Pro | Xiaomi | 1463.3 | 53.83 | 12 | $3.00 | 50 | 1M | 49.0 |
| 16 | Grok 4.1 | xAI | 1468.3 | 38.61 | 58 | $5.00 | 75 | 1M | 48.4 |
| 17 | GLM-5.1 | Zhipu AI | 1470.5 | 51.41 | 65 | $3.20 | 50 | 198K | 47.8 |
| 18 | Qwen3.6 Max | Alibaba | 1456.7 | 51.81 | 72 | $6.40 | 50 | 256K | 47.3 |
| 19 | GLM-5 | Zhipu AI | 1470.5 | 49.77 | 65 | $3.20 | 50 | 198K | 46.5 |
| 20 | Qwen3.6 Plus | Alibaba | 1447.3 | 49.98 | 72 | $2.40 | 50 | 256K | 46.4 |
| 21 | Kimi K2.6 | Moonshot | 1460.0 | 53.9 | 38 | $4.00 | 50 | 255K | 44.8 |
| 22 | GPT-4o | OpenAI | 1442.7 | 18.64 | 96 | $10.00 | 75 | 125K | 42.1 |
| 23 | Qwen3.5-397B | Alibaba | 1447.1 | 45.05 | 72 | $3.60 | 50 | 256K | 41.7 |
| 24 | Claude Haiku 4.5 | Anthropic | 1408.1 | 37.09 | 88 | $5.00 | 75 | 195K | 38.9 |
| 25 | Kimi K2.5 | Moonshot | 1449.5 | 46.81 | 38 | $3.00 | 50 | 255K | 38.6 |
| 26 | Qwen3.5 Max | Alibaba | 1463.0 | N/A | 72 | $6.40 | 50 | 256K | 38.5 |
| 27 | GLM-4.7 | Zhipu AI | 1442.5 | 42.11 | 65 | $2.20 | 50 | 198K | 38.2 |
| 28 | DeepSeek V3.2 | DeepSeek | 1424.5 | 41.71 | 45 | $0.40 | 50 | 128K | 37.4 |
| 29 | Qwen3-235B | Alibaba | 1422.4 | 29.54 | 72 | $3.00 | 50 | 128K | 34.2 |
| 30 | DeepSeek R1 | DeepSeek | 1421.9 | 27.07 | 45 | $2.19 | 50 | 128K | 30.7 |

---

## Detailed Model Data

### OpenAI

#### GPT-5.5 High
- **Arena Rating:** 1487.6
- **AI Index:** 60.24
- **Ecosystem Score:** 96
- **Output Price:** $30.00/1M tokens
- **Multimodal:** 75/100 (text+think+vision)
- **Context Window:** 1,050,000 tokens
- **Region:** US

#### GPT-5.4 High
- **Arena Rating:** 1476.8
- **AI Index:** 56.8
- **Ecosystem Score:** 96
- **Output Price:** $15.00/1M tokens
- **Multimodal:** 75/100 (text+think+vision)
- **Context Window:** 1,050,000 tokens
- **Region:** US

#### GPT-5.1 High
- **Arena Rating:** 1454.6
- **AI Index:** 47.7
- **Ecosystem Score:** 96
- **Output Price:** $10.00/1M tokens
- **Multimodal:** 75/100 (text+think+vision)
- **Context Window:** 128,000 tokens
- **Region:** US

#### GPT-4o
- **Arena Rating:** 1442.7
- **AI Index:** 18.64
- **Ecosystem Score:** 96
- **Output Price:** $10.00/1M tokens
- **Multimodal:** 75/100 (text+vision+generation(no think))
- **Context Window:** 128,000 tokens
- **Region:** US

### Google

#### Gemini 3.1 Pro
- **Arena Rating:** 1492.6
- **AI Index:** 57.18
- **Ecosystem Score:** 94
- **Output Price:** $12.00/1M tokens
- **Multimodal:** 75/100 (text+think+vision)
- **Context Window:** 1,048,576 tokens
- **Region:** US

#### Gemini 3 Flash
- **Arena Rating:** 1473.6
- **AI Index:** 46.43
- **Ecosystem Score:** 94
- **Output Price:** $0.40/1M tokens
- **Multimodal:** 75/100 (text+think+vision)
- **Context Window:** 1,048,576 tokens
- **Region:** US

#### Gemini 2.5 Pro
- **Arena Rating:** 1447.7
- **AI Index:** 34.63
- **Ecosystem Score:** 94
- **Output Price:** $5.00/1M tokens
- **Multimodal:** 75/100 (text+think+vision)
- **Context Window:** 1,048,576 tokens
- **Region:** US

### Anthropic

#### Claude Opus 4.7
- **Arena Rating:** 1502.7
- **AI Index:** 57.28
- **Ecosystem Score:** 88
- **Output Price:** $25.00/1M tokens
- **Multimodal:** 75/100 (text+think+vision)
- **Context Window:** 1,000,000 tokens
- **Region:** US

#### Claude Opus 4.6
- **Arena Rating:** 1502.0
- **AI Index:** 52.95
- **Ecosystem Score:** 88
- **Output Price:** $25.00/1M tokens
- **Multimodal:** 75/100 (text+think+vision)
- **Context Window:** 1,000,000 tokens
- **Region:** US

#### Claude Sonnet 4.6
- **Arena Rating:** 1463.2
- **AI Index:** 51.72
- **Ecosystem Score:** 88
- **Output Price:** $15.00/1M tokens
- **Multimodal:** 75/100 (text+think+vision)
- **Context Window:** 1,000,000 tokens
- **Region:** US

#### Claude Haiku 4.5
- **Arena Rating:** 1408.1
- **AI Index:** 37.09
- **Ecosystem Score:** 88
- **Output Price:** $5.00/1M tokens
- **Multimodal:** 75/100 (text+think+vision)
- **Context Window:** 200,000 tokens
- **Region:** US

### xAI

#### Grok 4.3
- **Arena Rating:** 1455.7
- **AI Index:** 53.2
- **Ecosystem Score:** 58
- **Output Price:** $25.00/1M tokens
- **Multimodal:** 75/100 (text+think+vision, newest)
- **Context Window:** 1,048,576 tokens
- **Region:** US

#### Grok 4.20
- **Arena Rating:** 1479.6
- **AI Index:** 49.33
- **Ecosystem Score:** 58
- **Output Price:** $25.00/1M tokens
- **Multimodal:** 75/100 (text+think+vision, 2M ctx)
- **Context Window:** 2,000,000 tokens
- **Region:** US

#### Grok 4.1
- **Arena Rating:** 1468.3
- **AI Index:** 38.61
- **Ecosystem Score:** 58
- **Output Price:** $5.00/1M tokens
- **Multimodal:** 75/100 (text+think+vision, 2M ctx)
- **Context Window:** 2,000,000 tokens
- **Region:** US

### DeepSeek

#### DeepSeek V4 Pro
- **Arena Rating:** 1463.0
- **AI Index:** 51.51
- **Ecosystem Score:** 45
- **Output Price:** $0.87/1M tokens
- **Multimodal:** 50/100 (text+think only, no vision)
- **Context Window:** 1,048,576 tokens
- **Region:** CN

#### DeepSeek V4 Flash
- **Arena Rating:** 1438.8
- **AI Index:** 46.52
- **Ecosystem Score:** 45
- **Output Price:** $0.28/1M tokens
- **Multimodal:** 50/100 (text+think only)
- **Context Window:** 1,048,576 tokens
- **Region:** CN

#### DeepSeek V3.2
- **Arena Rating:** 1424.5
- **AI Index:** 41.71
- **Ecosystem Score:** 45
- **Output Price:** $0.40/1M tokens
- **Multimodal:** 50/100 (text+think only)
- **Context Window:** 131,072 tokens
- **Region:** CN

#### DeepSeek R1
- **Arena Rating:** 1421.9
- **AI Index:** 27.07
- **Ecosystem Score:** 45
- **Output Price:** $2.19/1M tokens
- **Multimodal:** 50/100 (text+reasoning only)
- **Context Window:** 131,072 tokens
- **Region:** CN

### Xiaomi

#### MiMo V2.5
- **Arena Rating:** 1463.3
- **AI Index:** 49.03
- **Ecosystem Score:** 12
- **Output Price:** $2.00/1M tokens
- **Multimodal:** 75/100 (text+think+vision (base=multimodal))
- **Context Window:** 1,048,576 tokens
- **Region:** CN

#### MiMo V2.5 Pro
- **Arena Rating:** 1463.3
- **AI Index:** 53.83
- **Ecosystem Score:** 12
- **Output Price:** $3.00/1M tokens
- **Multimodal:** 50/100 (text+think only (Pro=text-only))
- **Context Window:** 1,048,576 tokens
- **Region:** CN

### Zhipu AI

#### GLM-5.1
- **Arena Rating:** 1470.5
- **AI Index:** 51.41
- **Ecosystem Score:** 65
- **Output Price:** $3.20/1M tokens
- **Multimodal:** 50/100 (text+think only)
- **Context Window:** 202,752 tokens
- **Region:** CN

#### GLM-5
- **Arena Rating:** 1470.5
- **AI Index:** 49.77
- **Ecosystem Score:** 65
- **Output Price:** $3.20/1M tokens
- **Multimodal:** 50/100 (text+think only)
- **Context Window:** 202,752 tokens
- **Region:** CN

#### GLM-4.7
- **Arena Rating:** 1442.5
- **AI Index:** 42.11
- **Ecosystem Score:** 65
- **Output Price:** $2.20/1M tokens
- **Multimodal:** 50/100 (text+think only)
- **Context Window:** 202,752 tokens
- **Region:** CN

### Alibaba

#### Qwen3.6 Max
- **Arena Rating:** 1456.7
- **AI Index:** 51.81
- **Ecosystem Score:** 72
- **Output Price:** $6.40/1M tokens
- **Multimodal:** 50/100 (text+think only)
- **Context Window:** 262,144 tokens
- **Region:** CN

#### Qwen3.6 Plus
- **Arena Rating:** 1447.3
- **AI Index:** 49.98
- **Ecosystem Score:** 72
- **Output Price:** $2.40/1M tokens
- **Multimodal:** 50/100 (text+think only)
- **Context Window:** 262,144 tokens
- **Region:** CN

#### Qwen3.5-397B
- **Arena Rating:** 1447.1
- **AI Index:** 45.05
- **Ecosystem Score:** 72
- **Output Price:** $3.60/1M tokens
- **Multimodal:** 50/100 (open source, text+think)
- **Context Window:** 262,144 tokens
- **Region:** CN

#### Qwen3.5 Max
- **Arena Rating:** 1463.0
- **AI Index:** 0
- **Ecosystem Score:** 72
- **Output Price:** $6.40/1M tokens
- **Multimodal:** 50/100 (text+think, no AA score yet)
- **Context Window:** 262,144 tokens
- **Region:** CN

#### Qwen3-235B
- **Arena Rating:** 1422.4
- **AI Index:** 29.54
- **Ecosystem Score:** 72
- **Output Price:** $3.00/1M tokens
- **Multimodal:** 50/100 (open source, text+think)
- **Context Window:** 131,072 tokens
- **Region:** CN

### Moonshot

#### Kimi K2.6
- **Arena Rating:** 1460.0
- **AI Index:** 53.9
- **Ecosystem Score:** 38
- **Output Price:** $4.00/1M tokens
- **Multimodal:** 50/100 (text+think only)
- **Context Window:** 262,142 tokens
- **Region:** CN

#### Kimi K2.5
- **Arena Rating:** 1449.5
- **AI Index:** 46.81
- **Ecosystem Score:** 38
- **Output Price:** $3.00/1M tokens
- **Multimodal:** 50/100 (text+think only)
- **Context Window:** 262,142 tokens
- **Region:** CN

---

## Multimodal Capabilities Detail

| Model | Text | Thinking | Vision | Generation | Total |
|-------|------|----------|--------|------------|-------|
| GPT-5.5 High | ✅ | ✅ | ✅ | ❌ | 75 |
| Gemini 3.1 Pro | ✅ | ✅ | ✅ | ❌ | 75 |
| Claude Opus 4.7 | ✅ | ✅ | ✅ | ❌ | 75 |
| GPT-5.4 High | ✅ | ✅ | ✅ | ❌ | 75 |
| Gemini 3 Flash | ✅ | ✅ | ✅ | ❌ | 75 |
| Claude Opus 4.6 | ✅ | ✅ | ✅ | ❌ | 75 |
| Claude Sonnet 4.6 | ✅ | ✅ | ✅ | ❌ | 75 |
| Grok 4.3 | ✅ | ✅ | ✅ | ❌ | 75 |
| Grok 4.20 | ✅ | ✅ | ✅ | ❌ | 75 |
| DeepSeek V4 Pro | ✅ | ✅ | ❌ | ❌ | 50 |
| DeepSeek V4 Flash | ✅ | ✅ | ❌ | ❌ | 50 |
| Gemini 2.5 Pro | ✅ | ✅ | ✅ | ❌ | 75 |
| MiMo V2.5 | ✅ | ✅ | ✅ | ❌ | 75 |
| GPT-5.1 High | ✅ | ✅ | ✅ | ❌ | 75 |
| MiMo V2.5 Pro | ✅ | ✅ | ❌ | ❌ | 50 |
| Grok 4.1 | ✅ | ✅ | ✅ | ❌ | 75 |
| GLM-5.1 | ✅ | ✅ | ❌ | ❌ | 50 |
| Qwen3.6 Max | ✅ | ✅ | ❌ | ❌ | 50 |
| GLM-5 | ✅ | ✅ | ❌ | ❌ | 50 |
| Qwen3.6 Plus | ✅ | ✅ | ❌ | ❌ | 50 |
| Kimi K2.6 | ✅ | ✅ | ❌ | ❌ | 50 |
| GPT-4o | ✅ | ✅ | ✅ | ❌ | 75 |
| Qwen3.5-397B | ✅ | ✅ | ❌ | ❌ | 50 |
| Claude Haiku 4.5 | ✅ | ✅ | ✅ | ❌ | 75 |
| Kimi K2.5 | ✅ | ✅ | ❌ | ❌ | 50 |
| Qwen3.5 Max | ✅ | ✅ | ❌ | ❌ | 50 |
| GLM-4.7 | ✅ | ✅ | ❌ | ❌ | 50 |
| DeepSeek V3.2 | ✅ | ✅ | ❌ | ❌ | 50 |
| Qwen3-235B | ✅ | ✅ | ❌ | ❌ | 50 |
| DeepSeek R1 | ✅ | ✅ | ❌ | ❌ | 50 |

---

## Ecosystem Scores Detail

| Company | Score | Key Products |
|---------|-------|-------------|
| OpenAI | 96 | ChatGPT (web/mobile/desktop), Codex, DALL·E, Sora, API, SDKs, GPT Store, Voice |
| Google | 94 | Gemini (web/mobile), AI Studio, Workspace, Imagen, Veo, API |
| Anthropic | 88 | Claude (web/mobile/desktop), Claude Code CLI, MCP, API, SDKs |
| Alibaba | 72 | Tongyi (通义千问), Lingma coding, Wanxiang image, Tingwu meetings, API |
| Zhipu AI | 65 | ChatGLM, CodeGeeX, CogView/CogVideo, API |
| xAI | 58 | Grok (web/mobile), X integration, API, image gen, voice |
| DeepSeek | 45 | DeepSeek Chat, API, mobile apps, open-source models |
| Moonshot | 38 | Kimi (web/mobile), API, long-context search |
| Xiaomi | 12 | MiMo model (open-source only, no product ecosystem) |

---

## Pricing Source Detail

| Model | Input $/M | Output $/M | Source |
|-------|-----------|------------|--------|
| Gemini 3.1 Pro | $2.00 | $12.00 | Google AI pricing |
| Gemini 3 Flash | $0.30 | $0.40 | Google AI pricing |
| Gemini 2.5 Pro | $1.25 | $5.00 | litellm / Google |
| GPT-5.5 | $5.00 | $30.00 | OpenAI pricing |
| GPT-5.4 | $2.50 | $15.00 | OpenAI pricing |
| GPT-5.1 | $1.25 | $10.00 | OpenAI pricing |
| GPT-4o | $2.50 | $10.00 | OpenAI pricing |
| Claude Opus 4.7 | $5.00 | $25.00 | Anthropic pricing |
| Claude Opus 4.6 | $5.00 | $25.00 | Anthropic pricing |
| Claude Sonnet 4.6 | $3.00 | $15.00 | Anthropic pricing |
| Claude Haiku 4.5 | $1.00 | $5.00 | Anthropic pricing |
| Grok 4.20 | $12.50 | $25.00 | xAI pricing |
| Grok 4.3 | $12.50 | $25.00 | xAI pricing |
| Grok 4.1 | $2.00 | $5.00 | xAI pricing |
| DeepSeek V4 Pro | $0.435* | $0.87* | DeepSeek (75% discount til 5/31) |
| DeepSeek V4 Flash | $0.14 | $0.28 | DeepSeek pricing |
| DeepSeek V3.2 | $0.28 | $0.40 | litellm / DeepSeek |
| DeepSeek R1 | $0.55 | $2.19 | litellm / DeepSeek |
| Qwen3.5 Max | $1.60 | $6.40 | litellm (qwen-max) |
| Qwen3.6 Max | $1.60 | $6.40 | litellm (qwen-max) |
| Qwen3.6 Plus | $0.40 | $2.40 | litellm (qwen-plus) |
| Qwen3.5-397B | $0.60 | $3.60 | litellm |
| Qwen3-235B | $0.60 | $3.00 | litellm |
| GLM-5.1 | $1.00 | $3.20 | litellm / Zhipu |
| GLM-5 | $1.00 | $3.20 | litellm / Zhipu |
| GLM-4.7 | $0.60 | $2.20 | litellm / Zhipu |
| Kimi K2.6 | $0.95 | $4.00 | litellm / Moonshot |
| Kimi K2.5 | $0.60 | $3.00 | litellm / Moonshot |
| MiMo V2.5 Pro | $1.00 | $3.00 | litellm / OpenRouter |
| MiMo V2.5 | $0.50 | $2.00 | litellm / OpenRouter |
