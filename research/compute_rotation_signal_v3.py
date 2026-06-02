"""Rotation Signal V3 — V2 + per-asset DD circuit breaker.

Same as V2 but adds: if the WINNER coin is currently in -15% DD from its
60d high, force CASH (don't rotate into a falling knife).

This catches the case where momentum says 'enter SOL' but SOL just
dropped 20% in a few days — wait for recovery.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import numpy as np

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "user_data" / "data" / "binance"
OUT = REPO / "user_data" / "data" / "rotation_signal_v3.feather"

PAIRS = ["BTC", "ETH", "SOL", "BNB"]
CONFIRM = 3
DD_LIMIT = 0.15  # 15% DD from 60d high disqualifies a coin


def load_pair(coin):
    df = pd.read_feather(DATA / f"{coin}_USDT-1d.feather")
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df.set_index("date").sort_index()


def momentum(df):
    return 0.5*df["close"].pct_change(30) + 0.3*df["close"].pct_change(60) + 0.2*df["close"].pct_change(90)


def ema(df, p=200):
    return df["close"].ewm(span=p, adjust=False).mean()


def adx(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    tr = pd.concat([(high-low), (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    pdi = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    mdi = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    dx = 100 * (pdi-mdi).abs() / (pdi+mdi).replace(0, np.nan)
    return dx.ewm(alpha=1/period, adjust=False).mean()


def main():
    coin_data = {}
    for coin in PAIRS:
        df = load_pair(coin)
        df["mom"] = momentum(df)
        df["ema200"] = ema(df, 200)
        df["ret_30d"] = df["close"].pct_change(30)
        df["high_60d"] = df["high"].rolling(60, min_periods=1).max()
        df["dd_60d"] = (df["high_60d"] - df["close"]) / df["high_60d"]
        if coin == "BTC":
            df["adx"] = adx(df, 14)
        coin_data[coin] = df

    btc = coin_data["BTC"]
    bull = (btc["close"] > btc["ema200"]) & (btc["ret_30d"] > 0.05) & (btc["adx"] > 20)
    bear = (btc["close"] < btc["ema200"]) & (btc["ret_30d"] < -0.10)
    rcode = pd.Series(0.0, index=btc.index); rcode[bull]=1.0; rcode[bear]=-1.0
    rmin = rcode.rolling(CONFIRM, min_periods=CONFIRM).min()
    rmax = rcode.rolling(CONFIRM, min_periods=CONFIRM).max()
    btc_regime = rcode.where(rmin==rmax, other=pd.NA).ffill().fillna(0)

    common = sorted(set.intersection(*[set(d.index) for d in coin_data.values()]))
    common = [d for d in common if d >= pd.Timestamp("2021-01-01", tz="UTC")]
    rows = []
    for date in common:
        if date not in btc_regime.index:
            rows.append({"date": date, "winner_pair": "CASH", "winner_score": 0.0}); continue
        btc_reg = btc_regime.loc[date]
        if btc_reg == -1.0:
            rows.append({"date": date, "winner_pair": "CASH", "winner_score": 0.0}); continue

        scores = {}
        for coin in PAIRS:
            d = coin_data[coin].loc[date]
            if pd.isna(d["mom"]) or pd.isna(d["ema200"]): continue
            # V3: DD filter — skip coins in deep drawdown
            if float(d["dd_60d"]) > DD_LIMIT:
                continue
            scores[coin] = {
                "mom": float(d["mom"]),
                "above_ema200": bool(d["close"] > d["ema200"]),
                "ret_30d": float(d["ret_30d"]),
            }

        if not scores:
            rows.append({"date": date, "winner_pair": "CASH", "winner_score": 0.0}); continue
        ranked = sorted(scores.items(), key=lambda kv: kv[1]["mom"], reverse=True)
        top_coin, top = ranked[0]
        min_mom = 0.20 if btc_reg == 0.0 else 0.0
        cash = (top["mom"] <= min_mom or top["ret_30d"] < 0.05 or not top["above_ema200"])
        if cash:
            rows.append({"date": date, "winner_pair": "CASH", "winner_score": top["mom"]})
        else:
            rows.append({"date": date, "winner_pair": top_coin, "winner_score": top["mom"]})

    out = pd.DataFrame(rows)
    print("V3 distribution:")
    print(out["winner_pair"].value_counts())
    out["year"] = pd.to_datetime(out["date"]).dt.year
    print("\nPer year:")
    print(out.groupby(["year", "winner_pair"]).size().unstack(fill_value=0).to_string())
    out[["date", "winner_pair", "winner_score"]].to_feather(OUT)
    print(f"\nSaved: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
