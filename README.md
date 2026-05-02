# Simon's LLM Ranking

Multi-dimensional weighted evaluation of **56 large language models** from **12 vendors**.

🔗 **Live Site**: [handsomezhuzhu.github.io/LLMrank](https://handsomezhuzhu.github.io/LLMrank/)

## Ranking Dimensions

| Dimension | Weight | Source | Method |
|-----------|--------|--------|--------|
| **Arena** | 25% | [Arena AI](https://arena.ai/leaderboard) | Log normalization (1300-1520) |
| **AI Index** | 25% | [Artificial Analysis](https://artificialanalysis.ai/leaderboards/models) | Log normalization (5-60) |
| **Price** | 15% | [LiteLLM](https://github.com/BerriAI/litellm) + vendor docs | Linear base + log10 compression |
| **Multimodal** | 15% | Official docs | Text/Thinking/Vision/Generation (25pts each) |
| **Context** | 15% | Vendor docs | Sigmoid (centered at 256K) |

### Data Inclusion Criteria

Only models that appear in **BOTH** of the following leaderboards are included:
- **Arena AI** (arena.ai) — human preference ratings
- **Artificial Analysis** (artificialanalysis.ai) — Intelligence Index

This ensures every model has both human preference data and automated benchmark data.

### Thinking/Non-Thinking Averaging

When a model has multiple variants (e.g., "Claude Opus 4.7 Reasoning" and "Claude Opus 4.7 Non-reasoning"), their AI Index scores are **averaged** to produce a single score for that model. Arena ratings are taken from the base model entry (single rating per model in Arena).

### Scoring Details

- **Arena (25%)**: Bradley-Terry ratings from human blind tests, log-normalized to 0-100
- **AI Index (25%)**: Intelligence Index from 60 diverse prompts, log-normalized to 0-100
- **Price (15%)**: Output token cost, cheapest=100, diminishing returns via log10. Free/open-source models scored as 0.
- **Multimodal (15%)**: Model-native capabilities only (not company products): Text=25, Thinking=25, Vision=25, Generation=25
- **Context (15%)**: Sigmoid normalization centered at 256K, diminishing returns above 256K

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
