#!/usr/bin/env python3
"""
Audit MODEL_MAPPING / openrouter_id against the live boards.

Catches the failure mode this repo hit: a typo'd slug makes a model look
"not on the board", so its score silently freezes forever while every run
still reports success.

    python audit_mappings.py            # report only
    python audit_mappings.py --fix      # rewrite the three slug typos in place

Checks
  1. aa slug with no exact match on AA  -> maybe a typo, proposes a near match
  2. arena alias with no exact match    -> alias will never apply
  3. unresolved mappings (no row in models.json is harmless; a *ranked* row
     with a broken slug is not)
  4. openrouter_id that resolves to a differently-named model
  5. openrouter_id missing from OpenRouter entirely

Exit: 0 clean, 1 problems found, 2 a source failed.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys

import update_rankings as u

# Confirmed corrections found by this audit (literal slug typos).
KNOWN_FIXES = {
    "solar-pro4": "solar-pro-4",
    "step-5": "step-5-preview",
    "nvidia-nemotron-3-ultra-550b-a55b": "nemotron-3-ultra-550b-a55b",
}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


_EFFORT_SUFFIXES = ("non-reasoning", "reasoning", "minimal", "medium", "xhigh", "high", "max", "low", "none")


def _base(slug: str) -> str:
    """Strip one reasoning-effort suffix ('kimi-k3-low' -> 'kimi-k3')."""
    s = str(slug)
    for suf in _EFFORT_SUFFIXES:
        if s.endswith("-" + suf):
            return s[: -(len(suf) + 1)]
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fix", action="store_true", help="apply KNOWN_FIXES to update_rankings.py")
    args = ap.parse_args()

    try:
        arena_rows = u.fetch_arena_leaderboard() or []
    except Exception as e:
        print(f"FATAL: Arena unavailable: {e}", file=sys.stderr)
        return 2
    if not arena_rows:
        print("FATAL: Arena unavailable", file=sys.stderr)
        return 2
    try:
        aa_rows = u.fetch_aa_intelligence() or []
    except Exception as e:
        print(f"FATAL: AA unavailable: {e}", file=sys.stderr)
        return 2
    if not aa_rows:
        print("FATAL: AA unavailable", file=sys.stderr)
        return 2

    arena = {r["model"] for r in arena_rows}
    aa_slugs = {(r.get("slug") or "") for r in aa_rows}
    aa_by_slug = {(r.get("slug") or ""): r for r in aa_rows}

    doc = u.load_doc()
    ranked = {m["name"] for m in doc["models"]}
    problems = 0

    print("1. AA slugs that do not exist on the live index")
    print("   (typed wrongly / AA retired it — either way the score cannot refresh)")
    # AA's API keys records by base slug (effort suffix stripped), so a mapping
    # of "kimi-k3" must match the record published as "kimi-k3-low".
    aa_bases = {_base(s) for s in aa_slugs if s}
    unresolved_ranked = []
    for name, (arena_key, slug) in u.MODEL_MAPPING.items():
        if not slug or slug in aa_slugs or _base(slug) in aa_bases:
            continue
        if name in ranked:
            problems += 1
            unresolved_ranked.append(name)
        mark = "RANKED  " if name in ranked else "retired "
        note = ""
        if slug in KNOWN_FIXES:
            r = aa_by_slug.get(KNOWN_FIXES[slug]) or {}
            note = (f"  CONFIRMED TYPO -> {KNOWN_FIXES[slug]!r} "
                    f"(II={r.get('intelligence_index')}, {r.get('model')!r})")
        print(f"   {mark}{name:26s} slug={slug:36s}{note}")
    if not unresolved_ranked:
        print("   none affecting a ranked row")

    print("\n2. Arena aliases that do not exist on the live board")
    missing_arena = 0
    for name, (arena_key, slug) in u.MODEL_MAPPING.items():
        if not arena_key or arena_key in arena:
            continue
        missing_arena += 1
        mark = "RANKED  " if name in ranked else "retired "
        near = difflib.get_close_matches(arena_key, arena, n=1, cutoff=0.85)
        hint = f"  maybe {near[0]!r}" if near else ""
        print(f"   {mark}{name:26s} arena={arena_key:40s}{hint}")
        if name in ranked:
            problems += 1
    if not missing_arena:
        print("   none")

    print("\n3. openrouter_id resolving to a different model")
    try:
        orm = {m["id"]: m for m in u.fetch_openrouter_models()}
    except Exception as e:
        print(f"   (skipped: OpenRouter unavailable: {e})")
        orm = {}

    # A vendored alias is fine when it is the *only* listing for that model:
    # `openai/gpt-5.5` is the price proxy for GPT-5.5 Instant because OpenRouter
    # publishes no Instant SKU. Only flag an id whose price visibly disagrees
    # with what the row already stores - that is the symptom of a real mismatch.
    for m in doc["models"]:
        oid = m.get("openrouter_id")
        if not oid or oid not in orm:
            continue
        orname = norm(orm[oid].get("name") or "")
        own = norm(m["name"])
        if own in orname or orname in own:
            continue
        price = m.get("price") or {}
        live = orm[oid].get("pricing") or {}

        def per_m(v):
            try:
                return round(float(v) * 1_000_000, 6)
            except (TypeError, ValueError):
                return None

        stored_in, live_in = price.get("input"), per_m(live.get("prompt"))
        agrees = (stored_in is not None and live_in is not None
                  and abs(float(stored_in) - live_in) < 0.01)
        if agrees:
            print(f"   RANKED  {m['name']:26s} openrouter_id={oid!r} is {orm[oid].get('name')!r}"
                  f" — vendored alias, price agrees, OK")
        else:
            problems += 1
            print(f"   RANKED  {m['name']:26s} openrouter_id={oid!r} is really "
                  f"{orm[oid].get('name')!r} — price will be grafted from the wrong model")

    print("\n4. openrouter_id absent from OpenRouter (price frozen silently)")
    for m in doc["models"]:
        oid = m.get("openrouter_id")
        if oid and orm and oid not in orm:
            problems += 1
            print(f"   RANKED  {m['name']:26s} openrouter_id={oid!r} not found")

    print()
    if not problems:
        print("RESULT: clean")
        return 0

    print(f"RESULT: {problems} problem(s)")
    if args.fix:
        src_path = u.__file__
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        changed = 0
        for old, new in KNOWN_FIXES.items():
            pat = f'"{old}"'
            if pat in src:
                src = src.replace(pat, f'"{new}"')
                changed += 1
                print(f"  fixed {old} -> {new}")
        if changed:
            with open(src_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(src)
            print(f"  wrote {src_path}")
    else:
        print("  re-run with --fix to apply the confirmed slug corrections")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
