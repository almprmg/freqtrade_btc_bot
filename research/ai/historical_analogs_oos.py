"""historical_analogs_oos.py — Out-of-Sample validation for AnalogV2.

الفكرة الصارمة:
  - نُدرّب الـKNN engine على pool محدود: <= 2022-12-31 فقط
  - نُولّد analog signals لـ2023-2026 (التي لم يرها الـAI)
  - إذا الـsignal بقي قوي → الإشارة حقيقية (مش overfit)
  - إذا انهار → كانت overfit (over the training period)

النتيجة: نعرف الـCAGR الحقيقي المتوقّع لـAnalogV2 على بيانات لم يرها أبدًا.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import talib.abstract as ta
from sklearn.neighbors import NearestNeighbors

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "user_data" / "data" / "binance"
HALVING = REPO / "user_data" / "data" / "halving_cycle.feather"
MACRO = REPO / "user_data" / "data" / "macro_signals.feather"
OUT_OOS = REPO / "user_data" / "data" / "historical_analogs_v2_oos.feather"

K = 30
TRAIN_END = pd.Timestamp("2022-12-31", tz="UTC")   # Pool limited to <= this
FWD_HORIZON = 30
COINS = ["BTC", "ETH", "BNB"]


def load_coin(coin):
    p = DATA_DIR / f"{coin}_USDT-1d.feather"
    if not p.exists(): return None
    df = pd.read_feather(p)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.sort_values("date").reset_index(drop=True)
    df["coin"] = coin
    return df


def build_features(df):
    df = df.copy()
    df["ret_7d"] = df["close"].pct_change(7)
    df["ret_30d"] = df["close"].pct_change(30)
    df["ema200"] = ta.EMA(df, timeperiod=200)
    df["above_ema200_pct"] = (df["close"] - df["ema200"]) / df["ema200"]
    df["rsi"] = ta.RSI(df, timeperiod=14)
    df["adx"] = ta.ADX(df, timeperiod=14)
    df["atr"] = ta.ATR(df, timeperiod=14)
    df["atr_pct"] = df["atr"] / df["close"]
    df["fwd_30d_ret"] = df["close"].pct_change(FWD_HORIZON).shift(-FWD_HORIZON)
    return df


def main():
    print("=" * 70)
    print("  Out-of-Sample Validation: AnalogV2")
    print(f"  TRAIN: <= {TRAIN_END.date()}")
    print(f"  TEST:  > {TRAIN_END.date()}")
    print("=" * 70)

    macro = pd.read_feather(MACRO)
    macro["date"] = pd.to_datetime(macro["date"], utc=True)
    macro = macro.set_index("date")

    hc = pd.read_feather(HALVING)
    hc["date"] = pd.to_datetime(hc["date"], utc=True)
    hc = hc.set_index("date")
    phase_map = {"ACCUMULATION": 1, "EARLY_BULL": 2, "PARABOLIC": 3,
                 "DISTRIBUTION": 4, "BEAR": 5, "REACCUMULATION": 6, "NEUTRAL": 0}

    feat_cols = ["above_ema200_pct", "ret_7d", "ret_30d", "rsi", "adx",
                 "atr_pct", "dxy_zscore", "vix", "spy_above_ema50", "macro_risk_on"]

    # Build TRAIN pool: only data <= TRAIN_END from BTC + ETH + BNB
    print("\nBuilding TRAIN pool (data <= 2022-12-31)...")
    train_pool = []
    for coin in COINS:
        d = load_coin(coin)
        if d is None: continue
        d = build_features(d)
        d_idx = d["date"].dt.normalize()
        for col_in in ["dxy_zscore", "vix", "spy_above_ema50", "macro_risk_on"]:
            d[col_in] = d_idx.map(macro[col_in].ffill() if col_in in macro.columns else pd.Series()).ffill().fillna(0)
        d["phase_code"] = d_idx.map(hc["phase"]).map(phase_map).fillna(0).astype(int)
        # Filter to train period
        train_only = d[d["date"] <= TRAIN_END].dropna(subset=feat_cols + ["fwd_30d_ret"]).copy()
        train_only["pool_coin"] = coin
        train_pool.append(train_only[["date", "pool_coin"] + feat_cols + ["fwd_30d_ret", "phase_code"]])
        print(f"  {coin}: {len(train_only)} train days")

    pool = pd.concat(train_pool, ignore_index=True)
    print(f"\nTotal train pool: {len(pool):,} samples")

    # Normalize features using TRAIN stats only (avoid lookahead in normalization)
    means = pool[feat_cols].mean()
    stds = pool[feat_cols].std().replace(0, 1)
    pool_norm = (pool[feat_cols] - means) / stds
    pool_norm["phase_code"] = pool["phase_code"]
    pool_features = pool_norm.values
    pool_fwds = pool["fwd_30d_ret"].values

    # Build BTC test queries (2023 onwards)
    btc = load_coin("BTC")
    btc = build_features(btc)
    d_idx = btc["date"].dt.normalize()
    for col_in in ["dxy_zscore", "vix", "spy_above_ema50", "macro_risk_on"]:
        btc[col_in] = d_idx.map(macro[col_in].ffill() if col_in in macro.columns else pd.Series()).ffill().fillna(0)
    btc["phase_code"] = d_idx.map(hc["phase"]).map(phase_map).fillna(0).astype(int)

    test_days = btc[btc["date"] > TRAIN_END].dropna(subset=feat_cols).copy()
    test_norm = (test_days[feat_cols] - means) / stds  # use TRAIN stats
    test_norm["phase_code"] = test_days["phase_code"]

    print(f"\nBuilding signals for {len(test_norm)} test days (2023-2026)...")
    analog_means = []
    nn = NearestNeighbors(n_neighbors=K, algorithm="auto")
    nn.fit(pool_features)
    for i in range(len(test_norm)):
        query = test_norm.iloc[i].values.reshape(1, -1)
        dists, idxs = nn.kneighbors(query)
        weights = 1 / (dists[0] + 0.001)
        weights = weights / weights.sum()
        analog_means.append(float(np.sum(weights * pool_fwds[idxs[0]])))

    test_days["analog_v2_mean_oos"] = analog_means

    # Save
    out_df = test_days[["date", "analog_v2_mean_oos"]].rename(columns={"analog_v2_mean_oos": "analog_v2_mean"})
    out_df.to_feather(OUT_OOS)
    print(f"Saved: {OUT_OOS}")

    # Correlation check
    check = test_days.dropna(subset=["fwd_30d_ret"])
    if len(check) > 50:
        corr = check["analog_v2_mean_oos"].corr(check["fwd_30d_ret"])
        print(f"\n=== Out-of-Sample Results ===")
        print(f"Test samples: {len(check)}")
        print(f"OOS correlation with actual fwd_30d: {corr:+.4f}")
        print(f"(In-sample V2 was: +0.0603)")
        if abs(corr) < 0.02:
            print(f"WARNING: signal vanished out-of-sample = OVERFIT")
        elif corr > 0.04:
            print(f"PASS: signal holds out-of-sample = real edge")
        else:
            print(f"WEAK: signal degraded but present")

    # Compare quintile analysis
    print(f"\n=== BTC fwd_30d return by analog_v2 quintile (OOS) ===")
    check2 = check.copy()
    check2["quintile"] = pd.qcut(check2["analog_v2_mean_oos"], 5, labels=["Q1 low","Q2","Q3","Q4","Q5 high"], duplicates="drop")
    g = check2.groupby("quintile", observed=False)["fwd_30d_ret"].agg(["mean","count"])
    for q in g.index:
        print(f"  {q}: n={int(g.loc[q,'count'])}, mean fwd_30d={g.loc[q,'mean']*100:+.2f}%")


if __name__ == "__main__":
    main()
