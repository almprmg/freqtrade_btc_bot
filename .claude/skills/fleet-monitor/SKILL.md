---
name: fleet-monitor
description: Daily/weekly health monitor for the deployed crypto bot fleet (currently 29 bots / 57 containers on trad-server). Checks container uptime, last-heartbeat, live drawdown vs backtest, anomaly detection on live trades, and emits actionable alerts. Use when user asks "how are the bots", "fleet status", "any alerts", "is everything OK", "check bot X", "monitor health", "drawdown alert", or daily-check workflows. Read-only observation — does NOT restart bots or reallocate (that's portfolio-risk-manager).
---

# Fleet Monitor — Live Bot Health Watcher

The operations-watcher skill. Eyes on the fleet.

For deployment, use `bot-builder`. For risk decisions, use `portfolio-risk-manager`. For debugging WHY a bot misbehaves, use `strategy-debugger`. For deeper data-vs-backtest analysis, use `strategy-researcher`.

## When to invoke

- "How are the bots?" / "Fleet status"
- "Any alerts?" / "Health check"
- "Is everything OK?"
- "Check bot X"
- "What's deploying / what's broken?"
- Daily/weekly review
- Triggered by alert: "Drawdown > 15%"

## Health checks

### Check 1: Container uptime
```bash
ssh trad-server 'docker ps --filter "name=freqtrade_" --format "table {{.Names}}\t{{.Status}}"'
```
Flag any bot NOT showing "Up X (days|hours)".

### Check 2: Bridge sync lag
```bash
ssh trad-server 'docker logs freqtrade_<X>_bridge --tail 20 | grep -i "synced\|error"'
```
Bridge should be polling every 30s. If last "synced" > 5 min ago → ALERT.

### Check 3: Database trade flow
```sql
SELECT subscription_id,
       MAX(closed_at) AS last_trade,
       NOW() - MAX(closed_at) AS gap
FROM trades
WHERE status = 'closed'
GROUP BY subscription_id
ORDER BY gap DESC;
```
- 1d strategies should have a trade within 30 days (or be in BEAR regime with intentional 0 trades)
- If gap > 60 days AND backtest expected trades → ALERT

### Check 4: Live PnL vs backtest expectation
For each bot:
```python
days_live = (now - deployment_date).days
expected_yearly = bot.backtest_annual_pct
expected_pnl_so_far = wallet * (expected_yearly / 100) * (days_live / 365)
actual_pnl = sum(trades.pnl WHERE closed_at >= deployment_date)
deviation_pct = (actual_pnl - expected_pnl_so_far) / max(abs(expected_pnl_so_far), 1) * 100
```
- |deviation| > 50% → WARN
- |deviation| > 100% → ALERT (significant divergence)

### Check 5: Drawdown alarm
```python
peak = max(running_wallet_value)
current = wallet + sum(open_trade.unrealized_pnl)
drawdown_pct = (peak - current) / peak * 100
```
- > 10% → INFO
- > 15% → WARN
- > 25% → ALERT
- > 35% → URGENT (consider deactivation, defer to `portfolio-risk-manager`)

### Check 6: Anomalous trade detection
For each closed trade in last 7 days:
- PnL > 3σ from per-bot historical mean → flag for inspection
- Trade duration > 2× typical → flag (might indicate hung order)
- Slippage > 1% on entry/exit → flag (book depth issue)

### Check 7: Backtest archive freshness
```bash
ls -t research/experiments/ | head -1
```
If no new entries in last 30 days → ALERT (strategy development has stalled OR experiment_logger broken)

### Check 8: Cron jobs
```bash
ssh trad-server 'crontab -l'
# Should include weekly meta_allocator
```
Verify scheduled jobs still defined. Check last run logs for errors.

## Output format (daily summary)

```
=== Fleet Health: 2026-XX-XX ===

Fleet: 29 bots / 57 containers
Status: ✅ ALL HEALTHY  /  ⚠️ N WARNINGS  /  🚨 N ALERTS

Per-bot snapshot (Top 5 most active):
| Sub | Bot | Up | Last trade | Live PnL | vs BT | DD |
|---|---|---|---|---|---|---|
| #98 | ai_shield_v2 | 5d | 2d ago | +$120 | +5% | 3% |
| #100 | calendar | 5d | 4d ago | +$95 | +2% | 1% |
| ...

🚨 ALERTS (if any):
- #X bot offline for 6 hours
- #Y drawdown 28% (URGENT)

⚠️ WARNINGS (if any):
- #Z no trades in 45 days (verify regime)
- Bridge lag 8 min on #W

📊 Highlights:
- Best 7d performer: #105 (+$220)
- Worst 7d performer: #X (-$180)
- Total fleet PnL 7d: +$Y / weekly target $Z

Next check: <when>
```

## Alert severity

| Level | Action |
|---|---|
| INFO | Log only |
| WARN | Note in daily summary |
| ALERT | Notify user, suggest investigation via `strategy-debugger` |
| URGENT | Notify user immediately, recommend deactivation via `portfolio-risk-manager` |

## What this skill does NOT do

- **Restart bots** — that's manual / portfolio-risk-manager decision
- **Reallocate capital** — that's portfolio-risk-manager
- **Debug WHY** — that's strategy-debugger
- **Take destructive action** — read-only observation

If an investigation reveals the need for action, HAND OFF to the appropriate skill with the findings.

## Tools (existing in repo)

- `research/ai/meta_allocator.py` — has bot scoring logic, useful for "which bot is hurting"
- `scripts/run_meta_allocator.sh` — weekly cron (separate concern)

This skill creates NEW operational scripts in `scripts/`:

- `scripts/daily_check.py` — runs all 8 checks, emits summary
- `scripts/drawdown_alert.py` — drawdown-specific monitoring
- `scripts/bridge_sync_check.py` — bridge container health

## Cadence

| Check type | Frequency |
|---|---|
| Container uptime | Daily |
| Bridge sync | Daily |
| Live PnL vs backtest | Weekly |
| Drawdown | Daily |
| Anomalous trades | Weekly |
| Archive freshness | Weekly |
| Full audit | Monthly |

Can be automated via cron on trad-server. Skill's role is providing the check-list + interpretation.

## State capture (for trend analysis)

Each daily check should ALSO append a row to `research/fleet_health_log.csv`:

| date | n_bots_up | n_alerts | total_wallet | total_pnl_today | top_performer | worst_performer |

Over time, this enables:
- Trend detection ("PnL declining 3 weeks in a row")
- Volatility detection ("alert frequency rising")
- Capacity planning ("we added 5 bots, did total PnL scale?")

## When to escalate to user

Auto-flag the following without waiting for user to ask:

- Any URGENT-level alert
- Total fleet PnL negative for 7+ consecutive days
- 3+ bots simultaneously diverging > 50% from backtest
- Bridge container down for > 1 hour
- Any container restart count > 5 in 24 hours (suggests crash loop)

For these, ALSO suggest the appropriate next-step skill in the message.
