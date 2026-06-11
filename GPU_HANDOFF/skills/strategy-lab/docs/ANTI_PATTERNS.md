# Anti-Patterns — What NOT to Do

Each anti-pattern below was a real mistake made (or avoided) during the AI integration sweep. They're listed with the actual failure data so future-you can recognize the symptoms early.

---

## Anti-Pattern 1: Trust Single-Window Backtests

**Failure case: AVAX Btc3Layer (Idea C audit)**

The archive showed `Btc3LayerStrategy` had:
- n=15 runs on AVAX
- Median ROI +107%
- **Sharpe 0.79** (compared to current live AVAX MetaAdaptive at Sharpe 0.11)

We deployed a fresh 5-year backtest as A/B candidate. Result:

| Year | ROI |
|---|---|
| 2021 | +285% |
| **2022** | **-63%** |
| 2023 | +180% |
| 2024 | -7% |
| **2025** | **-46%** |
| **2026 Q12** | **-24%** |

**Adversarial: CATASTROPHIC** (all 3 windows negative).

The 0.79 Sharpe came from runs covering 2021-2023, missing the 2022 bear period entirely. Pure timerange cherry-picking.

**Lesson:** Archive Sharpe is informative but never decisive. ALWAYS run fresh 6-year + 3-window adversarial before trusting any archive ranking.

---

## Anti-Pattern 2: Assume BTC Indicators Transfer

