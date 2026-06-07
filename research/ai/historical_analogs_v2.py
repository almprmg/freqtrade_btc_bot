"""historical_analogs_v2.py — KNN موسّع: multi-coin pool + macro context.

التحسينات عن V1:
  1. State vector يضيف macro features: dxy_zscore, vix_level, spy_above_ema50
     → الـAI يلاحظ سياق الاقتصاد العالمي أيضًا
  2. KNN search pool يضم BTC + ETH + BNB sky days
     → 3x المزيد من الـ "analogs"، إشارة أقوى
  3. Weighted KNN (closer days have more weight)
  4. Cross-asset learning: analog من ETH يفيد BTC والعكس

الناتج: user_data/data/historical_analogs_v2.feather
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
OUT = REPO / "user_data" / "data" / "historical_analogs_v2.feather"

K_NEIGHBORS = 30            # أكثر من V1 (20) بسبب pool أكبر
MIN_HISTORY = 365
EXCLUDE_RECENT = 30
FWD_HORIZON = 30
COINS_POOL = ["BTC", "ETH", "BNB"]   # المصدر للـsimilar days
TARGET_COIN = "BTC"                    # نولّد signals لـBTC


def load_coin_data(coin):
    """Load OHLCV + indicators for one coin."""
    p = DATA_DIR / f"{coin}_USDT-1d.feather"
    if not p.exists():
        return None
    df = pd.read_feather(p)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.sort_values("date").reset_index(drop=True)
    df["coin"] = coin
    return df


def build_features(df):
    """Build state vector features for a coin."""
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


def add_macro_features(df, macro):
    """Map macro signals to each row."""
    d = df["date"].dt.normalize()
    cols = ["dxy_zscore", "vix", "spy_above_ema50", "macro_risk_on"]
    for c in cols:
        if c in macro.columns:
            df[c] = d.map(macro[c].ffill()).ffill().fillna(0)
        else:
            df[c] = 0
    return df


def add_halving_phase(df, hc):
    if hc.empty:
        df["phase_code"] = 0
        return df
    d = df["date"].dt.normalize()
    phase_map = {"ACCUMULATION": 1, "EARLY_BULL": 2, "PARABOLIC": 3,
                 "DISTRIBUTION": 4, "BEAR": 5, "REACCUMULATION": 6, "NEUTRAL": 0}
    df["phase_code"] = d.map(hc["phase"]).map(phase_map).fillna(0).astype(int)
    return df


def main():
    # Load macro + halving once
    print("Loading macro signals...")
    macro = pd.DataFrame()
    if MACRO.exists():
        macro = pd.read_feather(MACRO)
        macro["date"] = pd.to_datetime(macro["date"], utc=True)
        macro = macro.set_index("date")
        print(f"  Macro: {len(macro)} rows")

    print("Loading halving...")
    hc = pd.DataFrame()
    if HALVING.exists():
        hc = pd.read_feather(HALVING)
        hc["date"] = pd.to_datetime(hc["date"], utc=True)
        hc = hc.set_index("date")

    # Load all coins, build features, add macro/phase
    print(f"Loading + featurizing {len(COINS_POOL)} coins...")
    all_data = {}
    for coin in COINS_POOL:
        d = load_coin_data(coin)
        if d is None:
            print(f"  {coin}: missing"); continue
        d = build_features(d)
        d = add_macro_features(d, macro)
        d = add_halving_phase(d, hc)
        all_data[coin] = d
        print(f"  {coin}: {len(d)} rows ({d['date'].min().date()} -> {d['date'].max().date()})")

    # Combine pool: all coins with their fwd returns
    pool_frames = []
    feat_cols = ["above_ema200_pct", "ret_7d", "ret_30d", "rsi", "adx",
                 "atr_pct", "dxy_zscore", "vix", "spy_above_ema50", "macro_risk_on"]
    for coin, d in all_data.items():
        sub = d.dropna(subset=feat_cols + ["fwd_30d_ret"]).copy()
        sub["pool_coin"] = coin
        pool_frames.append(sub[["date", "pool_coin"] + feat_cols + ["fwd_30d_ret", "phase_code"]])
    pool = pd.concat(pool_frames, ignore_index=True).sort_values("date").reset_index(drop=True)
    print(f"\nTotal pool size: {len(pool):,} rows across {len(COINS_POOL)} coins")

    # Normalize features
    means = pool[feat_cols].mean()
    stds = pool[feat_cols].std().replace(0, 1)
    pool_norm = (pool[feat_cols] - means) / stds
    pool_norm["phase_code"] = pool["phase_code"]

    # Now generate analog signals FOR BTC only
    btc = all_data[TARGET_COIN]
    btc_query = (btc[feat_cols].dropna() - means) / stds
    btc_query["phase_code"] = btc.loc[btc_query.index, "phase_code"]

    # Pre-normalize pool data
    pool_features = pool_norm.values
    btc_dates = btc.loc[btc_query.index, "date"].values
    pool_dates = pool["date"].values

    print(f"\nComputing analogs for {len(btc_query)} BTC days against {len(pool_features)} pool samples...")
    analog_means = []
    analog_winrates = []
    for i, q_idx in enumerate(btc_query.index):
        q_date = btc_dates[i]
        # Mask: pool entries must be < q_date - EXCLUDE_RECENT
        cutoff = q_date - np.timedelta64(EXCLUDE_RECENT, "D")
        mask = pool_dates < cutoff
        if mask.sum() < 50:
            analog_means.append(np.nan)
            analog_winrates.append(np.nan)
            continue
        pool_sub = pool_features[mask]
        fwds = pool["fwd_30d_ret"].values[mask]
        query = btc_query.iloc[i].values.reshape(1, -1)
        k = min(K_NEIGHBORS, len(pool_sub))
        nn = NearestNeighbors(n_neighbors=k, algorithm="auto")
        nn.fit(pool_sub)
        dists, idxs = nn.kneighbors(query)
        idxs = idxs[0]
        # Weighted by inverse distance
        weights = 1 / (dists[0] + 0.001)
        weights = weights / weights.sum()
        analog_fwds = fwds[idxs]
        weighted_mean = float(np.sum(weights * analog_fwds))
        winrate = float((analog_fwds > 0).mean())
        analog_means.append(weighted_mean)
        analog_winrates.append(winrate)
        if i % 500 == 0:
            print(f"  {i}/{len(btc_query)}...")

    # Attach back to BTC dates
    out = pd.DataFrame({
        "date": btc_dates,
        "analog_v2_mean": analog_means,
        "analog_v2_winrate": analog_winrates,
    })
    out["date"] = pd.to_datetime(out["date"], utc=True)
    out.to_feather(OUT)

    valid = out.dropna(subset=["analog_v2_mean"])
    print(f"\nSaved: {OUT}")
    print(f"  Valid signals: {len(valid)} / {len(out)} ({len(valid)/len(out)*100:.0f}%)")

    # Correlation check against BTC actual fwd_30d
    check = btc.dropna(subset=["fwd_30d_ret"]).merge(out, on="date", how="inner")
    if len(check) > 100:
        corr = check["analog_v2_mean"].corr(check["fwd_30d_ret"])
        print(f"\nCorrelation analog_v2_mean -> actual fwd_30d_ret: {corr:+.4f}")
        # Compare to V1
        v1_path = REPO / "user_data" / "data" / "historical_analogs.feather"
        if v1_path.exists():
            v1 = pd.read_feather(v1_path)
            v1["date"] = pd.to_datetime(v1["date"], utc=True)
            check2 = check.merge(v1[["date", "analog_fwd_30d_mean"]], on="date", how="inner")
            if len(check2) > 100:
                v1_corr = check2["analog_fwd_30d_mean"].corr(check2["fwd_30d_ret"])
                print(f"  (V1 was: {v1_corr:+.4f})")
                print(f"  Improvement: {corr - v1_corr:+.4f}")


if __name__ == "__main__":
    main()
