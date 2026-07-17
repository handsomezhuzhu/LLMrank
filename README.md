# Simon's LLM Ranking

Multi-dimensional weighted evaluation of large language models.

🔗 **Live Site**: [rank.zhuzihan.com](https://rank.zhuzihan.com) · [GitHub Pages](https://handsomezhuzhu.github.io/LLMrank/)

## Data model (canonical)

**Single source of truth: [`data/models.json`](data/models.json)**

Scores are **not** hand-maintained. Python (`update_rankings.py`) and the site (`index.html`) both compute Formula v4 from this file.

### Schema (per model)

| Field | Meaning |
|-------|---------|
| `arena` | Arena AI rating |
| `ai_index` | Artificial Analysis Intelligence Index |
| `multi` | Multimodal capability tag (50/75/100) |
| `eco` | Eco score (display only; not in v4 total) |
| `ctx` | Context window (tokens) |
| `price.currency` | `USD` or `CNY` |
| `price.input` | $/¥ per **1M input** tokens |
| `price.output` | $/¥ per **1M output** tokens |
| `price.cache_read` | $/¥ per **1M cache-read** tokens |
| `price.cache_write` | $/¥ per **1M cache-write** tokens |
| `openrouter_id` | Optional OpenRouter model id for price refresh |
| `price_source` | `openrouter` \| `manual` |
| `auto_price` | `false` freezes price (manual/official/deprecated); auto OpenRouter refresh skips these |
| `note` | Unused (kept empty for a clean UI) |

**Missing price components use `-1`** (not null). They are ignored when blending the effective price.

`corrected_models.json` is a **derived legacy export** (includes computed `s*` / `total`). Prefer editing `data/models.json` only.

## Formula v4 (July 2026)

Capability-first. Weights sum to **100%**.

| Dimension | Weight | Method |
|-----------|--------|--------|
| **Arena** | 30% | Hybrid: linear abs (1300–1520) 65% + in-list percentile 35% |
| **AI Index** | 35% | Hybrid: linear abs (0–60) 65% + percentile 35% |
| **Price** | 10% | Effective $/1M from 4-part price → log vs $1/M ref; missing/free = 20 |
| **Multimodal** | 15% | Raw multi compressed: 50/75/100 → 70/85/100 |
| **Context** | 10% | Sigmoid centered ~400K |

### Effective price blend

```
input 25% + output 55% + cache_read 10% + cache_write 10%
```

If a component is `-1` / missing, its weight is redistributed among the present ones.  
CNY amounts convert with `CNY_PER_USD = 7.2` before scoring.

## Daily update

```bash
python3 update_rankings.py
```

1. **Arena**: Hugging Face `lmarena-ai/leaderboard-dataset` (text / overall). On failure or incomplete payload → **skip Arena field writes** (no partial overwrite).
2. **AI Index**: trusted remote only. Current default skips writes when no remote refresh is available (local cache is not force-applied).
3. **OpenRouter prices/ctx**: only models with `auto_price=true` and a live `openrouter_id`. Manual / deprecated / missing-id rows are frozen.
4. Recalculate scores from `data/models.json`, export legacy `corrected_models.json`, touch `last_check.txt`, commit/push when there are real diffs.

## Local preview

GitHub Pages serves `index.html`, which **fetch**es `data/models.json`.  
Open via any static server (file:// may block fetch):

```bash
python3 -m http.server 8080 -d /root/LLMrank
```

## License

MIT
