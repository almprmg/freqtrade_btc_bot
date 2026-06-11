---
name: portfolio-risk-manager
description: Portfolio-level capital and risk manager across the entire bot fleet. Tracks total exposure, per-coin concentration, drawdown limits, max-loss circuit breakers, and capital reallocation decisions. Use when user asks "total exposure", "am I over-allocated to X", "reduce risk", "rebalance", "kill switches", "max wallet per bot", "what should I deactivate", "portfolio drawdown". Decides on capital movement — does not modify code.
---

# Portfolio Risk Manager — Capital & Risk Officer

The capital allocation skill. Looks at the WHOLE picture, not individual bots.

For per-bot monitoring, use `fleet-monitor`. For strategy decisions, use `strategy-architect`. For deployment, use `bot-builder`.

## When to invoke

- "Total exposure across the fleet?"
- "Am I over-allocated to X coin?"
- "Reduce risk on Y"
- "Rebalance"
- "Set up kill switches"
- "Max wallet per bot policy"
- "Portfolio drawdown"
- "What should I deactivate?"
- "Is total leverage safe?"
- "Concentration check"

## What this skill tracks

### Total exposure
```sql
SELECT SUM(allocated_capital) AS total_exposed,
       COUNT(*) AS n_active_bots
FROM user_strategy_subscriptions
WHERE user_id = 10 AND status = 'active'
  AND custom_parameters->>'source' LIKE 'freqtrade_%';
```

Current state (as of session end): ~$33K across 29 bots.

### Per-coin concentration
```sql
SELECT trading_symbol,
       SUM(allocated_capital) AS coin_total,
       COUNT(*) AS n_bots
FROM user_strategy_subscriptions
WHERE user_id = 10 AND status = 'active'
  AND custom_parameters->>'source' LIKE 'freqtrade_%'
GROUP BY trading_symbol
ORDER BY coin_total DESC;
```

### Total live PnL
```sql
SELECT
  SUM(pnl) FILTER (WHERE status = 'closed') AS realized_pnl,
  SUM(unrealized_pnl) FILTER (WHERE status = 'open') AS unrealized,
  COUNT(*) FILTER (WHERE status = 'open') AS open_positions
FROM trades
WHERE subscription_id IN (
  SELECT id FROM user_strategy_subscriptions
  WHERE user_id = 10 AND status = 'active'
);
```

### Portfolio drawdown
Track running portfolio value (wallet allocations + cumulative PnL). Compute drawdown from running peak.

## Policy framework

Read `policies/risk_limits.md` for current values. Defaults:

### Per-bot limits
- Min wallet: $500 (operational minimum — Binance min order sizes)
- Default wallet for PASS: $3,000
- Default wallet for WARN: $2,000
- MAX wallet without explicit user approval: $5,000

