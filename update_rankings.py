#!/usr/bin/env python3
"""
LLM Ranking Daily Update Script
================================
1. Try to scrape Arena ELO from arena.ai and AI Index from artificialanalysis.ai
2. Match data to existing models using explicit slug mapping
3. Recalculate all scores (matching index.html formulas exactly)
4. Update corrected_models.json and index.html
5. Git commit and push

Both Arena and AA sites use Cloudflare protection, so scraping may fail.
When that happens, the script uses existing data and just recalculates + pushes.
"""

import json, re, math, os, subprocess
from datetime import datetime

REPO = os.path.dirname(os.path.abspath(__file__))
MODELS_JSON = os.path.join(REPO, 'corrected_models.json')
INDEX_HTML = os.path.join(REPO, 'index.html')
ARENA_JSON = os.path.join(REPO, 'data', 'arena_leaderboard_full.json')
AA_JSON = os.path.join(REPO, 'data', 'aa_intelligence_index.json')

# ── Scoring formulas v4 (matching index.html exactly) ──
# Weights: Arena 30% + AI Index 35% + Price 10% + Multimodal 15% + Context 10% = 100%
# Capability-first: dampen cheap-model free wins and pure multimodal tag dominance.

def lin_norm(v, lo, hi):
    if hi == lo:
        return 0.0
    return max(0.0, min(100.0, (v - lo) / (hi - lo) * 100.0))

def percentile_scores(vals):
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

def hybrid(abs_score, perc_score, w_abs=0.65):
    return abs_score * w_abs + perc_score * (1.0 - w_abs)

def score_price(po, p_ref=1.0):
    """Relative to $1/M output. Missing/free -> low neutral (20), not free 100."""
    if po is None or po <= 0:
        return 20
    multiple = max(po / p_ref, 0.05)
    return int(round(max(5, min(100, 100 / (1 + math.log10(multiple * 4))))))

def score_ctx(ctx):
    """Sigmoid centered ~400K. 128K~35, 256K~44, 1M~73, 2M~84."""
    if not ctx or ctx <= 0:
        return 0
    return int(round(100 / (1 + math.exp(-1.1 * (math.log10(ctx) - math.log10(400000))))))

def score_multi(multi):
    """Compress raw multi 50/75/100 -> 70/85/100."""
    return int(round(40 + (multi or 0) * 0.6))

def total_score(s_arena, s_ai, s_price, s_multi, s_ctx):
    return round(s_arena * 0.30 + s_ai * 0.35 + s_price * 0.10 + s_multi * 0.15 + s_ctx * 0.10, 1)


# ── Data scraping (best-effort, sites use Cloudflare) ──

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
                        ct = response.headers.get('content-type', '')
                        body = response.text()
                        if ('json' in ct) and len(body) > 500 and '"rating"' in body:
                            api_data.append(body)
                except:
                    pass
            page.on('response', handle_response)
            page.goto('https://arena.ai/leaderboard', timeout=30000, wait_until='commit')
            page.wait_for_timeout(20000)
            browser.close()
            for body in api_data:
                try:
                    data = json.loads(body)
                    if isinstance(data, list) and len(data) > 10 and 'rating' in data[0]:
                        return data
                except:
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
                        ct = response.headers.get('content-type', '')
                        body = response.text()
                        if ('json' in ct) and len(body) > 500 and 'intelligence_index' in body:
                            api_data.append(body)
                except:
                    pass
            page.on('response', handle_response)
            page.goto('https://artificialanalysis.ai/leaderboards/models', timeout=30000, wait_until='commit')
            page.wait_for_timeout(20000)
            browser.close()
            for body in api_data:
                try:
                    data = json.loads(body)
                    if isinstance(data, list) and len(data) > 10 and 'intelligence_index' in str(data[0]):
                        return data
                except:
                    pass
    except Exception as e:
        print(f"  AA scrape failed: {e}")
    return None


# ── Explicit model slug mapping ──
# Format: display_name -> (arena_model_key, aa_slug)
# Verified against actual data on 2026-06-19

