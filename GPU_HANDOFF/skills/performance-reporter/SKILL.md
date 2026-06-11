---
name: performance-reporter
description: Generates weekly/monthly/quarterly performance reports for the crypto bot fleet. Produces structured markdown reports with per-bot stats, portfolio summary, top performers, laggards, comparison vs backtest, and actionable recommendations. Use when user asks "weekly report", "monthly summary", "performance review", "how did we do this week", "generate report", "year-to-date stats". Reads from trad_pg and research/experiments archive.
---

# Performance Reporter — Periodic Performance Summaries

The reporting skill. Turns raw bot stats into readable summaries.

For real-time monitoring, use `fleet-monitor`. For deep analysis, use `strategy-researcher`. For capital decisions based on reports, use `portfolio-risk-manager`.

## When to invoke

- "Weekly report"
- "Monthly summary"
- "Performance review"
- "How did we do this week/month/quarter?"
- "Year-to-date stats"
- "Generate report"
- Cron-triggered (weekly Mondays, monthly 1st)

## Report types

### Daily snapshot (1 page)
- Total wallet, total PnL today, today's best/worst bot
- Active alerts (from fleet-monitor)
- 1 chart: daily PnL last 30 days

### Weekly report (3-5 pages)
- All daily metrics, plus:
- Per-bot 7-day PnL ranking
- Per-coin aggregate (BTC vs ETH vs ... combined)
- Vs-backtest divergence per bot
- Top 3 highlights, top 3 concerns
- Next week's planned changes (new deploys, rebalances)

### Monthly report (5-10 pages)
- All weekly metrics aggregated, plus:
- Month-over-month trends
- New deploys made / rejected / pending
- Drawdown chart for portfolio
- Cumulative PnL since fleet inception
- Adversarial verdict status (any backtests run this month)
- Strategy lifecycle (new live, deactivated, paused)

### Quarterly review (15-20 pages)
- All monthly aggregated, plus:
- Per-strategy postmortem
- Hypothesis success rate (proposed vs deployed vs profitable)
- Methodology improvements
- Yearly projection extrapolation
- Recommendations for next quarter

## Templates

Located in `templates/`:

- `daily.md.tmpl` — 1-page
- `weekly.md.tmpl` — sectioned report
- `monthly.md.tmpl` — comprehensive
- `quarterly.md.tmpl` — narrative + tables

## Generation logic

### Data sources
- `trad_pg.trades` — every closed trade
- `trad_pg.user_strategy_subscriptions` — wallet allocations
- `research/fleet_health_log.csv` — daily health snapshots (from fleet-monitor)
- `research/experiments/INDEX.csv` — backtest archive

### Key metrics computed

```python
# For a given period (e.g. "last 7 days"):

period_pnl_per_bot = """
SELECT s.custom_parameters->>'source' AS bot,
       SUM(t.pnl) AS pnl,
       COUNT(*) AS n_trades,
       AVG((t.exit_price - t.entry_price) / t.entry_price * 100) AS avg_pct_pnl,
       MAX((t.exit_price - t.entry_price) / t.entry_price * 100) AS best_trade_pct
FROM trades t
JOIN user_strategy_subscriptions s ON s.id = t.subscription_id
WHERE t.closed_at >= NOW() - INTERVAL '{period}'
  AND t.status = 'closed'
GROUP BY bot
ORDER BY pnl DESC;
"""

period_pnl_per_coin = """
SELECT s.trading_symbol AS coin,
       SUM(t.pnl) AS pnl,
       COUNT(DISTINCT s.id) AS n_bots
FROM trades t
JOIN user_strategy_subscriptions s ON s.id = t.subscription_id
WHERE t.closed_at >= NOW() - INTERVAL '{period}'
  AND t.status = 'closed'
GROUP BY coin;
"""

portfolio_drawdown_in_period = "..."  # rolling peak calculation
```

### Comparison vs backtest

