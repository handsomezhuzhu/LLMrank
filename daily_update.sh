#!/usr/bin/env bash
# Daily LLMrank refresh, meant to be called from a scheduled job.
#
#   ./daily_update.sh            # pull, update, push, report
#   ./daily_update.sh --dry-run  # update locally but never push
#   ./daily_update.sh --no-pull  # use the checkout as-is
#
# Output is written for an agent (or a human) to read and decide whether to
# notify anyone. Sections:
#   RESULT: ok | no-change | failed
#   NEW_MODELS: ...     (candidates found on BOTH boards, not yet ranked)
#   SUMMARY: ...        (top-3 line printed by update_rankings.py)
#   CHANGED_FILES: ...
#
# Exit codes: 0 ok/no-change, 1 a data source failed, 2 environment problem.

set -uo pipefail

REPO_DIR="${LLMRANK_DIR:-/root/.llmrank-repo}"
DRY_RUN=0
NO_PULL=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --no-pull) NO_PULL=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

fail() { echo "RESULT: failed"; echo "REASON: $*"; exit "${2:-1}"; }

[ -d "$REPO_DIR/.git" ] || fail "repo not found at $REPO_DIR (set LLMRANK_DIR)" 2
cd "$REPO_DIR" || fail "cannot cd to $REPO_DIR" 2

# A previous run that died mid-way must not brick this one, but never throw away
# work: keep the leftover changes as a stash instead of a hard reset.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  STASH_TAG="llmrank-leftover-$(date -u +%Y%m%dT%H%M%SZ)"
  git stash push -q -m "$STASH_TAG" || fail "cannot stash leftover changes" 2
  echo "NOTE: stashed leftover tracked changes as '$STASH_TAG'"
fi

if [ "$NO_PULL" -eq 0 ]; then
  git pull --ff-only --quiet >/dev/null 2>&1 || echo "NOTE: git pull failed; continuing on the local checkout"
fi

echo "=== update_rankings.py ==="
DRY_BASE="$(git rev-parse HEAD)"
if [ "$DRY_RUN" -eq 1 ]; then
  # Commit locally, never push, then undo exactly that commit afterwards.
  UPDATE_LOG="$(LLMRANK_NO_PUSH=1 python3 update_rankings.py 2>&1)"
else
  UPDATE_LOG="$(python3 update_rankings.py 2>&1)"
fi
UPDATE_CODE=$?
echo "$UPDATE_LOG"
if [ $UPDATE_CODE -ne 0 ]; then
  # The updater commits at the end; a failure after saving still leaves changes.
  echo "CHANGED_FILES:"
  git status --porcelain
  [ "$DRY_RUN" -eq 1 ] && git reset --quiet --hard "$DRY_BASE"
  fail "update_rankings.py exited $UPDATE_CODE"
fi
if [ "$DRY_RUN" -eq 1 ]; then
  echo "CHANGED_FILES (dry-run, local commit only):"
  git diff --stat "$DRY_BASE" HEAD
  # Undo only the commit this run made, back to the exact starting point.
  git reset --quiet --hard "$DRY_BASE"
fi

SUMMARY="$(printf '%s\n' "$UPDATE_LOG" | grep -E '^📊 LLM排名已更新' | tail -1)"
[ -n "$SUMMARY" ] || SUMMARY="(no summary line produced)"

echo
echo "=== new_models.py ==="
NEW_LOG="$(python3 new_models.py --json 2>&1)"
NEW_CODE=$?
NEW_COUNT=0
NEW_LINES=""
if [ $NEW_CODE -ne 0 ]; then
  echo "$NEW_LOG"
  NEW_COUNT=-1
else
  NEW_COUNT="$(printf '%s' "$NEW_LOG" | python3 -c '
import json, sys
try:
    print(len((json.load(sys.stdin).get("candidates") or [])))
except Exception:
    print(0)
')"
  if [ "$NEW_COUNT" -gt 0 ]; then
    NEW_LINES="$(printf '%s' "$NEW_LOG" | python3 -c '
import json, sys
for c in (json.load(sys.stdin).get("candidates") or []):
    print("  - {} (Arena {}, AI {}, slug {})".format(
        c["suggested_name"], c["arena"], c["ai_index"], c["aa_slug"]))
')"
  fi
fi

echo
echo "SUMMARY: $SUMMARY"
echo "NEW_MODELS: $NEW_COUNT candidate(s)"
[ -n "$NEW_LINES" ] && printf '%s\n' "$NEW_LINES"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "CHANGED_FILES (dry-run, not pushed):"
  git status --porcelain
  echo "RESULT: ok"
  exit 0
fi

echo "CHANGED_FILES:"
if [ -n "$(git log origin/main..HEAD --oneline 2>/dev/null)" ]; then
  git log origin/main..HEAD --oneline
  echo "RESULT: ok"
else
  echo "  (none)"
  echo "RESULT: no-change"
fi
exit 0
