"""Fetch 5+ years of on-chain BTC data from blockchain.info free API.

Pulls daily values for the metrics our strategy uses, joins them into one
feather file the BtcOnChainStrategy reads at startup.

Metrics:
  hash-rate                            (miner commitment)
  difficulty                           (hashpower indirect)
  miners-revenue                       (Puell-like input)
  n-unique-addresses                   (network usage)
  estimated-transaction-volume-usd     (economic throughput)
  mempool-size                         (network stress, last 6 months max)

Endpoint: https://api.blockchain.info/charts/{name}?format=json&timespan=5years
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "user_data" / "data" / "onchain.feather"

METRICS = [
    "hash-rate",
    "difficulty",
    "miners-revenue",
    "n-unique-addresses",
    "estimated-transaction-volume-usd",
    "mempool-size",  # only ~6m of history
]


def fetch(metric: str, timespan: str = "all") -> pd.DataFrame:
    url = f"https://api.blockchain.info/charts/{metric}?format=json&timespan={timespan}&sampled=false"
    print(f"  fetching {metric}...", end=" ", flush=True)
    with urllib.request.urlopen(url, timeout=30) as r:
        d = json.loads(r.read())
    rows = [{"date": pd.to_datetime(v["x"], unit="s", utc=True).normalize(), metric.replace("-", "_"): v["y"]}
            for v in d["values"]]
    df = pd.DataFrame(rows).drop_duplicates("date").set_index("date")
    print(f"got {len(df)} rows ({df.index.min().date()} to {df.index.max().date()})")
    return df


def main() -> int:
    all_dfs = []
    for m in METRICS:
        try:
            df = fetch(m)
            all_dfs.append(df)
            time.sleep(1)  # polite
        except Exception as e:
            print(f"  WARN: {m} failed: {e}")
    # Outer join — different metrics may have different histories.
    out = pd.concat(all_dfs, axis=1).sort_index()
    # Forward-fill mempool-size (only 6m history) by ffill, leave others NaN.
    out["mempool_size"] = out["mempool_size"].ffill()
    # Forward-fill any small gaps in other series.
    out = out.ffill(limit=2)
    print(f"\ncombined: {len(out)} rows, cols={list(out.columns)}")
    print(f"date range: {out.index.min().date()} to {out.index.max().date()}")
    print(out.tail(3).to_string())

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.reset_index().to_feather(OUT)
    print(f"\nsaved: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
