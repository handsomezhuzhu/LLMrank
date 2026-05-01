# Simon's LLM Ranking

Multi-dimension weighted evaluation of Large Language Models.

## Live Demo

🔗 **[zhuzihan.com](https://zhuzihan.com)**

## Ranking Formula

```
Total = Arena(40%) + Ecosystem(15%) + Price(15%) + Multimodal(15%) + Context(10%)
```

## Dimensions

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Arena | 40% | LMSYS Chatbot Arena ELO, human blind test |
| Ecosystem | 15% | Official AI software products |
| Price | 15% | Log-compressed output price |
| Multimodal | 15% | Text + Thinking + Vision + Generation |
| Context | 10% | Max context window size |

## Data Sources

- [LMSYS Arena](https://lmarena.ai/leaderboard) — Human blind test rankings
- [LiveBench](https://livebench.ai/) — Dynamic benchmarks
- [OpenRouter](https://openrouter.ai/) — API pricing
- [HuggingFace](https://huggingface.co/) — Model verification

## License

MIT