### Per-coin limits
- Max % of total capital in any single coin: 30%
- Max number of bots per coin: 3
- Special: BTC can go up to 40% (it's the major asset)

### Drawdown limits
- Single-bot DD > 25% → recommend deactivation (defer to user)
- Portfolio DD > 15% → URGENT: pause new deployments
- Portfolio DD > 25% → recommend reducing total exposure 50%

### Total exposure limits
- Default cap: $50K across all bots
- Exceeding requires explicit user authorization

## Decisions this skill makes (proposals, user approves)

### Decision 1: Should bot X be DEACTIVATED?
Triggers:
- Single-bot live drawdown > 25%
- Bot strategy file becomes obsolete (replaced by better version)
- Bot is bleeding capital with no recovery signal for 60+ days
- User capital constraint requires shrinkage

Process:
1. Pull bot's recent performance
2. Show pros/cons of deactivation
3. Wait for user approval
4. If approved:
```bash
ssh trad-server 'docker compose -f docker-compose.<bot>.yml stop'
ssh trad-server 'docker exec trad_pg psql -U trading -d trading -c "UPDATE user_strategy_subscriptions SET status='"'"'paused'"'"' WHERE id = X;"'
```

### Decision 2: Should we ADD MORE CAPITAL to bot X?
Triggers:
- Live PnL exceeds backtest expectation by > 30%
- Coin's main bot is bull-running, supplement with more capital
- User has fresh capital to deploy
Process: propose, user approves, update `allocated_capital`

### Decision 3: Should we REBALANCE between bots?
Triggered by meta_allocator weekly cron OR manual request.

Process:
1. Pull each bot's 90-day score from `meta_allocator`
2. Propose moves: increase top performers, reduce laggards
3. Subject to constraints:
   - No bot below $500
   - No bot above $5K (without user override)
   - No coin above 30% (40% for BTC)
   - Total exposure unchanged (rebalance, not net add)
4. User approves → apply changes

### Decision 4: PAUSE new deployments?
Triggered automatically when:
- Portfolio drawdown > 15%
- Fleet has 3+ bots in WARN/FAIL adversarial status
- Recent live-vs-backtest divergence is widespread

Pause action: refuse `bot-builder` deploys until resolved. Notify user.

## Kill switches

Configurable triggers that AUTO-DEACTIVATE bots:

```yaml
# policies/kill_switches.yml
single_bot:
  - condition: live_dd_pct > 30
    action: pause_bot
    notify: user

  - condition: days_since_last_trade > 90 AND backtest_expected_trades > 0
    action: investigate_then_pause
    notify: strategy-debugger

portfolio:
  - condition: total_dd_pct > 20
    action: pause_all_new_deployments
    notify: user

  - condition: total_pnl_negative_for_days > 14
    action: emergency_review
    notify: user_urgent
```

These are RECOMMENDATIONS this skill makes. Actual triggering should be: user approves once, then automated thereafter.

## Outputs

### "Portfolio status" report
```
=== Portfolio Status: 2026-XX-XX ===

Total exposure: $33,000 across 29 bots
Total PnL realized: +$XXX
Total PnL unrealized: +$YYY (Z open positions)
Portfolio value: $XX,XXX (peak: $YY,YYY, DD: ZZ%)

Concentration:
  BTC: $10,000 (30%, 3 bots) ✓
  ETH: $6,000  (18%, 3 bots) ✓
  SOL: $6,000  (18%, 2 bots) ✓
  BNB: $4,000  (12%, 2 bots) ✓
  ADA: $3,000  (9%,  2 bots) ✓
  DOGE: $2,000 (6%,  1 bot)  ✓
  AVAX: $2,000 (6%,  1 bot)  ✓
  ✅ all within 30% per-coin limit

Bot performance (last 30d):
  Best: #105 ETH Calendar (+$XXX, +X%)
  Worst: #X (-$YYY, -Y%)

Active alerts: NONE / N alerts
Kill switches armed: 5 active, 0 tripped

Recommended actions: <list>
```

### "Pre-deploy check" (called by bot-builder before deploy)
- [ ] Wallet ≤ $5K (or user-approved)
- [ ] Coin total (existing + new) ≤ 30%/40% limit
- [ ] Total exposure ≤ $50K
- [ ] Portfolio not in pause-mode
- [ ] No kill switch trip on this coin in last 24h

If any fail → BLOCK deployment until resolved.

## Data sources

- `trad_pg.user_strategy_subscriptions` — wallet allocations
- `trad_pg.trades` — PnL stream
- `research/fleet_health_log.csv` — historical portfolio metrics

## What this skill does NOT do

- Run technical analysis (use `strategy-debugger`)
- Build/test strategies (use `bot-builder`, `strategy-critic`)
- Set up MONITORING (use `fleet-monitor`)
- Trigger TRADES on the exchange directly (that's freqtrade)
- Make decisions WITHOUT user approval for any irreversible action

## Default policy file (to be customized by user)

```yaml
# policies/risk_limits.md
max_total_exposure_usd: 50000
default_wallet_pass_usd: 3000
default_wallet_warn_usd: 2000
max_wallet_per_bot_usd: 5000
min_wallet_per_bot_usd: 500
max_concentration_per_coin_pct: 30
max_concentration_btc_pct: 40
max_bots_per_coin: 3
portfolio_dd_warn_pct: 15
portfolio_dd_alert_pct: 25
single_bot_dd_deactivate_pct: 25
days_without_trade_investigate: 60
days_without_trade_pause: 90
```

These are STARTING POINTS. Adjust based on user's risk tolerance.

## Escalation matrix

| Condition | Skill notifies | Action authority |
|---|---|---|
| Bot DD > 20% | `fleet-monitor` daily summary | Recommendation only |
| Bot DD > 30% | DIRECT user message | Pause bot, await approval |
| Portfolio DD > 15% | DIRECT user message | Pause new deploys |
| Portfolio DD > 25% | URGENT user message | Recommend 50% reduction |
| Daily PnL negative for 7d | DIRECT user message | Trigger meta-allocator review |
| New deploy violates concentration | BLOCK in bot-builder | Refuse until rebalanced |

## When to invoke this skill proactively

- After every `bot-builder` deploy → update concentration tracker
- After every `meta_allocator` weekly cron → review proposed reallocation
- Whenever `fleet-monitor` reports an ALERT → assess portfolio impact
- Daily during market stress (when |daily_pnl| > 5% of portfolio)
