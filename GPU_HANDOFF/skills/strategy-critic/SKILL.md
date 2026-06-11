---
name: strategy-critic
description: Adversarial reviewer with veto power over deployments. Runs strategies through hard tests, identifies overfit signals, redundancy, vol-profile mismatches, and unsafe deployment patterns. Use BEFORE every deployment, when user asks "is this safe to deploy", "review this strategy", "should we trust these backtest numbers", "validate before going live". Encodes the 11 honest rejections from the major session as concrete signs to look for. The deploy gate.
---

# Strategy Critic — Adversarial Reviewer & Deployment Gate

The critic skill. Veto power. Runs hard tests against any candidate before live capital touches it.

For DESIGN, use `strategy-architect`.
For BUILDING, use `bot-builder`.
For RESEARCH, use `strategy-researcher`.
For NEW IDEAS, use `strategy-explorer`.

## When to invoke

- "Is this safe to deploy?"
- "Review this candidate"
- "Should we trust these backtest numbers?"
- "Validate before going live"
- "Check for overfit"
- "Adversarial review of <strategy>"
- AUTOMATICALLY: before any `bot-builder` deployment

## The 4-step review

### Step 1: Adversarial Validator (the gate)

Run `research/ai/adversarial_validator.py`:

```bash
cd d:/pythone/freqtrade_btc_bot
./.venv/Scripts/python.exe -m research.ai.adversarial_validator \
  --strategy <ClassName>Strategy \
  --config config.<slug>.json \
  --name <slug> \
  --skip-baselines
```

Three windows tested:
- BEAR_2022 (2022-01-01 → 2023-01-01)
- SIDEWAYS_2025 (2025-01-01 → 2026-01-01)
- BEAR_2026Q12 (2026-01-01 → 2026-06-01)

Verdict logic (from `checklists/adversarial_thresholds.md`):
- **PASS:** all 3 ≥ 0%, DD ≤ 5%
- **WARN:** 1 window mildly negative, worst > -15%, DD ≤ 15%
- **FAIL:** 2+ negative OR worst < -15%
- **CATASTROPHIC:** worst < -30% OR DD > 30%

**Action by verdict:**
- PASS → green-light deployment with full $3K-5K
- WARN → green-light with reduced $2K-3K + documentation
- FAIL → **VETO.** Document why in `examples/loss_*.md`
- CATASTROPHIC → **VETO with prejudice.** Architect must redesign.

### Step 2: Overfit signal detection

Before deployment, scan for these red flags from `checklists/overfit_signs.md`:

1. **Single-window darling**: best ROI in archive comes from one specific year window
2. **Sharpe inflation**: archive Sharpe > 0.5 but n_trades < 5
3. **No bear in archive**: all archive runs lack 2022 or any explicit BEAR window
4. **Magic parameters**: thresholds like "0.0537" or "27.3" (overfit smell)
5. **Heavy feature stack**: > 4 added features beyond base archetype
6. **No pre-mortem**: hypothesis can't articulate failure mode

If ANY red flag is present → ask user before proceeding, OR demand fresh adversarial.

### Step 3: Redundancy check

Before deploying a NEW feature on top of existing strategy, verify INDEPENDENT information.

Test:
- Run strategy WITHOUT new feature → compound A
- Run strategy WITH new feature → compound B
- If |B - A| / A < 5% → likely redundant
- If new feature was already captured by an existing signal (e.g. FGI ≈ cycle_phase) → reject

Real example: Sentiment Shield vs Calendar Shield were essentially tied ($50,953 vs $51,779). Sentiment was redundant with cycle_phase. NOT DEPLOYED despite PASSING adversarial.

### Step 4: Vol-profile sanity check

For cross-coin ports, verify vol-profile match:

```python
import pandas as pd
df = pd.read_feather(f"user_data/data/binance/{COIN}_USDT-1d.feather")
df["ret_1d"] = df["close"].pct_change()
ann_vol = df["ret_1d"].std() * (365 ** 0.5) * 100
```

| Source coin | Target coin | Vol diff | Action |
|---|---|---|---|
| BTC (55%) | ETH (70%) | +15pp | Likely ports OK |
| BTC (55%) | BNB (65%) | +10pp | Should port |
| BTC (55%) | SOL (95%) | +40pp | DEMAND VolShield template, not Pure Shield |
| BTC (55%) | DOGE (110%) | +55pp | DEMAND custom design |

If user wants to port a BTC strategy directly to SOL/AVAX/DOGE → flag immediately.

## Critic's veto list (when to refuse deployment)

ABSOLUTE vetoes (no exception):
1. Adversarial verdict is FAIL or CATASTROPHIC
2. Strategy file has UNRESOLVED `{{ var }}` substitutions
3. Smoke test fails (won't run for even 30 days)
4. Database SQL would conflict with existing subscription
5. Wallet > $5K without explicit user authorization

CONDITIONAL vetoes (require user override):
1. Coin already has ≥ 3 live bots (over-concentration)
2. Strategy is < 5% better than existing live counterpart (marginal)
3. New feature shows < 5% effect size (redundancy risk)
4. Vol-profile mismatch (BTC strategy → SOL/AVAX/DOGE)
5. Pre-mortem reveals untested failure mode

## What the critic CAN'T catch

Be honest about limits:
- Live regime shifts (e.g. crypto behaves differently post-ETF approvals)
- Black swan events (-99% in 1 day from exchange hack)
- Implementation bugs not visible in backtest (live-only race conditions)
- Liquidity issues at deploy size (backtest assumes instant fills)
- Slippage on real orderbooks

These require LIVE monitoring (see `strategy-researcher` Playbook 3 — live vs backtest divergence detection).

## Output format

When reviewing, produce:

```
=== Adversarial Review: <strategy_name> ===

Adversarial Verdict: <PASS|WARN|FAIL|CATASTROPHIC>
  BEAR_2022:     ROI=<x>% DD=<y>%
  SIDEWAYS_2025: ROI=<x>% DD=<y>%
  BEAR_2026Q12:  ROI=<x>% DD=<y>%

Red flags detected: <list or "none">

Vol-profile match: <yes|caution|mismatch>
  Source archetype calibrated for: <vol range>
  Target coin vol: <X%>
  
Redundancy check: <pass|fail|n/a>
  Baseline compound:  $<A>
  With new feature:   $<B>
  Effect size:        <((B-A)/A)*100>%

DEPLOYMENT RECOMMENDATION:
  [ ] DEPLOY ($X wallet)
  [ ] DEPLOY WITH CAUTION ($Y wallet, monitor live for Z days)
  [X] VETO — reason: <specific reason>
  
Documentation: <where to write up the rejection if vetoed>
```

## Escalation

When VETO is contested, request user to explicitly:
1. Acknowledge the specific risk
2. Confirm the wallet size
3. Set a kill-switch trigger (e.g. "if down 20% in first 30 days, deactivate")
4. Schedule a 30-day review

Without all 4, the veto stands.

## Critic remembers

After every review, log to `research/critic_log.md`:
- Date
- Strategy reviewed
- Verdict (PASS/WARN/VETO + reason)
- If deployed, projected outcomes
- 30/60/90 day follow-up: did the live behavior match the verdict's prediction?

This creates a calibration feedback loop. Over time, the critic's accuracy can be measured and improved.
