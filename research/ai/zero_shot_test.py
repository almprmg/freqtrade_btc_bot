"""Zero-shot test: can Chronos-Bolt predict BTC next-day direction?

No training. Just load pre-trained Chronos-Bolt-Small (45MB), feed it the
last N days of BTC closes, and ask for a forecast distribution. Then we
check direction-accuracy on a held-out sample.

If zero-shot direction accuracy > 55% (vs 50% chance), this is worth
deploying. If close to 50%, we need to fine-tune on BTC data.
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

CONTEXT_LEN = 64       # last 64 days as context
PREDICTION_LEN = 1     # predict next 1 day
NUM_SAMPLES = 20       # sample-based forecast


def load_btc() -> pd.DataFrame:
    df = pd.read_feather(DATA)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df.set_index("date").sort_index()


def main():
    print(f"loading Chronos-Bolt small ({200} MB)...", flush=True)
    from chronos import BaseChronosPipeline
    t0 = time.time()
    pipeline = BaseChronosPipeline.from_pretrained(
        "amazon/chronos-bolt-small",
        device_map="cpu",
        torch_dtype=torch.float32,
    )
    print(f"  loaded in {time.time()-t0:.1f}s")

    df = load_btc().loc["2021-01-01":]
    closes = df["close"].astype(float).values
    dates = df.index

    print(f"\n=== Walk-forward direction-accuracy test ===")
    print(f"  data: {len(closes)} days from {dates[0].date()} to {dates[-1].date()}")
    print(f"  using context={CONTEXT_LEN} days, predicting next {PREDICTION_LEN} day")

    # Walk-forward: for each position i where i >= CONTEXT_LEN,
    # take closes[i-CONTEXT_LEN:i] as context, predict day i, compare to actual.
    correct = 0
    total = 0
    sample_step = 7  # sample every 7 days to keep runtime reasonable
    predicted = []
    actual = []

    test_start = max(CONTEXT_LEN, len(closes) - 365)  # last year for test
    for i in range(test_start, len(closes) - 1, sample_step):
        context = torch.tensor(closes[i - CONTEXT_LEN:i], dtype=torch.float32)
        # predict — Chronos-Bolt API: inputs as positional, returns (batch, 9_quantiles, pred_len)
        forecast = pipeline.predict(
            inputs=context.unsqueeze(0),
            prediction_length=PREDICTION_LEN,
        )
        # forecast shape: (1, 9, 1) for 9 quantiles [0.1..0.9], 1-step-ahead.
        # Median is quantile index 4 (0.5).
        median = float(forecast[0, 4, 0])
        actual_close = closes[i]
        last_close = closes[i - 1]
        pred_direction = median > last_close
        actual_direction = actual_close > last_close
        if pred_direction == actual_direction:
            correct += 1
        total += 1
        predicted.append(median)
        actual.append(actual_close)

    acc = correct / total * 100
    print(f"\n=== RESULT ===")
    print(f"  samples tested: {total}")
    print(f"  direction accuracy: {acc:.1f}%  ({'WORTH PURSUING' if acc > 55 else 'MARGINAL' if acc > 52 else 'NO BETTER THAN COINFLIP'})")

    # Also MAE on return
    pred_returns = np.array([p / closes[test_start + i*sample_step - 1] - 1
                              for i, p in enumerate(predicted)])
    act_returns = np.array([a / closes[test_start + i*sample_step - 1] - 1
                              for i, a in enumerate(actual)])
    mae = np.mean(np.abs(pred_returns - act_returns))
    print(f"  MAE (return %): {mae*100:.2f}%")
    print(f"  Naive 'tomorrow=today' MAE: {np.mean(np.abs(act_returns))*100:.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
