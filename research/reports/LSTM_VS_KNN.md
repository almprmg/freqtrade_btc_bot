# LSTM Embedding vs KNN — AnalogV3 Results

**Date:** 2026-06-11 · **Machine:** GPU (RTX A3000, 6 GB) · **Branch:** `gpu/lstm-v1-btc`

GPU_HANDOFF task #1: replace the KNN-based AnalogV2 signal (corr +0.06) with an
LSTM that encodes the last 60 days → embedding → predicts fwd-30d return.
Target was corr ≥ +0.15.

---

## 1. Correlation — single-split vs walk-forward

The single 80/20 split is **optimistic** (it lands on one regime). Walk-forward
(5 expanding folds, per-fold train-only scaling) is the number to trust.

| Coin | KNN | LSTM single-split | **LSTM walk-forward** (mean ± std) |
|---|---|---|---|
| BTC | +0.06 | +0.51 | **+0.33 ± 0.24** |
| ETH | +0.06 | +0.57 | **+0.26 ± 0.31** |
| BNB | +0.06 | +0.27 | **+0.31 ± 0.24** |
| XRP | +0.06 | +0.13 | **+0.32 ± 0.27** |
| DOGE | +0.06 | +0.29 | **+0.26 ± 0.18** |
| SOL | +0.06 | +0.15 | **+0.27 ± 0.14** |
| ADA | +0.06 | +0.45 | **+0.06 ± 0.20** |

**Walk-forward avg ≈ +0.26** (corr loss), well above KNN +0.06 and the +0.15 target.
ADA shows no real edge; all others beat target on average. Variance is high
(~0.2–0.3) → the edge is real but regime-dependent.

## 2. What drove it

- **Macro + halving-cycle features are the signal.** Price-only LSTM peaked +0.147
  then overfit to −0.16; adding DXY/VIX/SPY + halving phase lifted it to the table above.
- **Correlation loss > MSE.** The signal is directional, so a Pearson-corr loss beats
  MSE: walk-forward avg +0.19 → +0.26, SOL flipped −0.19 → +0.27, DOGE variance 0.47 → 0.18.
  (ETH alone prefers MSE.)
- **Joint multi-coin model did NOT help** under walk-forward (avg ~+0.18 vs +0.26 separate).
  Ship separate per-coin models.

## 3. Does corr turn into PnL? (freqtrade-free OOS backtest)

Long/flat vs buy&hold on the out-of-sample tail (2024-10 → 2026-05), offset-robust
rule (long when pred > trailing mean), **no fees**. See `GPU_HANDOFF/backtest_signal.py`.

| Coin | Strat CAGR | Buy&Hold | Strat Sharpe | B&H | Strat maxDD | B&H |
|---|---|---|---|---|---|---|
| **BTC** | **+37.5%** | +19.3% | **1.09** | 0.61 | **−31%** | −50% |
| SOL | +9.1% | −42.3% | 0.42 | −0.40 | −42% | −69% |
| DOGE | −4.8% | −50.0% | 0.24 | −0.35 | −42% | −69% |
| ADA | −37.7% | −52.0% | −0.15 | −0.23 | −65% | −81% |
| XRP | −4.9% | −1.5% | 0.20 | 0.40 | −47% | −66% |
| ETH | −21.3% | −2.4% | −0.15 | 0.33 | −62% | −63% |
| BNB | −12.2% | +6.9% | −0.15 | 0.39 | −39% | −55% |

Beats buy&hold: **CAGR 4/7, Sharpe 4/7**; mean Sharpe +0.21 vs +0.11.

**Read:** strong alpha on BTC + drawdown reduction on *every* coin (it sits out
crashes). Loses by being flat during sharp ETH/BNB rallies. One regime, fees not modeled.

## 4. AnalogV3 strategy

`user_data/strategies/btc_analog_v3_strategy.py` — identical to AnalogV2 except the
analog tilt comes from `dl_signals_lstm_{coin}.feather` (causal z-scored) instead of
the KNN feather. Fair A/B with AnalogV2.

⚠️ **The 9-year freqtrade backtest must run on the CPU machine** — freqtrade /
TA-Lib won't install on this GPU box (compiled DLL blocked by Windows Application
Control). The vectorized OOS check above is the GPU-side substitute.

## 5. Verdict & next

- ✅ Task #1 target met: walk-forward corr ~+0.26 avg (vs +0.15 target, +0.06 KNN).
- ✅ BTC is the deploy candidate (corr +0.33, OOS +37.5% vs +19.3%, lower DD).
- ⏭️ On CPU machine: run AnalogV3 9-year backtest, compare to AnalogV2 (+32% BTC / +42% ETH).
- ⏭️ Add fees to confirm BTC survives costs; consider LSTM as a risk-overlay on AnalogV2.
- ⏭️ Cut fold variance: rank/IC loss, regime-conditioning, more data.
