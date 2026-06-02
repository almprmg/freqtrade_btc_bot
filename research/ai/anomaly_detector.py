"""Anomaly Detector — Isolation Forest on price/volume/volatility features.

Flags abnormal market states (flash crashes, low-liquidity gaps, manipulation
events) so strategies can EXIT or SKIP trading during those bars.

Features:
  - 1d return magnitude
  - 1d range / ATR ratio (range expansion)
  - volume z-score (60d)
  - returns autocorrelation (5d window)
  - volatility z-score (30d)
  - skewness of returns (30d)
  - 1d return relative to vol-of-vol

Output: per-day anomaly score (higher = more anomalous).
Threshold: top 2.5% of training distribution = "anomaly" flag.

Trained on BTC 2019-2024, tested on 2025-2026. The "anomaly" flag becomes
a new column in the OHLCV-derived feature feather; strategies can use it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "user_data" / "data" / "binance"
OUT = REPO / "user_data" / "data" / "anomaly_flags.feather"


def load_pair(coin: str) -> pd.DataFrame:
    df = pd.read_feather(DATA / f"{coin}_USDT-1d.feather")
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df.set_index("date").sort_index()


def features(df: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    log_ret = np.log(df["close"] / df["close"].shift(1))
    f["abs_ret"] = log_ret.abs()
    f["range_atr"] = (df["high"] - df["low"]) / (df["close"].pct_change().abs().rolling(14).mean() * df["close"] + 1e-9)
    f["vol_z"] = (df["volume"] - df["volume"].rolling(60).mean()) / df["volume"].rolling(60).std().replace(0, np.nan)
    f["autocorr_5d"] = log_ret.rolling(5).corr(log_ret.shift(1))
    f["vol_30d"] = log_ret.rolling(30).std()
    f["vol_z_30d"] = (f["vol_30d"] - f["vol_30d"].rolling(180).mean()) / f["vol_30d"].rolling(180).std().replace(0, np.nan)
    f["skew_30d"] = log_ret.rolling(30).skew()
    return f.dropna()


def main():
    from sklearn.ensemble import IsolationForest

    print("Computing anomaly flags for BTC/ETH/SOL/BNB/AVAX/DOGE/ADA...")
    all_flags = []
    for coin in ["BTC", "ETH", "SOL", "BNB", "AVAX", "DOGE", "ADA"]:
        try:
            df = load_pair(coin)
        except FileNotFoundError:
            print(f"  skip {coin}: no data")
            continue
        feats = features(df)
        # Train on 2019-2023, predict on full series
        train = feats.loc["2019-01-01":"2023-12-31"]
        if len(train) < 200:
            print(f"  skip {coin}: not enough training data")
            continue
        clf = IsolationForest(contamination=0.025, random_state=42, n_jobs=1)
        clf.fit(train.values)
        scores = -clf.score_samples(feats.values)  # higher = more anomalous
        flag = (clf.predict(feats.values) == -1).astype(int)
        cdf = pd.DataFrame({
            "date": feats.index,
            "coin": coin,
            "anomaly_score": scores,
            "is_anomaly": flag,
        })
        cdf["coin"] = coin
        all_flags.append(cdf)
        per_year = cdf.copy()
        per_year["year"] = pd.to_datetime(per_year["date"]).dt.year
        flag_yr = per_year.groupby("year")["is_anomaly"].sum().to_dict()
        print(f"  {coin}: {flag.sum()} anomaly days; per-year: {flag_yr}")

    out_df = pd.concat(all_flags, ignore_index=True)
    out_df.to_feather(OUT)
    print(f"\nSaved: {OUT}  ({len(out_df)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
