"""Sentiment-signal feasibility — Idea H phase 1.

Test if sentiment is even worth pursuing for BTC before building the FinBERT
pipeline. Uses alternative.me Fear & Greed Index as sentiment proxy. If FGI
shows no signal, FinBERT (noisier source) won't help. If it does, we have a
cheap signal already.

Tests:
  1. Correlation: FGI today vs BTC returns over next N days (1, 3, 7, 14)
  2. Extreme regime check: returns conditional on FGI extreme zones
  3. Buy/sell signal: if FGI < 25 (extreme fear) — outperform random?
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
FGI_URL = "https://api.alternative.me/fng/?limit=0"
FGI_CACHE = REPO / "user_data" / "data" / "fgi.feather"


def fetch_fgi() -> pd.DataFrame:
    if FGI_CACHE.exists():
        df = pd.read_feather(FGI_CACHE)
        return df
    print("Fetching FGI...")
    with urllib.request.urlopen(FGI_URL, timeout=30) as r:
        data = json.loads(r.read().decode())
    rows = [{"timestamp": int(x["timestamp"]),
             "value": int(x["value"]),
             "classification": x["value_classification"]}
            for x in data["data"]]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.normalize()
    df = df[["date", "value", "classification"]].sort_values("date").reset_index(drop=True)
    df.to_feather(FGI_CACHE)
    print(f"  cached {len(df)} rows: {df['date'].min()} -> {df['date'].max()}")
    return df


def main():
    fgi = fetch_fgi()
    print(f"FGI rows: {len(fgi)}, range: {fgi['date'].min().date()} -> {fgi['date'].max().date()}")

    # Load BTC
    btc = pd.read_feather(REPO / "user_data" / "data" / "binance" / "BTC_USDT-1d.feather")
    btc["date"] = pd.to_datetime(btc["date"], utc=True).dt.normalize()
    btc = btc[["date", "close"]]
    btc["ret_1d"] = btc["close"].pct_change()

    df = btc.merge(fgi, on="date", how="inner")
    print(f"Merged rows: {len(df)}, range: {df['date'].min().date()} -> {df['date'].max().date()}")

    print("\n=== 1. Correlation: FGI today vs next-N-day BTC return ===")
    for n in [1, 3, 7, 14, 30]:
        df[f"fwd_ret_{n}d"] = df["close"].pct_change(n).shift(-n)
        c = df[["value", f"fwd_ret_{n}d"]].corr().iloc[0, 1]
        print(f"  FGI -> fwd_{n}d return: corr = {c:+.4f}")

    print("\n=== 2. Returns by FGI zone (next 7d) ===")
    df["fgi_zone"] = pd.cut(df["value"], bins=[0, 25, 45, 55, 75, 100],
                            labels=["X_FEAR", "FEAR", "NEUTRAL", "GREED", "X_GREED"])
    g = df.groupby("fgi_zone", observed=False)["fwd_ret_7d"].agg(["mean", "median", "std", "count"])
    g["mean_pct"] = g["mean"] * 100
    g["median_pct"] = g["median"] * 100
    print(g[["mean_pct", "median_pct", "std", "count"]].to_string())

    print("\n=== 3. Extreme Fear signal test ===")
    # Buy signal: FGI <= 25 (Extreme Fear)
    df["signal_xfear"] = (df["value"] <= 25).astype(int)
    # Average forward return on signal days vs non-signal days
    signal_days = df[df["signal_xfear"] == 1]
    nonsignal_days = df[df["signal_xfear"] == 0]
    for n in [3, 7, 14, 30]:
        col = f"fwd_ret_{n}d"
        s_mean = signal_days[col].mean() * 100
        n_mean = nonsignal_days[col].mean() * 100
        s_pos_rate = (signal_days[col] > 0).mean() * 100
        n_pos_rate = (nonsignal_days[col] > 0).mean() * 100
        print(f"  fwd_{n}d:  X-FEAR mean={s_mean:+.2f}% pos-rate={s_pos_rate:.1f}%  | other mean={n_mean:+.2f}% pos-rate={n_pos_rate:.1f}%  diff={s_mean-n_mean:+.2f}pp")

    print("\n=== 4. Extreme Greed signal test (exit/short signal) ===")
    df["signal_xgreed"] = (df["value"] >= 75).astype(int)
    signal_days = df[df["signal_xgreed"] == 1]
    nonsignal_days = df[df["signal_xgreed"] == 0]
    for n in [3, 7, 14, 30]:
        col = f"fwd_ret_{n}d"
        s_mean = signal_days[col].mean() * 100
        n_mean = nonsignal_days[col].mean() * 100
        s_pos_rate = (signal_days[col] > 0).mean() * 100
        n_pos_rate = (nonsignal_days[col] > 0).mean() * 100
        print(f"  fwd_{n}d:  X-GREED mean={s_mean:+.2f}% pos-rate={s_pos_rate:.1f}%  | other mean={n_mean:+.2f}% pos-rate={n_pos_rate:.1f}%  diff={s_mean-n_mean:+.2f}pp")

    print("\n=== Verdict ===")
    # Significant signal? > 1pp difference + > 100 samples
    df["signal_xfear"] = (df["value"] <= 25).astype(int)
    sigA = (df[df["signal_xfear"] == 1]["fwd_ret_30d"].mean() -
            df[df["signal_xfear"] == 0]["fwd_ret_30d"].mean()) * 100
    df["signal_xgreed"] = (df["value"] >= 75).astype(int)
    sigB = (df[df["signal_xgreed"] == 1]["fwd_ret_30d"].mean() -
            df[df["signal_xgreed"] == 0]["fwd_ret_30d"].mean()) * 100
    print(f"  X-FEAR 30d edge:   {sigA:+.2f}pp  (positive = signal works)")
    print(f"  X-GREED 30d edge:  {sigB:+.2f}pp  (negative = signal works)")

    OUT = REPO / "research" / "sentiment_findings.md"
    OUT.write_text(
        f"# Sentiment feasibility — Fear & Greed Index test\n\n"
        f"Data: FGI {df['date'].min().date()} -> {df['date'].max().date()} "
        f"({len(df)} rows merged with BTC)\n\n"
        f"X-FEAR (FGI<=25) edge on 30d forward returns: **{sigA:+.2f}pp**\n\n"
        f"X-GREED (FGI>=75) edge on 30d forward returns: **{sigB:+.2f}pp**\n\n"
        f"Interpretation:\n"
        f"  - X-FEAR positive (e.g. +5pp) means contrarian buy signal works\n"
        f"  - X-GREED negative (e.g. -3pp) means contrarian sell signal works\n\n"
        f"If both signals are <1pp, sentiment likely won't add much value. "
        f"In that case, FinBERT (noisier source than FGI) is unlikely to help.\n",
        encoding="utf-8")
    print(f"\nSaved: {OUT}")


if __name__ == "__main__":
    main()
