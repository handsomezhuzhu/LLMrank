# Simon's LLM Ranking

Multi-dimensional weighted evaluation of **59 large language models** from **13 vendors**.

🔗 **Live Site**: [handsomezhuzhu.github.io/LLMrank](https://handsomezhuzhu.github.io/LLMrank/)

## Ranking Dimensions

| Dimension | Weight | Source | Method |
|-----------|--------|--------|--------|
| **Arena** | 20% | [Arena AI](https://arena.ai/leaderboard) | Log normalization (1300-1520) |
| **AI Index** | 20% | [Artificial Analysis](https://artificialanalysis.ai/leaderboards/models) | Log normalization (5-60) |
| **Ecosystem** | 15% | Official AI products | Manual 0-100 |
| **Price** | 15% | [LiteLLM](https://github.com/BerriAI/litellm) + vendor docs | Linear base + log10 compression |
| **Multimodal** | 15% | Official docs | Text/Thinking/Vision/Generation (25pts each) |
| **Context** | 10% | Vendor docs | Sigmoid (centered at 256K) |

### Data Inclusion Criteria

Only models that appear in **BOTH** of the following leaderboards are included:
- **Arena AI** (arena.ai) — human preference ratings
- **Artificial Analysis** (artificialanalysis.ai) — Intelligence Index

This ensures every model has both human preference data and automated benchmark data.

### Thinking/Non-Thinking Averaging

When a model has multiple variants (e.g., "Claude Opus 4.7 Reasoning" and "Claude Opus 4.7 Non-reasoning"), their AI Index scores are **averaged** to produce a single score for that model. Arena ratings are taken from the base model entry (single rating per model in Arena).

### Scoring Details

- **Arena (20%)**: Bradley-Terry ratings from human blind tests, log-normalized to 0-100
- **AI Index (20%)**: Intelligence Index from 60 diverse prompts, log-normalized to 0-100
- **Ecosystem (15%)**: Official AI software products only (CLI, web, desktop, mobile, API, dev tools)
- **Price (15%)**: Output token cost, cheapest=100, diminishing returns via log10. Free/open-source models scored as 0.
- **Multimodal (15%)**: Model-native capabilities only (not company products): Text=25, Thinking=25, Vision=25, Generation=25
- **Context (10%)**: Sigmoid normalization centered at 256K, diminishing returns above 256K

## Vendors

| Vendor | Ecosystem | Models |
|--------|-----------|--------|
| OpenAI | 96 | GPT-5.5 High, GPT-5.5, GPT-5.4 High, GPT-5.4, GPT-5.2, GPT-5.1 High, GPT-5, GPT-5 mini, GPT-4.1, GPT-4o, o3, o1 |
| Google | 94 | Gemini 3.1 Pro, Gemini 3 Flash, Gemini 3 Pro, Gemini 2.5 Pro, Gemini 2.5 Flash, Gemma 4 31B |
| Anthropic | 88 | Claude Opus 4.7, Claude Opus 4.6, Claude Sonnet 4.6, Claude Haiku 4.5 |
| Meta | 80 | Muse Spark |
| Alibaba | 72 | Qwen3.6 Max/Plus, Qwen3.5 Max, Qwen3.5-397B/122B/27B/35B, Qwen3 Max, Qwen3-235B |
| Mistral | 60 | Mistral Large 3 |
| Zhipu AI | 65 | GLM-5.1, GLM-5, GLM-4.7, GLM-4.6, GLM-4.5 |
| xAI | 58 | Grok 4.20, Grok 4.3, Grok 4.1, Grok 4 Fast, Grok 3 |
| MiniMax | 55 | MiniMax M2.7, MiniMax M2.5 |
| DeepSeek | 45 | DeepSeek V4 Pro/Flash, V3.2, V3.1, V3, R1 |
| StepFun | 40 | Step 3.5 Flash |
| Moonshot | 38 | Kimi K2.6, Kimi K2.5, Kimi K2 Thinking, Kimi K2 |
| Xiaomi | 12 | MiMo V2.5 Pro, MiMo V2.5, MiMo V2 Pro |

## Tech Stack

- Pure HTML + Vue 3 CDN (no build step)
- Dark theme (#06061a background)
- Responsive design
- GitHub Actions auto-deploy to GitHub Pages

## Data Sources

- [Arena AI](https://arena.ai/leaderboard) — Human preference ratings (628 models across 10 leaderboards)
- [Artificial Analysis](https://artificialanalysis.ai/leaderboards/models) — Intelligence Index (475 models)
- [LiteLLM Database](https://github.com/BerriAI/litellm) — Pricing data
- [HuggingFace](https://huggingface.co/) — Model verification

## License

MIT
