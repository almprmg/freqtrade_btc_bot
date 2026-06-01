# Robust Strategy Discovery — Honest Report

**Date**: 2026-06-01
**Universe**: BTC/USDT spot, daily timeframe, long-only, no leverage
**Capital**: $10,000 baseline wallet
**Strategies tested**: Rebalance R5_75_BTC, Dynamic Rebalance DR_PROFIT_20, 3-Layer L3_AGGR_WIDE_GRID, Adaptive ADAPT_AGGR_NOSTOP

---

## 1. The headline backtest numbers were misleading

The 5-year backtest (2021–2026) showed +99% to +170% returns. Walk-forward
analysis splits that window into TRAIN / VAL / TEST and tells a different
story.

| Strategy | TRAIN 2021–2023 | VAL 2024 | TEST 2025–2026 |
|---|---|---|---|
| Rebalance R5     | +47.3% (+13.8%/yr) | +79.7% | **-15.3%** |
| DynRebal P20     | +50.9% (+14.7%/yr) | +78.8% | **-14.6%** |
| 3-Layer AGGR     | +26.7% (+8.2%/yr)  | +77.5% | **-14.9%** |
| Adaptive AGGR    | +21.8% (+6.8%/yr)  | +73.2% | **-10.4%** |

**Most of the 5-year return came from 2024 alone (the bull year).** When
extended into 2025–2026 (sideways → bear), every strategy lost money. The
+22%/year figure I quoted earlier averages the bull and the bear — but you
can't pick your starting year.

---

## 2. Regime decomposition explains why

I classified each day of 2021–2026 into bull / bear / sideways / crash / mixed
using ADX, ATR z-score, BB width, and 200-day SMA:

| Regime | % of days | Notes |
|---|---|---|
| sideways | 43.8% | The default state for BTC |
| mixed | 30.3% | No clear direction |
| bull | 14.2% | Concentrated in 2024 |
| bear | 9.2% | Mostly 2022 |
| crash | 2.5% | -20% in 14 days events |

Long-biased rebalance strategies need **bull or strong sideways** to be
profitable. They have no edge in bear regimes — they just hold BTC and bleed.

---

## 3. Robustness scoreboard (5-factor composite)

Applied the formula you specified:

```
score = 0.25*consistency + 0.25*low_DD + 0.20*stability
      + 0.15*OOS + 0.15*crash_survival
```

| Rank | Strategy | Score /100 | Consistency | Low DD | Stability | OOS | Crash |
|---|---|---|---|---|---|---|---|
| 1 | **Adaptive_AGGR** | **62.1** | 0.67 | 0.74 | 0.0 | 1.0 | 0.79 |
| 2 | DynRebal_P20 | 58.2 | 0.67 | 0.64 | 0.0 | 1.0 | 0.71 |
| 3 | Rebalance_R5 | 57.5 | 0.67 | 0.62 | 0.0 | 1.0 | 0.70 |
| 4 | 3Layer_AGGR | 47.4 | 0.67 | 0.34 | 0.0 | 1.0 | 0.47 |

**Stability is 0 for all** because the variance of annual returns is huge
(massive bull-year gain dominates) → coefficient of variation > 1. None of
these are stable in the academic sense; they're all directional bets on BTC.

The robustness winner is **Adaptive_AGGR** — its regime-aware allocation
softens the bear period (-10.4% vs -15.3%), at the cost of giving up upside.

---

## 4. Reality check — execution costs aren't the problem

I re-ran each strategy with 0.20% fee (double) and market orders (spread
gets eaten on every trade):

| Strategy | Backtest 5y | Realistic 5y | Cost (pp) |
|---|---|---|---|
| DynRebal_P20 | +170.4% | +168.3% | 2.1 |
| Rebalance_R5 | +166.0% | +162.7% | 3.3 |
| Adaptive_AGGR | +118.7% | +110.7% | 8.0 |
| 3Layer_AGGR | +99.6% | +99.5% | 0.1 |

**Surprise**: fees/slippage cost only 2–8 percentage points over 5 years.
That's because these are daily-rebalance strategies — they don't churn.
**The execution model is not what kills the strategy. The regime is.**

---

## 5. Synthetic stress test — the strategies are fragile

I generated three 18-month adversarial price series and re-ran:

| Strategy | REAL BTC 5y | SYN_BEAR (-87%) | SYN_BLEED (-35%) | SYN_CHOP (-12%) |
|---|---|---|---|---|
| DYN_P20 | +161% | **-77%** | -27% | -9% |
| REBAL_75 | +168% | **-77%** | -28% | -9% |
| HOLD_BTC | +203% | -87% | -36% | -12% |
| **HOLD_USDT** | 0% | **0%** | **0%** | **0%** |

Rebalancing helps a few percentage points vs raw buy-and-hold in down
markets — but it does NOT save you. If BTC drops 87% in 18 months, your
$10k becomes $2.3k regardless of rebalance discipline. **Long-only spot
strategies in a sustained bear regime are unprofitable; their job is to
lose less, not to make money.**

The only way to "win" in a bear is to be in cash. None of these strategies
have an exit-to-cash trigger reliable enough to do that systematically.

