"""Classify each historical period as bull / bear / sideways / crash.

Rule set (applied on a 1d BTC series, no lookahead):
  - Compute 30-day return and 30-day realized volatility.
  - bull:     return > +15% over 30d AND price above 200d SMA
  - bear:     return < -15% over 30d AND price below 200d SMA
  - sideways: |return| < 10% over 30d AND volatility z-score < 1
  - crash:    return < -20% over 14d (overrides everything else)
  - mixed:    anything not matching above (default fallback)

Output: per-day label + summary of regime durations across the data.
The same classification is reused by the walk-forward + robustness modules.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "user_data" / "data" / "binance"

REGIME_LABELS = ["bull", "bear", "sideways", "crash", "mixed"]


def load_btc_daily() -> pd.DataFrame:
    df = pd.read_feather(DATA / "BTC_USDT-1d.feather")
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df.set_index("date")


def classify(df: pd.DataFrame) -> pd.DataFrame:
    px = df["close"].astype(float)
    rng = np.log(px).diff()
    vol_30 = rng.rolling(30).std() * np.sqrt(252)
    vol_30_avg = vol_30.rolling(180, min_periods=30).mean()
    vol_30_std = vol_30.rolling(180, min_periods=30).std()
    vol_z = (vol_30 - vol_30_avg) / vol_30_std.replace(0, np.nan)

    ret_30 = px.pct_change(30)
    ret_14 = px.pct_change(14)
    sma_200 = px.rolling(200).mean()

    above_200 = px > sma_200
    label = pd.Series("mixed", index=px.index)
    label[(ret_30 > 0.15) & above_200] = "bull"
    label[(ret_30 < -0.15) & ~above_200] = "bear"
    label[(ret_30.abs() < 0.10) & (vol_z < 1)] = "sideways"
    label[ret_14 < -0.20] = "crash"  # overrides

    return pd.DataFrame({
        "price": px, "ret_30d": ret_30, "ret_14d": ret_14,
        "vol_30d_z": vol_z, "above_sma200": above_200, "regime": label,
    }).dropna(subset=["regime"])


def summary(labels: pd.Series) -> pd.DataFrame:
    counts = labels.value_counts().reindex(REGIME_LABELS, fill_value=0)
    pct = (counts / counts.sum() * 100).round(1)
    rows = []
    for lbl in REGIME_LABELS:
        rows.append({"regime": lbl, "days": int(counts[lbl]), "pct": float(pct[lbl])})
    return pd.DataFrame(rows)


def per_year_breakdown(reg: pd.DataFrame) -> pd.DataFrame:
    reg = reg.copy()
    reg["year"] = reg.index.year
    rows = []
    for y, sub in reg.groupby("year"):
        dist = sub["regime"].value_counts(normalize=True).reindex(REGIME_LABELS, fill_value=0)
        rows.append({
            "year": y,
            **{lbl: round(float(dist[lbl]) * 100, 1) for lbl in REGIME_LABELS},
        })
    return pd.DataFrame(rows)


def main() -> int:
    df = load_btc_daily()
    df = df.loc["2020-12-01":"2026-06-01"]  # generous window for SMA200 warmup
    reg = classify(df)
    reg = reg.loc["2021-01-01":]  # report only after warmup
    print("=== Overall regime distribution (2021-01-01 to end) ===")
    print(summary(reg["regime"]).to_string(index=False))
    print()
    print("=== Per-year regime mix ===")
    print(per_year_breakdown(reg).to_string(index=False))

    # Persist for downstream modules.
    out = REPO / "research" / "_regime_labels.csv"
    reg[["regime"]].to_csv(out)
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