MODEL_MAPPING = {
    "Gemini 3 Flash":       ("gemini-3-flash", "gemini-3-flash-reasoning"),
    "Gemini 3.5 Flash":     ("gemini-3.5-flash", "gemini-3-5-flash"),
    "Gemini 3.1 Pro":       ("gemini-3.1-pro-preview", "gemini-3-1-pro-preview"),
    "Gemini 3 Pro":         ("gemini-3-pro", "gemini-3-pro"),
    "Claude Opus 4.7":      ("claude-opus-4-7", "claude-opus-4-7"),
    "Claude Opus 4.8":      ("claude-opus-4-8", "claude-opus-4-8"),
    "GPT-5.5 High":         ("gpt-5.5-high", "gpt-5-5"),
    "Claude Opus 4.6":      ("claude-opus-4-6", "claude-opus-4-6-adaptive"),
    "GPT-5.4 High":         ("gpt-5.4-high", "gpt-5-4"),
    "GPT-5.5 Instant":      ("gpt-5.5-instant", "gpt-5-5-medium"),
    "DeepSeek V4 Flash":    ("deepseek-v4-flash", "deepseek-v4-flash"),
    "Claude Sonnet 4.6":    ("claude-sonnet-4-6", "claude-sonnet-4-6-adaptive"),
    "GPT-5.5":              ("gpt-5.5", "gpt-5-5-medium"),
    "Grok 4.20":            ("grok-4.20-beta-0309-reasoning", "grok-4-20"),
    "GPT-5.4":              ("gpt-5.4", "gpt-5-4-low"),
    "Qwen3.7 Max":          ("qwen3.7-max-preview", "qwen3-7-max"),
    "GPT-5.2":              ("gpt-5.2-chat-latest-20260210", "gpt-5-2"),
    "DeepSeek V4 Pro":      ("deepseek-v4-pro", "deepseek-v4-pro-high"),
    "GLM-5.2":              ("glm-5.2 (max)", "glm-5-2"),
    "MiMo V2.5":            ("mimo-v2.5", "mimo-v2-5-0424"),
    "Gemini 2.5 Pro":       ("gemini-2.5-pro", "gemini-2-5-pro"),
    "MiMo V2.5 Pro":        ("mimo-v2.5-pro", "mimo-v2-5-pro"),
    "Grok 4.1":             ("grok-4.1", "grok-4-1-fast-reasoning"),
    "GLM-5.1":              ("glm-5.1", "glm-5-1"),
    "MiMo V2 Pro":          ("mimo-v2-pro", "mimo-v2-pro"),
    "Grok 4.3":             ("grok-4.3", "grok-4-3"),
    "GPT-5.1 High":         ("gpt-5.1-high", "gpt-5-1"),
    "Kimi K2.6":            ("kimi-k2.6", "kimi-k2-6"),
    "GLM-5":                ("glm-5", "glm-5"),
    "Qwen3.6 Max":          ("qwen3.6-max-preview", "qwen3-6-max"),
    "Kimi K2.5":            ("kimi-k2.5-thinking", "kimi-k2-5"),
    "GPT-5":                ("gpt-5-high", "gpt-5"),
    "Qwen3.6 Plus":         ("qwen3.6-plus", "qwen3-6-plus"),
    "MiniMax M2.7":         ("minimax-m2.7", "minimax-m2-7"),
    "Grok 4 Fast":          ("grok-4-fast-chat", "grok-4-fast-reasoning"),
    "GLM-4.7":              ("glm-4.7", "glm-4-7"),
    "Qwen3.5-397B":         ("qwen3.5-397b-a17b", "qwen3-5-397b-a17b"),
    "DeepSeek V3.2":        ("deepseek-v3.2", "deepseek-v3-2"),
    "o3":                   ("o3-2025-04-16", "o3"),
    "Muse Spark":           ("muse-spark", "muse-spark"),
    "GPT-5 mini":           ("gpt-5-mini-high", "gpt-5-mini"),
    "MiniMax M2.5":         ("minimax-m2.5", "minimax-m2-5"),
    "Qwen3.5-122B":         ("qwen3.5-122b-a10b", "qwen3-5-122b-a10b"),
    "Gemini 2.5 Flash":     ("gemini-2.5-flash", "gemini-2-5-flash"),
    "DeepSeek V3.1":        ("deepseek-v3.1", "deepseek-v3-1"),
    "Kimi K2 Thinking":     ("kimi-k2-thinking-turbo", "kimi-k2-thinking"),
    "Qwen3.5-27B":          ("qwen3.5-27b", "qwen3-5-27b"),
    "Step 3.5 Flash":       ("step-3.5-flash", "step-3-5-flash"),
    "GPT-4.1":              ("gpt-4.1-2025-04-14", "gpt-4-1"),
    "GLM-4.6":              ("glm-4.6", "glm-4-6"),
    "Qwen3.5-35B":          ("qwen3.5-35b-a3b", "qwen3-5-35b-a3b"),
    "Qwen3 Max":            ("qwen3-max-preview", "qwen3-max"),
    "GLM-4.5":              ("glm-4.5", None),  # No AA data available
    "o1":                   ("o1-2024-12-17", "o1"),
    "Mistral Large 3":      ("mistral-large-3", "mistral-large-3"),
    "Grok 3":               ("grok-3-preview-02-24", "grok-3"),
    "Kimi K2":              ("kimi-k2-0711-preview", "kimi-k2"),
    "GPT-4o":               ("chatgpt-4o-latest-20250326", "gpt-4o"),
    "DeepSeek R1":          ("deepseek-r1", "deepseek-r1"),
    "Claude Haiku 4.5":     ("claude-haiku-4-5-20251001", "claude-3-5-haiku"),
    "Qwen3-235B":           ("qwen3-235b-a22b", "qwen3-235b-a22b-instruct-2507"),
    "DeepSeek V3":          ("deepseek-v3", "deepseek-v3"),
}


