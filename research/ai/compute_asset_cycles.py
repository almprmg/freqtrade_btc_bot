"""Per-asset cycle detector — works for any coin, no halving needed.

Approach: identify each coin's MAJOR BOTTOMS automatically from price.
A "bottom" is the point where the rolling 365-day max drawdown
reached its peak (deepest pain). Between consecutive bottoms = one
full cycle.

For each day, compute:
  cycle_age_days = days since last detected bottom
  cycle_phase = bucket by age (ACCUMULATION/EARLY_BULL/PARABOLIC/DISTRIBUTION/BEAR/REACCUMULATION)
  cycle_bias = same -1..+1 curve mapped to age

This generalizes the BTC halving signal: instead of relying on the
4-year halving schedule, we detect the de-facto cycle bottoms from
each coin's own price action.

Output: user_data/data/asset_cycles.feather with columns
  date, coin, cycle_age_days, cycle_phase, cycle_bias
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "user_data" / "data" / "binance"
OUT = REPO / "user_data" / "data" / "asset_cycles.feather"

COINS = ["BTC", "ETH", "SOL", "BNB", "AVAX", "DOGE", "ADA"]
LOOKBACK_DD = 365     # 1-year rolling window for max DD
MIN_CYCLE_DAYS = 200  # bottoms must be at least this far apart


def detect_bottoms(df: pd.DataFrame) -> list:
    """Find local max-DD-from-rolling-high points (the 'bottoms')."""
    high_365 = df["high"].rolling(LOOKBACK_DD, min_periods=30).max()
    dd = (high_365 - df["close"]) / high_365
    bottoms = []
    last_bottom_idx = None
    in_dd = False
    cur_max_dd_idx = None
    cur_max_dd = 0
    for i, (date, row) in enumerate(df.iterrows()):
        d = dd.iloc[i]
        if pd.isna(d):
            continue
        if d > 0.30 and not in_dd:
            in_dd = True
            cur_max_dd = d
            cur_max_dd_idx = i
        elif in_dd:
            if d > cur_max_dd:
                cur_max_dd = d
                cur_max_dd_idx = i
            elif d < 0.15:
                # Recovered from drawdown — finalize the bottom
                bot_idx = cur_max_dd_idx
                bot_date = df.index[bot_idx]
                if not bottoms or (bot_date - bottoms[-1]).days >= MIN_CYCLE_DAYS:
                    bottoms.append(bot_date)
                in_dd = False
                cur_max_dd = 0
                cur_max_dd_idx = None
    return bottoms


def phase_from_age(d: int) -> str:
    if d < 180: return "ACCUMULATION"
    if d < 365: return "EARLY_BULL"
    if d < 540: return "PARABOLIC"
    if d < 700: return "DISTRIBUTION"
    if d < 900: return "BEAR"
    return "REACCUMULATION"


def bias_from_age(d: int) -> float:
    if d < 180: return 0.2
    if d < 365: return 0.6 + 0.3 * (d - 180) / 185
    if d < 540: return 0.9 - 0.3 * (d - 365) / 175
    if d < 700: return 0.5 - 1.0 * (d - 540) / 160
    if d < 900: return -0.5 + 0.5 * (d - 700) / 200
    return -0.1 + 0.5 * min((d - 900) / 560, 1.0)


def days_since_last(bottoms: list, date: pd.Timestamp) -> int:
    if not bottoms:
        return 9999
    last = max((b for b in bottoms if b <= date), default=bottoms[0])
    return int((date - last).days)


def main():
    all_rows = []
    print("Detecting cycles per coin...")
    for coin in COINS:
        f = DATA / f"{coin}_USDT-1d.feather"
        if not f.exists():
            print(f"  {coin}: no data")
            continue
        df = pd.read_feather(f)
        df["date"] = pd.to_datetime(df["date"], utc=True)
        df = df.set_index("date").sort_index()
        bottoms = detect_bottoms(df)
        print(f"  {coin}: detected {len(bottoms)} bottoms")
        for b in bottoms:
            print(f"    - {b.date()}")

        for date in df.index:
            age = days_since_last(bottoms, date)
            all_rows.append({
                "date": date,
                "coin": coin,
                "cycle_age_days": age,
                "cycle_phase": phase_from_age(age),
                "cycle_bias": bias_from_age(age),
            })

    out = pd.DataFrame(all_rows)
    out.to_feather(OUT)
    print(f"\nSaved: {OUT}  ({len(out)} rows)")

    # Distribution per coin
    print("\n=== Phase distribution per coin ===")
    print(out.groupby(["coin", "cycle_phase"]).size().unstack(fill_value=0).to_string())

    # Current state
    today = pd.Timestamp.now(tz="UTC").normalize()
    cur = out[pd.to_datetime(out["date"]) <= today].groupby("coin").tail(1)
    print("\n=== Current state per coin ===")
    print(cur[["coin", "cycle_age_days", "cycle_phase", "cycle_bias"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
