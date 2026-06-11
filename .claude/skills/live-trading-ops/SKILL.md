---
name: live-trading-ops
description: Operations skill for transitioning bots from dryrun to LIVE trading with real capital on Binance (or other exchanges). Manages API key provisioning, gradual rollout (canary deploys), slippage tracking, fee accounting, listen-key streams, order monitoring. Use ONLY when user explicitly says "go live", "enable live trading", "transition to real money", "production exchange". Refuses without explicit confirmation. The safety-most-critical skill.
---

# Live Trading Ops — Dryrun → Live Transition

The skill that handles REAL MONEY. Every other skill assumes `dry_run: true`. This one flips the switch.

For development, use the other 10 skills. This skill is invoked ONLY when transitioning to live execution.

## When to invoke

ONLY when user explicitly says:
- "Enable live trading on bot X"
- "Transition to real money"
- "Go live with sub #Y"
- "Production deployment"
- "Real exchange execution"

If user says any of the above WITHOUT specifying which bot → ASK first. Never assume "all bots".

## Default refusal posture

This skill REFUSES to act unless ALL of the following are true:

- [ ] User has explicitly authorized THIS specific bot
- [ ] Bot has been running in dryrun for ≥ 30 days
- [ ] Live-vs-backtest divergence is < 30% (verified via `strategy-researcher` Playbook 3)
- [ ] Adversarial verdict is PASS or WARN (verified via `strategy-critic`)
- [ ] Portfolio drawdown < 10% (verified via `portfolio-risk-manager`)
- [ ] Wallet to deploy with is ≤ $5,000 (start small)
- [ ] User has rotated Binance API keys recently AND keys have:
  - Spot trading permission (no margin, no futures)
  - Withdrawal DISABLED
  - IP whitelist set to trad-server's IP only

If ANY are missing → refuse + list what's missing.

## The transition procedure

### Step 1: Pre-flight checklist

Walk through `checklists/pre_live_checklist.md` item by item. Each requires user confirmation.

### Step 2: Provision Binance API keys

Tell user to:
1. Log into Binance.com
2. Create new API key (NOT use existing)
3. Permissions: Spot trading ONLY (no margin, no withdrawal)
4. IP restriction: trad-server's IP (`72.62.179.86`)
5. Copy key + secret to a secure location

Then on server:
```bash
ssh trad-server '
cd /srv/trad/pythone/freqtrade_btc_bot
# Edit the bot-specific .env file
nano .env.<slug>
# Add:
# FREQTRADE__EXCHANGE__KEY=<real_key>
# FREQTRADE__EXCHANGE__SECRET=<real_secret>
chmod 600 .env.<slug>
'
```

### Step 3: Update config to live mode

```bash
ssh trad-server '
cd /srv/trad/pythone/freqtrade_btc_bot
# Edit config.<slug>.json:
# Change "dry_run": true → "dry_run": false
# Set realistic "dry_run_wallet" → "stake_amount" or similar
'
```

### Step 4: Restart with canary wallet

NEVER go from $0 → full target. Use canary:

| Day | Wallet | What we're testing |
|---|---|---|
| 1-3 | $200 | Connectivity, fills, no API errors |
| 4-7 | $500 | Real PnL emerging |
| 8-14 | $1,500 | Confirms slippage is acceptable |
| 15-30 | $3,000 (target) | Production wallet |

Each step requires verification before increasing:
- Fills happen as expected (price ~ market)
- Slippage < 0.5%
- Fees within expectations
- No "insufficient balance" errors

### Step 5: Restart container

```bash
ssh trad-server '
cd /srv/trad/pythone/freqtrade_btc_bot
docker compose -f docker-compose.<slug>.yml --env-file .env.<slug> down
docker compose -f docker-compose.<slug>.yml --env-file .env.<slug> up -d
sleep 10
docker logs freqtrade_<slug> --tail 50 2>&1 | head -30
# Look for "Dry-run is disabled" or equivalent live-mode indicator
'
```

### Step 6: Watch first trade

The MOMENT the first live trade fires, do:

```bash
ssh trad-server 'docker logs freqtrade_<slug> --tail 100'
# Look for:
# - "Bought X.YY @ Z" in actual log
# - Order ID returned from exchange (not "dry_X")
```

Then verify on Binance:
1. Log into Binance, go to Spot Trade History
2. Confirm the order appears with correct symbol, side, amount
3. Compare execution price vs strategy's expected
4. Note slippage if any

### Step 7: First-week intensive monitoring

For 7 days post-transition, daily check:
- All orders are filling
- No API rate-limit errors in logs
- PnL is being correctly attributed in `trad_pg.trades`
- Bridge container is syncing properly

