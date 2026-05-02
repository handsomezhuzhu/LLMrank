# Simon's LLM Ranking

Multi-dimensional weighted evaluation of 33 large language models from 9 vendors.

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

### Scoring Details

- **Arena (20%)**: Bradley-Terry ratings from human blind tests, log-normalized to 0-100
- **AI Index (20%)**: Intelligence Index from 60 diverse prompts, raw scores used (range 5-60)
- **Ecosystem (15%)**: Official AI software products only (CLI, web, desktop, mobile, API, dev tools)
- **Price (15%)**: Output token cost, cheapest=100, diminishing returns via log10
- **Multimodal (15%)**: Model-native capabilities only (not company products): Text=25, Thinking=25, Vision=25, Generation=25
- **Context (10%)**: Sigmoid normalization centered at 256K, diminishing returns above 1M

## Vendors

| Vendor | Ecosystem | Models |
|--------|-----------|--------|
| OpenAI | 96 | GPT-5.5, GPT-5.4, GPT-5.1, GPT-4o |
| Google | 94 | Gemini 3.1 Pro, Gemini 3 Flash, Gemini 2.5 Pro |
| Anthropic | 88 | Claude Opus 4.7/4.6, Sonnet 4.6, Haiku 4.5 |
| Alibaba | 72 | Qwen3.6 Max/Plus, Qwen3.5 Max, Qwen3.5-397B, Qwen3-235B |
| Zhipu AI | 65 | GLM-5.1, GLM-5, GLM-4.7 |
| xAI | 58 | Grok 4.20, Grok 4.3, Grok 4.1 |
| DeepSeek | 45 | DeepSeek V4 Pro/Flash, V3.2, R1 |
| Moonshot | 38 | Kimi K2.6, Kimi K2.5 |
| Xiaomi | 12 | MiMo V2.5 Pro, MiMo V2.5 |

## Tech Stack

- Pure HTML + Vue 3 CDN (no build step)
- Dark theme (#06061a background)
- Responsive design
- GitHub Actions auto-deploy to GitHub Pages

## Data Sources

- [Arena AI](https://arena.ai/leaderboard) — Human preference ratings (628 models)
- [Artificial Analysis](https://artificialanalysis.ai/leaderboards/models) — Intelligence Index (475 models)
- [LiteLLM Database](https://github.com/BerriAI/litellm) — Pricing data
- [HuggingFace](https://huggingface.co/) — Model verification

## License

MIT
