#!/usr/bin/env python3
"""
Refresh only the prices, then show what moved.

The full update_rankings.py also touches Arena, AA and the site; this is the
narrow tool for "just re-check pricing". It applies the repo's own rules:
auto_price=false, price_source=manual, deprecated rows and rows without an
openrouter_id are frozen and never rewritten.

    python refresh_prices.py              # apply + report changes
    python refresh_prices.py --dry-run    # report what would change, write nothing
    python refresh_prices.py --json

Exit: 0 ok, 1 OpenRouter unavailable (nothing was written).
"""

from __future__ import annotations

import argparse
import json
import sys

import update_rankings as u


def fmt(v) -> str:
    return "-" if v is None or (isinstance(v, (int, float)) and v < 0) else f"{v:.4f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        or_models = u.fetch_openrouter_models()
    except Exception as e:
        print(f"FATAL: OpenRouter unavailable: {e}", file=sys.stderr)
        return 1

    pmap = u.openrouter_price_map(or_models)
    doc = u.load_doc()
    models = doc["models"]

    moved, frozen, missing = [], [], []
    for m in models:
        if not u.should_auto_refresh_price(m):
            frozen.append(m["name"])
            continue
        oid = m["openrouter_id"]
        src = pmap.get(oid)
        if not src or (src["input"] is None and src["output"] is None):
            missing.append((m["name"], oid))
            continue
        p = m.get("price") or {}
        new = {
            "input": src["input"] if src["input"] is not None else -1,
            "output": src["output"] if src["output"] is not None else -1,
            "cache_read": src["cache_read"] if src["cache_read"] is not None else -1,
            "cache_write": src["cache_write"] if src["cache_write"] is not None else -1,
        }
        old = {k: p.get(k, -1) for k in new}
        if any(abs(float(old[k] if old[k] is not None else -1) - float(new[k])) > 1e-9 for k in new):
            moved.append((m["name"], oid, old, new))

    if args.json:
        print(json.dumps({
            "moved": [{"name": n, "openrouter_id": o, "old": ov, "new": nv} for n, o, ov, nv in moved],
            "frozen": frozen,
            "missing": [{"name": n, "openrouter_id": o} for n, o in missing],
        }, indent=2, ensure_ascii=False))
        return 0

    print(f"OpenRouter: {len(pmap)} models priced\n")
    if moved:
        print(f"PRICE CHANGES ({len(moved)}):")
        for name, oid, old, new in moved:
            print(f"  {name}  ({oid})")
            for k in ("input", "output", "cache_read", "cache_write"):
                o = float(old[k] if old[k] is not None else -1)
                n = float(new[k])
                if abs(o - n) > 1e-9:
                    print(f"     {k:12s} {fmt(o):>9s} -> {fmt(n):>9s}")
    else:
        print("PRICE CHANGES: none - every auto-priced row already matches OpenRouter")

    if missing:
        print(f"\nAUTO-PRICED BUT UNRESOLVABLE ({len(missing)}) - price stays as-is:")
        for name, oid in missing:
            print(f"  {name:26s} openrouter_id={oid}")

    print(f"\nFrozen by rule (auto_price=false / manual / deprecated): {len(frozen)}")
    for name in frozen:
        print(f"  {name}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    if not moved:
        print("\nNothing to write.")
        return 0

    changed = u.refresh_prices_from_openrouter(models, u.find_openrouter_key())
    u.save_doc(doc)
    print(f"\nWrote data/models.json ({len(changed)} row(s) updated).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
