# LSTM Experiments — Final Report

**Date:** 2026-06-11 · **Machine:** GPU (RTX A3000) · **Branch:** `gpu/lstm-v1-btc`
**Metric:** walk-forward correlation (5 expanding folds, per-fold train-only scaling) — the only honest metric; single-split misled us repeatedly.

Goal: train/experiment with AI models to predict fwd return, beating the KNN AnalogV2 (corr +0.06).

---

## 1. Timeframe — the edge is DAILY only

WF mean corr (corr loss, lstm baseline):

| Coin | 1d | 4h | 1h | 15m |
|---|---|---|---|---|
| BTC | **+0.33** | +0.05 | +0.05 | +0.06 |
| ETH | **+0.26** | +0.07 | +0.08 | +0.06 |

Intraday collapses to noise — the signal is driven by **daily** macro (DXY/VIX/SPY) + halving-cycle features, constant within a day.

## 2. Architecture / capacity / loss sweep (BTC+ETH 1d)

One-factor-at-a-time vs baseline (lstm, hidden64, layers2, dropout0.3, seq60, corr loss), ranked by avg(BTC,ETH):

| Rank | Config | BTC | ETH | **Avg** |
|---|---|---|---|---|
| 1 | **arch=transformer** | +0.42 | +0.39 | **+0.41** |
| 2 | seq=30 | +0.37 | +0.29 | +0.33 |
| 3 | baseline (lstm) | +0.31 | +0.27 | +0.29 |
| 4 | hidden=128 | +0.34 | +0.21 | +0.28 |
| 5 | loss=combo | +0.32 | +0.24 | +0.28 |
| 6 | arch=gru | +0.23 | +0.31 | +0.27 |
| 7 | dropout=0.5 | +0.28 | +0.25 | +0.27 |
| 8 | seq=90 | +0.27 | +0.26 | +0.27 |
| 9 | layers=3 | +0.30 | +0.22 | +0.26 |
| 10 | layers=1 | +0.30 | +0.22 | +0.26 |
| 11 | loss=mse | +0.15 | +0.27 | +0.21 |

Combo test: transformer+seq30 → BTC +0.27 / ETH +0.42 (ETH std 0.04, most stable) — didn't stack for BTC, so best overall stays **transformer + seq60**.

**Takeaways:**
- **Transformer wins clearly** (+0.41 vs +0.29 LSTM) — best architecture. Matches the planned task #3.
- **Shorter lookback helps** (seq30 > seq60 > seq90) — recent month carries the signal.
- **corr/combo loss >> mse** (mse worst at +0.21) — confirms directional objective.
- hidden/layers/dropout: minor.

## 3. Intraday rescue with funding rate — failed

Adding perp funding rate (8h, intraday-native) to the 1h model:

| Coin | base | +funding | Δ |
|---|---|---|---|
| BTC 1h | +0.049 | +0.076 | +0.028 |
| ETH 1h | +0.073 | +0.072 | −0.001 |

Still noise. One intraday feature isn't enough; intraday would need a richer microstructure/order-flow stack.

---

## 4. Verdict

- **Best model so far: Transformer, daily, seq≈30-60, corr loss → WF corr ~+0.41** (vs KNN +0.06, LSTM +0.29). ~7× the KNN baseline.
- Keep it **daily-only**. Intraday is not viable with the current feature set.
- Still regime-dependent (fold std ~0.2-0.3); ETH transformer+seq30 was the most stable (std 0.04).

## 5. Next levers
1. **Ship a Transformer model** (wire build_model into train()/inference, save arch in checkpoint) and regenerate signals.
2. Reduce fold variance: ensemble across seeds, regime-conditioning.
3. On the CPU machine: AnalogV3 (transformer signal) vs AnalogV2 9-year freqtrade backtest — the real PnL test.

Scripts: `dl_train_lstm.py` (--arch/--hidden/--layers/--dropout/--seq/--timeframe), `sweep.py`, `intraday_funding_test.py`, `download_funding.py`. Raw grid: `research/dl_models/sweep_results.json`.
