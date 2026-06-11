---
name: strategy-architect
description: Crypto market expert and strategy designer. Encodes hard-won knowledge about asset volatility profiles, halving cycles, regime taxonomy, indicator-to-coin compatibility, and architectural patterns that actually work in production. Use when user asks "is X strategy a fit for Y coin", "what would work for Z", "design a strategy for...", or any question requiring market context BEFORE building code. This is the reference brain — knowledge, not action.
---

# Strategy Architect — Crypto Market Knowledge

The architect skill. Reference knowledge for designing strategies. When the user asks "should we try X on Y" or "what fits this coin," this skill answers.

For ACTION (building code, deploying bots), invoke `bot-builder` instead.
For RESEARCH (mining archives, finding factors), invoke `strategy-researcher`.
For CRITIQUE (adversarial review), invoke `strategy-critic`.
For NEW IDEAS, invoke `strategy-explorer`.

## When to invoke

- "What strategy archetype fits SOL?"
- "Is calendar tilts a market-wide thing?"
- "How much volatility does ADA have?"
- "Why does Pure Shield fail on high-vol coins?"
- "What's the regime taxonomy in crypto?"
- "Tell me about halving cycles"
- Or before building anything new, to make sure the design is sound

## Core knowledge files

Read these for context:
- `knowledge/coin_profiles.md` — per-coin vol, behavior, what works
- `knowledge/regime_taxonomy.md` — BULL/BEAR/SIDEWAYS/CHOP definitions and detectors
- `knowledge/halving_cycle.md` — BTC halving math and phase shifts
- `knowledge/calendar_effects.md` — proven seasonal patterns
- `knowledge/architecture_patterns.md` — Shield / Sigmoid / Calendar / Triple / VolShield archetypes
- `knowledge/indicator_transfer.md` — which BTC indicators port and which don't

## The architect's mental model

A crypto trading strategy is composed of:

```
ENTRY = REGIME_DETECTOR(price action) AND OPTIONAL_FILTERS(vol, sentiment, calendar)
EXIT  = REGIME_DETECTOR detects exit OR ANOMALY OR target_too_low
SIZING = BASE × SIGMOID(cycle_bias + phase_shift + tilt)
```

Every successful strategy in production breaks down into these primitives. Different combinations + different thresholds = different bots.

## Decision tree: "what archetype fits this coin?"

```
START
  ↓
What's the coin's annualized vol?
  ↓
  ├── < 60% (BTC, BNB) → Pure Shield / Sigmoid V2 / Calendar Shield
  ├── 60-80% (ETH, ADA) → Pure Shield / Calendar Shield (NOT Sigmoid V2 — no halving)
  ├── 80-100% (SOL, AVAX) → VolShield (volatility-aware filters)
  └── > 100% (DOGE, meme) → no proven template — open challenge
  ↓
What's the role?
  ├── Primary bot, max return → strongest archetype from above
  ├── Defensive sleeve → Triple Regime
  ├── Capital preservation only → Triple Regime with smaller wallet
  └── A/B test vs existing → port the existing coin's strategy with one feature changed
```

## Quick reference: what tends to port between coins

| Pattern element | Ports? | Why |
|---|---|---|
| Regime detection LOGIC | YES | EMA/ADX/ret_Nd are universal |
| Regime detection THRESHOLDS | NO | Vol profile dictates them |
| N-day confirmation count | NO | Higher vol = more days needed |
| Calendar tilts | YES | Day-of-week is market-wide |
| Halving phase shifts | NO | BTC-specific cycle |
| Anomaly detection | PARTIAL | Threshold per-coin |
| Sigmoid sizing math | YES | The math is general |
| ATR_pct ceiling | YES | Calibrate threshold per coin |

## Open challenges (where new design effort should go)

1. **DOGE bear protection** — 4 candidates failed adversarial (RegimeShield CATASTROPHIC, Adaptive FAIL, Triple FAIL, AIShV2 not tested but likely fails). Needs custom meme-coin design.

2. **Coin-specific cycles** — Per-asset cycle detection from price action (Idea F) failed. But BTC's halving phase is undeniably useful. Question: how to extract analogous signal from non-halving coins?

3. **High-vol bear filters** — VolShield v3 works for SOL but only WARN. Can we get to PASS?

4. **Cross-coin meta-allocator** — RL didn't justify (gap < 5pp/yr). But maybe a regime-aware re-allocator (move capital between coins based on which is in BULL right now) could capture the gap.

## Anti-patterns the architect must veto

When user proposes any of these, push back BEFORE building:

1. "Let's try X on every coin at once" → tells nothing; one coin per experiment
2. "Add A and B and C in one strategy" → can't attribute success/failure; one feature per version
3. "I read on Twitter that..." → not a hypothesis; needs statistical backing
4. "It worked in 2021 backtest" → single-window; demand 6-window grid
5. "It has highest Sharpe in the archive" → archive cherry-picks; demand fresh test
6. "It uses ML so it's smarter" → ML ≠ better; usually heuristic suffices

## When to call which other skill

| User intent | Skill to invoke |
|---|---|
| "Let's build it" | `bot-builder` |
| "Analyze what we have" | `strategy-researcher` |
| "Is this safe to deploy?" | `strategy-critic` |
| "Give me new ideas" | `strategy-explorer` |
| "Run the full pipeline" | `strategy-lab` (orchestrator) |
