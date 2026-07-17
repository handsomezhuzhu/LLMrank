# Simon's LLM Ranking

Multi-dimensional weighted evaluation of **65 large language models** from major vendors.

🔗 **Live Site**: [rank.zhuzihan.com](https://rank.zhuzihan.com) · [GitHub Pages](https://handsomezhuzhu.github.io/LLMrank/)

## Formula v4 (July 2026)

Capability-first scoring. Weights sum to **100%**.

| Dimension | Weight | Source | Method |
|-----------|--------|--------|--------|
| **Arena** | 30% | [Arena AI](https://arena.ai/leaderboard) | Hybrid: linear abs (1380–1520) 65% + in-list percentile 35% |
| **AI Index** | 35% | [Artificial Analysis](https://artificialanalysis.ai/leaderboards/models) | Hybrid: linear abs (15–60) 65% + percentile 35% |
| **Price** | 10% | LiteLLM + vendor docs | Relative to $1/M output, log compression; missing/free = 20 |
| **Multimodal** | 15% | Official docs | Raw multi compressed: 50/75/100 → 70/85/100 |
| **Context** | 10% | Vendor docs | Sigmoid centered ~400K |

### Why v4 (vs old 25/25/15/15/15)

1. **Old weights only summed to 95%** (bug).
2. **Cheap models were over-rewarded** (cheapest forced to 100 price score → Gemini 3 Flash / DeepSeek Flash ranked above stronger flagships).
3. **Multimodal 100 was a free +15 win** over text-only 50 with little quality signal.
4. **Context 1M sat near the same band** for almost all modern models, adding noise at 15% weight.
5. **Log-normalization compressed top Arena/AI gaps**, making utility dimensions dominate.

v4 raises capability to **65%** (Arena+AI), dampens price free-wins, compresses multi labels, and lowers context weight.

### Data Inclusion Criteria

Only models that appear in **BOTH**:
- **Arena AI** — human preference ratings
- **Artificial Analysis** — Intelligence Index

### Thinking / Non-Thinking Averaging

When a model has multiple AA variants (reasoning / non-reasoning), AI Index scores are **averaged**. Arena uses the base model entry.

## Tech Stack

- Pure HTML + Vue 3 CDN (no build step)
- Daily update script: `update_rankings.py`
- GitHub Actions / Pages deploy
- Custom domain may need CDN purge after push

## Data Sources

- [Arena AI](https://arena.ai/leaderboard)
- [Artificial Analysis](https://artificialanalysis.ai/leaderboards/models)
- [LiteLLM](https://github.com/BerriAI/litellm)
- [HuggingFace](https://huggingface.co/)

## License

MIT
