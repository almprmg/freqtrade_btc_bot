# Critic Log

Calibration feedback loop for strategy-critic reviews.

---

## 2026-06-11 — BtcAnalogV3Strategy (LSTM signal) + LSTM v1 models

Reviewer: strategy-critic (applied manually; skill activated this session, loads next session).

```
=== Adversarial Review: AnalogV3 / LSTM v1 ===

Adversarial Verdict: INCOMPLETE — gate not run
  adversarial_validator.py requires freqtrade, which will NOT install on the
  GPU machine (TA-Lib compiled DLL blocked by Windows Application Control).
  Walk-forward (5 folds) is a partial proxy but is NOT the 3-window gate.

Overfit red flags detected (8 of 15 checklist items):
  #1  single-window darling — single-split corr was optimistic 3x (BTC +0.47,
      multi-coin +0.37, joint +0.37); only walk-forward (~+0.26) is honest. CAUGHT.
  #2  magic thresholds — build_halving.py phase boundaries (150/400/550/730/880/1200
      days) are a hand-tuned heuristic, not derived. Mild.
  #5  WR/profit-factor not measured in the vectorized backtest. GAP.
  #6  short history — SOL (2020+) / DOGE (2019+) lack a full pre-2020 bear;
      their LSTM edge is least trustworthy (SOL WF +0.27 but ADA-like risk).
  #9  metric degrades with more data — single-split >> walk-forward. CONFIRMED.
  #14 extreme constants inherited (stoploss -0.99, roi 10.0) — exit-via-regime;
      exit firing UNVERIFIED (no freqtrade run here).
  redundancy (#3 review) — LSTM ingests macro+halving, which AnalogV2 ALREADY
      uses (macro_tilt + cycle logic). AnalogV3's marginal value over V2 is
      therefore UNTESTED — could be largely redundant. HIGH-PRIORITY GAP.
  fees — OOS backtest models NO fees; 40-50% time-in-market = real turnover.

Strengths (counter-evidence, honestly):
  + Strong ablation done: price-only vs +macro/halving; MSE vs corr loss;
    separate vs joint. (checklist #12 satisfied)
  + HODL baseline shown (#13). BTC OOS +37.5% vs +19.3%, Sharpe 1.09 vs 0.61.
  + Pre-mortem articulated (#7): "fails when flat during sharp rallies" —
    CONFIRMED on ETH/BNB.
  + Leakage-free normalization (train-only scaler); no year-specific hacks (#11).

DEPLOYMENT RECOMMENDATION:
  [X] VETO (research-only) — reason: deploy gate (adversarial_validator) never
      run; AnalogV3-vs-AnalogV2 redundancy untested; 9-yr backtest + fees pending.
  Promising signal, NOT deploy-certified.

Required before any live capital (all on the CPU machine):
  1. freqtrade 9-yr backtest: AnalogV3 vs AnalogV2 vs base (no-analog) — ablation
     to prove the LSTM tilt adds independent value over V2's existing macro/cycle.
  2. adversarial_validator: BEAR_2022 / SIDEWAYS_2025 / BEAR_2026Q12, with fees.
  3. Report WR, profit-factor, max DD, fees-net return.
  4. For SOL/DOGE: stress-test vs simulated -50% (short history).

30/60/90-day follow-up: N/A (not deployed).
```
