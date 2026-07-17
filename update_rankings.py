#!/usr/bin/env python3
"""
LLM Ranking Daily Update Script
================================
Single source of truth: data/models.json

Each model stores:
  - arena, ai_index (leaderboard scores)
  - multi, eco, ctx (capability / context)
  - price.{currency,input,output,cache_read,cache_write}  ($ or ¥ per 1M tokens; missing=-1)

This script:
1. Optionally scrapes Arena / Artificial Analysis (best-effort)
2. Optionally refreshes price/ctx from OpenRouter for mapped models
3. Recalculates Formula v4 scores purely from models.json
4. Writes derived views (corrected_models.json for legacy) and updates index.html subheader
5. Git commit + push

index.html loads data/models.json at runtime and scores client-side with the same formulas.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import urllib.request
from datetime import datetime, timezone
from typing import Any

REPO = os.path.dirname(os.path.abspath(__file__))
MODELS_JSON = os.path.join(REPO, "data", "models.json")
LEGACY_JSON = os.path.join(REPO, "corrected_models.json")
INDEX_HTML = os.path.join(REPO, "index.html")
ARENA_JSON = os.path.join(REPO, "data", "arena_leaderboard_full.json")
AA_JSON = os.path.join(REPO, "data", "aa_intelligence_index.json")

# USD per CNY for price scoring when currency == CNY
CNY_PER_USD = 7.2

# ── Formula v4 ──────────────────────────────────────────────────────────────
# Arena 30% + AI Index 35% + Price 10% + Multimodal 15% + Context 10%


def lin_norm(v: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 0.0
    return max(0.0, min(100.0, (v - lo) / (hi - lo) * 100.0))


def percentile_scores(vals: list[float]) -> list[float]:
    n = len(vals)
    order = sorted(range(n), key=lambda i: vals[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    if n == 1:
        return [50.0]
    return [r / (n - 1) * 100.0 for r in ranks]


def hybrid(abs_score: float, perc_score: float, w_abs: float = 0.65) -> float:
    return abs_score * w_abs + perc_score * (1.0 - w_abs)


def to_usd(amount: float, currency: str) -> float:
    c = (currency or "USD").upper()
    if c in ("USD", "US$"):
        return amount
    if c in ("CNY", "RMB", "¥", "元"):
        return amount / CNY_PER_USD
    return amount


def price_component(price: dict[str, Any], key: str) -> float | None:
    """Return USD/1M for a component, or None if missing (-1 / null)."""
    if not price:
        return None
    raw = price.get(key, -1)
    if raw is None or raw < 0:
        return None
    return to_usd(float(raw), str(price.get("currency", "USD")))


def effective_price_usd(price: dict[str, Any] | None) -> float | None:
    """
    Blend input/output/cache into one effective $/1M for scoring.

    Default weights when all present:
      input 25% + output 55% + cache_read 10% + cache_write 10%

    Missing components (sentinel -1) redistribute their weight among available ones.
    If only output is known, use output. If nothing known, return None.
    """
    if not price:
        return None
    weights = {
        "input": 0.25,
        "output": 0.55,
        "cache_read": 0.10,
        "cache_write": 0.10,
    }
    parts: dict[str, float] = {}
    for k in weights:
        v = price_component(price, k)
        if v is not None:
            parts[k] = v
    if not parts:
        return None
    wsum = sum(weights[k] for k in parts)
    return sum(parts[k] * (weights[k] / wsum) for k in parts)


def score_price_from_effective(eff: float | None, p_ref: float = 1.0) -> int:
    """Relative to $1/M effective. Missing/free -> low neutral 20 (not free=100)."""
    if eff is None or eff <= 0:
        return 20
    multiple = max(eff / p_ref, 0.05)
    return int(round(max(5, min(100, 100 / (1 + math.log10(multiple * 4))))))


def score_ctx(ctx: float) -> int:
    if not ctx or ctx <= 0:
        return 0
    return int(round(100 / (1 + math.exp(-1.1 * (math.log10(ctx) - math.log10(400000))))))


def score_multi(multi: float) -> int:
    return int(round(40 + (multi or 0) * 0.6))


def total_score(s_arena: float, s_ai: float, s_price: float, s_multi: float, s_ctx: float) -> float:
    return round(s_arena * 0.30 + s_ai * 0.35 + s_price * 0.10 + s_multi * 0.15 + s_ctx * 0.10, 1)


# ── Scraping (best-effort) ──────────────────────────────────────────────────


def try_scrape_arena():
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            api_data = []

            def handle_response(response):
                try:
                    if response.status == 200:
                        ct = response.headers.get("content-type", "")
                        body = response.text()
                        if ("json" in ct) and len(body) > 500 and '"rating"' in body:
                            api_data.append(body)
                except Exception:
                    pass

            page.on("response", handle_response)
            page.goto("https://arena.ai/leaderboard", timeout=30000, wait_until="commit")
            page.wait_for_timeout(20000)
            browser.close()
            for body in api_data:
                try:
                    data = json.loads(body)
                    if isinstance(data, list) and len(data) > 10 and "rating" in data[0]:
                        return data
                except Exception:
                    pass
    except Exception as e:
        print(f"  Arena scrape failed: {e}")
    return None


def try_scrape_aa():
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            api_data = []

            def handle_response(response):
                try:
                    if response.status == 200:
                        ct = response.headers.get("content-type", "")
                        body = response.text()
                        if ("json" in ct) and len(body) > 500 and "intelligence_index" in body:
                            api_data.append(body)
                except Exception:
                    pass

            page.on("response", handle_response)
            page.goto(
                "https://artificialanalysis.ai/leaderboards/models",
                timeout=30000,
                wait_until="commit",
            )
            page.wait_for_timeout(20000)
            browser.close()
            for body in api_data:
                try:
                    data = json.loads(body)
                    if isinstance(data, list) and len(data) > 10:
                        return data
                    if isinstance(data, dict):
                        for v in data.values():
                            if isinstance(v, list) and len(v) > 10:
                                return v
                except Exception:
                    pass
    except Exception as e:
        print(f"  AA scrape failed: {e}")
    return None


def fetch_openrouter_models(api_key: str | None = None) -> list[dict]:
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request("https://openrouter.ai/api/v1/models", headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    return data.get("data", data)


def to_per_m(v) -> float | None:
    if v is None:
        return None
    try:
        return round(float(v) * 1_000_000, 6)
    except Exception:
        return None


def openrouter_price_map(or_models: list[dict]) -> dict[str, dict]:
    out = {}
    for m in or_models:
        p = m.get("pricing") or {}
        mid = m.get("id")
        if not mid:
            continue
        out[mid] = {
            "ctx": int(m.get("context_length") or 0),
            "input": to_per_m(p.get("prompt")),
            "output": to_per_m(p.get("completion")),
            "cache_read": to_per_m(p.get("input_cache_read")),
            "cache_write": to_per_m(p.get("input_cache_write") or p.get("input_cache_write_1h")),
        }
    return out


# Explicit Arena / AA slug mapping (display name -> (arena_key, aa_slug))
MODEL_MAPPING = {
    "Claude Opus 4.7": ("claude-opus-4-7-20260305", "claude-opus-4-7"),
    "GPT-5.5 High": ("gpt-5.5-high", "gpt-5.5"),
    "Claude Opus 4.8": ("claude-opus-4-8", "claude-opus-4-8"),
    "Gemini 3.5 Flash": ("gemini-3.5-flash", "gemini-3.5-flash"),
    "Gemini 3.1 Pro": ("gemini-3.1-pro", "gemini-3.1-pro"),
    "GPT-5.4 High": ("gpt-5.4-high", "gpt-5.4"),
    "Claude Opus 4.6": ("claude-opus-4-6", "claude-opus-4-6"),
    "GLM-5.2": ("glm-5.2", "glm-5.2"),
    "GPT-5.5": ("gpt-5.5", "gpt-5.5"),
    "Claude Sonnet 4.6": ("claude-sonnet-4-6", "claude-sonnet-4-6"),
    "GPT-5.5 Instant": ("gpt-5.5-instant", "gpt-5.5"),
    "Gemini 3 Pro": ("gemini-3-pro", "gemini-3-pro"),
    "Qwen3.7 Max": ("qwen3.7-max", "qwen3.7-max"),
    "Gemini 3 Flash": ("gemini-3-flash", "gemini-3-flash"),
    "GPT-5.2": ("gpt-5.2", "gpt-5.2"),
    "Muse Spark": ("muse-spark", "muse-spark"),
    "MiMo V2.5 Pro": ("mimo-v2.5-pro", "mimo-v2.5-pro"),
    "GLM-5.1": ("glm-5.1", "glm-5.1"),
    "DeepSeek V4 Pro": ("deepseek-v4-pro", "deepseek-v4-pro"),
    "GPT-5.4": ("gpt-5.4", "gpt-5.4"),
    "Grok 4.20": ("grok-4.20", "grok-4.20"),
    "Kimi K2.6": ("kimi-k2.6", "kimi-k2.6"),
    "DeepSeek V4 Flash": ("deepseek-v4-flash", "deepseek-v4-flash"),
    "MiMo V2 Pro": ("mimo-v2-pro", "mimo-v2-pro"),
    "Qwen3.6 Max": ("qwen3.6-max", "qwen3.6-max"),
    "MiMo V2.5": ("mimo-v2.5", "mimo-v2.5"),
    "GLM-5": ("glm-5", "glm-5"),
    "GPT-5.1 High": ("gpt-5.1-high", "gpt-5.1"),
    "Qwen3.6 Plus": ("qwen3.6-plus", "qwen3.6-plus"),
    "Grok 4.3": ("grok-4.3", "grok-4.3"),
    "Grok 4.1": ("grok-4.1", "grok-4.1"),
    "Kimi K2.5": ("kimi-k2.5", "kimi-k2.5"),
    "Gemini 2.5 Pro": ("gemini-2.5-pro", "gemini-2.5-pro"),
    "GPT-5": ("gpt-5", "gpt-5"),
    "MiniMax M2.7": ("minimax-m2.7", "minimax-m2.7"),
    "GLM-4.7": ("glm-4.7", "glm-4.7"),
    "Qwen3.5-397B": ("qwen3.5-397b-a17b", "qwen3.5-397b"),
    "o3": ("o3", "o3"),
    "Kimi K2 Thinking": ("kimi-k2-thinking", "kimi-k2-thinking"),
    "Grok 4 Fast": ("grok-4-fast", "grok-4-fast"),
    "Qwen3.5-122B": ("qwen3.5-122b", "qwen3.5-122b"),
    "Qwen3.5-27B": ("qwen3.5-27b", "qwen3.5-27b"),
    "DeepSeek V3.2": ("deepseek-v3.2", "deepseek-v3.2"),
    "MiniMax M2.5": ("minimax-m2.5", "minimax-m2.5"),
    "GPT-5 mini": ("gpt-5-mini", "gpt-5-mini"),
    "Qwen3 Max": ("qwen3-max", "qwen3-max"),
    "GLM-4.6": ("glm-4.6", "glm-4.6"),
    "DeepSeek V3.1": ("deepseek-v3.1", "deepseek-v3.1"),
    "Qwen3.5-35B": ("qwen3.5-35b", "qwen3.5-35b"),
    "GLM-4.5": ("glm-4.5", "glm-4.5"),
    "GPT-4o": ("chatgpt-4o-latest-20250326", "gpt-4o"),
    "GPT-4.1": ("gpt-4.1", "gpt-4.1"),
    "Step 3.5 Flash": ("step-3.5-flash", "step-3.5-flash"),
    "Gemini 2.5 Flash": ("gemini-2.5-flash", "gemini-2.5-flash"),
    "o1": ("o1-2024-12-17", "o1"),
    "Kimi K2": ("kimi-k2-0711-preview", "kimi-k2"),
    "Mistral Large 3": ("mistral-large-3", "mistral-large-3"),
    "Grok 3": ("grok-3-preview-02-24", "grok-3"),
    "Claude Haiku 4.5": ("claude-haiku-4-5-20251001", "claude-3-5-haiku"),
    "DeepSeek R1": ("deepseek-r1", "deepseek-r1"),
    "DeepSeek V3": ("deepseek-v3", "deepseek-v3"),
    "Qwen3-235B": ("qwen3-235b-a22b", "qwen3-235b-a22b-instruct-2507"),
    "Claude Fable 5": ("claude-fable-5", "claude-fable-5"),
    "GPT-5.6 Sol High": ("gpt-5.6-sol", "gpt-5.6"),
    "Kimi K3": ("kimi-k3", "kimi-k3"),
}


def load_doc() -> dict:
    with open(MODELS_JSON) as f:
        return json.load(f)


def save_doc(doc: dict) -> None:
    doc["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(MODELS_JSON, "w") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")


def update_leaderboard_fields(models: list[dict], arena_data, aa_data) -> list[str]:
    arena_map = {m.get("model") or m.get("name"): m for m in arena_data if isinstance(m, dict)}
    aa_map = {}
    for m in aa_data if isinstance(aa_data, list) else []:
        if not isinstance(m, dict):
            continue
        slug = m.get("slug") or m.get("id") or m.get("name")
        if slug:
            aa_map[slug] = m

    changes = []
    for m in models:
        name = m["name"]
        mapping = MODEL_MAPPING.get(name)
        if not mapping:
            continue
        arena_key, aa_slug = mapping
        if arena_key in arena_map and "rating" in arena_map[arena_key]:
            new_rating = float(arena_map[arena_key]["rating"])
            old = float(m.get("arena", 0))
            if abs(new_rating - old) > 0.01:
                changes.append(f"  {name}: Arena {old:.2f} -> {new_rating:.2f}")
                m["arena"] = new_rating
        if aa_slug and aa_slug in aa_map:
            entry = aa_map[aa_slug]
            new_ii = entry.get("intelligence_index") or entry.get("index") or entry.get("score")
            if new_ii is not None:
                new_ii = float(new_ii)
                old = float(m.get("ai_index", 0))
                if abs(new_ii - old) > 0.01:
                    changes.append(f"  {name}: AI Index {old:.4f} -> {new_ii:.4f}")
                    m["ai_index"] = new_ii
    return changes


def refresh_prices_from_openrouter(models: list[dict], api_key: str | None = None) -> list[str]:
    try:
        or_models = fetch_openrouter_models(api_key)
    except Exception as e:
        print(f"  OpenRouter fetch failed: {e}")
        return []
    pmap = openrouter_price_map(or_models)
    changes = []
    for m in models:
        oid = m.get("openrouter_id")
        if not oid or oid not in pmap:
            continue
        src = pmap[oid]
        price = m.setdefault("price", {"currency": "USD"})
        price["currency"] = "USD"
        before = (price.get("input"), price.get("output"), price.get("cache_read"), price.get("cache_write"), m.get("ctx"))
        price["input"] = src["input"] if src["input"] is not None else -1
        price["output"] = src["output"] if src["output"] is not None else -1
        price["cache_read"] = src["cache_read"] if src["cache_read"] is not None else -1
        price["cache_write"] = src["cache_write"] if src["cache_write"] is not None else -1
        if src["ctx"]:
            m["ctx"] = src["ctx"]
        m["price_source"] = "openrouter"
        after = (price.get("input"), price.get("output"), price.get("cache_read"), price.get("cache_write"), m.get("ctx"))
        if before != after:
            changes.append(f"  {m['name']}: price/ctx refreshed via {oid}")
    return changes


def recalculate_scores(models: list[dict]) -> list[dict]:
    """Return ranked list of score dicts; also attaches s* fields onto copies for legacy export."""
    arenas = [float(m.get("arena", 0) or 0) for m in models]
    ais = [float(m.get("ai_index", 0) or 0) for m in models]
    pA = percentile_scores(arenas)
    pI = percentile_scores(ais)
    scored = []
    for i, m in enumerate(models):
        sA = round(hybrid(lin_norm(arenas[i], 1380, 1520), pA[i], 0.65))
        sAI = round(hybrid(lin_norm(ais[i], 15, 60), pI[i], 0.65), 1)
        eff = effective_price_usd(m.get("price"))
        sP = score_price_from_effective(eff)
        sM = score_multi(m.get("multi", 50))
        sC = score_ctx(m.get("ctx", 0))
        total = total_score(sA, sAI, sP, sM, sC)
        row = {
            **m,
            "sArena": int(sA),
            "sAI": sAI,
            "sPrice": int(sP),
            "sMulti": int(sM),
            "sCtx": int(sC),
            "sEco": m.get("eco", 0),
            "effective_price_usd": None if eff is None else round(eff, 6),
            "total": total,
            "po": (m.get("price") or {}).get("output", -1),  # legacy field = output $/M
            "r": m.get("region", m.get("r", "US")),
        }
        scored.append(row)
    scored.sort(key=lambda x: x["total"], reverse=True)
    return scored


def export_legacy(scored: list[dict]) -> None:
    legacy = []
    for m in scored:
        legacy.append(
            {
                "name": m["name"],
                "vendor": m["vendor"],
                "r": m.get("region") or m.get("r"),
                "arena": m["arena"],
                "ai_index": m["ai_index"],
                "eco": m.get("eco", 0),
                "po": (m.get("price") or {}).get("output", -1),
                "price_input": (m.get("price") or {}).get("input", -1),
                "price_output": (m.get("price") or {}).get("output", -1),
                "price_cache_read": (m.get("price") or {}).get("cache_read", -1),
                "price_cache_write": (m.get("price") or {}).get("cache_write", -1),
                "price_currency": (m.get("price") or {}).get("currency", "USD"),
                "multi": m.get("multi", 0),
                "ctx": m.get("ctx", 0),
                "note": m.get("note", ""),
                "url": m.get("url", ""),
                "openrouter_id": m.get("openrouter_id"),
                "sArena": m["sArena"],
                "sAI": m["sAI"],
                "sPrice": m["sPrice"],
                "sMulti": m["sMulti"],
                "sCtx": m["sCtx"],
                "sEco": m.get("sEco", 0),
                "total": m["total"],
            }
        )
    with open(LEGACY_JSON, "w") as f:
        json.dump(legacy, f, indent=2, ensure_ascii=False)
        f.write("\n")


def update_subheader(html_content: str, num_models: int) -> str:
    month_year = datetime.now().strftime("%B %Y")
    pattern = r'<p class="sub">.*?</p>'
    replacement = f'<p class="sub">Multi-Dimension Weighted Evaluation · {month_year} · {num_models} Models · data/models.json</p>'
    return re.sub(pattern, replacement, html_content)


def git_commit_push(message: str) -> bool:
    subprocess.run(["git", "add", "-A"], cwd=REPO, check=True)
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO)
    if result.returncode == 0:
        print("No changes to commit.")
        return False
    subprocess.run(["git", "commit", "-m", message], cwd=REPO, check=True)
    subprocess.run(["git", "push"], cwd=REPO, check=True)
    return True


def find_openrouter_key() -> str | None:
    for p in ("/root/openrouter_monitor.py", os.path.expanduser("~/.hermes/.env"), "/root/.env"):
        if not os.path.exists(p):
            continue
        text = open(p).read()
        m = re.search(r"sk-or-v1-[A-Za-z0-9]+", text)
        if m:
            return m.group(0)
    return os.environ.get("OPENROUTER_API_KEY")


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"=== LLM Ranking Update: {today} ===\n")

    doc = load_doc()
    models = doc["models"]
    print(f"Loaded {len(models)} models from data/models.json")

    arena_data, aa_data = [], []
    if os.path.exists(ARENA_JSON):
        with open(ARENA_JSON) as f:
            arena_data = json.load(f)
    if os.path.exists(AA_JSON):
        with open(AA_JSON) as f:
            aa_data = json.load(f)

    print("\n1. Scraping Arena ELO...")
    new_arena = try_scrape_arena()
    if new_arena:
        arena_data = new_arena
        with open(ARENA_JSON, "w") as f:
            json.dump(arena_data, f, indent=2, ensure_ascii=False)
        print(f"  Updated: {len(arena_data)} entries")
    else:
        print("  Using existing data")

    print("\n2. Scraping AI Index...")
    new_aa = try_scrape_aa()
    if new_aa:
        aa_data = new_aa
        with open(AA_JSON, "w") as f:
            json.dump(aa_data, f, indent=2, ensure_ascii=False)
        print(f"  Updated: {len(aa_data)} entries")
    else:
        print("  Using existing data")

    print("\n3. Updating leaderboard fields...")
    changes = update_leaderboard_fields(models, arena_data, aa_data)
    if changes:
        for c in changes:
            print(c)
    else:
        print("  No leaderboard changes")

    print("\n4. Refreshing OpenRouter prices/ctx...")
    pchanges = refresh_prices_from_openrouter(models, find_openrouter_key())
    if pchanges:
        for c in pchanges[:20]:
            print(c)
        if len(pchanges) > 20:
            print(f"  ... +{len(pchanges)-20} more")
    else:
        print("  No price changes / fetch skipped")

    print("\n5. Recalculating scores from models.json...")
    scored = recalculate_scores(models)
    print("\n  Top 10:")
    for i, m in enumerate(scored[:10]):
        print(
            f"  {i+1:2d}. {m['name']:25s} Arena={m['sArena']:2d} AI={m['sAI']:4.1f} "
            f"Price={m['sPrice']:2d} Multi={m['sMulti']:2d} Ctx={m['sCtx']:2d} "
            f"eff$={m['effective_price_usd']} Total={m['total']:5.1f}"
        )

    print("\n6. Saving...")
    save_doc(doc)
    export_legacy(scored)
    print(f"  Saved {MODELS_JSON}")
    print(f"  Saved legacy {LEGACY_JSON}")

    with open(INDEX_HTML) as f:
        html = f.read()
    html = update_subheader(html, len(models))
    with open(INDEX_HTML, "w") as f:
        f.write(html)
    print(f"  Updated subheader in {INDEX_HTML}")

    with open(os.path.join(REPO, "last_check.txt"), "w") as f:
        f.write(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ\n"))

    print("\n7. Git push...")
    pushed = git_commit_push(f"update: models.json source + price reaudit {today}")
    if pushed:
        print("  Pushed")
    else:
        print("  No changes")

    top3 = scored[:3]
    summary = f"📊 LLM排名已更新 ({today}): "
    summary += " | ".join([f"#{i+1} {m['name']}({m['total']})" for i, m in enumerate(top3)])
    print(f"\n{summary}")
    return summary


if __name__ == "__main__":
    main()
