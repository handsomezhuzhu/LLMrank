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

# How close two Arena ratings must be for one model's AI Index to stand in for
# another's (KNN band, in Arena rating points).
IMPUTE_ARENA_BAND = 20.0

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


# Multimodal score from modality coverage: how many non-text input modalities a
# model accepts, per OpenRouter's architecture.input_modalities. Derived data, so
# it can never drift the way a hand-maintained tag does.
MULTI_TIER_SCORE = {0: 50, 1: 70, 2: 85, 3: 95, 4: 100}
MULTI_MODALITIES = ("image", "file", "video", "audio")


def modalities_to_multi(modalities: list[str] | None) -> int:
    """Map a modality list to the canonical tier (50/75/100 or a tier score)."""
    if not modalities:
        return 50
    return MULTI_TIER_SCORE[min(len(set(modalities) & set(MULTI_MODALITIES)), 4)]


def score_multi(multi: float) -> int:
    """A tier value is already its score; anything else is clamped to the ladder."""
    if multi in MULTI_TIER_SCORE.values():
        return int(multi)
    return int(round(40 + (multi or 0) * 0.6))


def total_score(
    s_arena: float,
    s_ai: float,
    s_price: float,
    s_multi: float,
    s_ctx: float,
    has_arena: bool = True,
    has_ai: bool = True,
) -> float:
    """Weighted total; a dimension with no observation is dropped and the rest
    re-normalized so the weights still sum to 1 (never scored as zero)."""
    weights = {
        "arena": (s_arena, 0.30, has_arena),
        "ai": (s_ai, 0.30, has_ai),
        "price": (s_price, 0.15, True),
        "multi": (s_multi, 0.15, True),
        "ctx": (s_ctx, 0.10, True),
    }
    live = [(v, w) for v, w, present in weights.values() if present and v is not None]
    if not live:
        return 0.0
    total_w = sum(w for _, w in live)
    if total_w <= 0:
        return 0.0
    return round(sum(v * w for v, w in live) / total_w, 1)


# ── External data fetch ─────────────────────────────────────────────────────
# Policy: never write partial/failed leaderboard scrapes into models.json.
# Prefer stable HTTP sources; fall back to on-disk cache only.

MIN_ARENA_ROWS = 50
MIN_AA_ROWS = 50
MIN_OPENROUTER_MODELS = 50

AA_LIVE_URL = "https://artificialanalysis.ai/leaderboards/models"
AA_FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LLMrank/1.0; +https://rank.zhuzihan.com)",
    "Accept": "text/html,application/xhtml+xml",
}
AA_FETCHED_LIVE = False
ARENA_FETCHED_LIVE = False
AA_LIVE_RELEASES = {}


def _http_json(url: str, headers: dict | None = None, timeout: int = 60) -> Any:
    req = urllib.request.Request(
        url,
        headers=headers or {"User-Agent": "LLMrank/1.0 (+https://rank.zhuzihan.com)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _normalize_arena_rows(rows: list[dict]) -> list[dict] | None:
    """Normalize to [{model, rating, organization?, votes?}, ...]."""
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        name = r.get("model") or r.get("model_name") or r.get("modelDisplayName") or r.get("modelKey") or r.get("name")
        rating = r.get("rating")
        if rating is None:
            rating = r.get("score")
        if not name or rating is None:
            continue
        try:
            rating_f = float(rating)
        except Exception:
            continue
        out.append(
            {
                "model": str(name),
                "modelKey": str(r.get("modelKey") or name),
                "rating": rating_f,
                "organization": r.get("organization") or r.get("vendor") or "",
                "votes": int(r.get("votes") or r.get("vote_count") or 0),
            }
        )
    if len(out) < MIN_ARENA_ROWS:
        return None
    # de-dupe by model, keep highest rating
    best: dict[str, dict] = {}
    for row in out:
        prev = best.get(row["model"])
        if prev is None or row["rating"] > prev["rating"]:
            best[row["model"]] = row
    return list(best.values())


def _normalize_aa_rows(rows: list[dict]) -> list[dict] | None:
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        slug = r.get("slug") or r.get("id")
        name = r.get("model") or r.get("name") or slug
        score = (
            r.get("intelligence_index")
            or r.get("index")
            or r.get("score")
            or r.get("artificial_analysis_intelligence_index")
        )
        if not slug or score is None:
            continue
        try:
            score_f = float(score)
        except Exception:
            continue
        out.append(
            {
                "model": str(name or slug),
                "slug": str(slug),
                "intelligence_index": score_f,
            }
        )
    if len(out) < MIN_AA_ROWS:
        return None
    best: dict[str, dict] = {}
    for row in out:
        prev = best.get(row["slug"])
        if prev is None or row["intelligence_index"] > prev["intelligence_index"]:
            best[row["slug"]] = row
    return list(best.values())


def _parse_arena_live_page(page: str) -> list[dict] | None:
    """Extract the current overall leaderboard from Arena's rendered Next.js payload."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)', page, re.S)
    if not chunks:
        return None
    try:
        text = "".join(json.loads('"' + chunk + '"') for chunk in chunks)
    except Exception:
        return None
    # Arena migrated the public leaderboard view from /leaderboard to /leaderboard/text.
    # Keep the endpoint anchored to the explicit text overall leaderboard path.
    marker = '"id":"leaderboard-sets/public/leaderboards/text-overall-style_control/leaderboard-snapshots/latest","entries":'
    pos = text.find(marker)
    if pos < 0:
        return None
    try:
        rows, _ = json.JSONDecoder().raw_decode(text[pos + len(marker):])
    except Exception:
        return None
    if not isinstance(rows, list):
        return None
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        display = row.get("modelDisplayName")
        rating = row.get("rating")
        if not display or rating is None:
            continue
        normalized.append({
            "model": str(display),
            "modelKey": str(display),
            "rating": float(rating),
            "organization": row.get("modelOrganization") or "",
            "votes": int(row.get("votes") or 0),
            "rank": row.get("rank"),
            "model_url": row.get("modelUrl"),
        })
    return normalized if len(normalized) >= MIN_ARENA_ROWS else None


_BROWSER_FETCH_HELPER = r"""
import sys
from playwright.sync_api import sync_playwright

out_path = sys.argv[1]
with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1366, "height": 900},
        locale="en-US",
    )
    page = ctx.new_page()
    page.goto("https://arena.ai/leaderboard/text", wait_until="domcontentloaded", timeout=60000)
    for _ in range(45):
        title = page.title() or ""
        if "moment" not in title.lower():
            break
        page.wait_for_timeout(2000)
    page.wait_for_timeout(5000)
    html = page.content()
    with open(out_path, "w") as f:
        f.write(html)
    browser.close()
