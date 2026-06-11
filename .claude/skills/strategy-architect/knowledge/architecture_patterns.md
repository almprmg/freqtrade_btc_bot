# Strategy Architecture Patterns

The 5 proven archetypes + how to compose them.

## Archetype 1: Pure Shield

**Code shape:** `regime detector → BULL=75% / BEAR=0%`

**Components:**
- EMA200 + ADX + ret_30d → regime
- N-day confirmation
- Anomaly circuit breaker
- 75% target during BULL

**Deployed examples:** Original BTC/ETH/BNB/DOGE/ADA shield bots.

**Best for:** Baseline. Always start here before adding complexity.

**Fails when:** High-vol coin (SOL, AVAX) — chop creates whipsaw.

## Archetype 2: Sigmoid V2 (Shield + Halving + Smooth Sizing)

**Code shape:** `Pure Shield + halving phase shifts + sigmoid sizing`

**Components:**
- Pure Shield base
- `cycle_bias` from halving_cycle.feather
- `PHASE_SHIFTS` dict (ACCUMULATION/PARABOLIC/etc)
- `sigmoid(cycle_bias + phase_shift, k=4)` → smooth target % of wallet

**Deployed example:** sub #98 BtcAiShieldV2Strategy.

**Best for:** BTC. +10pp/yr over Pure Shield baseline.

**Fails when:** Non-BTC coins (halving data doesn't apply).

## Archetype 3: Calendar Shield (V2 + Day/Month Tilts)

**Code shape:** `V2 + CALENDAR_TILTS added to adjusted_bias`

**Components:**
- Sigmoid V2 base
- `CALENDAR_TILTS = {"is_october": 0.15, "is_july": 0.05, ...}`
- Total tilt clamped to ±0.30

**Deployed examples:**
- sub #100 BtcCalendarShieldStrategy (BTC): +38.2%/yr, PASS
- sub #105 BtcCalendarShieldStrategy (ETH): **+55%/yr**, PASS ← STRONGEST OF SESSION

**Best for:** BTC, ETH. Calendar effects port across coins.

**Fails when:** High-vol coins still fail at the underlying regime detection layer.

## Archetype 4: Triple Regime (Defensive Consensus)

**Code shape:** `3 independent detectors AND → 70% / 0%`

**Components:**
- Detector 1: EMA + ADX
- Detector 2: Donchian breakout
- Detector 3: MACD positive
- ALL 3 must agree

**Deployed examples:**
- sub #99 BTC: +10.5%/yr, PASS
- sub #103 BNB: +17.7%/yr, WARN
- sub #104 ADA: +14.4%/yr, PASS

**Best for:** Defensive sleeve alongside a primary bot that FAILS adversarial.

**Fails when:** Used as primary bot (too defensive, misses bull) OR on coins with violent sideways (DOGE).

## Archetype 5: VolShield (Chop-Aware for High-Vol Coins)

**Code shape:** `Pure Shield + EMA50 cross + ret_60d + ATR ceiling + 5-day confirm`

**Components:**
- close > EMA200 AND ema50 > ema200 (golden cross)
- ret_30d > 5% AND ret_60d > 15% (double window)
- ADX > 30 (stronger than Pure's 20)
- atr_pct < 0.10 (NOT during high vol)
- 5-day regime confirmation

**Deployed example:** sub #102 SolVolShieldStrategy (SOL): +45%/yr, WARN.

**Best for:** Coins with ann. vol > 80% (SOL, AVAX).

**Tuning sensitivity:**
- Tighten filters → fewer trades but cleaner (test v3 → v1 = 0 trades)
- Loosen filters → more trades but FAIL adversarial (test v2)
- Sweet spot is narrow

## Composition rules

### Compose only by EXTENDING bias, not by gating

GOOD: `adjusted_bias = cycle_bias + phase_shift + calendar_tilt + sentiment_tilt`
- Each adds a small contribution
- Sigmoid normalizes to [0, 1]
- Easy to attribute success/failure to specific tilt

BAD: `if calendar_says_buy AND sentiment_says_buy: enter`
- Gates compose multiplicatively → easy to never trigger
- Hard to attribute

### Compose only ONE new feature per version

GOOD: V2 → V3 = V2 + cooldown. (Even though V3 failed, attribution is clean.)
BAD: V4 = V2 + cooldown + sentiment + new_anomaly. Can't tell what helped/hurt.

### When deploying multiple archetypes for one coin

Use SEPARATE bots, not one combined bot:
- BTC: V2 (#98), Triple (#99), Calendar (#100) — 3 SEPARATE bots
- Each gets its own wallet, own backtest, own adversarial verdict

This makes:
- Each strategy's performance measurable independently
- Failure of one doesn't bleed into others
- Easy to deactivate the worst performer based on live results

## Decision: which archetype to start with

Given: a coin + a hypothesis. Ask:

1. **Has any archetype been tried on this coin?** Check `coin_profiles.md`.
2. **What's the coin's vol?**
   - < 60% → Pure Shield → Sigmoid V2 → Calendar (progressive)
   - 60-80% → Pure Shield → Calendar (skip Sigmoid V2 — needs halving)
   - 80-100% → VolShield
   - 100% → custom (no proven template yet)
3. **What's the role?**
   - Primary, maximize return → start with the closest proven archetype
   - Defensive sleeve → Triple Regime
4. **What's the hypothesis adding?**
   - New feature on existing archetype → use that archetype's template + 1 added feature
   - New regime detector entirely → custom from scratch (rare)

When in doubt: start with the simplest archetype that fits, validate, then add ONE feature at a time.

## Anti-architecture (what NOT to design)

1. **"Mega-strategy" with all features**: combines Sigmoid + Calendar + Sentiment + 3 detectors + cooldown. Untrackable, overfit-prone.
2. **Re-implementing FX strategies**: forex/equity patterns don't transfer cleanly to crypto.
3. **Per-trade signal classifiers**: deep-learning per-trade entry classifiers fail on 1d timeframe (too few samples per coin).
4. **Self-tuning hyperparameters**: walk-forward optimization sounds smart but ALWAYS overfits at the timeframe boundaries.

## When to extend the archetype list

When you discover a new pattern that:
- PASSES adversarial on at least 2 coins
- Outperforms its base archetype by ≥ 5pp/yr
- Has interpretable mechanism (you can explain WHY it works)

Then add to `architecture_patterns.md` as Archetype 6+. Until then, don't proliferate.
