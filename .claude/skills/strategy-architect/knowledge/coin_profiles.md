# Per-Coin Profiles

Hard-won knowledge per coin from 22+ tested candidates across the major batch session.

## Quick table

| Coin | Ann. Vol | What works (PASS/WARN) | What fails | Live bots |
|---|---|---|---|---|
| BTC | ~55% | AI Shield V2, Calendar Shield, Triple | AI Shield V3 (cooldown), Per-asset Cycles, Rotation alts | 3 bots |
| ETH | ~70% | Pure Shield, Calendar Shield | DynRebal alone (bear-exposed) | 2-3 bots |
| BNB | ~65% | Pure Shield, Triple Regime | Rotation (no improvement) | 2 bots |
| ADA | ~80% | MetaAdaptive, Triple Regime | AI Shield V2 (CATASTROPHIC), Calendar untested | 2 bots |
| SOL | ~95% | VolShield v3 (custom) | Pure Shield, AIShV2, Triple, "any BTC port" | 2 bots |
| AVAX | ~95% | MetaAdaptive (status quo) | Btc3Layer (CATASTROPHIC), all alternatives | 1 bot |
| DOGE | ~110% | Pure Shield Defensive (status quo) | Triple, Adaptive — none work | 1 bot (open challenge) |

## BTC

**Vol profile:** ~55% annualized — lowest among the seven we track.

**Why it's special:**
- Has halving cycle data (4-year periodicity)
- Phase-based bias works
- Calendar effects strongest here (Bonferroni-survived)
- Indicators behave "textbook"

**Production live:**
- AI Shield V2 (#98) — sigmoid sizing on halving cycle. +36.5%/yr.
- Triple Regime (#99) — defensive sleeve. +10.5%/yr.
- Calendar Shield (#100) — V2 + calendar tilts. +38.2%/yr. ← currently strongest on BTC.

**Recommended next experiments:**
- Combining V2 + Calendar + Triple in a meta-bot ensemble
- Testing Calendar's tilts with different weights for different cycle phases

## ETH

**Vol profile:** ~70% annualized.

**Behavior notes:**
- Bear drawdowns are deeper than BTC (-77% in 2022 vs BTC's -65%)
- DynRebal essentially HODL — bear-exposed
- Calendar tilts ported beautifully (+55%/yr deploy, strongest in session)

**Production live:**
- DynRebal (existing) — bear-exposed, FAILS adversarial
- Pure Shield (#101) — fixed bear gap. +47%/yr.
- Calendar Shield (#105) — Pure Shield + tilts. +55%/yr ← strongest deploy of session.

**Recommended next experiments:**
- Sentiment overlay (specifically for ETH — different from BTC)
- ETH-specific anomaly thresholds (currently using BTC-trained model)

## BNB

**Vol profile:** ~65%.

**Behavior notes:**
- Behaves similar to BTC in bull years
- Bears are moderate (-30 to -50% range)
- Pure Shield gets -20% in 2022 — FAILS adversarial despite +52%/yr compound

**Production live:**
- Pure Shield (existing) — strong compound but FAILS adversarial
- Triple Regime (#103) — defensive sleeve. +17.7%/yr WARN.

**Recommended next experiments:**
- Calendar Shield port (untested — should work based on ETH success)
- Hybrid: Pure Shield with stricter bear exit

## ADA

**Vol profile:** ~80% annualized.

**Behavior notes:**
- Borderline between low and high vol
- Pure Shield works but with degraded performance
- Triple Regime is the cleanest PASS adversarial

**Production live:**
- MetaAdaptive (existing) — FAILS adversarial (-22% in 2025 sideways)
- Triple Regime (#104) — defensive. +14.4%/yr PASS.

**Failed experiments:**
- AI Shield V2 → -44% in 2025 (CATASTROPHIC) — halving phases don't transfer

**Recommended next:**
- Calendar Shield port to ADA (untested, may work given ETH success)
- ADA-specific volshield calibration (between Pure and Vol thresholds)

## SOL

**Vol profile:** ~95% annualized — the chop king.

**Behavior notes:**
- Massive bull years (+637% in 2021, +509% in 2023)
- Brutal bears (-87% in 2022 — worst of the 7)
- Multi-month chop periods kill simple shields
- 4 Shield variants needed before one passed (VolShield v3)

**Production live:**
- DynRebal (existing) — strong compound but CATASTROPHIC adversarial
- VolShield v3 (#102) — custom design. +45%/yr WARN.

**Failed experiments (all rejected):**
- Pure Shield → -43% in 2025 (CATASTROPHIC)
- AI Shield V2 → -35% in 2025 (CATASTROPHIC)
- Triple Regime → +3.6%/yr (too defensive)
- VolShield v1 (too strict) → 0 trades
- VolShield v2 (too loose) → -16% in 2025 (FAIL)

**Recommended next:**
- VolShield v4 with sentiment overlay (FGI signal)
- Multi-position SOL (small + sized — to dampen single-trade losses)

## AVAX

**Vol profile:** ~95% — twin to SOL but with different microstructure.

**Behavior notes:**
- Better volume profile than SOL (cleaner candles)
- Same chop problem in sideways
- Archive's "Btc3Layer Sharpe 0.79" was the worst overfit trap of the session

**Production live:**
- MetaAdaptive (existing) — modest +33%/yr median

**Failed experiments:**
- Btc3Layer → -63% in 2022 (CATASTROPHIC) — pure archive overfit

**Recommended next:**
- VolShield port from SOL (the pattern that works on SOL might work on AVAX)
- Custom AVAX strategy combining MetaAdaptive's strengths with VolShield filters

## DOGE — OPEN CHALLENGE

**Vol profile:** ~110% — highest of the seven.

**Behavior notes:**
- Meme-coin dynamics: pump-and-dump cycles overlay on macro
- Bull years +1679% (extreme)
- Bears moderate-to-bad (-30 to -50%)
- NO bear protection strategy has worked yet

**Production live:**
- Pure Shield Defensive (existing) — CATASTROPHIC adversarial but holds because compound is so strong

**Failed experiments:**
- RegimeShield → -32% / -19% (CATASTROPHIC)
- BtcAdaptive → -23% / -27% (FAIL)
- Triple Regime → -17% in 2025 (FAIL)

**Why none work:** DOGE moves on social momentum, not technical regime. Indicators arrive after the move.

**Recommended next:**
- Social-driven entries (volume spike + price-acceleration filter)
- Tighter trailing stops (DOGE pumps are short-lived)
- Position sizing based on recent vol expansion