"""


def _fetch_arena_with_browser() -> str | None:
    """arena.ai is behind a Cloudflare challenge that blocks plain HTTP clients.

    Render the leaderboard page in a real (Xvfb-displayed) Chromium and return the HTML.
    """
    import subprocess
    import tempfile

    helper = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False)
    helper.write(_BROWSER_FETCH_HELPER)
    helper.close()
    out_path = helper.name + ".html"
    try:
        subprocess.run(
            ["xvfb-run", "-a", "python3", helper.name, out_path],
            timeout=180,
            check=False,
        )
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            with open(out_path) as f:
                return f.read()
    except Exception as e:
        print(f"  Browser fallback failed: {e}")
    finally:
        for p in (helper.name, out_path):
            try:
                os.unlink(p)
            except OSError:
                pass
    return None


ARENA_HF_LATEST_URL = (
    "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset/"
    "resolve/main/text/latest-00000-of-00001.parquet"
)


def _fetch_arena_from_hf() -> list[dict] | None:
    """Arena's site sits behind a Cloudflare bot wall that refuses every automated
    client (plain HTTP and headless/headed Chromium alike). Use Arena's own official
    Hugging Face dataset instead: the "latest" text snapshot, overall category.

    The snapshot trails the live site by a few days, which is fine for a daily job.
    Returns rows in the same shape _normalize_arena_rows accepts.
    """
    import io

    req = urllib.request.Request(
        ARENA_HF_LATEST_URL,
        headers={"User-Agent": "LLMrank/1.0 (+https://rank.zhuzihan.com)"},
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        blob = response.read()
    if len(blob) < 1024:
        raise RuntimeError(f"HF parquet too small: {len(blob)} bytes")
    try:
        import pyarrow.parquet as pq
    except ImportError as e:  # pragma: no cover - depends on the host
        raise RuntimeError("pyarrow not installed; run: pip install pyarrow") from e
    table = pq.read_table(io.BytesIO(blob))
    rows = [
        {
            "model": r.get("model_name"),
            "modelKey": r.get("model_name"),
            "rating": r.get("rating"),
            "organization": r.get("organization") or "",
            "votes": r.get("vote_count") or 0,
            "publish_date": r.get("leaderboard_publish_date"),
        }
        for r in table.to_pylist()
        if r.get("category") == "overall"
    ]
    if rows:
        dates = {r.get("publish_date") for r in rows if r.get("publish_date")}
        if dates:
            print(f"  Arena HF snapshot dated {max(dates)}")
    return rows or None


def fetch_arena_leaderboard() -> list[dict] | None:
    """Fetch the current overall Arena leaderboard from its official HF dataset."""
    global ARENA_FETCHED_LIVE
    ARENA_FETCHED_LIVE = False
    normalized = None
    try:
        normalized = _normalize_arena_rows(_fetch_arena_from_hf() or [])
    except Exception as e:
        print(f"  Arena HF fetch failed: {e}")
    if not normalized:
        print("  Arena HF snapshot did not yield a validated overall leaderboard")
        return None
    print(f"  Arena fetch ok (HF): {len(normalized)} overall models")
    ARENA_FETCHED_LIVE = True
    return normalized

def _parse_aa_live_page(page: str) -> list[dict] | None:
    """Extract scored model records from Artificial Analysis's rendered RSC payload."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)', page, re.S)
    if not chunks:
        return None
    try:
        text = "".join(json.loads('"' + chunk + '"') for chunk in chunks)
    except Exception:
        return None
    decoder = json.JSONDecoder()
    best: dict[str, dict] = {}
    # Release dates are separate sibling records in the RSC payload, e.g.
    # {"slug":"gpt-6-luna","name":"GPT-6 Luna","deprecated":false,"releaseDate":"2026-09-22",...}
    release_date_pattern = re.compile(r'\{"slug":"([^"\\]+)","name":"[^"\\]+","deprecated":(?:true|false),"releaseDate":"([^"\\]+)"')
    releases = {slug: date for slug, date in release_date_pattern.findall(text)}
    for match in re.finditer(r'\{"slug":"[^"\\]+","name":"[^"\\]+","shortName":', text):
        try:
            row, _ = decoder.raw_decode(text, match.start())
        except Exception:
            continue
        slug = row.get("slug")
        score = row.get("intelligenceIndex")
        if not slug or not isinstance(score, (int, float)):
            continue
        best[slug] = {
            "slug": slug,
            "model": row.get("name") or slug,
            "intelligence_index": float(score),
            "deprecated": bool(row.get("deprecated", False)),
            "released": releases.get(slug),
            "context_window": row.get("contextWindowTokens"),
            "price_input": row.get("price1mInputTokens"),
            "price_output": row.get("price1mOutputTokens"),
            "cache_read": row.get("cacheHitPrice"),
            "cache_write": row.get("cacheWritePrice"),
            "intelligence_index_cost_per_task": row.get("intelligenceIndexCostPerTask"),
        }
    global AA_LIVE_RELEASES
    AA_LIVE_RELEASES = releases
    return list(best.values()) if len(best) >= MIN_AA_ROWS else None