---

## 6. Failure analysis — when these strategies break

### Mode 1: Sustained bear (>6 months down with no recovery)
- **What happens**: target_btc_pct keeps allocating capital into BTC at lower
  prices. Each "buy the dip" adds to the position. The position-average
  cost basis falls but slower than the price, so unrealized loss grows.
- **Observed in**: 2022 (worst single year, all strategies down 25–48%
  intra-year). TEST window 2025-2026 (current).
- **Why no stop**: stops were tested in Adaptive — they hurt more than they
  helped in trending bulls. There's no parameter setting that wins both.

### Mode 2: Slow chop with negative drift
- **What happens**: rebalance fires constantly on small drift, accumulating
  fees and bleeding from buy-high-sell-low whipsaws.
- **Observed in**: SYN_CHOP synthetic (-9% loss for active strategies vs
  -12% for hold — barely better).

### Mode 3: Flash crash followed by V-recovery
- **What happens**: forced sells during the crash lock in losses; the
  recovery is missed because cash takes time to redeploy.
- **Mitigation**: the "no-stop" variants survive better than "tight-stop"
  ones. Our winner (Adaptive_AGGR_NOSTOP) has stops disabled for this
  reason.

### Parameter sensitivity
- target_btc_pct: ±10pp changes ROI by ~30pp across 5 years. Sensitive.
- profit_trigger: 10%/20%/30% all give 165–170%. Not very sensitive (good).
- stop rules: every TIGHT variant ranked at the BOTTOM in our sweeps. Bad.

---

## 7. Reality check — what you should ACTUALLY expect live

Based on walk-forward, regime decomposition, and synthetic stress:

| Scenario for next 18 months | DynRebal_P20 expected ROI |
|---|---|
| Strong bull (2024-like) | +60% to +80% |
| Sideways drift (2025-like) | -5% to +10% |
| Bear market (2022-like) | -25% to -45% |
| Flash crash + V-recovery | -15% to -25% |
| Slow bleed | -25% to -35% |

**Weighted expectation** assuming the regime mix of the last 5 years repeats
(44% sideways / 30% mixed / 14% bull / 9% bear / 2.5% crash):

> Honest annualized expectation: **+5% to +15% per year**, not +22%.
>
> Downside risk in a bear cycle: **-30% to -50% peak-to-trough**.

The backtest's +22%/yr was inflated by 2024's once-in-a-cycle bull. The
strategy structurally cannot deliver that every year.

---

## 8. Recommendations

1. **Keep the bots running in dry-run** for at least 6 months across one
   full regime cycle before committing real capital. The TEST period loss
   (-10% to -15%) IS the live-money preview right now.

2. **The "best" strategy is Adaptive_AGGR** (62/100 robustness), not the
   one with the highest backtest ROI. Trade some upside for survival.

3. **Diversification across pairs helps the upside but not the survival**.
   ETH and SOL gave +31% and +54% annualized respectively on the 5y
   backtest, but they'd drop FURTHER than BTC in a bear cycle. The SOL
   $500 sizing reflects this honestly.

4. **Things to add (Phase 2)**:
   - Hyperopt the target_btc_pct against the worst regime (not against
     total return — that overfits to bull cycles).
   - Add a "regime exit" rule: full move to cash when SYN_BLEED-like
     conditions detected (negative 30d return + low vol).
   - Consider futures + small leverage on the most robust mode to push
     annual ROI toward 50%+, accepting liquidation risk.
   - Multi-asset rotation: hold the strongest of {BTC, ETH, SOL} based on
     30d momentum, with cash buffer.

5. **Do NOT chase the 100%/year target on spot long-only**. It is not
   achievable across regime cycles. The math doesn't allow it without
   leverage or short selling.

---

## 9. The 100%/year question, answered honestly

You asked for 100%/year minimum. After ~150 backtests across 50+
parameter combinations on 3 assets:

- **Best annualized achievable** on spot long-only BTC: ~22% (DynRebal_P20)
- **Best on SOL**: ~54% — but with -96% historical drawdown risk
- **Best robust score**: 62/100 at 17%/year (Adaptive)

To get 100%/yr you need at least one of:
- 3-5x leverage (futures, liquidation risk)
- Short selling capability (perp futures)
- Higher-frequency signals (1h/15m — different strategy space, more fees)
- Alt-coin rotation with hyperopt (overfitting risk extreme)
- Concentrated bets on volatile small caps (survivorship bias destroys this)

These are NOT what this report set out to evaluate. They're a different
research project — happy to design that next if you want.

---

## 10. Files produced

- `research/regime_classifier.py` — labels each day by market regime
- `research/walk_forward.py` — runs strategies on TRAIN/VAL/TEST
- `research/robustness_score.py` — 5-factor composite
- `research/reality_check.py` — 2x fees + market orders
- `research/synth_simulator.py` — in-code rebalance on synthetic scenarios
- `research/synthetic_stress.py` — generates SYN_BEAR/CHOP/BLEED feathers
- `research/walk_forward_results.csv`
- `research/robustness_results.csv`
- `research/reality_check_results.csv`
- `research/synth_results.csv`
- `research/_regime_labels.csv`