def update_models_from_source(models, arena_data, aa_data):
    """Update models with fresh arena/ai_index data from source data files."""
    arena_map = {m['model']: m for m in arena_data}
    aa_map = {m['slug']: m for m in aa_data}

    changes = []
    for m in models:
        name = m['name']
        mapping = MODEL_MAPPING.get(name)
        if not mapping:
            continue
        arena_key, aa_slug = mapping

        # Update Arena rating
        if arena_key in arena_map:
            new_rating = arena_map[arena_key]['rating']
            old_rating = m.get('arena', 0)
            if abs(new_rating - old_rating) > 0.01:
                changes.append(f"  {name}: Arena {old_rating:.2f} -> {new_rating:.2f}")
                m['arena'] = new_rating

        # Update AI Index (exact slug match only)
        if aa_slug and aa_slug in aa_map:
            new_ii = aa_map[aa_slug]['intelligence_index']
            old_ii = m.get('ai_index', 0)
            if abs(new_ii - old_ii) > 0.01:
                changes.append(f"  {name}: AI Index {old_ii:.4f} -> {new_ii:.4f}")
                m['ai_index'] = new_ii

    return changes


def recalculate_scores(models):
    """Recalculate all scores for the models list (Formula v4)."""
    arenas = [m.get('arena', 0) for m in models]
    ais = [m.get('ai_index', 0) for m in models]
    pA = percentile_scores(arenas)
    pI = percentile_scores(ais)
    for i, m in enumerate(models):
        sA = round(hybrid(lin_norm(m.get('arena', 0), 1380, 1520), pA[i], 0.65))
        sAI = round(hybrid(lin_norm(m.get('ai_index', 0), 15, 60), pI[i], 0.65), 1)
        sP = score_price(m.get('po', 0))
        sM = score_multi(m.get('multi', 50))
        sC = score_ctx(m.get('ctx', 0))
        m['sArena'] = int(sA)
        m['sAI'] = sAI
        m['sPrice'] = int(sP)
        m['sMulti'] = int(sM)
        m['sCtx'] = int(sC)
        m['sEco'] = m.get('eco', 0)
        m['total'] = total_score(m['sArena'], m['sAI'], m['sPrice'], m['sMulti'], m['sCtx'])


def generate_models_js(models):
    """Generate the models JavaScript array for index.html."""
    lines = []
    for m in models:
        parts = [
            f"name:\"{m['name']}\"",
            f"vendor:\"{m['vendor']}\"",
            f"r:\"{m['r']}\"",
            f"arena:{m['arena']}",
            f"eco:{m.get('eco', 0)}",
            f"po:{m.get('po', 0)}",
            f"multi:{m.get('multi', 0)}",
            f"ctx:{m.get('ctx', 0)}",
            f"ai_index:{m['ai_index']}",
        ]
        if m.get('note'):
            parts.append(f"note:\"{m['note']}\"")
        parts.append(f"url:\"{m.get('url', '')}\"")
        lines.append("    {" + ",".join(parts) + "}")
    return "const models = [\n" + ",\n".join(lines) + "\n]\n"


