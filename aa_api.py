#!/usr/bin/env python3
"""
Artificial Analysis — official Data API client.

Replaces the HTML/RSC scraping in update_rankings.py. The legacy
`/api/v2/data/*` endpoints returned 410 Gone on 2026-11-04; the documented
replacement is `/api/v2/language/models`, and its *free* variant
(`/models/free`) is enough for this project: model list, Intelligence Index,
input/output prices.

Auth: the key is read from the environment only. It is never written to the
repo, models.json, or any log.

    AA_API_KEY=xxxx python aa_api.py            # report + verify
    AA_API_KEY=xxxx python aa_api.py --json
    AA_API_KEY=xxxx python aa_api.py --apply    # write measured indices

Free tier: 100 requests/24h. A full refresh is 4 pages, so ~25 runs/day.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

import update_rankings as u

BASE = "https://artificialanalysis.ai/api/v2/language/models"
FREE = BASE + "/free"
PAGE_SIZE = 200
MAX_PAGES = 10
KEY_ENV = "AA_API_KEY"

# The free tier allows 100 requests per rolling 24h and one refresh costs 4
# pages, so repeated calls in a day would burn the quota fast. Cache the raw
# payload for CACHE_HOURS and reuse it; a daily job still sees fresh data.
CACHE_PATH = os.path.join(u.REPO, ".aa_api_cache.json")
CACHE_HOURS = 6


def _load_cache() -> list[dict] | None:
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            blob = json.load(f)
        age = time.time() - float(blob.get("fetched_at", 0))
        if age <= CACHE_HOURS * 3600 and isinstance(blob.get("rows"), list):
            return blob["rows"]
    except Exception:
        pass
    return None


def _save_cache(rows: list[dict]) -> None:
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({"fetched_at": time.time(), "rows": rows}, f)
    except OSError:
        pass

# One AA slug carries a row per reasoning effort. Rank them so "the strongest"
# is picked deterministically instead of "whichever we saw last".
EFFORT_RANK = {"non-reasoning": 0, "low": 1, "medium": 2, "high": 3, "xhigh": 4, "max": 5}


def api_key() -> str | None:
    key = os.environ.get(KEY_ENV)
    return key.strip() if key and key.strip() else None


def _get(url: str, key: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers={"x-api-key": key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read()[:300].decode("utf-8", "replace")
        if e.code == 401:
            raise RuntimeError(f"AA API rejected the key (401): {body}") from e
        if e.code == 403:
            raise RuntimeError(
                f"AA API: your tier does not cover this endpoint (403): {body}\n"
                f"         the model *list* needs Pro; the free list is /language/models/free"
            ) from e
        if e.code == 429:
            raise RuntimeError(
                f"AA API daily quota exhausted (429). Retry-After={e.headers.get('Retry-After')}s"
            ) from e
        raise RuntimeError(f"AA API {e.code}: {body}") from e


def fetch_models(key: str, free: bool = True, use_cache: bool = True) -> list[dict]:
    """Every row AA publishes, paginated. 4 pages on the free tier."""
    if use_cache:
        cached = _load_cache()
        if cached:
            print(f"  AA API cache hit: {len(cached)} rows (<= {CACHE_HOURS}h old)")
            return cached

    rows: list[dict] = []
    page = 1
    while page <= MAX_PAGES:
        url = f"{FREE if free else BASE}?page={page}&page_size={PAGE_SIZE}"
        data = _get(url, key)
        chunk = data.get("data") or []
        rows.extend(chunk)
        pag = data.get("pagination") or {}
        if not pag.get("has_more") or not chunk:
            break
        page += 1
    if rows and use_cache:
        _save_cache(rows)
    return rows


def _effort(slug: str) -> str:
    for suffix in EFFORT_RANK:
        if str(slug).endswith("-" + suffix):
            return suffix
    return "max"  # unsuffixed slug = the model's headline row


_EFFORT_SUFFIX = ("non-reasoning", "reasoning", "minimal", "medium", "xhigh", "high", "max", "low", "none")


def _base_slug(slug: str) -> str:
    """'kimi-k3-low' -> 'kimi-k3'  (strip one reasoning-effort suffix)."""
    s = str(slug)
    for suf in _EFFORT_SUFFIX:
        if s.endswith("-" + suf):
            return s[: -(len(suf) + 1)]
    return s


def to_records(rows: list[dict]) -> list[dict]:
    """Flatten API rows into the shape update_rankings expects.

    One record per *base* slug, because that is what MODEL_MAPPING points at.

    Effort selection is the subtle part. AA publishes a row per reasoning
    effort, and a single model can be scored at one effort and null at another
    (Kimi K3: `kimi-k3` is null, `kimi-k3-low`=17.4; Grok 4.6 is the reverse,
    only `grok-4-6-xhigh`=31). So:
      1. the unsuffixed slug wins if it is scored (it is AA's headline row);
      2. otherwise take the highest *scored* effort;
      3. the effort actually used is recorded in `aa_effort` so a surprising
         pick is visible rather than silent.
    """
    families: dict[str, list[dict]] = {}
    for m in rows:
        slug = m.get("slug")
        if not slug:
            continue
        families.setdefault(_base_slug(slug), []).append(m)

    out: list[dict] = []
    for base, members in families.items():
        scored = []
        for m in members:
            ev = m.get("evaluations") or {}
            ii = ev.get("artificial_analysis_intelligence_index")
            if isinstance(ii, (int, float)):
                scored.append(m)
        if not scored:
            continue
        # Prefer AA's headline row (exact base slug), else the strongest effort.
        pick = next((m for m in scored if m["slug"] == base), None)
        if pick is None:
            pick = max(scored, key=lambda m: EFFORT_RANK.get(_effort(m["slug"]), 9))
        ev = pick.get("evaluations") or {}
        pri = pick.get("pricing") or {}
        out.append({
            "slug": pick["slug"],
            "base_slug": base,
            "model": pick.get("name") or base,
            "intelligence_index": float(ev["artificial_analysis_intelligence_index"]),
            "deprecated": False,
            "released": pick.get("release_date"),
            "aa_effort": _effort(pick["slug"]),
            "price_input": pri.get("price_1m_input_tokens"),
            "price_output": pri.get("price_1m_output_tokens"),
            "cache_read": pri.get("price_1m_cache_hit_tokens"),
            "cache_write": pri.get("price_1m_cache_write_tokens"),
            "intelligence_index_cost_per_task": (
                ((pick.get("artificial_analysis_intelligence_index_cost") or {})
                 .get("cost_per_task") or {}).get("total_cost")
            ),
        })
    return out


def fetch_aa_api(key: str | None = None, free: bool = True) -> list[dict] | None:
    """Drop-in replacement for update_rankings.fetch_aa_intelligence()."""
    key = key or api_key()
    if not key:
        return None
    try:
        raw = fetch_models(key, free=free)
    except Exception as e:
        print(f"  AA API fetch failed: {e}")
        return None
    records = to_records(raw)
    if len(records) < u.MIN_AA_ROWS:
        print(f"  AA API returned only {len(records)} scored models - treated as incomplete")
        return None
    print(f"  AA API ok: {len(records)} scored models from {len(raw)} rows")
    return records


def verify(models: list[dict], records: list[dict]) -> dict:
    """Compare stored ai_index values against the API. Nothing is written."""
    by_base = {r["base_slug"]: r for r in records}
    by_slug = {r["slug"]: r for r in records}
    same, diff, absent, imputed = [], [], [], []
    for m in models:
        mapping = u.MODEL_MAPPING.get(m["name"])
        slug = mapping[1] if mapping else None
        if not slug:
            continue
        rec = by_slug.get(slug) or by_base.get(_base_slug(slug))
        stored = m.get("ai_index")
        if rec is None:
            absent.append(m["name"])
            continue
        if abs(rec["intelligence_index"] - float(stored or 0)) > 0.05:
            diff.append({"name": m["name"], "slug": slug,
                         "stored": stored, "api": rec["intelligence_index"],
                         "aa_effort": rec.get("aa_effort"),
                         "was_imputed": bool(m.get("ai_index_imputed"))})
        else:
            same.append(m["name"])
        if m.get("ai_index_imputed"):
            imputed.append(m["name"])
    return {"same": same, "diff": diff, "absent": absent, "imputed": imputed}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--apply", action="store_true", help="write measured indices into models.json")
    ap.add_argument("--pro", action="store_true", help="use the Pro endpoint instead of /free")
    ap.add_argument("--no-cache", action="store_true", help="force a fresh fetch (costs 4 requests)")
    args = ap.parse_args()

    if not api_key():
        print(f"FATAL: {KEY_ENV} is not set. The key lives in the environment, never in the repo.",
              file=sys.stderr)
        return 2

    try:
        raw = fetch_models(api_key(), free=not args.pro, use_cache=not args.no_cache)
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 1
    records = to_records(raw)
    if len(records) < u.MIN_AA_ROWS:
        print(f"FATAL: only {len(records)} scored models - payload looks incomplete", file=sys.stderr)
        return 1
    print(f"AA API: {len(records)} scored models from {len(raw)} rows")

    doc = u.load_doc()
    report = verify(doc["models"], records)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    print(f"\nmatched {len(report['same'])}, differing {len(report['diff'])}, "
          f"not in API {len(report['absent'])}")

    if report["diff"]:
        print("\nDIFFERENCES (stored -> API):")
        for d in report["diff"]:
            tag = "  [stored value was IMPUTED]" if d["was_imputed"] else ""
            print(f"  {d['name']:24s} {float(d['stored'] or 0):7.2f} -> {d['api']:7.2f}{tag}")

    if report["imputed"]:
        print(f"\nIMPUTED rows ({len(report['imputed'])}) - replace with measured values when possible:")
        for n in report["imputed"]:
            print(f"  {n}")

    if report["absent"]:
        print(f"\nNOT IN API ({len(report['absent'])}) - AA publishes no index; stored value stands:")
        for n in report["absent"]:
            print(f"  {n}")

    if not args.apply:
        print("\nReport only. Re-run with --apply to write the measured values.")
        return 0

    by_base = {r["base_slug"]: r for r in records}
    by_slug = {r["slug"]: r for r in records}
    written = 0
    for m in doc["models"]:
        mapping = u.MODEL_MAPPING.get(m["name"])
        slug = mapping[1] if mapping else None
        if not slug:
            continue
        rec = by_slug.get(slug) or by_base.get(_base_slug(slug))
        if not rec:
            continue
        if abs(rec["intelligence_index"] - float(m.get("ai_index") or 0)) > 0.05:
            m["ai_index"] = rec["intelligence_index"]
            m.pop("ai_index_imputed", None)
            m.pop("ai_index_neighbours", None)
            m["ai_index_source"] = "aa-api"
            m["ai_index_aa_slug"] = rec["slug"]
            written += 1
    if written:
        u.save_doc(doc)
        print(f"\nWrote {written} measured value(s) to data/models.json")
    else:
        print("\nNothing to write; every stored value already matches the API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
