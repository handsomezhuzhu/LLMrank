#!/usr/bin/env python3
"""Detect models that NEWLY appear on BOTH leaderboards at once.

The owner's rule: a model joins the ranking only when both the Arena board and
the Artificial Analysis Intelligence Index list it. This tool finds exactly those
candidates and never edits data/models.json itself — it prints a proposal.

Usage (from the repo root):

    python3 new_models.py                 # human-readable report
    python3 new_models.py --json          # machine-readable proposal
    python3 new_models.py --json -o out.json

Exit codes: 0 = ran fine (candidates may or may not exist), 1 = a data source
failed and no conclusion can be drawn.

On exit 0 with candidates, the caller decides whether to add them. Adding means:
pick a display name, add both a `MODEL_MAPPING` entry and a `models.json` row
(see --json output for the exact arena/ai_index values to carry over).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata

import update_rankings as u

# AA lists one row per reasoning-effort variant (…-low, …-high, …-xhigh,
# …-non-reasoning). For "is this model on the board?" collapse them to the base
# slug and keep the best score.
_VARIANT_SUFFIX = re.compile(
    r"-(low|medium|high|xhigh|minimal|none|non-reasoning|non_reasoning|"
    r"thinking|thinking-\d+|reasoning)$"
)

# Vendor noise that differs between the two boards ("-preview", "-it", dates).
_NAME_NOISE = re.compile(
    r"(-preview|-it|-instruct|-\d{2}-\d{2}|-\d{4}\d{2}\d{2}|:\s*free|\bfree\b)$"
)


def _base_slug(slug: str) -> str:
    """Collapse an AA variant slug to the model it belongs to."""
    base = slug
    while True:
        stripped = _VARIANT_SUFFIX.sub("", base)
        if stripped == base:
            return base
        base = stripped


def _normalize_name(name: str) -> str:
    """Loose key for matching a display name across boards."""
    s = unicodedata.normalize("NFKD", str(name)).lower().strip()
    s = s.replace("&", " and ")
    s = re.sub(r"\(.*?\)", " ", s)          # drop "(High)"-style qualifiers
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    while True:
        stripped = _NAME_NOISE.sub("", s)
        if stripped == s:
            break
        s = stripped
    return s


def collect_arena() -> dict[str, dict]:
    """model-key -> {name, rating} for the current Arena overall board."""
    rows = u.fetch_arena_leaderboard()
    if not rows:
        raise RuntimeError(
            "Arena board unavailable (HF snapshot fetch/validation failed)"
        )
    out: dict[str, dict] = {}
    for r in rows:
        name = r.get("model")
        if not name:
            continue
        key = _normalize_name(name)
        prev = out.get(key)
        if prev is None or float(r["rating"]) > float(prev["rating"]):
            out[key] = {"name": name, "rating": float(r["rating"]),
                        "organization": r.get("organization", "")}
    return out


def collect_aa() -> dict[str, dict]:
    """base-slug -> {name, ai_index, best_slug} for the AA index.

    Only a *live* fetch counts; a stale on-disk snapshot must not be used to
    argue that something is on the board today.
    """
    rows = u.fetch_aa_intelligence()
    if not rows or not u.AA_FETCHED_LIVE:
        raise RuntimeError(
            "AI Index unavailable (no trusted live refresh; local cache is not evidence)"
        )
    out: dict[str, dict] = {}
    for r in rows:
        slug = r.get("slug") or r.get("id")
        score = r.get("intelligence_index")
        if not slug or score is None:
            continue
        base = _base_slug(str(slug))
        prev = out.get(base)
        if prev is None or float(score) > float(prev["ai_index"]):
            out[base] = {
                "name": r.get("model") or slug,
                "ai_index": float(score),
                "best_slug": str(slug),
            }
    return out


def _aliases(model: dict) -> set[str]:
    """Every normalized key under which an existing model may appear."""
    keys = set()
    for field in ("name", "id", "slug", "openrouter_id"):
        val = model.get(field)
        if not val:
            continue
        val = str(val).split("/")[-1]        # openrouter_id: vendor/model
        keys.add(_normalize_name(val))
        keys.add(_normalize_name(_base_slug(val)))
    mapping = u.MODEL_MAPPING.get(model.get("name") or "")
    if mapping:
        arena_key, aa_slug = mapping
        if arena_key:
            keys.add(_normalize_name(arena_key))
        if aa_slug:
            keys.add(_normalize_name(_base_slug(str(aa_slug))))
    return {k for k in keys if k}


def find_candidates(models: list[dict]) -> list[dict]:
    """Models on both boards that the ranking does not carry yet."""
    arena = collect_arena()
    aa = collect_aa()

    known: set[str] = set()
    for m in models:
        known |= _aliases(m)
    # A mapping that already exists for a retired model still counts as known.
    for display, (arena_key, aa_slug) in u.MODEL_MAPPING.items():
        known.add(_normalize_name(display))
        if arena_key:
            known.add(_normalize_name(arena_key))
        if aa_slug:
            known.add(_normalize_name(_base_slug(str(aa_slug))))

    found = []
    for key, a_row in arena.items():
        if key in known:
            continue
        aa_row = aa.get(key)
        if not aa_row:
            # Try a looser pass: AA base slug contained in the Arena key or vice versa.
            hits = [
                (k, v) for k, v in aa.items()
                if k == key or (len(k) > 6 and (k in key or key in k))
            ]
            if len(hits) != 1:
                continue
            key, aa_row = hits[0]
            if key in known:
                continue
        found.append({
            "suggested_name": a_row["name"],
            "arena": round(a_row["rating"], 4),
            "ai_index": round(aa_row["ai_index"], 4),
            "arena_org": a_row.get("organization", ""),
            "aa_slug": aa_row["best_slug"],
            "match_key": key,
        })
    found.sort(key=lambda c: c["ai_index"], reverse=True)
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="print a JSON proposal")
    ap.add_argument("-o", "--output", help="write the proposal to this path too")
    args = ap.parse_args()

    doc = u.load_doc()
    models = doc["models"]
    try:
        candidates = find_candidates(models)
    except RuntimeError as e:
        print(f"new_models: {e}", file=sys.stderr)
        return 1

    payload = {
        "checked_at": u.datetime.now(u.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tracked_models": len(models),
        "candidates": candidates,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        if not candidates:
            print(f"No new dual-board models (tracked {len(models)}).")
        else:
            print(f"NEW on both boards ({len(candidates)}):")
            for c in candidates:
                print(f"  {c['suggested_name']:32s} Arena={c['arena']:<9} "
                      f"AI={c['ai_index']:<7} slug={c['aa_slug']}")
            print("\nThese are proposals only; add a MODEL_MAPPING entry and a "
                  "models.json row to admit one.")
    if args.output:
        with open(args.output, "w") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
