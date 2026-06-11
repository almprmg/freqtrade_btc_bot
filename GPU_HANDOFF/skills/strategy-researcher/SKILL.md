---
name: strategy-researcher
description: Crypto strategy researcher who mines the experiment archive (3500+ backtests) and live trade database to discover patterns. Identifies what factors are SHARED across winning strategies vs losing ones, finds common-mechanism hypotheses, merges archive data with current performance to surface non-obvious insights. Use when user asks "analyze what's working", "find common factors", "mine the archive", "what do winners share", "data-driven new ideas", "compare strategies historically". This is the discovery engine — pattern detection, not building.
---

# Strategy Researcher — Archive Miner & Factor Discoverer

The research skill. Mines the experiment archive + live trade DB to surface patterns invisible from single-strategy analysis.

For DESIGN context, use `strategy-architect`.
For BUILDING bots, use `bot-builder`.
For VALIDATION, use `strategy-critic`.
For NEW HYPOTHESES, use `strategy-explorer` (which often calls THIS skill first).

## When to invoke

- "Mine the backtest archive"
- "What factors do our winning strategies share?"
- "Analyze the experiments from the last session"
- "Compare BTC strategies vs ETH strategies"
- "Find common patterns across passing strategies"
- "What do losers have in common?"
- "Audit historical performance"
- "Merge backtest data with live trade results"

## Data sources

### 1. experiment_logger archive
Location: `d:/pythone/freqtrade_btc_bot/research/experiments/`
- `INDEX.csv` — one row per backtest with: timestamp, strategy, mode, pair, timerange, n_trades, win_rate, roi, max_dd, sharpe, sortino, profit_factor, calmar, total_pnl, run_dir, notes
- Per-run folders: `<timestamp>__<strategy>__<mode>__<pair>/` containing:
  - `metadata.json` — summary
  - `trades.csv` — every individual trade
  - `orders.csv` — every order
  - `raw_payload.json` — full freqtrade output

### 2. freqtrade native backtest zips
Location: `d:/pythone/freqtrade_btc_bot/user_data/backtest_results/`
- ~2600 zip files
- Each has `results_per_pair` with per-coin breakdown

