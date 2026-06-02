"""Compute composite on-chain bullishness score (0-100) from blockchain.info data.

Weights are intentionally simple and not over-tuned to avoid curve-fitting.
Each of 5 sub-scores is normalized 0-1 then weighted into a 0-100 score.

Sub-scores:
  hashrate_ribbon (25 pts) — 1 when HR_30d > HR_60d (Charles Edwards' indicator)
  puell_inverse   (20 pts) — bullish when miner revenue compressed
  addr_momentum   (20 pts) — z-score of 30d address-growth change
  txv_momentum    (15 pts) — z-score of 30d tx volume change
  difficulty_grow (20 pts) — 90d % change in difficulty (proxy for net hashpower commit)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import numpy as np

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "user_data" / "data" / "onchain.feather"
OUT = REPO / "user_data" / "data" / "onchain_features.feather"


def compute(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_index().copy()

    # 1. Hashrate Ribbon
    df["hr_30"] = df["hash_rate"].rolling(30).mean()
    df["hr_60"] = df["hash_rate"].rolling(60).mean()
    df["hr_ribbon"] = (df["hr_30"] > df["hr_60"]).astype(float)

    # 2. Puell-like: miner revenue / 365d MA. <0.5 bullish (capitulation), >4 bearish (top).
    df["mr_365"] = df["miners_revenue"].rolling(365).mean()
    df["puell"] = df["miners_revenue"] / df["mr_365"]
    # Map [4, 0.5] linearly to [0, 1]; outside clipped.
    df["puell_score"] = ((4.0 - df["puell"]) / (4.0 - 0.5)).clip(0, 1)

    # 3. Active addresses momentum (30d change z-score over 180d).
    addr_chg = df["n_unique_addresses"].pct_change(30)
    addr_z = (addr_chg - addr_chg.rolling(180).mean()) / addr_chg.rolling(180).std().replace(0, np.nan)
    df["addr_score"] = (0.5 + addr_z.clip(-2, 2) / 4).clip(0, 1)

    # 4. TX volume momentum.
    tv = df["estimated_transaction_volume_usd"]
    txv_chg = tv.pct_change(30)
    txv_z = (txv_chg - txv_chg.rolling(180).mean()) / txv_chg.rolling(180).std().replace(0, np.nan)
    df["txv_score"] = (0.5 + txv_z.clip(-2, 2) / 4).clip(0, 1)

    # 5. Difficulty 90d growth.
    diff_pct = df["difficulty"].pct_change(90)
    # +10% in 90d -> 1.0, -10% -> 0
    df["diff_score"] = (0.5 + (diff_pct * 5).clip(-0.5, 0.5)).clip(0, 1)

    # Composite 0-100.
    df["onchain_score"] = (
        25.0 * df["hr_ribbon"]
        + 20.0 * df["puell_score"].fillna(0.5)
        + 20.0 * df["addr_score"].fillna(0.5)
        + 15.0 * df["txv_score"].fillna(0.5)
        + 20.0 * df["diff_score"].fillna(0.5)
    )
    return df


def main():
    if not SRC.exists():
        print(f"missing {SRC} — run onchain_fetcher.py first", file=sys.stderr)
        return 1
    raw = pd.read_feather(SRC)
    raw["date"] = pd.to_datetime(raw["date"], utc=True)
    raw = raw.set_index("date").sort_index()
    out = compute(raw)
    print(f"computed {len(out)} rows of on-chain features.")
    print()
    print("=== Last 5 rows of composite score ===")
    print(out[["hr_ribbon", "puell_score", "addr_score", "txv_score", "diff_score", "onchain_score"]].tail(5).to_string())
    print()
    print("=== Score distribution per year (mean) ===")
    yearly = out["onchain_score"].dropna()
    if len(yearly):
        yearly.index = pd.to_datetime(yearly.index)
        print(yearly.groupby(yearly.index.year).agg(["mean", "min", "max"]).round(1).to_string())

    # Save
    out_to_save = out[["onchain_score", "hr_ribbon", "puell_score", "addr_score",
                       "txv_score", "diff_score"]]
    out_to_save.reset_index().to_feather(OUT)
    print(f"\nsaved: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
