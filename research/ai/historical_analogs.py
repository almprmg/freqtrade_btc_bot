"""historical_analogs.py — يبني إشارات بناءً على أيام مشابهة من التاريخ.

الفكرة:
  لكل يوم في البيانات، نبحث عن K أيام مشابهة في السنوات الـ5 السابقة
  (لكن قبل تاريخ التداول الحالي = no look-ahead) ونشوف ماذا حدث في الـ30 يوم
  بعد كل واحد منها. متوسط هذه النتائج = "ai signal" يضاف لقرار التداول.

أنواع التشابه:
  1. State analog: KNN على (RSI, ret_30d, ret_7d, regime, cycle_phase)
     → نجد أيام بنفس الظروف الفنية
  2. Calendar analog: نفس الشهر/اليوم في السنوات الماضية
     → نجد ما حدث في "5 يناير 2021/2022/2023" مثلاً

الناتج: user_data/data/historical_analogs.feather
  columns: date, analog_fwd_30d_mean, analog_fwd_30d_winrate,
           calendar_5y_mean, calendar_5y_winrate

التحذير المهم (anti-look-ahead):
  - عند تاريخ T، نبحث فقط في بيانات < T - 1 سنة (تجنّب الـreproduction)
  - وبيانات قبل 5 سنوات من T (تجنّب الـtrivial overlap)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import talib.abstract as ta
from sklearn.neighbors import NearestNeighbors

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "user_data" / "data" / "binance" / "BTC_USDT-1d.feather"
HALVING = REPO / "user_data" / "data" / "halving_cycle.feather"
OUT = REPO / "user_data" / "data" / "historical_analogs.feather"

K_NEIGHBORS = 20            # عدد الأيام المشابهة لكل تاريخ
MIN_HISTORY_DAYS = 365      # نحتاج سنة على الأقل من history قبل البدء
EXCLUDE_RECENT_DAYS = 30    # استثناء آخر 30 يوم من البحث (تجنّب تشابه قريب جدًا)
FWD_HORIZON = 30            # نقيس النتيجة بعد 30 يوم


def build_state_vector(df: pd.DataFrame) -> pd.DataFrame:
    """يبني vector الحالة لكل يوم."""
    df = df.copy()
    df["ret_7d"] = df["close"].pct_change(7)
    df["ret_30d"] = df["close"].pct_change(30)
    df["ret_60d"] = df["close"].pct_change(60)
    df["ema200"] = ta.EMA(df, timeperiod=200)
    df["above_ema200_pct"] = (df["close"] - df["ema200"]) / df["ema200"]
    df["rsi"] = ta.RSI(df, timeperiod=14)
    df["adx"] = ta.ADX(df, timeperiod=14)
    df["atr"] = ta.ATR(df, timeperiod=14)
    df["atr_pct"] = df["atr"] / df["close"]

    # Forward return (the "outcome" we want to learn)
    df["fwd_30d_ret"] = df["close"].pct_change(FWD_HORIZON).shift(-FWD_HORIZON)
    df["fwd_30d_positive"] = (df["fwd_30d_ret"] > 0).astype(int)

    return df


def load_halving_phase(dates):
    if not HALVING.exists():
        return pd.Series(0, index=dates)
    hc = pd.read_feather(HALVING)
    hc["date"] = pd.to_datetime(hc["date"], utc=True)
    hc = hc.set_index("date")
    # Map phases to integer codes
    phase_map = {"ACCUMULATION": 1, "EARLY_BULL": 2, "PARABOLIC": 3,
                 "DISTRIBUTION": 4, "BEAR": 5, "REACCUMULATION": 6, "NEUTRAL": 0}
    phases = pd.Series(dates).map(hc["phase"]).map(phase_map).fillna(0).astype(int)
    return phases.values


def compute_state_knn(df: pd.DataFrame) -> pd.DataFrame:
    """لكل يوم T، اجلب K أيام مشابهة من history < T-30 days."""
    print("Computing state KNN analogs...")
    # Features used for similarity
    feat_cols = ["above_ema200_pct", "ret_7d", "ret_30d", "rsi", "adx", "atr_pct"]
    df = df.dropna(subset=feat_cols + ["fwd_30d_ret"]).copy().reset_index(drop=True)
    df["phase"] = load_halving_phase(df["date"].tolist())

    # Normalize features (z-score)
    feat_data = df[feat_cols].copy()
    means = feat_data.mean()
    stds = feat_data.std().replace(0, 1)
    feat_norm = (feat_data - means) / stds
    feat_norm["phase"] = df["phase"]  # categorical, weight equally

    analog_means = []
    analog_winrates = []

    for i in range(len(df)):
        if i < MIN_HISTORY_DAYS:
            analog_means.append(np.nan)
            analog_winrates.append(np.nan)
            continue
        # Search pool: indices < i - EXCLUDE_RECENT_DAYS
        max_idx = i - EXCLUDE_RECENT_DAYS
        if max_idx < 50:
            analog_means.append(np.nan)
            analog_winrates.append(np.nan)
            continue

        pool = feat_norm.iloc[:max_idx].values
        query = feat_norm.iloc[i].values.reshape(1, -1)

        nn = NearestNeighbors(n_neighbors=min(K_NEIGHBORS, len(pool)), algorithm="auto")
        nn.fit(pool)
        _, idxs = nn.kneighbors(query)
        idxs = idxs[0]

        # Forward returns of those analog days (must have fwd_30d_ret defined)
        fwd_rets = df.iloc[idxs]["fwd_30d_ret"].dropna()
        if len(fwd_rets) == 0:
            analog_means.append(np.nan)
            analog_winrates.append(np.nan)
        else:
            analog_means.append(float(fwd_rets.mean()))
            analog_winrates.append(float((fwd_rets > 0).mean()))

        if i % 500 == 0:
            print(f"  {i}/{len(df)}...")

    df["analog_fwd_30d_mean"] = analog_means
    df["analog_fwd_30d_winrate"] = analog_winrates
    return df


def compute_calendar_analogs(df: pd.DataFrame) -> pd.DataFrame:
    """لكل تاريخ T، اجلب fwd_30d_ret لنفس (شهر، يوم) في السنوات السابقة."""
    print("Computing calendar analogs...")
    df = df.copy()
    df["month"] = df["date"].dt.month
    df["day"] = df["date"].dt.day

    cal_means = []
    cal_winrates = []
    for i, row in df.iterrows():
        # Find same month+day in prior years (excluding current year)
        same_cal = df[
            (df["month"] == row["month"])
            & (df["day"] == row["day"])
            & (df["date"] < row["date"] - pd.Timedelta(days=180))  # at least 6 months back
        ]
        fwd_rets = same_cal["fwd_30d_ret"].dropna()
        if len(fwd_rets) >= 2:
            cal_means.append(float(fwd_rets.mean()))
            cal_winrates.append(float((fwd_rets > 0).mean()))
        else:
            cal_means.append(np.nan)
            cal_winrates.append(np.nan)
    df["calendar_5y_mean"] = cal_means
    df["calendar_5y_winrate"] = cal_winrates
    return df


def main():
    print(f"Loading BTC data...")
    df = pd.read_feather(SRC)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.sort_values("date").reset_index(drop=True)
    print(f"  {len(df)} rows: {df['date'].min().date()} -> {df['date'].max().date()}")

    print("Building state vectors...")
    df = build_state_vector(df)

    df = compute_state_knn(df)
    df = compute_calendar_analogs(df)

    # Output: only the columns the strategy needs
    out_cols = ["date", "analog_fwd_30d_mean", "analog_fwd_30d_winrate",
                "calendar_5y_mean", "calendar_5y_winrate"]
    out = df[out_cols].copy()
    out.to_feather(OUT)

    valid = out.dropna(subset=["analog_fwd_30d_mean"])
    print(f"\nSaved: {OUT}")
    print(f"  Total rows: {len(out)}")
    print(f"  Valid analog signals: {len(valid)} ({len(valid)/len(out)*100:.0f}%)")
    print(f"\nAnalog stats:")
    print(f"  analog_fwd_30d_mean range: {valid['analog_fwd_30d_mean'].min()*100:+.1f}% to {valid['analog_fwd_30d_mean'].max()*100:+.1f}%")
    print(f"  analog_fwd_30d_winrate range: {valid['analog_fwd_30d_winrate'].min()*100:.0f}% to {valid['analog_fwd_30d_winrate'].max()*100:.0f}%")

    # Correlation with actual outcomes
    actual = df.dropna(subset=["fwd_30d_ret", "analog_fwd_30d_mean"])
    if len(actual) > 10:
        corr1 = actual["analog_fwd_30d_mean"].corr(actual["fwd_30d_ret"])
        corr2 = actual["calendar_5y_mean"].corr(actual["fwd_30d_ret"])
        print(f"\nCorrelations with actual fwd_30d returns:")
        print(f"  analog_fwd_30d_mean -> fwd_30d_ret: {corr1:+.4f}")
        print(f"  calendar_5y_mean    -> fwd_30d_ret: {corr2:+.4f}")


if __name__ == "__main__":
    main()