def fetch_aa_intelligence() -> list[dict] | None:
    """Fetch current AA Intelligence Index records, falling back to the full local cache."""
    global AA_FETCHED_LIVE, AA_LIVE_RELEASES
    AA_FETCHED_LIVE = False
    AA_LIVE_RELEASES = {}
    try:
        req = urllib.request.Request(AA_LIVE_URL, headers=AA_FETCH_HEADERS)
        with urllib.request.urlopen(req, timeout=60) as response:
            page = response.read().decode("utf-8", "replace")
        live = _parse_aa_live_page(page)
        if live:
            AA_FETCHED_LIVE = True
            print(f"  AA live fetch ok: {len(live)} models")
            return live
        print("  AA live page did not yield a validated index — trying local cache")
    except Exception as e:
        print(f"  AA live fetch failed — trying local cache: {e}")
    try:
        if os.path.exists(AA_JSON):
            with open(AA_JSON) as f:
                cached = json.load(f)
            if isinstance(cached, list):
                normalized = _normalize_aa_rows(cached)
                if normalized:
                    print(f"  AA using cached snapshot: {len(normalized)} models")
                    return normalized
        print("  AA cache unavailable/invalid — skip update")
        return None
    except Exception as e:
        print(f"  AA cache load failed: {e}")
        return None


# Back-compat names used by older cron prompts / imports
def try_scrape_arena():
    return fetch_arena_leaderboard()


def try_scrape_aa():
    return fetch_aa_intelligence()


