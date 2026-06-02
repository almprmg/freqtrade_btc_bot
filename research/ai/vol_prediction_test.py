"""Can Chronos predict next-7-day realized volatility better than a naive 'last 30d
vol = next 7d vol' baseline?

Volatility is auto-correlated, so naive prediction works ~well already.
If Chronos beats naive by >10% MAE, AI-augmented sizing wins.
If close or worse, naive vol-targeting is enough.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "user_data" / "data" / "binance" / "BTC_USDT-1d.feather"


def load_btc():
    df = pd.read_feather(DATA)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df.set_index("date").sort_index()


def realized_vol_7d(returns: np.ndarray) -> float:
    """Realized 7-day volatility (std of returns over 7 days, daily scale)."""
    return float(np.std(returns[-7:]))


def main():
    df = load_btc().loc["2021-01-01":]
    closes = df["close"].astype(float).values
    returns = np.diff(np.log(closes))  # log returns
    print(f"BTC: {len(closes)} days, {len(returns)} returns\n")

    # Load Chronos
    from chronos import BaseChronosPipeline
    print("Loading chronos-bolt-small...")
    t0 = time.time()
    pipeline = BaseChronosPipeline.from_pretrained(
        "amazon/chronos-bolt-small", device_map="cpu", torch_dtype=torch.float32
    )
    print(f"  loaded in {time.time()-t0:.1f}s\n")

    # Walk-forward test: at each point, predict next 7d realized vol.
    context_len = 64  # last 64 days of returns
    test_start = max(context_len, len(returns) - 365)  # last year for test
    sample_step = 7

    chronos_errs = []
    naive_errs = []
    actual_vols = []
    chronos_preds = []
    naive_preds = []

    for i in range(test_start, len(returns) - 7, sample_step):
        # Context = last 64 days of log returns
        ctx_returns = returns[i - context_len:i]
        # Naive prediction: last 30d realized vol (daily scale)
        naive_pred = float(np.std(returns[i - 30:i]))

        # Chronos: feed absolute returns, predict 7 days, compute std of predicted
        # Actually better: feed daily volatility series, predict 1 step (= next 7d vol)
        # For simplicity, feed daily |returns| (abs returns proxy vol), predict 7d ahead
        abs_returns = np.abs(returns[i - context_len:i])
        ctx_tensor = torch.tensor(abs_returns, dtype=torch.float32)
        forecast = pipeline.predict(
            inputs=ctx_tensor.unsqueeze(0),
            prediction_length=7,
        )
        # Median of predicted abs returns = ~vol per day
        chronos_pred = float(forecast[0, 4].mean())

        # Actual realized 7d vol after this point
        actual = realized_vol_7d(returns[i:i + 7])

        chronos_errs.append(abs(chronos_pred - actual))
        naive_errs.append(abs(naive_pred - actual))
        actual_vols.append(actual)
        chronos_preds.append(chronos_pred)
        naive_preds.append(naive_pred)

    chronos_mae = np.mean(chronos_errs)
    naive_mae = np.mean(naive_errs)

    # Correlation with actual
    chronos_corr = np.corrcoef(chronos_preds, actual_vols)[0, 1]
    naive_corr = np.corrcoef(naive_preds, actual_vols)[0, 1]

    print("=== VOLATILITY PREDICTION COMPARISON ===")
    print(f"  samples: {len(chronos_errs)}")
    print(f"  Naive (last 30d vol):    MAE={naive_mae:.5f}, corr={naive_corr:.3f}")
    print(f"  Chronos-Bolt small:      MAE={chronos_mae:.5f}, corr={chronos_corr:.3f}")
    improvement = (naive_mae - chronos_mae) / naive_mae * 100
    print(f"  Chronos improvement:     {improvement:+.1f}% (positive = AI better)")
    print()
    if improvement > 10:
        print("  -> AI MEANINGFULLY BETTER. Use Chronos for vol sizing.")
    elif improvement > 0:
        print("  -> AI slightly better. Could use either.")
    else:
        print("  -> Naive vol is just as good or better. Use simple rolling vol.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
