"""download_fng.py — Crypto Fear & Greed Index (free, orthogonal sentiment).

From alternative.me. Daily 0-100 sentiment, history since 2018-02. This is
NOT derived from the price-macro features the LSTM already uses, so it's a
genuine test of whether ORTHOGONAL data adds predictive power.

Writes user_data/data/fng.feather  [date, fng].

USAGE:  python GPU_HANDOFF/download_fng.py
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "user_data" / "data" / "fng.feather"


def main():
    url = "https://api.alternative.me/fng/?limit=0&format=json"
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.load(r)["data"]
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["timestamp"].astype(int), unit="s", utc=True).dt.normalize()
    df["fng"] = df["value"].astype(float)
    df = df[["date", "fng"]].drop_duplicates("date").sort_values("date").reset_index(drop=True)
    df.to_feather(OUT)
    print(f"Saved {len(df)} FNG points -> {OUT}")
    print(f"Range: {df['date'].min().date()} .. {df['date'].max().date()}")
    print(df.tail(3).to_string(index=False))


if __name__ == "__main__":
    main()