def fetch_openrouter_models(api_key: str | None = None) -> list[dict]:
    headers = {"User-Agent": "LLMrank/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request("https://openrouter.ai/api/v1/models", headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    models = data.get("data", data)
    if not isinstance(models, list) or len(models) < MIN_OPENROUTER_MODELS:
        raise RuntimeError(f"OpenRouter payload too small: {type(models)} len={len(models) if isinstance(models, list) else 'n/a'}")
    return models


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


# Explicit Arena / AA slug mapping (display name -> (arena_alias, aa_slug))
# Arena aliases are the exact live display names from arena.ai/leaderboard/text
# (e.g. "Claude Opus 5.5 (High)"); AA slugs are Artificial Analysis model slugs.
MODEL_MAPPING = {
    "Gemini 4 Carbon": ("Gemini 4 Carbon (High)", "gemini-4-carbon"),
    "Claude Haiku 5.5": ("Claude Haiku 5.5 (High)", "claude-haiku-5-5"),
    "Nemotron 3 Ultra 550B": ("NVIDIA-Nemotron-3-Ultra-550B-A55B (NVFP4)", "nvidia-nemotron-3-ultra-550b-a55b"),
    "Nemotron 3.5 Super VL": ("NVIDIA-Nemotron-3.5-Super-VL-120B-A12B (NVFP4)", "nemotron-3-5-super-vl"),
    "Nemotron 3.5 Lightning": ("NVIDIA-Nemotron-3.5-Lightning-30B-A3B (NVFP4)", "nemotron-3-5-lightning"),
    "Command A+": ("Command A (03-2025)", "command-a-plus"),
    "Hy3": ("Hy3", "hy3"),
    "Inkling": ("Inkling", "inkling"),
    "Inkling Small": ("Inkling-Small", "inkling-small"),
    "Muse Glimmer 30B": ("Muse Glimmer", "muse-glimmer"),
    "Claude Fable 5.1": ("Claude Fable 5.1 (Max)", "claude-fable-5-1"),
    "Muse Spark 1.3": ("Muse Spark 1.3 (Max)", "muse-spark-1-3"),
    "GPT-5.6 Terra": ("GPT-5.6 Terra (xHigh)", "gpt-5-6-terra"),
    "MiniMax M3": ("MiniMax-M3", "minimax-m3"),
    "Claude Opus 5": ("Claude Opus 5 (High)", "claude-opus-5"),
    "Gemini 3.8 Flash": ("Gemini 3.8 Flash (High)", "gemini-3-8-flash"),
    "GLM-5.3": ("GLM-5.3 (Max)", "glm-5-3"),
    "GLM-5.3 Flash": ("GLM-5.3-Flash", "glm-5-3-flash"),
    "Qwen3.8 Max": ("Qwen3.8-Max", "qwen3-8-max"),
    "Grok 4.5": ("Grok 4.5", "grok-4-5"),
    "Claude Opus 5.5": ("Claude Opus 5.5 (High)", "claude-opus-5-5"),
    "GPT-6 Luna": ("GPT-6 Luna (Max)", "gpt-6-luna"),
    "GPT-6 Sol": ("GPT-6 Sol (Max)", "gpt-6-sol"),
    "GPT-5.6 Luna": ("GPT-5.6 Luna (xHigh)", "gpt-5-6-luna"),
    "Muse Spark 1.2": ("Muse Spark 1.2 (xHigh)", "muse-spark-1-2"),
    "Muse Spark 1.1": ("Muse Spark 1.1", "muse-spark-1-1"),
    "MiMo V2.6 Pro": ("MiMo-V2.6-Pro", "mimo-v2-6-pro"),
    "MiMo V2.6 Flash": ("MiMo-V2.6-Flash", "mimo-v2-6-flash"),
    "DeepSeek V4.1 Flash": ("DeepSeek-V4.1-Flash-20260910 (Max)", "deepseek-v4-1-flash-1017"),
    "Gemini 3.5 Flash Lite": ("Gemini 3.5 Flash-Lite", "gemini-3-5-flash-lite"),
    "Qwen3.7 Plus": ("Qwen3.7-Plus", "qwen3-7-plus"),
    "Qwen3.8 27B": ("Qwen3.8-27B", "qwen3-8-27b"),
    "Gemma 4 31B": ("Gemma 4 31B", "gemma-4-31b"),
    "Gemma 4 26B A4B": ("Gemma 4 26B A4B", "gemma-4-26b-a4b"),
    "Solar Pro 4": ("Solar Pro 4", "solar-pro4"),
    "Mistral Medium 3.5": ("Mistral Medium 3.5", "mistral-medium-3-5"),
    "GPT-5.4 mini": ("GPT-5.4 mini (High)", "gpt-5-4-mini"),
    "GPT-5.4 nano": ("GPT-5.4 nano (High)", "gpt-5-4-nano"),
    "Mistral Large 4": ("Mistral Large 4", "mistral-large-4"),
    "Grok 4.7": ("Grok 4.7 (xHigh)", "grok-4-7"),
    "GPT-6 Astra": ("GPT-6 Astra (Max)", "gpt-6-astra"),
    "Gemini 3.7 Flash": ("Gemini 3.7 Flash (High)", "gemini-3-7-flash"),
    "Gemini 3.6 Flash": ("Gemini 3.6 Flash (High)", "gemini-3-6-flash"),
    "Claude Opus 4.7": ("Claude Opus 4.7", "claude-opus-4-7"),
    "GPT-5.5 High": ("GPT-5.5 (High)", "gpt-5-5-high"),
    "Claude Opus 4.8": ("Claude Opus 4.8", "claude-opus-4-8"),
    "Gemini 3.5 Flash": ("Gemini 3.5 Flash (High)", "gemini-3-5-flash"),
    "Gemini 3.1 Pro": ("Gemini 3.1 Pro Preview", "gemini-3-1-pro-preview"),
    "GPT-5.4 High": ("GPT-5.4 (High)", "gpt-5-4"),
    "Claude Opus 4.6": ("Claude Opus 4.6", "claude-opus-4-6"),
    "GLM-5.2": ("GLM-5.2 (Max)", "glm-5-2"),
    "GPT-5.5": ("GPT-5.5", "gpt-5-5"),
    "Claude Sonnet 4.6": ("Claude Sonnet 4.6", "claude-sonnet-4-6"),
    "GPT-5.5 Instant": ("GPT-5.5 Instant", "gpt-5-5-instant-06-26"),
    "Gemini 3 Pro": ("Gemini 3 Pro", "gemini-3-pro"),
    "Qwen3.7 Max": ("Qwen3.7-Max-Preview", "qwen3-7-max"),
    "Gemini 3 Flash": ("Gemini 3 Flash", "gemini-3-flash"),
    "GPT-5.2": ("GPT-5.2", "gpt-5-2"),
    "Muse Spark": ("Muse Spark", "muse-spark"),
    "MiMo V2.5 Pro": ("MiMo-V2.5-Pro", "mimo-v2-5-pro"),
    "GLM-5.1": ("GLM-5.1", "glm-5-1"),
    "DeepSeek V4 Pro 0813": ("DeepSeek-V4-Pro", "deepseek-v4-pro"),
    "GPT-5.4": ("GPT-5.4", "gpt-5-4"),
    "Grok 4.6": ("Grok 4.6 (High)", "grok-4-6"),
    "Grok 4.20": ("Grok 4.20 Beta 1", "grok-4-20"),
    "Kimi K2.7 Code": (None, "kimi-k2-7-code"),
    "Kimi K2.6": ("Kimi K2.6", "kimi-k2-6"),
    "DeepSeek V4 Flash 0731": ("DeepSeek-V4-Flash", "deepseek-v4-flash"),
    "MiMo V2 Pro": ("MiMo-V2-Pro", "mimo-v2-pro"),
    "Qwen3.6 Max": ("Qwen3.6-Max-Preview", "qwen3-6-max"),
    "MiMo V2.5": ("MiMo-V2.5", "mimo-v2-5-pro"),
    "GLM-5": ("GLM-5", "glm-5"),
    "GPT-5.1 High": ("GPT-5.1 (High)", "gpt-5-1"),
    "Qwen3.6 Plus": ("Qwen3.6-Plus", "qwen3-6-plus"),
    "Grok 4.3": ("Grok 4.3", "grok-4-3"),
    "Grok 4.1": ("Grok 4.1", "grok-4"),
    "Kimi K2.5": ("Kimi K2.5 (Thinking)", "kimi-k2-5"),
    "Gemini 2.5 Pro": ("Gemini 2.5 Pro", "gemini-2-5-pro"),
    "GPT-5": ("GPT-5 (High)", "gpt-5"),
    "MiniMax M2.7": ("MiniMax-M2.7", "minimax-m2-7"),
    "GLM-4.7": ("GLM-4.7", "glm-4-7"),
    "Qwen3.5-397B": ("Qwen3.5-397B-A17B", "qwen3-5-397b-a17b"),
    "o3": ("o3 (2025-04-16)", "o3"),
    "Kimi K2 Thinking": ("Kimi K2 Thinking Turbo", "kimi-k2-thinking"),
    "Grok 4 Fast": ("Grok 4 Fast (Reasoning)", "grok-4-fast"),
    "Qwen3.5-122B": ("Qwen3.5-122B-A10B", "qwen3-5-122b-a10b"),
    "Qwen3.5-27B": ("Qwen3.5-27B", "qwen3-5-27b"),
    "DeepSeek V3.2": ("DeepSeek-V3.2", "deepseek-v3-2"),
    "MiniMax M2.5": ("MiniMax-M2.5", "minimax-m2-5"),
    "GPT-5 mini": ("GPT-5 mini (High)", "gpt-5-mini"),
    "Qwen3 Max": ("Qwen3-Max (2025-09-23)", "qwen3-max"),
    "GLM-4.6": ("GLM-4.6", "glm-4-6"),
    "DeepSeek V3.1": ("DeepSeek-V3.1", "deepseek-v3-1"),
    "Qwen3.5-35B": ("Qwen3.5-35B-A3B", "qwen3-5-35b-a3b"),
    "GLM-4.5": ("GLM-4.5", "glm-4-5-air"),
    "GPT-4o": ("ChatGPT-4o Latest (20250326)", "gpt-4o"),
    "GPT-4.1": ("GPT-4.1 (2025-04-14)", "gpt-4-1"),
    "Step 3.5 Flash": ("Step-3.5-Flash", "step-3-5-flash"),
    "Gemini 2.5 Flash": ("Gemini 2.5 Flash", "gemini-2-5-flash"),
    "o1": ("o1 (2024-12-17)", "o1"),
    "Kimi K2": ("Kimi K2 Preview (0711)", "kimi-k2"),
    "Mistral Large 3": ("Mistral Large 3", "mistral-large-3"),
    "Grok 3": ("Grok 3 Preview (02-24)", "grok-3"),
    "Claude Haiku 4.5": ("Claude Haiku 4.5 (20251001)", "claude-3-5-haiku"),
    "DeepSeek R1": ("DeepSeek-R1", "deepseek-r1"),
    "DeepSeek V3": ("DeepSeek-V3", "deepseek-v3"),
    "Qwen3-235B": ("Qwen3-235B-A22B", "qwen3-235b-a22b-instruct-2507"),
    "Claude Fable 5": ("Claude Fable 5 (High)", "claude-fable-5"),
    "gpt-oss-120b": ("gpt-oss-120b", "gpt-oss-120b"),
    "GPT-5.6 Sol High": ("GPT-5.6 Sol (xHigh)", "gpt-5-6-sol"),
    "Kimi K3": ("Kimi K3 (Max)", "kimi-k3-1-pro"),
    "Muse Wonder": ("Muse Wonder (Max)", "muse-wonder"),
    "Gemini 4 Argon": ("Gemini 4 Argon (High)", "gemini-4-argon"),
    "Step 5 Preview": ("Step 5 Preview", "step-5"),
    "GPT-6.1 Sol": ("GPT-6.1 Sol (Max)", "gpt-6-1-sol"),
    "Claude Sonnet 5.5": ("Claude Sonnet 5.5 (xHigh)", "claude-sonnet-5-5"),
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
    arena_map = {}
    for row in arena_data:
        if not isinstance(row, dict):
            continue
        model_name = row.get("model") or row.get("name")
        model_key = row.get("modelKey")
        for key in (model_name, model_key):
            if key:
                prev = arena_map.get(key)
                if prev is None or float(row.get("rating", 0)) > float(prev.get("rating", 0)):
                    arena_map[key] = row
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
            # No mapping: leave whatever score the row already carries.
            continue
        arena_key, aa_slug = mapping
        arena_row = arena_map.get(arena_key) if arena_key else None
        if arena_row and arena_row.get("rating") is not None:
            new_rating = float(arena_row["rating"])
            old = m.get("arena")
            if old is None or abs(new_rating - float(old)) > 0.01:
                changes.append(f"  {name}: Arena {old} -> {new_rating:.2f}")
            m["arena"] = new_rating
        # Absent from a fresh board: keep the last known rating untouched.
        entry = aa_map.get(aa_slug) if aa_slug else None
        new_ii = None
        if entry:
            new_ii = entry.get("intelligence_index") or entry.get("index") or entry.get("score")
        if new_ii is not None:
            new_ii = float(new_ii)
            old = m.get("ai_index")
            if old is None or abs(new_ii - float(old)) > 0.01:
                changes.append(f"  {name}: AI Index {old} -> {new_ii:.4f}")
            m["ai_index"] = new_ii
        # Absent from a fresh index: keep the last known AI Index untouched.
        if entry and new_ii is not None:
            if entry.get("context_window"):
                m["ctx"] = int(entry["context_window"])
            if isinstance(entry.get("intelligence_index_cost_per_task"), (int, float)):
                m["aa_cost_per_task_usd"] = float(entry["intelligence_index_cost_per_task"])
            price = m.setdefault("price", {"currency": "USD"})
            price["currency"] = "USD"
            if not m.get("openrouter_id") and isinstance(entry.get("price_input"), (int, float)) and isinstance(entry.get("price_output"), (int, float)):
                price.update({
                    "input": float(entry["price_input"]),
                    "output": float(entry["price_output"]),
                    "cache_read": float(entry["cache_read"]) if isinstance(entry.get("cache_read"), (int, float)) else -1,
                    "cache_write": float(entry["cache_write"]) if isinstance(entry.get("cache_write"), (int, float)) else -1,
                })
                m["price_source"] = "artificialanalysis"
            else:
                for field, aa_field in (("input", "price_input"), ("output", "price_output"), ("cache_read", "cache_read"), ("cache_write", "cache_write")):
                    value = entry.get(aa_field)
                    if isinstance(value, (int, float)) and (price.get(field) is None or float(price.get(field, -1)) < 0):
                        price[field] = float(value)
            release_date = AA_LIVE_RELEASES.get(aa_slug)
            if release_date:
                m["released"] = release_date
                if name in {"GPT-6 Luna", "GPT-6 Sol", "Claude Opus 5.5"}:
                    arena_status = "Arena已收录" if m.get("arena") is not None else "Arena尚未收录"
                    m["note"] = f"新模型收录 {release_date} · {arena_status} · price/OpenRouter"
    return changes


def should_auto_refresh_price(m: dict) -> bool:
    """
    Skip manual / deprecated / redirected legacy models.
    auto_price=False or price_source=manual freezes official list prices.
    Missing openrouter_id also skips.
    """
    if m.get("auto_price") is False:
        return False
    if str(m.get("price_source") or "").lower() == "manual":
        return False
    if m.get("deprecated") is True:
        return False
    oid = m.get("openrouter_id")
    if not oid:
        return False
    return True


def openrouter_modality_map(or_models: list[dict]) -> dict[str, list[str]]:
    """model id -> its input modalities, per OpenRouter's architecture block."""
    out: dict[str, list[str]] = {}
    for m in or_models:
        mid = m.get("id")
        if not mid:
            continue
        arch = m.get("architecture") or {}
        mods = arch.get("input_modalities")
        if isinstance(mods, list) and mods:
            out[mid] = [str(x) for x in mods]
    return out


def sync_multi_from_openrouter(models: list[dict], or_models: list[dict]) -> list[str]:
    """Recompute every row's multimodal tag from its modality coverage.

    Models with no OpenRouter listing keep their current tag (they simply have no
    modality data to derive from).
    """
    mmap = openrouter_modality_map(or_models)
    changes = []
    for m in models:
        oid = m.get("openrouter_id")
        mods = mmap.get(oid) if oid else None
        if not mods:
            continue
        want = modalities_to_multi(mods)
        if m.get("multi") != want:
            changes.append(f"  {m['name']}: multi {m.get('multi')} -> {want} "
                           f"({','.join(sorted(set(mods) & set(MULTI_MODALITIES))) or 'text only'})")
            m["multi"] = want
        m["modalities"] = sorted(mods)
    return changes


def refresh_prices_from_openrouter(
    models: list[dict], api_key: str | None = None, cache: dict | None = None
) -> list[str]:
    """Refresh prices/ctx. `cache` receives the raw OpenRouter payload so the
    modality pass can reuse it instead of fetching twice."""
    try:
        or_models = fetch_openrouter_models(api_key)
    except Exception as e:
        print(f"  OpenRouter fetch failed — keeping existing prices: {e}")
        return []
    if cache is not None:
        cache["or_models"] = or_models
    pmap = openrouter_price_map(or_models)
    if len(pmap) < MIN_OPENROUTER_MODELS:
        print(f"  OpenRouter map too small ({len(pmap)}) — skip price update")
        return []
    changes = []
    skipped = 0
    missing = 0
    for m in models:
        if not should_auto_refresh_price(m):
            skipped += 1
            continue
        oid = m.get("openrouter_id")
        if oid not in pmap:
            missing += 1
            continue
        src = pmap[oid]
        # If OR returns no usable IO prices, do not clobber manual/official values
        if src["input"] is None and src["output"] is None:
            missing += 1
            continue
        price = m.setdefault("price", {"currency": "USD"})
        price["currency"] = "USD"
        before = (
            price.get("input"),
            price.get("output"),
            price.get("cache_read"),
            price.get("cache_write"),
            m.get("ctx"),
        )
        price["input"] = src["input"] if src["input"] is not None else -1
        price["output"] = src["output"] if src["output"] is not None else -1
        price["cache_read"] = src["cache_read"] if src["cache_read"] is not None else -1
        price["cache_write"] = src["cache_write"] if src["cache_write"] is not None else -1
        if src["ctx"]:
            m["ctx"] = src["ctx"]
        m["price_source"] = "openrouter"
        m["auto_price"] = True
        after = (
            price.get("input"),
            price.get("output"),
            price.get("cache_read"),
            price.get("cache_write"),
            m.get("ctx"),
        )
        if before != after:
            changes.append(f"  {m['name']}: price/ctx refreshed via {oid}")
    print(f"  OpenRouter: updated {len(changes)}, skipped frozen/manual {skipped}, missing id {missing}")
    return changes


def impute_missing_scores(models: list[dict], band: float) -> None:
    """Fill a missing AI Index from Arena-neighbours (KNN, +/- band points).

    Only that direction: an Arena rating is a *measured* score, so models sitting
    within a narrow Arena band are genuinely comparable, and their AA Index is
    the best available estimate for a model AA has not published yet. The reverse
    (guessing an Arena rating from AA) is not done — AA measures a different
    quantity and its neighbourhoods are not interchangeable.

    Sets `ai_index_imputed` (and `ai_index_neighbours`) when the value is an
    estimate. A measured value is never overwritten.
    """
    measured = [
        (float(m["arena"]), float(m["ai_index"]))
        for m in models
        if m.get("arena") is not None
        and m.get("ai_index") is not None
        and not m.get("ai_index_imputed")
    ]
    for m in models:
        if m.get("ai_index") is not None or m.get("arena") is None:
            continue
        arena = float(m["arena"])
        near = [ai for a, ai in measured if abs(a - arena) <= band]
        if not near:
            continue  # nothing comparable: leave it unscored rather than guess
        m["ai_index"] = round(sum(near) / len(near), 4)
        m["ai_index_imputed"] = True
        m["ai_index_neighbours"] = len(near)


def model_status(m: dict) -> str:
    """How much of this row is actually measured.

    verified  — Arena and AI Index both observed on their boards
    estimated — at least one value imputed from comparable models
    stale     — a board no longer lists it; values carried over from earlier runs
    """
    if m.get("ai_index_imputed"):
        return "estimated"
    has_arena = m.get("arena") is not None
    has_ai = m.get("ai_index") is not None
    if has_arena and has_ai and not m.get("board_missing"):
        return "verified"
    return "stale"


def recalculate_scores(models: list[dict]) -> list[dict]:
    """Return ranked list of score dicts; also attaches s* fields onto copies for legacy export.

    A model needs at least an Arena rating to be ranked. When its AI Index is
    missing (and could not be imputed), that dimension is dropped from the total
    rather than scored as zero, and the row is labelled stale.
    """
    arenas = [float(m["arena"]) if m.get("arena") is not None else None for m in models]
    ais = [float(m["ai_index"]) if m.get("ai_index") is not None else None for m in models]
    valid_indices = [i for i, value in enumerate(arenas) if value is not None]
    models = [models[i] for i in valid_indices]
    if not models:
        return []
    arenas = [float(m["arena"]) for m in models]
    ais = [float(m["ai_index"]) if m.get("ai_index") is not None else None for m in models]
    # Percentile / linear maps are built from rows that actually have each value.
    pA = percentile_scores(arenas)
    ai_present = [a for a in ais if a is not None]
    pI = percentile_scores(ai_present) if len(ai_present) > 1 else [100.0] * len(ai_present)
    ai_rank = {round(v, 6): pI[i] for i, v in enumerate(ai_present)}
    scored = []
    for i, m in enumerate(models):
        sA = round(hybrid(lin_norm(arenas[i], 1300, 1520), pA[i], 0.65))
        if ais[i] is None:
            sAI = None
        else:
            sAI = round(hybrid(lin_norm(ais[i], 0, 60), ai_rank.get(round(ais[i], 6), 50.0), 0.65), 1)
        eff = effective_price_usd(m.get("price"))
        sP = score_price_from_effective(eff)
        sM = score_multi(m.get("multi", 50))
        sC = score_ctx(m.get("ctx", 0))
        total = total_score(sA, sAI, sP, sM, sC, has_ai=sAI is not None)
        row = {
            **m,
            "sArena": None if sA is None else int(sA),
            "sAI": sAI,
            "sPrice": int(sP),
            "sMulti": int(sM),
            "sCtx": int(sC),
            "sEco": m.get("eco", 0),
            "effective_price_usd": None if eff is None else round(eff, 6),
            "total": total,
            "po": (m.get("price") or {}).get("output", -1),  # legacy field = output $/M
            "r": m.get("region", m.get("r", "US")),
            # Provenance, so the site can label verified / estimated / stale.
            "status": model_status(m),
            "ai_imputed": bool(m.get("ai_index_imputed")),
            "ai_neighbours": m.get("ai_index_neighbours"),
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
    # LLMRANK_NO_PUSH=1 commits locally but never pushes, so a dry run can
    # inspect the outcome without touching origin.
    if os.environ.get("LLMRANK_NO_PUSH") == "1":
        print("LLMRANK_NO_PUSH=1 — committed locally, not pushed.")
        return True
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

    # Load on-disk leaderboard caches as fallback (never invent data).
    arena_data, aa_data = [], []
    if os.path.exists(ARENA_JSON):
        with open(ARENA_JSON) as f:
            arena_data = json.load(f)
    if os.path.exists(AA_JSON):
        with open(AA_JSON) as f:
            aa_data = json.load(f)

    print("\n1. Fetching Arena ratings...")
    new_arena = fetch_arena_leaderboard()
    arena_fresh = bool(new_arena and ARENA_FETCHED_LIVE)
    if new_arena:
        arena_data = new_arena
        arena_fresh = True
        with open(ARENA_JSON, "w") as f:
            json.dump(arena_data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"  Cache rewritten: {len(arena_data)} entries")
    else:
        print("  Fetch failed/incomplete — will NOT patch Arena fields from stale/partial data")

    print("\n2. Fetching AI Index...")
    new_aa = fetch_aa_intelligence()
    aa_fresh = bool(new_aa and AA_FETCHED_LIVE)
    if new_aa:
        aa_data = new_aa
        if aa_fresh:
            with open(AA_JSON, "w") as f:
                json.dump(aa_data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            print(f"  Refreshed AA cache: {len(aa_data)} models")
        else:
            print(f"  Using AA snapshot fallback: {len(aa_data)} models (not written as fresh)")
    else:
        print("  No AA update")

    print("\n3. Updating leaderboard fields...")
    # A model missing from a fresh fetch KEEPS its last known score (the owner's
    # rule: stay listed, carry the old value forward). Only a genuinely new
    # observation overwrites a field; nothing is ever nulled out by absence.
    apply_arena = arena_data if arena_fresh else []
    apply_aa = aa_data if aa_fresh else []
    if not arena_fresh:
        print("  Skipping Arena field writes (fetch not fresh)")
    if not aa_fresh:
        print("  Skipping AI Index field writes (no trusted remote refresh)")
    changes = update_leaderboard_fields(models, apply_arena, apply_aa)
    live_arena_keys = set()
    live_aa_slugs = set()
    if arena_fresh:
        live_arena_keys = {row.get("model") or row.get("name") for row in apply_arena}
    if aa_fresh:
        live_aa_slugs = {row.get("slug") or row.get("id") for row in apply_aa}
    # Report (never mutate) how each listed model stands against the two boards.
    missing_arena, missing_aa = [], []
    for model in models:
        mapping = MODEL_MAPPING.get(model.get("name"))
        arena_key, aa_slug = mapping if mapping else (None, None)
        gone = []
        if arena_fresh and arena_key and arena_key not in live_arena_keys:
            missing_arena.append(model.get("name"))
            gone.append("arena")
        if aa_fresh and aa_slug and aa_slug not in live_aa_slugs:
            missing_aa.append(model.get("name"))
            gone.append("aa")
        # Remember which board dropped it, so the row can be labelled stale.
        model["board_missing"] = sorted(gone)
    if missing_arena:
        print(f"  Not on current Arena board ({len(missing_arena)}) — keeping last known rating:")
        for name in missing_arena:
            print(f"    {name}")
    if missing_aa:
        print(f"  Not on current AI Index ({len(missing_aa)}) — keeping last known index:")
        for name in missing_aa:
            print(f"    {name}")
    unaffected = len(models) - len(set(missing_arena) | set(missing_aa))
    print(f"  Models still on both boards: {unaffected}/{len(models)}; none dropped.")
    if changes:
        for c in changes:
            print(c)
    else:
        print("  No leaderboard field changes")

    print("\n4. Refreshing OpenRouter prices/ctx...")
    or_cache: dict = {}
    pchanges = refresh_prices_from_openrouter(models, find_openrouter_key(), or_cache)
    if pchanges:
        for c in pchanges[:20]:
            print(c)
        if len(pchanges) > 20:
            print(f"  ... +{len(pchanges)-20} more")
    else:
        print("  No price changes / fetch skipped")

    print("\n4b. Recomputing multimodal tiers from modality coverage...")
    if or_cache.get("or_models"):
        mchanges = sync_multi_from_openrouter(models, or_cache["or_models"])
        if mchanges:
            print(f"  Updated {len(mchanges)} model(s):")
            for c in mchanges:
                print(c)
        else:
            print("  All tiers already match modality coverage")
    else:
        print("  Skipped (no OpenRouter payload)")

    print("\n5. Recalculating scores from models.json...")
    # Models AA has not scored yet borrow an AI Index from Arena-nearby models
    # so they can still be ranked (labelled `estimated`, never `verified`).
    impute_missing_scores(models, IMPUTE_ARENA_BAND)
    imputed_rows = [m for m in models if m.get("ai_index_imputed")]
    if imputed_rows:
        print(f"  Imputed AI Index for {len(imputed_rows)} model(s) "
              f"(Arena +/-{IMPUTE_ARENA_BAND:g}, labelled estimated):")
        for m in imputed_rows:
            print(f"    {m['name']}: ~{m['ai_index']} "
                  f"(from {m.get('ai_index_neighbours')} neighbours)")
    scored = recalculate_scores(models)
    print("\n  Top 10:")
    for i, m in enumerate(scored[:10]):
        print(
            f"  {i+1:2d}. {m['name']:25s} Arena={m['sArena'] if m['sArena'] is not None else '—':>3} AI={m['sAI']:4.1f} "
            f"Price={m['sPrice']:2d} Multi={m['sMulti']:2d} Ctx={m['sCtx']:2d} "
            f"eff$={m['effective_price_usd']} Total={m['total']:5.1f}"
        )

    print("\n6. Saving...")
    # Record provenance on each row so the site can label verified / estimated /
    # stale without re-deriving it (the site recomputes scores in the browser).
    by_name = {r["name"]: r for r in scored}
    for m in doc["models"]:
        row = by_name.get(m.get("name"))
        if row:
            m["status"] = row["status"]
        elif m.get("arena") is None and m.get("ai_index") is None:
            m["status"] = "stale"
    # Always re-export derived views; models.json only changes if fields changed.
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
    if not arena_fresh:
        summary += " | Arena fetch skipped"
    if not aa_fresh:
        summary += " | AI Index fetch skipped"
    print(f"\n{summary}")
    return summary


if __name__ == "__main__":
    main()
