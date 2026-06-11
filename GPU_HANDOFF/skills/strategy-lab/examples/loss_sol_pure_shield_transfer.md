# LOSS: SOL Pure Shield — indicator transfer failure

**Date tested:** 2026-06-03
**Outcome:** Rejected (later replaced by VolShield v3)
**Why this case matters:** Demonstrates that BTC-calibrated indicators don't always transfer.

## Hypothesis

> "Pure Shield (close > EMA200 AND ret_30d > 5% AND ADX > 20) works for BTC. Should also work for SOL with same thresholds."

ETH Pure Shield port had just succeeded (+47%/yr, sub #101). So SOL should work too, right?

## Result

| Year | ROI |
|---|---|
| 2021 | +903% |
| 2022 | -32% |
| 2023 | +231% |
| 2024 | +44% |
| **2025** | **-43%** 🔴 |
| 2026 Q12 | 0% |

**Adversarial: CATASTROPHIC** (-43% in sideways window).

## Why the transfer failed

SOL's annualized volatility is ~95% (vs BTC's ~55%, ETH's ~70%). At higher vol:
- `ret_30d > 5%` triggers on every minor bounce (false BULL)
- `ADX > 20` is the NORMAL state, not "trending" — SOL's ADX is rarely below 20
- 3-day confirmation is shorter than typical SOL false-move duration (2-4 days)

The thresholds were calibrated for BTC's vol profile. SOL needs DIFFERENT thresholds.

## The fix (SolVolShield v3)

Took 3 iterations to find the right SOL-calibrated values:
- ret_30d > 5% AND ret_60d > 15% (double window)
- ADX > 30 (vs 20)
- ATR_pct < 0.10 (new — chop filter)
- EMA50 > EMA200 (new — golden cross)
- 5-day confirmation (vs 3)

Result: +45%/yr, **WARN** adversarial.

## Lessons

1. **Vol profile dictates threshold.** Annualized vol > 80% requires recalibration, not just porting.
2. **What ports vs what doesn't:**
   - PORTS: pattern structure (regime detection logic, sigmoid sizing math, calendar tilts)
   - DOESN'T PORT: specific thresholds (5%, 20, 3-day)
3. **Test before celebrating.** ETH Pure Shield worked, but that doesn't mean SOL will. Each coin is its own validation.

## Detection heuristic

When considering a port to a high-vol coin, check first:
```python
import pandas as pd
df = pd.read_feather(f"user_data/data/binance/{COIN}_USDT-1d.feather")
df["ret_1d"] = df["close"].pct_change()
ann_vol = df["ret_1d"].std() * (365 ** 0.5) * 100
print(f"{COIN} annualized vol: {ann_vol:.0f}%")
```

If > 80% → use `strategy_vol_shield.py.tmpl` (not `strategy_pure_shield.py.tmpl`).

## Quick reference: vol profiles (as of 2026-06)

| Coin | Annualized vol | Template |
|---|---|---|
| BTC | ~55% | pure_shield, sigmoid_v2, calendar |
| ETH | ~70% | pure_shield, calendar |
| BNB | ~65% | pure_shield, triple |
| ADA | ~80% | pure_shield (borderline), triple |
| AVAX | ~95% | vol_shield (custom) |
| SOL | ~95% | vol_shield (custom) |
| DOGE | ~110% | open challenge — no working template yet |
