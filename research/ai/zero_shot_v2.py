"""Try multiple Chronos configs to see if any zero-shot setup helps on BTC.

Variants:
  V1: small model, context=64, predict 1d
  V2: small model, context=256, predict 1d
  V3: small model, context=128, predict 7d
  V4: base model, context=256, predict 7d
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


def test_variant(pipeline, closes, context_len, pred_len, name):
    """Direction accuracy: predict close at horizon, compare with actual."""
    correct = 0
    total = 0
    sample_step = 7
    test_start = max(context_len, len(closes) - 365)
    test_end = len(closes) - pred_len

    for i in range(test_start, test_end, sample_step):
        context = torch.tensor(closes[i - context_len:i], dtype=torch.float32)
        forecast = pipeline.predict(
            inputs=context.unsqueeze(0),
            prediction_length=pred_len,
        )
        # forecast: (1, 9, pred_len), quantile 4 = median
        median_at_horizon = float(forecast[0, 4, pred_len - 1])
        actual_at_horizon = closes[i + pred_len - 1]
        last_close = closes[i - 1]
        pred_dir = median_at_horizon > last_close
        actual_dir = actual_at_horizon > last_close
        if pred_dir == actual_dir:
            correct += 1
        total += 1
    return correct / total * 100, total


def main():
    from chronos import BaseChronosPipeline
    df = load_btc().loc["2021-01-01":]
    closes = df["close"].astype(float).values
    print(f"BTC: {len(closes)} days\n")

    # Variant 1+2+3: small model with different configs
    print("Loading chronos-bolt-small...")
    t0 = time.time()
    small = BaseChronosPipeline.from_pretrained(
        "amazon/chronos-bolt-small", device_map="cpu", torch_dtype=torch.float32
    )
    print(f"  loaded in {time.time()-t0:.1f}s\n")

    for ctx, pred, name in [(64, 1, "V1 small/ctx64/1d"),
                             (256, 1, "V2 small/ctx256/1d"),
                             (128, 7, "V3 small/ctx128/7d")]:
        acc, n = test_variant(small, closes, ctx, pred, name)
        verdict = "WORTH IT" if acc > 55 else "marginal" if acc > 52 else "FAIL"
        print(f"  {name}: {acc:.1f}% on {n} samples  [{verdict}]")

    # V4: base model
    print("\nLoading chronos-bolt-base (larger)...")
    t0 = time.time()
    base = BaseChronosPipeline.from_pretrained(
        "amazon/chronos-bolt-base", device_map="cpu", torch_dtype=torch.float32
    )
    print(f"  loaded in {time.time()-t0:.1f}s")
    acc, n = test_variant(base, closes, 256, 7, "V4 base/ctx256/7d")
    verdict = "WORTH IT" if acc > 55 else "marginal" if acc > 52 else "FAIL"
    print(f"  V4 base/ctx256/7d: {acc:.1f}% on {n} samples  [{verdict}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