**Failure case: SOL Pure Shield (sub #102 → rejected first time)**

BTC's Pure Shield (close > EMA200 AND ret_30d > 5% AND ADX > 20) works beautifully on BTC.
On SOL:

| Year | ROI |
|---|---|
| 2021 | +903% (great but cycle-favored) |
| 2022 | -32% |
| 2023 | +231% |
| 2024 | +44% |
| **2025** | **-43%** ← killed by sideways chop |
| 2026 Q12 | 0% |

**Adversarial: CATASTROPHIC** (-43% in sideways).

Same failure for SOL AI Shield V2 (-35% in 2025).

The fix took 3 iterations and a custom volatility-aware design (Pattern 4). Default thresholds calibrated to BTC's ~55% annualized vol won't work for SOL's ~95%.

**Lesson:** Annualized vol > 80% requires custom filters. Specifically: longer trend windows (ret_60d not ret_30d), higher ADX threshold (30 not 20), ATR_pct ceiling, and 5-day regime confirmation.

---

## Anti-Pattern 3: Deploy Despite Failed Adversarial

**Temptation:** SOL DynRebal (existing live bot) has -87% in 2022. **FAILS adversarial.** But its 5y compound is +440% (~40%/yr). Should we keep it?

Reasoning that FAILS:
- "The bull years dominate compound, so net we win"
- "It's already live, we'd disrupt things by changing"
- "What are the odds of repeating 2022?"

Why this reasoning is wrong:
- A user starting a fresh $3K deployment in Q1 2022 saw -87%. The historical bull years are not in their personal future.
- Adversarial failure means a forward-looking risk. We're betting against another 2022.
- "Odds of repeating" — bear markets in crypto have happened repeatedly (2014, 2018, 2022, 2026). Pattern is real.

**Correct response:** Find a strategy that passes adversarial AND has acceptable compound. We did — SOL VolShield v3 (+45%/yr, WARN). Deployed alongside.

**Lesson:** Adversarial verdict is a GATE, not a recommendation. Compound is INTERESTING, not decisive.

---

## Anti-Pattern 4: Add Features Beyond Hypothesis

**Failure case:** (avoided) Initial Calendar Shield design proposal included:
- Calendar tilts ✓ (the hypothesis)
- Hour-of-day filtering (added "for completeness")
- Volume-weighted entry size (added "while we're at it")
- Sentiment integration (added "to be thorough")

If we'd shipped this, every failure would be untraceable. Which feature caused the -30% in 2025? Calendar? Volume? Sentiment? Impossible to know.

What we actually shipped: Calendar tilts ONLY, on top of V2 with NOTHING else changed.

**Result:** +1.7pp/yr clearly attributable to calendar tilts. If it had failed, we'd know exactly why.

**Lesson:** ONE hypothesis = ONE feature change. Compose later if individual changes prove out.

---

## Anti-Pattern 5: Skip the Pre-Mortem

Before testing a new idea, ask: "What would failure look like?"

If you can't articulate the failure mode, you don't understand the hypothesis well enough to test it.

**Examples of good pre-mortems:**

- AI Shield V3 Cooldown (post-anomaly skip 7 days): "Would fail if anomalies are SETUPS for bigger moves, not corrections." Result: failed exactly this way. -8% from missed rebounds.

- Sentiment Shield (FGI tilt): "Would fail if FGI is redundant with cycle_phase (because both are correlated)." Result: failed exactly this way. Compound was within $1K of Calendar Shield.

- SOL 3Layer: "Would fail if archive scores came from cycle-favored windows." Result: -63% in 2022 bear.

**Examples of missed pre-mortems:**

- ADA AI Shield V2: didn't pre-mortem the SOL→ADA transfer risk. Got CATASTROPHIC -44%.

**Lesson:** Spend 60 seconds on pre-mortem BEFORE running backtests. Saves hours of explaining bad results.

---

## Anti-Pattern 6: Pursue ML When Heuristic Suffices

**Failure case:** Idea I — RL Meta-Allocator.

Portfolio simulator over actual yearly returns showed:
- Equal weight: 46%/yr
- Top-3 trailing Sharpe (heuristic): 50.2%/yr
- Hindsight best: 163%/yr (unreachable)
- Hindsight top-3: 119%/yr (unreachable)

The REALISTIC improvement RL could deliver = ~4pp/yr over heuristic. Training cost: 4-8 hours + complex code maintenance.

**Decision:** Skip RL, use heuristic meta-allocator already built (scored sub-rebalancing). Schedule as weekly cron.

**Lesson:** Before building ML solutions, simulate the BEST POSSIBLE outcome (oracle). If oracle - heuristic < 10pp, don't bother with ML. Maintenance overhead alone usually eats > 10pp/yr in attention drain.

---

## Anti-Pattern 7: Test Expensive Signal First

**Failure case:** (avoided) Idea H — FinBERT.

Planning to do FinBERT meant:
- 440MB model download
- News headline scraping infrastructure
- Historical news data (which doesn't exist for 5y windows cheaply)
- Transformer inference pipeline
- Sentiment-to-signal conversion

Estimated effort: 1-2 days.

**What we did instead:** Tested Fear & Greed Index (free, historical, 2018-2026 data). It's a smoothed sentiment proxy.

Result: FGI had +13.5% correlation with 30d fwd returns BUT was redundant with cycle_phase. Signal exists but adds nothing new.

If FGI was useful, FinBERT might have added granularity. Since FGI was redundant, FinBERT (noisier source) would be MORE redundant.

**Lesson:** Always test the cheapest proxy first. If it shows no signal, skip the expensive pipeline. If it shows signal, you may not need the expensive pipeline.

---

## Anti-Pattern 8: Document Failures Vaguely

Documenting "this didn't work" is useless. Future-you needs the SPECIFIC failure mode.

**Bad failure note:**
> "AI Shield V3 didn't beat V2."

**Good failure note (what we actually wrote):**
> "AI Shield V3 (cooldown after anomaly): added 7-day skip after anomaly_flag. Hypothesis was 'post-anomaly bounces are dead-cat'. WRONG for BTC bulls — anomalies are often SETUPS for bigger moves. 2023 result -8% from missed rebounds. Yearly: 2021 +77% (vs V2 +118%), 2022 0%, 2023 +31% (vs +44%), rest similar. Compound $33K vs V2's $48K. Adversarial PASS but inferior. Saved as research/ai/btc_ai_shield_v3_strategy.py for reference but NOT deployed."

The second version lets a future session know exactly when this idea WOULD work (e.g., if testing on a coin where bounces ARE dead-cats — meme coins maybe).

**Lesson:** Failure notes should be specific enough that the next person can decide whether to retry in a different context. Hypothesis + specific failure mode + numbers + next-time-when.

---

## Anti-Pattern 9: Optimize Over Multiple Single Metrics

Showcase: BNB strategy selection.

Live BNB: BtcRegimeShield. Backtest +52%/yr. Worst case -20%. **Adversarial FAIL.**
Alternative 1: BtcRotation. Backtest +27%/yr (lower). Worst case +9% (better!). **Still Adversarial FAIL** (different window).
Alternative 2: BtcTripleRegime. Backtest +17.7%/yr. Worst case -5.8%. **Adversarial WARN.**

Decisions to AVOID:
- "Rotation has better worst-case, switch" → Adversarial still FAIL, no real gain
- "Triple has lower compound, skip" → ignores the GATE
- "Compound max → RegimeShield" → ignores GATE

Correct decision: deploy Triple alongside RegimeShield as DEFENSIVE SLEEVE. Each plays a role.

**Lesson:** Don't optimize on compound OR Sharpe OR worst-case in isolation. Adversarial GATE first, then portfolio role second.

---

## Anti-Pattern 10: "Just one more parameter" tuning

Sign of overfit: you find your strategy fails one specific window, so you add a parameter to "fix" exactly that window.

**Failure example (avoided):** Tempted to add "if year >= 2025 and ret_30d < 0 then exit" to make SOL Pure Shield's -43% in 2025 disappear.

This would have:
- Made the 2025 number look good
- Failed on the NEXT sideways year (which we don't have data for)
- Been pure overfit

What we did instead: redesigned the FILTERS (vol-aware) so the strategy was inherently robust to sideways chop, not just to the specific 2025 sideways.

**Lesson:** Fix the GENERATING PROCESS (filter logic, regime detection), not the specific bad year. If you can't explain WHY the parameter change works in general, it's overfit.
