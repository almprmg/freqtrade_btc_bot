"""Multi-asset rotation signal — pick the strongest of BTC/ETH/SOL/BNB.

Each day, rank the 4 pairs by composite momentum score and emit:
  - winner_pair: the pair to hold today
  - is_cash:     True if no pair clears the bar (all weak/bearish)

Cash criteria (signal to stay USDT):
  - Winner's 30d return < +5% (no momentum)
  - OR winner's close < EMA200 (still in downtrend)
  - OR winner's momentum is negative

Momentum score (weighted):
  0.5 * ret_30d + 0.3 * ret_60d + 0.2 * ret_90d

Writes user_data/data/rotation_signal.feather:
  columns: date, winner_pair (str or 'CASH'), winner_score (float)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import numpy as np

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "user_data" / "data" / "binance"
OUT = REPO / "user_data" / "data" / "rotation_signal.feather"

PAIRS = ["BTC", "ETH", "SOL", "BNB"]


def load_pair(coin: str) -> pd.DataFrame:
    df = pd.read_feather(DATA / f"{coin}_USDT-1d.feather")
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df.set_index("date").sort_index()


def momentum_score(df: pd.DataFrame) -> pd.Series:
    r30 = df["close"].pct_change(30)
    r60 = df["close"].pct_change(60)
    r90 = df["close"].pct_change(90)
    return 0.5 * r30 + 0.3 * r60 + 0.2 * r90


def ema(df: pd.DataFrame, period: int = 200) -> pd.Series:
    return df["close"].ewm(span=period, adjust=False).mean()


def main():
    coin_data = {}
    for coin in PAIRS:
        df = load_pair(coin)
        df["mom"] = momentum_score(df)
        df["ema200"] = ema(df, 200)
        df["ret_30d"] = df["close"].pct_change(30)
        coin_data[coin] = df

    # Common date range — start when ALL pairs have data + 200d for EMA
    common = sorted(set.intersection(*[set(d.index) for d in coin_data.values()]))
    common = [d for d in common if d >= pd.Timestamp("2021-01-01", tz="UTC")]
    print(f"common days: {len(common)} from {common[0].date()} to {common[-1].date()}")

    rows = []
    for date in common:
        scores = {}
        for coin in PAIRS:
            d = coin_data[coin].loc[date]
            if pd.isna(d["mom"]) or pd.isna(d["ema200"]):
                continue
            scores[coin] = {
                "mom": float(d["mom"]),
                "above_ema200": bool(d["close"] > d["ema200"]),
                "ret_30d": float(d["ret_30d"]),
            }
        if not scores:
            rows.append({"date": date, "winner_pair": "CASH", "winner_score": 0.0})
            continue

        # Sort by momentum desc
        ranked = sorted(scores.items(), key=lambda kv: kv[1]["mom"], reverse=True)
        top_coin, top = ranked[0]

        # Cash criteria
        if (top["mom"] <= 0 or top["ret_30d"] < 0.05 or not top["above_ema200"]):
            rows.append({"date": date, "winner_pair": "CASH", "winner_score": top["mom"]})
        else:
            rows.append({"date": date, "winner_pair": top_coin,
                         "winner_score": top["mom"]})

    out = pd.DataFrame(rows)
    print()
    print("=== Rotation signal distribution ===")
    print(out["winner_pair"].value_counts())
    print()
    print("=== Per year ===")
    out["year"] = pd.to_datetime(out["date"]).dt.year
    print(out.groupby(["year", "winner_pair"]).size().unstack(fill_value=0).to_string())

    out_save = out[["date", "winner_pair", "winner_score"]].copy()
    out_save.to_feather(OUT)
    print(f"\nSaved: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
