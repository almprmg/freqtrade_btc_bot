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

Two training schemes:

  default (in-sample, LEGACY — what live bots read today):
      one model per coin trained on 2019-01-01..2023-12-31 and applied to the
      FULL series -> flags for 2019-2023 are IN-SAMPLE (audit finding C12).
      Output: user_data/data/anomaly_flags.feather

  --walk-forward (expanding window, no look-ahead):
      for each calendar year Y, train a fresh model (same features/params) on
      feature rows strictly before Y-01-01 and flag only year Y. Years with
      fewer than MIN_TRAIN_ROWS training rows are not flagged (no row ->
      strategies treat as "no anomaly"). Adds a `train_end` column (last
      training date). Output: user_data/data/anomaly_flags_wf.feather

Strategies pick the file via env ANOMALY_FLAGS_FILE (default
"anomaly_flags.feather", i.e. live behaviour unchanged).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "user_data" / "data" / "binance"
OUT = REPO / "user_data" / "data" / "anomaly_flags.feather"
OUT_WF = REPO / "user_data" / "data" / "anomaly_flags_wf.feather"

COINS = ["BTC", "ETH", "SOL", "BNB", "AVAX", "DOGE", "ADA"]
CONTAMINATION = 0.025
RANDOM_STATE = 42
MIN_TRAIN_ROWS = 200          # same guard as the legacy in-sample model


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


def _model():
    from sklearn.ensemble import IsolationForest
    return IsolationForest(contamination=CONTAMINATION, random_state=RANDOM_STATE, n_jobs=1)


def walk_forward_flags(feats: pd.DataFrame, coin: str,
                       min_train_rows: int = MIN_TRAIN_ROWS) -> pd.DataFrame:
    """Expanding-window flags: year Y is scored by a model fit on rows < Y-01-01.

    Returns columns date, coin, anomaly_score, is_anomaly, train_end.
    """
    feats = feats.sort_index()
    out = []
    for year in sorted(feats.index.year.unique()):
        start = pd.Timestamp(f"{year}-01-01", tz=feats.index.tz)
        end = pd.Timestamp(f"{year + 1}-01-01", tz=feats.index.tz)
        train = feats[feats.index < start]
        test = feats[(feats.index >= start) & (feats.index < end)]
        if len(train) < min_train_rows or test.empty:
            continue
        clf = _model()
        clf.fit(train.values)
        out.append(pd.DataFrame({
            "date": test.index,
            "coin": coin,
            "anomaly_score": -clf.score_samples(test.values),
            "is_anomaly": (clf.predict(test.values) == -1).astype(int),
            "train_end": train.index.max(),
        }))
    if not out:
        return pd.DataFrame(columns=["date", "coin", "anomaly_score", "is_anomaly", "train_end"])
    return pd.concat(out, ignore_index=True)


def main_walk_forward(out_path: Path = OUT_WF) -> int:
    print("Walk-forward anomaly flags (expanding window, per-year refit)...")
    all_flags = []
    for coin in COINS:
        try:
            df = load_pair(coin)
        except FileNotFoundError:
            print(f"  skip {coin}: no data")
            continue
        cdf = walk_forward_flags(features(df), coin)
        if cdf.empty:
            print(f"  skip {coin}: not enough training data")
            continue
        all_flags.append(cdf)
        flag_yr = cdf.groupby(pd.to_datetime(cdf["date"]).dt.year)["is_anomaly"].sum().to_dict()
        print(f"  {coin}: {int(cdf['is_anomaly'].sum())} anomaly days; per-year: {flag_yr}")
    out_df = pd.concat(all_flags, ignore_index=True)
    out_df.to_feather(out_path)
    print(f"\nSaved: {out_path}  ({len(out_df)} rows)")
    return 0


def main(out_path: Path = OUT):
    """LEGACY in-sample model (train 2019-2023, score everything). Kept as-is."""
    from sklearn.ensemble import IsolationForest

    print("Computing anomaly flags for BTC/ETH/SOL/BNB/AVAX/DOGE/ADA...")
    all_flags = []
    for coin in COINS:
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
    out_df.to_feather(out_path)
    print(f"\nSaved: {out_path}  ({len(out_df)} rows)")
    return 0


def cli(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Isolation-Forest anomaly flags")
    ap.add_argument("--walk-forward", action="store_true",
                    help="expanding-window per-year refit (writes anomaly_flags_wf.feather)")
    ap.add_argument("--out", type=Path, default=None, help="override output path")
    a = ap.parse_args(argv)
    if a.walk_forward:
        return main_walk_forward(a.out or OUT_WF)
    return main(a.out or OUT)


if __name__ == "__main__":
    sys.exit(cli())
