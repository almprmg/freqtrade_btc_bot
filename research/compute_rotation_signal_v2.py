"""Rotation Signal V2 — adds a BTC-regime GATE.

Same momentum logic as V1 BUT only allows a winner when BTC itself is
NOT in confirmed BEAR. This prevents rotating into volatile alts during
broad bear periods (which is what hurt V1 in 2024 and 2026).

BTC regime check (same as Pure Shield):
  BULL  : close > EMA200 AND ret_30d > +5% AND ADX > 20
  BEAR  : close < EMA200 AND ret_30d < -10%
  NEUTRAL: in between

V2 rule:
  if BTC_regime == BEAR -> CASH (no rotation allowed)
  if BTC_regime == NEUTRAL -> only enter if winner_score > 0.20 (very strong)
  if BTC_regime == BULL -> normal rotation
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import numpy as np

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "user_data" / "data" / "binance"
OUT = REPO / "user_data" / "data" / "rotation_signal_v2.feather"

PAIRS = ["BTC", "ETH", "SOL", "BNB"]
CONFIRM = 3


def load_pair(coin):
    df = pd.read_feather(DATA / f"{coin}_USDT-1d.feather")
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df.set_index("date").sort_index()


def momentum(df):
    r30 = df["close"].pct_change(30)
    r60 = df["close"].pct_change(60)
    r90 = df["close"].pct_change(90)
    return 0.5 * r30 + 0.3 * r60 + 0.2 * r90


def ema(df, p=200):
    return df["close"].ewm(span=p, adjust=False).mean()


def adx(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    tr = pd.concat([(high - low), (high - close.shift()).abs(),
                    (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    pdi = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    mdi = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1/period, adjust=False).mean()


def main():
    coin_data = {}
    for coin in PAIRS:
        df = load_pair(coin)
        df["mom"] = momentum(df)
        df["ema200"] = ema(df, 200)
        df["ret_30d"] = df["close"].pct_change(30)
        if coin == "BTC":
            df["adx"] = adx(df, 14)
        coin_data[coin] = df

    btc = coin_data["BTC"]
    # BTC regime
    bull = (btc["close"] > btc["ema200"]) & (btc["ret_30d"] > 0.05) & (btc["adx"] > 20)
    bear = (btc["close"] < btc["ema200"]) & (btc["ret_30d"] < -0.10)
    rcode = pd.Series(0.0, index=btc.index)
    rcode[bull] = 1.0
    rcode[bear] = -1.0
    # Confirmation
    rmin = rcode.rolling(CONFIRM, min_periods=CONFIRM).min()
    rmax = rcode.rolling(CONFIRM, min_periods=CONFIRM).max()
    stable = rmin == rmax
    btc_regime = rcode.where(stable, other=pd.NA).ffill().fillna(0)

    common = sorted(set.intersection(*[set(d.index) for d in coin_data.values()]))
    common = [d for d in common if d >= pd.Timestamp("2021-01-01", tz="UTC")]
    print(f"common days: {len(common)}")

    rows = []
    for date in common:
        # BTC gate
        if date not in btc_regime.index:
            rows.append({"date": date, "winner_pair": "CASH", "winner_score": 0.0})
            continue
        btc_reg = btc_regime.loc[date]

        # Hard cash if BTC bear
        if btc_reg == -1.0:
            rows.append({"date": date, "winner_pair": "CASH", "winner_score": 0.0})
            continue

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

        ranked = sorted(scores.items(), key=lambda kv: kv[1]["mom"], reverse=True)
        top_coin, top = ranked[0]

        # Cash filters
        min_mom = 0.20 if btc_reg == 0.0 else 0.0  # tighter for neutral
        cash = (top["mom"] <= min_mom or top["ret_30d"] < 0.05
                or not top["above_ema200"])
        if cash:
            rows.append({"date": date, "winner_pair": "CASH", "winner_score": top["mom"]})
        else:
            rows.append({"date": date, "winner_pair": top_coin, "winner_score": top["mom"]})

    out = pd.DataFrame(rows)
    print("\nWinner distribution V2:")
    print(out["winner_pair"].value_counts())
    print("\nPer year:")
    out["year"] = pd.to_datetime(out["date"]).dt.year
    print(out.groupby(["year", "winner_pair"]).size().unstack(fill_value=0).to_string())

    out[["date", "winner_pair", "winner_score"]].to_feather(OUT)
    print(f"\nSaved: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
