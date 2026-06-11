"""ai_diagnose.py — save trading results + diagnose WHY the AI isn't helping more.

Persists per-coin/per-variant daily equity + stats to research/dl_models/trading_results/
(for future improvement iterations), then answers the key question:

  Is the LSTM signal weak, or is the STRATEGY diluting/gating a good signal?

Two diagnostics:
  1. Signal quality — bucket the causal AI z-score into quintiles and show mean
     realized fwd-30d return per quintile (OOS). Monotonic => good raw signal.
  2. Plumbing — compare variants: buy&hold / baseline(no-AI) / blended-AI (V3) /
     pure-AI (position driven only by the AI signal, no regime/macro gating).
     If pure-AI >> blended-AI, the strategy is throttling the signal.

USAGE:  python GPU_HANDOFF/ai_diagnose.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_strategy import coin_strat_returns, load_coin_signal, metrics

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "research" / "dl_models" / "trading_results"
OUT.mkdir(parents=True, exist_ok=True)
COINS = ["BTC", "ETH", "SOL", "BNB", "ADA", "XRP", "DOGE"]
FEE = 0.0006
VAL_SPLIT = 0.20
ZW = 90


def causal_z(pred):
    rm = pred.rolling(ZW, min_periods=20).mean()
    rs = pred.rolling(ZW, min_periods=20).std().replace(0, np.nan)
    return ((pred - rm) / rs).fillna(0.0)


def pure_ai_returns(df, mode="scaled"):
    """Position driven ONLY by the AI signal (no regime/macro/calendar gate)."""
    z = causal_z(df["lstm_pred"])
    if mode == "longflat":
        pos = (z > 0).astype(float)
    else:  # scaled allocation in [0,1] via sigmoid
        pos = 1.0 / (1.0 + np.exp(-1.5 * z))
    ret = df["close"].pct_change().fillna(0.0)
    turn = pos.diff().abs().fillna(pos.abs())
    return pos.shift(1).fillna(0) * ret - turn * FEE


def signal_quintiles(df, oos0):
    """Mean realized fwd-30d return by AI z-score quintile (OOS)."""
    z = causal_z(df["lstm_pred"])
    fwd = df["close"].pct_change(30).shift(-30)
    sub = pd.DataFrame({"z": z, "fwd": fwd}).iloc[oos0:].dropna()
    if len(sub) < 25:
        return None
    sub["q"] = pd.qcut(sub["z"], 5, labels=False, duplicates="drop")
    return sub.groupby("q")["fwd"].mean().to_dict()


def main():
    print("=== AI trading diagnosis ===\n")
    qhdr = f"{'coin':>4} | {'Q1(low)':>8} {'Q2':>8} {'Q3':>8} {'Q4':>8} {'Q5(high)':>9} | monotonic?"
    print(qhdr); print("-" * len(qhdr))
    quint_rows = []
    for coin in COINS:
        df = load_coin_signal(coin)
        if df is None:
            continue
        oos0 = int(len(df) * (1 - VAL_SPLIT))
        q = signal_quintiles(df, oos0)
        if q:
            vals = [q.get(i, float("nan")) for i in range(5)]
            mono = "YES" if vals[4] > vals[0] else "no"
            quint_rows.append((coin, vals, mono))
            print(f"{coin:>4} | " + " ".join(f"{v*100:>7.1f}%" for v in vals) + f" | {mono}")

    print("\n=== Variant comparison (full / OOS CAGR, Sharpe) ===\n")
    vhdr = f"{'coin':>4} | {'B&H':>16} {'baseline':>16} {'blendAI':>16} {'pureAI':>16}"
    print(vhdr); print("-" * len(vhdr))
    saved = {}
    for coin in COINS:
        df = load_coin_signal(coin)
        if df is None:
            continue
        oos0 = int(len(df) * (1 - VAL_SPLIT))
        dates = df["date"]
        variants = {
            "buyhold": df["close"].pct_change().fillna(0.0),
            "baseline": coin_strat_returns(coin, 0.0, use_analog=False)[1],
            "blendAI": coin_strat_returns(coin, 0.7, use_analog=True)[1],
            "pureAI": pure_ai_returns(df, "scaled"),
            "pureAI_lf": pure_ai_returns(df, "longflat"),
        }
        rec = {}
        for name, r in variants.items():
            full, oos = metrics(r), metrics(r.iloc[oos0:])
            rec[name] = {"cagr": full["cagr"], "sharpe": full["sharpe"], "maxdd": full["maxdd"],
                         "oos_cagr": oos["cagr"], "oos_sharpe": oos["sharpe"]}
            # persist daily equity for future work
            eq = (1 + r).cumprod()
            pd.DataFrame({"date": dates, "ret": r.values, "equity": eq.values}).to_feather(
                OUT / f"{coin}_{name}.feather")
        saved[coin] = rec

        def cell(n):
            return f"{rec[n]['cagr']*100:>6.0f}%/{rec[n]['oos_cagr']*100:>5.0f}%"
        print(f"{coin:>4} | {cell('buyhold'):>16} {cell('baseline'):>16} {cell('blendAI'):>16} {cell('pureAI'):>16}")

    (OUT / "summary.json").write_text(json.dumps(saved, indent=2), encoding="utf-8")

    # ---- DIAGNOSIS ----
    print("\n=== DIAGNOSIS ===")
    mono = sum(1 for _, v, m in quint_rows if m == "YES")
    print(f"Signal monotonic (Q5>Q1 realized fwd return) on {mono}/{len(quint_rows)} coins (OOS).")
    # pure vs blended OOS sharpe
    pure_better = sum(1 for c in saved if saved[c]["pureAI"]["oos_sharpe"] > saved[c]["blendAI"]["oos_sharpe"])
    print(f"pure-AI OOS Sharpe > blended-AI on {pure_better}/{len(saved)} coins.")
    blend_vs_base = sum(1 for c in saved if saved[c]["blendAI"]["oos_cagr"] > saved[c]["baseline"]["oos_cagr"])
    print(f"blended-AI OOS CAGR > baseline on {blend_vs_base}/{len(saved)} coins.")
    print(f"\nSaved daily equity + summary.json -> {OUT}")


if __name__ == "__main__":
    main()