def update_index_html(html_content, models_js):
    """Replace the models array in index.html."""
    pattern = r'const models = \[.*?\]\s*\n'
    match = re.search(pattern, html_content, re.DOTALL)
    if match:
        return html_content[:match.start()] + models_js + html_content[match.end():]
    return html_content


def update_subheader(html_content, num_models):
    """Update the subheader with current date and model count."""
    month_year = datetime.now().strftime('%B %Y')
    pattern = r'<p class="sub">.*?</p>'
    replacement = f'<p class="sub">Multi-Dimension Weighted Evaluation · {month_year} · {num_models} Models</p>'
    return re.sub(pattern, replacement, html_content)


def git_commit_push(message):
    """Git add, commit, and push."""
    subprocess.run(['git', 'add', '-A'], cwd=REPO, check=True)
    result = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=REPO)
    if result.returncode == 0:
        print("No changes to commit.")
        return False
    subprocess.run(['git', 'commit', '-m', message], cwd=REPO, check=True)
    subprocess.run(['git', 'push'], cwd=REPO, check=True)
    return True


def main():
    today = datetime.now().strftime('%Y-%m-%d')
    print(f"=== LLM Ranking Update: {today} ===\n")

    # Load existing data
    with open(MODELS_JSON) as f:
        models = json.load(f)
    with open(ARENA_JSON) as f:
        arena_data = json.load(f)
    with open(AA_JSON) as f:
        aa_data = json.load(f)
    print(f"Loaded {len(models)} models, {len(arena_data)} arena, {len(aa_data)} AA")

    # Step 1: Try scraping
    print("\n1. Scraping Arena ELO...")
    new_arena = try_scrape_arena()
    if new_arena:
        arena_data = new_arena
        with open(ARENA_JSON, 'w') as f:
            json.dump(arena_data, f, indent=2, ensure_ascii=False)
        print(f"  Updated: {len(arena_data)} entries")
    else:
        print("  Using existing data")

    print("\n2. Scraping AI Index...")
    new_aa = try_scrape_aa()
    if new_aa:
        aa_data = new_aa
        with open(AA_JSON, 'w') as f:
            json.dump(aa_data, f, indent=2, ensure_ascii=False)
        print(f"  Updated: {len(aa_data)} entries")
    else:
        print("  Using existing data")

    # Step 3: Update values
    print("\n3. Updating model data...")
    changes = update_models_from_source(models, arena_data, aa_data)
    if changes:
        print(f"  {len(changes)} changes:")
        for c in changes:
            print(c)
    else:
        print("  No changes")

    # Step 4: Recalculate
    print("\n4. Recalculating scores...")
    recalculate_scores(models)
    ranked = sorted(models, key=lambda m: m['total'], reverse=True)
    print("\n  Top 10:")
    for i, m in enumerate(ranked[:10]):
        print(f"  {i+1:2d}. {m['name']:25s} Arena={m['sArena']:2d} AI={m['sAI']:4.1f} "
              f"Price={m['sPrice']:2d} Multi={m['sMulti']:2d} Ctx={m['sCtx']:2d} Total={m['total']:5.1f}")

    # Step 5: Save
    print("\n5. Saving files...")
    with open(MODELS_JSON, 'w') as f:
        json.dump(models, f, indent=2, ensure_ascii=False)
    print(f"  Saved {MODELS_JSON}")

    with open(INDEX_HTML) as f:
        html = f.read()
    html = update_index_html(html, generate_models_js(models))
    html = update_subheader(html, len(models))
    with open(INDEX_HTML, 'w') as f:
        f.write(html)
    print(f"  Updated {INDEX_HTML}")

    # Step 6: Git push
    # Always update timestamp so there is something to commit
    with open(os.path.join(REPO, "last_check.txt"), "w") as f:
        f.write(datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ\n"))
    print("\n6. Git push...")
    pushed = git_commit_push(f"update: daily ranking refresh {today}")
    if pushed:
        print(f"  Pushed: update: daily ranking refresh {today}")
    else:
        print("  No changes")

    # Summary
    top3 = ranked[:3]
    summary = f"📊 LLM排名已更新 ({today}): "
    summary += " | ".join([f"#{i+1} {m['name']}({m['total']})" for i, m in enumerate(top3)])
    print(f"\n{summary}")
    return summary


if __name__ == '__main__':
    main()