If ANY anomaly → IMMEDIATELY revert to dryrun:
```bash
ssh trad-server '
# In config.<slug>.json, set dry_run: true
# Restart
docker compose ... down && docker compose ... up -d
'
```

## What goes wrong in live (and how)

### Slippage worse than expected
- Backtest assumes mid-price fills
- Live spot fills at ask (buy) / bid (sell)
- Typical extra cost: 0.05-0.20% per trade
- If slippage > 0.5% → check liquidity, reduce wallet to test

### Insufficient balance errors
- Bot tries to buy more than wallet holds
- Usually: stale balance from bridge sync lag
- Fix: ensure bridge polls every ≤30s

### Listen-key / WS issues
Binance user-data stream is **410 Gone** (per [[user-data-stream-gap]] memory).
Fills are caught via REST OrderPoller. WS-API push (Ed25519 session.logon) built but feature-flagged OFF until keys provisioned.

### Partial fills
- Binance may fill 0.99 of 1.0 BTC
- freqtrade handles, but verify the partial PnL is correctly attributed

### API rate limits
- Binance: 1200 requests/min per IP
- 29 bots × 30s polling × 2 endpoints = ~120 req/min — well under limit
- BUT if you add many more bots OR shorter polling → can hit limits

## Auditing live trades

Daily during first month:
```sql
-- Compare live execution vs backtest expected
SELECT
  t.subscription_id,
  s.custom_parameters->>'source' AS bot,
  COUNT(*) AS n_trades_today,
  AVG((t.exit_price - t.entry_price) / t.entry_price * 100) AS avg_pct_pnl,
  AVG(t.fees) AS avg_fees
FROM trades t
JOIN user_strategy_subscriptions s ON s.id = t.subscription_id
WHERE t.closed_at >= NOW() - INTERVAL '1 day'
  AND t.status = 'closed'
GROUP BY t.subscription_id, s.custom_parameters->>'source';
```

Compare to backtest expectations. Divergence > 30% → investigate via `strategy-debugger`.

## Multi-bot transition strategy

DON'T flip all 29 bots live at once. Stage:

1. **Phase A:** 1 bot live (lowest-risk: lowest wallet, highest backtest, PASS adversarial) — 14 days
2. **Phase B:** 3 bots live (add 2 more diverse coins) — 14 days
3. **Phase C:** Half the fleet live — 30 days
4. **Phase D:** Full fleet live — only if A/B/C all passed audit

If ANY phase reveals issues → halt, investigate, fix, restart phase.

## Backout plan (going back to dryrun)

If something goes wrong:

```bash
# IMMEDIATE: stop the bot
ssh trad-server 'cd /srv/trad/... && docker compose -f docker-compose.<slug>.yml down'

# Restore dryrun config
ssh trad-server 'cd /srv/trad/... && # edit config.<slug>.json back to "dry_run": true'

# Restart in dryrun
ssh trad-server 'cd /srv/trad/... && docker compose -f docker-compose.<slug>.yml up -d'
```

Then investigate via `strategy-debugger`.

## Security checklist (every transition)

- [ ] API keys NEVER committed to git (in .env files only, chmod 600)
- [ ] API keys have ONLY spot trading permission
- [ ] Withdrawal permission DISABLED on keys
- [ ] IP whitelist set on Binance to trad-server only
- [ ] Total exposure across all live bots < $50K (or user-approved)
- [ ] Kill-switch via `portfolio-risk-manager` is configured
- [ ] User has 2FA enabled on Binance
- [ ] User has account backup access (in case 2FA device lost)

If user can't confirm all → DELAY transition until they can.

## Output style

When invoked, ALWAYS state:

```
=== Live Trading Transition: <bot_slug> ===

Pre-flight check:
  [✓] Dryrun ≥ 30 days
  [✓] Adversarial PASS/WARN
  [✓] Live-vs-backtest divergence < 30%
  [✗] User has rotated API keys recently  ← BLOCKING

Status: REFUSED (1 blocker)

To proceed, user must:
1. <specific action>

Once resolved, re-invoke with confirmation: "go live with <slug>"
```

## When NEVER to act

- User said "go live" but didn't specify which bot → ASK
- Pre-flight has even ONE blocker → REFUSE
- Portfolio in drawdown > 10% → REFUSE
- User authorization is verbal-only without recent context → CONFIRM
- The skill itself has been invoked but the human hasn't explicitly approved THE specific transition step → PAUSE

This is the highest-risk skill. Bias HEAVILY toward refusal.
