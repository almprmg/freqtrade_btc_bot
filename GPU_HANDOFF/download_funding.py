"""download_funding.py — Binance perp funding-rate history (intraday-native feature).

Funding is posted every 8h and reflects perp/spot basis + leverage pressure —
genuinely intraday information the daily macro features don't carry. Used to
test whether intraday LSTM signal can be rescued (it was ~noise on price alone).

Writes user_data/data/funding_{COIN}.feather  [date, funding_rate].

USAGE:  python GPU_HANDOFF/download_funding.py --pair BTC/USDT
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "user_data" / "data"
BASE = "https://fapi.binance.com/fapi/v1/fundingRate"


def fetch(symbol: str) -> pd.DataFrame:
    # startTime=0 makes Binance return only the latest page; begin at perp launch.
    rows, start = [], 1567900800000  # 2019-09-08, ~BTCUSDT perp funding start
    while True:
        url = f"{BASE}?symbol={symbol}&startTime={start}&limit=1000"
        with urllib.request.urlopen(url, timeout=30) as r:
            batch = json.load(r)
        if not batch:
            break
        rows.extend(batch)
        last = batch[-1]["fundingTime"]
        if len(batch) < 1000:
            break
        start = last + 1
        time.sleep(0.25)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df["funding_rate"] = df["fundingRate"].astype("float64")
    return df[["date", "funding_rate"]].drop_duplicates("date").sort_values("date").reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", default="BTC/USDT")
    args = ap.parse_args()
    symbol = args.pair.replace("/", "")
    df = fetch(symbol)
    out = OUT_DIR / f"funding_{args.pair.split('/')[0]}.feather"
    df.to_feather(out)
    print(f"Saved {len(df)} funding points -> {out}")
    print(f"Range: {df['date'].min()} .. {df['date'].max()}")


if __name__ == "__main__":
    main()
