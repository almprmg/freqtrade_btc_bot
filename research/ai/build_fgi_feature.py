"""Build FGI feature for strategy consumption — produces fgi_signal.feather.

Logic: convert FGI to a sentiment_tilt value [-0.15, +0.20] used as additive
bias in the sigmoid sizing (same pattern as Calendar Shield).

Mapping (from sentiment_test findings):
  FGI >= 80  ->  +0.20  (very greedy + momentum bull)
  FGI >= 65  ->  +0.10
  FGI 45-65  ->   0
  FGI <= 30  ->  -0.10  (momentum bearish)
  FGI <= 20  ->  -0.15
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "user_data" / "data" / "fgi.feather"
OUT = REPO / "user_data" / "data" / "fgi_signal.feather"


def to_tilt(v: int) -> float:
    if v >= 80: return 0.20
    if v >= 65: return 0.10
    if v <= 20: return -0.15
    if v <= 30: return -0.10
    return 0.0


def main():
    df = pd.read_feather(SRC)
    df["sentiment_tilt"] = df["value"].apply(to_tilt)
    out = df[["date", "value", "sentiment_tilt"]].copy()
    out.columns = ["date", "fgi", "sentiment_tilt"]
    out.to_feather(OUT)
    print(f"Saved: {OUT}  ({len(out)} rows)")
    print(out["sentiment_tilt"].value_counts().sort_index())
    print(f"\nCurrent: FGI={out.iloc[-1]['fgi']}, tilt={out.iloc[-1]['sentiment_tilt']:+.2f}")


if __name__ == "__main__":
    main()
