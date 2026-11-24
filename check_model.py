#!/usr/bin/env python3
"""
LLMrank model freshness check.

Answers the one question that matters after a model ships:
"Is <model> scored yet, and where did the number come from?"

Usage:
    python check_model.py GLM-5.4            # any fragment of the name
    python check_model.py glm 5.4 --all      # also list every GLM* row
    python check_model.py --new              # every dual-board model we don't track

Sources, in order of authority:
    Arena  = lmarena-ai/leaderboard-dataset on Hugging Face (text/overall)
    AA     = artificialanalysis.ai/leaderboards/models (rendered RSC payload)
    Price  = OpenRouter /api/v1/models + AA fallback

Exit: 0 found somewhere, 1 not found anywhere, 2 a source failed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata

import update_rankings as u


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).lower()
    s = re.sub(r"[^a-z0-9.]+", "", s)
    return s


def fetch_all() -> dict:
    """Pull the three boards once. Any source that fails is reported, never faked."""
    out: dict = {"errors": []}

    try:
        arena = u.fetch_arena_leaderboard() or []
        out["arena"] = {r["model"]: r for r in arena}
        out["arena_live"] = u.ARENA_FETCHED_LIVE
    except Exception as e:
        out["arena"], out["arena_live"] = {}, False
        out["errors"].append(f"Arena: {e}")

    try:
        aa = u.fetch_aa_intelligence() or []
        out["aa"] = {}
        for r in aa:
            slug = r.get("slug") or r.get("id")
            if not slug:
                continue
            prev = out["aa"].get(slug)
            if prev is None or float(r.get("intelligence_index") or 0) > float(prev.get("intelligence_index") or 0):
                out["aa"][slug] = r
        out["aa_live"] = u.AA_FETCHED_LIVE
    except Exception as e:
        out["aa"], out["aa_live"] = {}, False
        out["errors"].append(f"AA: {e}")

    try:
        orm = u.fetch_openrouter_models()
        out["or"] = {m["id"]: m for m in orm}
    except Exception as e:
        out["or"] = {}
        out["errors"].append(f"OpenRouter: {e}")

    return out


def describe(hits: dict, q: str) -> list[str]:
    lines = []
    for src in ("arena", "aa", "or"):
        rows = hits.get(src) or []
        if not rows:
            lines.append(f"  {src:9s}: not listed")
            continue
        for name, detail in rows:
            lines.append(f"  {src:9s}: {name}{detail}")
    return lines


def search(boards: dict, q: str) -> dict:
    nq = norm(q)
    hits: dict = {"arena": [], "aa": [], "or": []}

    for name, r in (boards.get("arena") or {}).items():
        if nq in norm(name):
            hits["arena"].append((name, f"  · rating {r['rating']:.2f}  org={r.get('organization') or '?'}"))
    for slug, r in (boards.get("aa") or {}).items():
        label = r.get("model") or slug
        if nq in norm(slug) or nq in norm(label):
            ii = r.get("intelligence_index")
            rel = r.get("released") or "?"
            dep = " (deprecated)" if r.get("deprecated") else ""
            hits["aa"].append((f"{label}  [slug {slug}]",
                               f"  · II {ii:.2f}  released {rel}{dep}"))
    for mid, m in (boards.get("or") or {}).items():
        if nq in norm(mid) or nq in norm(m.get("name") or ""):
            p = m.get("pricing") or {}
            def pm(v):
                return "—" if v is None else f"${float(v) * 1_000_000:.4f}"
            hits["or"].append((f"{mid}  ({m.get('name')})",
                               f"  · in {pm(p.get('prompt'))}/M  out {pm(p.get('completion'))}/M  "
                               f"cache_r {pm(p.get('input_cache_read'))}/M"))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?", help="name fragment, e.g. GLM-5.4")
    ap.add_argument("--new", action="store_true", help="list dual-board models we don't track")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--all", action="store_true", help="list every match, not just the best")
    args = ap.parse_args()

    if not args.query and not args.new:
        ap.error("give a model name, or --new")

    boards = fetch_all()
    for err in boards["errors"]:
        print(f"WARN {err}", file=sys.stderr)

    tracked = {m["name"] for m in u.load_doc()["models"]}

    if args.new:
        try:
            cands = __import__("new_models").find_candidates(u.load_doc()["models"])
        except Exception as e:
            print(f"new-model detection failed: {e}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(cands, indent=2, ensure_ascii=False))
            return 0
        if not cands:
            print(f"No new dual-board models (tracking {len(tracked)}).")
            return 0
        print(f"On BOTH boards but not tracked ({len(cands)}):")
        for c in cands:
            print(f"  {c['suggested_name']:30s} Arena={c['arena']:<9} AI={c['ai_index']:<8} slug={c['aa_slug']}")
        return 0

    hits = search(boards, args.query)
    found = any(hits.values())
    ranked = [m for m in u.load_doc()["models"] if norm(args.query) in norm(m["name"])]

    if args.json:
        print(json.dumps({"query": args.query, "boards": hits,
                          "tracked_rows": ranked,
                          "arena_live": boards.get("arena_live"),
                          "aa_live": boards.get("aa_live")}, indent=2, ensure_ascii=False))
        return 0 if found else 1

    print(f"\n=== {args.query} ===")
    print("boards:")
    for line in describe(hits, args.query):
        print(line)

    if ranked:
        print("\nthis repo:")
        for m in ranked:
            mp = u.MODEL_MAPPING.get(m["name"])
            total = None
            try:
                total = next((r["total"] for r in u.recalculate_scores(u.load_doc()["models"])
                              if r["name"] == m["name"]), None)
            except Exception:
                pass
            print(f"  {m['name']:26s} arena={m.get('arena')}  ai_index={m.get('ai_index')}"
                  f"  multi={m.get('multi')}  status={m.get('status') or '?'}"
                  + (f"  total={total}" if total is not None else ""))
            print(f"  {'':26s} mapping arena={mp[0] if mp else None}  aa={mp[1] if mp else None}")
    else:
        print("\nthis repo: no row tracks it")

    if found:
        n_arena = len(hits["arena"])
        n_aa = len(hits["aa"])
        if n_arena and n_aa:
            verdict = "SCORED on both boards — ready to add/refresh"
        elif n_arena:
            verdict = "Arena only — no AI Index yet, can't be ranked without imputation"
        elif n_aa:
            verdict = "AA only — no Arena rating yet, cannot be ranked"
        else:
            verdict = "only priced on OpenRouter — no scores anywhere"
        print(f"\nVERDICT: {verdict}")
        return 0
    print("\nVERDICT: not found on any board")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