### 3. Live trade DB
- `trad_pg` (PostgreSQL on trad-server)
- Table: `trades` (synced from each bot's SQLite via bridge containers)
- Columns: subscription_id, opened_at, closed_at, status, pnl, unrealized_pnl, entry_price, exit_price, etc.

## Research playbooks

### Playbook 1: "What do winners share?"

Goal: find common factors across PASS-adversarial strategies.

```python
# Pseudo-code (see playbooks/find_common_factors.py)
1. Load INDEX.csv
2. Filter to recent runs (last 30 days)
3. Group by strategy
4. For each strategy: compute pass/warn/fail/cat counts across windows
5. Identify "winners" = strategies with PASS rate > 60% across windows
6. For winners, extract:
   - Common indicator patterns from source code
   - Common N_CONFIRM values
   - Common position sizing magnitudes
   - Common entry/exit conditions
7. For losers: same extraction
8. Diff: what's PRESENT in winners but ABSENT in losers, and vice versa
```

Output: markdown report ranking shared factors by frequency.

### Playbook 2: "Cross-coin transfer report"

Goal: identify which features port across coins and which don't.

```python
1. Find strategies that ran on ≥ 2 coins
2. For each (strategy, coin_A, coin_B):
   - Compute adversarial verdict on coin_A
   - Compute adversarial verdict on coin_B
   - If same verdict → strategy ports
   - If different → identify which features made the difference
3. Build matrix: features × ports/doesn't_port
```

Output: `transfer_report.md` with feature-portability ranking.

### Playbook 3: "Live vs backtest delta"

Goal: detect when live behavior diverges from backtest.

```python
1. For each live bot:
   - Backtest expected: latest mode-Y_2025/2026 from INDEX.csv
   - Live actual: query trad_pg for that subscription_id, last 90d
   - Compute: |live_roi - backtest_expected| / backtest_expected
   - Flag if > 50% divergence
2. For flagged bots, dig into trades.csv to find WHEN divergence started
3. Output: "Bot X started underperforming on Y date, possible cause: Z"
```

This is the highest-value playbook once 30+ days of live data exist.

### Playbook 4: "Yearly window heatmap"

Goal: visualize which strategies survive which years.

```python
1. Load all yearly mode entries from INDEX.csv (mode patterns: "Y_2021", "2022", "SOL_VOL3_2025", etc.)
2. Build matrix: rows = strategies, cols = years (2021-2026Q12), values = ROI %
3. Color-code: green > 0, red < -10, dark-red < -30
4. Sort strategies by total compound (best at top)
```

Output: ascii heatmap + CSV.

### Playbook 5: "Bug detection"

Goal: find strategies whose live behavior shows bugs.

```python
1. For each live bot, query trad_pg trades:
   - Avg trade duration → if < 1 day on 1d strategy, regime detection is whipsawing
   - Trade count vs backtest expectation → if 3x higher, entry conditions too loose
   - Win rate divergence → if backtest 70% but live 30%, something's wrong
2. Cross-reference with strategy file to identify candidate bugs:
   - String-rolling errors (pandas can't .rolling() strings)
   - Path resolution failures (auxiliary data not loading)
   - Anomaly-coin filter mismatch (using BTC anomalies for ETH bot)
```

## Common factor patterns to look for

From the major session, these factors correlated with PASS adversarial:

| Factor | Present in PASS rate | Absent in FAIL rate |
|---|---|---|
| N_CONFIRM ≥ 3 | 100% | (none of FAILs lacked it) |
| BEAR exit logic | 88% | 40% |
| Anomaly circuit breaker | 75% | 60% |
| ret_60d filter | 60% | 30% |
| Calendar tilts | 100% (n=2) | (none) |
| Phase shifts (BTC-only) | 100% (n=3) | (none on BTC) |
| ADX > 25 (vs 20) | 50% | 20% |

These ARE the kind of insights the researcher skill should surface — but EACH time it runs, regenerate against fresh data. Patterns shift.

## Anti-patterns in research

### Don't claim causation from correlation alone

"Strategies with PHASE_SHIFTS all PASS" — true, but PHASE_SHIFTS is only meaningful on BTC, and we only deployed PHASE_SHIFTS strategies on BTC. The correlation is real but the causation isn't "phase shifts cause PASS", it's "BTC + phase_shifts pattern works on BTC".

### Don't extrapolate from small n

PASS rate "100% (n=2)" is not the same as "100% reliable." Need n ≥ 5 to start trusting.

### Don't ignore negative findings

If 11 of 19 candidates failed, the negative cases are AS valuable for pattern detection. Filtering only on PASS examples produces survivorship bias in the meta-analysis.

### Don't mine without a question

"Tell me what's in the archive" produces noise. "What do strategies that PASS in 2025 sideways have in common?" produces signal. Always start with a specific question.

## Tools

The freqtrade_btc_bot repo has these existing tools — USE them, don't rebuild:

| Tool | Purpose |
|---|---|
| `research/ai/per_asset_audit.py` | Scans archive, ranks strategies per coin |
| `research/ai/portfolio_simulator.py` | Allocator comparison + RL ceiling estimate |
| `research/ai/calendar_analyzer.py` | DOW/Month/halving-phase statistical test |
| `research/ai/meta_analyzer.py` | (if exists) cross-strategy meta-analysis |
| `research/ai/sentiment_test.py` | FGI signal feasibility |

For NEW analyses, scripts go in this skill's `scripts/` folder:

- `scripts/find_common_factors.py` — Playbook 1
- `scripts/transfer_report.py` — Playbook 2
- `scripts/live_vs_backtest.py` — Playbook 3
- `scripts/yearly_heatmap.py` — Playbook 4
- `scripts/bug_detector.py` — Playbook 5

## Output style

For research outputs, always include:

1. **Question asked** (1 sentence)
2. **Data scope** (n strategies, n trades, date range)
3. **Top 5 findings** (ranked by signal strength)
4. **Confidence per finding** (sample size, p-value if applicable)
5. **Actionable next experiment** (1-2 specific hypotheses to test)
6. **Honesty caveat** (what we can't conclude from this data)

Example:

> Question: What do PASS-adversarial strategies share that FAILs don't?
> Scope: 22 strategies, 132 backtest runs, 2026-05 → 2026-06
> Findings:
>   1. PASS strategies all have ret_60d > 15% in entry (5/5). FAIL strategies have ret_60d > 5% (3/11). [strong, n=16]
>   2. PASS strategies all use N_CONFIRM ≥ 3 (5/5). FAIL: 8/11 use N=3, 3/11 use N=5. [weak — not differentiating]
>   ...
> Next experiment: Take 1 FAILing strategy, increase ret_60d threshold to 15%, re-backtest.
> Caveat: n=16 small; calendar tilts perfectly correlate with PASS BUT only tested on 2 strategies — can't isolate effect.

## Merging archive + live data

The most valuable analyses combine BOTH:

```python
# Backtest expectation
btest_index = pd.read_csv("research/experiments/INDEX.csv")
btest_recent = btest_index[btest_index["mode"].str.contains("2025|2026")]

# Live actual
import psycopg
with psycopg.connect(DSN) as conn:
    trades = pd.read_sql("SELECT * FROM trades WHERE opened_at > NOW() - INTERVAL '30 days'", conn)

# Join by subscription_id ↔ bot_name patterns
combined = btest_recent.merge(trades_grouped_by_bot, on="strategy")
```

The richest insights come from comparing how a strategy was PROJECTED to behave (backtest) vs how it's ACTUALLY behaving (live). Divergence → either backtest was overfit OR live conditions diverged from training distribution.

## When to escalate to user

Auto-flag for user attention when:

- A live bot has > 50% divergence from backtest
- Adversarial verdict for a NEW timerange (e.g. 2026Q3) fails for any deployed bot
- Common factor analysis reveals a likely bug in deployed code
- New pattern discovery has p < 0.001 AND n ≥ 10 (deploy candidate)