For each bot, retrieve latest yearly backtest from `INDEX.csv`. Compare:
- Expected weekly PnL = wallet × (annual_backtest_pct/100) × (days_in_period/365)
- Actual weekly PnL = sum of pnl in period
- Divergence % = (actual - expected) / |expected|

Flag if |divergence| > 50%.

## Report structure (weekly example)

```markdown
# Weekly Performance Report — Week ending YYYY-MM-DD

## TL;DR
Fleet: 29 bots, $33K exposure
Week PnL: +$XXX (+X.X% on portfolio)
YTD PnL: +$YYY
Best: bot_X (+$AAA)
Worst: bot_Y (-$BBB)

## Per-bot week summary
[table: bot | wallet | week PnL | n_trades | vs_BT divergence | win_rate]

## Per-coin aggregate
[table: coin | n_bots | week PnL | best bot | worst bot]

## Highlights
1. Top winner: ETH Calendar Shield (#105) delivered +X% over the week, X pp above backtest expectation
2. ...
3. ...

## Concerns
1. Bot Y diverged -45% from backtest — investigate via strategy-debugger
2. ...

## Adversarial status
- 0 new adversarial validations this week
- 0 rejections, 0 new deploys

## Plans for next week
- Refresh anomaly model (data-engineer)
- Consider AVAX VolShield port (strategy-explorer recommended)
- Run meta_allocator review (portfolio-risk-manager)

## Honest caveats
- Bot Z hasn't traded in 12 days; might be in expected NEUTRAL regime, but verify
- Live data only covers <N> days since fleet deployment; trends are nascent
```

## Output format options

- Markdown (default — for git commit, README, slack post)
- JSON (for dashboard ingestion)
- Plain text (for email)
- HTML (with embedded charts via plotly — TBD)

## Scheduling

Recommended cron on trad-server:
```cron
# Daily snapshot 23:55 UTC
55 23 * * * /srv/trad/.../scripts/generate_daily.sh

# Weekly Mondays 09:00 UTC
0 9 * * 1 /srv/trad/.../scripts/generate_weekly.sh

# Monthly 1st of month 09:00 UTC
0 9 1 * * /srv/trad/.../scripts/generate_monthly.sh

# Quarterly 1st of Apr/Jul/Oct/Jan 09:00 UTC
0 9 1 1,4,7,10 * /srv/trad/.../scripts/generate_quarterly.sh
```

Reports go to:
- `research/reports/daily/<date>.md`
- `research/reports/weekly/<week>.md`
- `research/reports/monthly/<month>.md`
- `research/reports/quarterly/<quarter>.md`

Optional: also append to MEMORY.md once monthly for trend retrievability.

## What this skill does NOT do

- Make decisions (just report) — defer to `portfolio-risk-manager`
- Modify code or deployments
- Detect anomalies (just report the data) — `fleet-monitor` does that
- Generate new hypotheses — `strategy-explorer` does that

## When the user asks for a custom report

Common variations:
- "Year-to-date" → similar to monthly but period = since fleet inception
- "Just BTC bots" → filter by coin
- "Excluding triple regime" → exclude defensive sleeves
- "vs HODL baseline" → include holdfair comparison column

Adapt the template, run the query with adjusted filters, produce report.

## Calibration over time

After 30+ days of reports, look back:
- Did "concerns" flagged 4 weeks ago resolve themselves or get worse?
- Did "next week" plans actually happen?
- Are the "honest caveats" recurring (suggests systemic issue) or one-off?

Use these meta-observations to improve report relevance.

## Quick-start script

```bash
# Generate this week's report
TRAD_PG_DSN=... ./.venv/Scripts/python.exe -m scripts.generate_weekly --week current

# Generate last month
TRAD_PG_DSN=... ./.venv/Scripts/python.exe -m scripts.generate_monthly --month last

# Generate Q1 2026
TRAD_PG_DSN=... ./.venv/Scripts/python.exe -m scripts.generate_quarterly --quarter 2026-Q1
```

Reports save to disk; user can review markdown in any editor.
