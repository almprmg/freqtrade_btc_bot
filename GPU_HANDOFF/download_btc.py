"""download_btc.py — Fetch full daily OHLCV from Binance public REST API.

Pure-Python (urllib + pandas). No freqtrade / ccxt / API key needed.
Writes freqtrade-compatible feather: columns [date, open, high, low, close, volume].

Used because the GPU machine has no SSH access to the old CPU machine
(sync_data.ps1 path) and TA-Lib/freqtrade can't install here (Windows
Application Control blocks the compiled TA-Lib DLL).

USAGE:
    python GPU_HANDOFF/download_btc.py --pair BTC/USDT --timeframe 1d
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "user_data" / "data" / "binance"
BASE = "https://api.binance.com/api/v3/klines"
LIMIT = 1000  # Binance max rows per request


def fetch_klines(symbol: str, interval: str) -> pd.DataFrame:
    rows: list[list] = []
    start = 0  # ms epoch; 0 → earliest available
    while True:
        url = f"{BASE}?symbol={symbol}&interval={interval}&startTime={start}&limit={LIMIT}"
        with urllib.request.urlopen(url, timeout=30) as r:
            batch = json.load(r)
        if not batch:
            break
        rows.extend(batch)
        last_open = batch[-1][0]
        if len(batch) < LIMIT:
            break
        start = last_open + 1  # next ms after last open time
        time.sleep(0.25)  # be gentle with the public endpoint
    return _to_frame(rows)


def _to_frame(rows: list[list]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "qav", "trades", "tbav", "tqav", "ignore",
    ])
    df["date"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype("float64")
    df = df[["date", "open", "high", "low", "close", "volume"]]
    df = df.drop_duplicates(subset="date").sort_values("date").reset_index(drop=True)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", default="BTC/USDT")
    ap.add_argument("--timeframe", default="1d")
    args = ap.parse_args()

    symbol = args.pair.replace("/", "")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{args.pair.replace('/', '_')}-{args.timeframe}.feather"

    print(f"Fetching {symbol} {args.timeframe} from Binance ...")
    df = fetch_klines(symbol, args.timeframe)
    df.to_feather(out)
    print(f"Saved {len(df)} candles -> {out}")
    print(f"Range: {df['date'].min().date()} .. {df['date'].max().date()}")


if __name__ == "__main__":
    main()
