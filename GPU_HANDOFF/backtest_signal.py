"""backtest_signal.py — Vectorized PnL test of the LSTM signals.

Does the +0.2-0.3 walk-forward correlation actually turn into money?
This is a quick, freqtrade-free check (freqtrade won't install here).

HONESTY:
- Evaluated on the OUT-OF-SAMPLE tail only (last `val_split` of each coin's
  signal dates) — the window the shipped model never trained on.
- The corr-loss signal has no anchored zero (correlation is scale/offset
  invariant), so the rule is offset-robust: go LONG when pred is above its
  own trailing mean, else FLAT. Enter next day (no lookahead).

USAGE:  python GPU_HANDOFF/backtest_signal.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "user_data" / "data"
COINS = ["BTC", "ETH", "SOL", "BNB", "ADA", "XRP", "DOGE"]
VAL_SPLIT = 0.20
TRAIL = 60          # trailing window for the offset-robust threshold
ANN = 365           # daily crypto -> annualization factor


def metrics(ret: pd.Series) -> dict:
    ret = ret.dropna()
    if len(ret) < 2:
        return {}
    eq = (1 + ret).cumprod()
    years = len(ret) / ANN
    cagr = eq.iloc[-1] ** (1 / years) - 1 if years > 0 and eq.iloc[-1] > 0 else float("nan")
    sharpe = (ret.mean() / ret.std() * np.sqrt(ANN)) if ret.std() > 0 else float("nan")
    dd = (eq / eq.cummax() - 1).min()
    return {"total": eq.iloc[-1] - 1, "cagr": cagr, "sharpe": sharpe, "maxdd": dd}


def run_coin(coin: str) -> dict | None:
    ohlcv = DATA / "binance" / f"{coin}_USDT-1d.feather"
    sig = DATA / f"dl_signals_lstm_{coin}.feather"
    if not ohlcv.exists() or not sig.exists():
        return None
    px = pd.read_feather(ohlcv)[["date", "close"]]
    s = pd.read_feather(sig)[["date", "lstm_pred_fwd30"]]
    px["date"] = pd.to_datetime(px["date"], utc=True)
    s["date"] = pd.to_datetime(s["date"], utc=True)
    df = px.merge(s, on="date", how="inner").sort_values("date").reset_index(drop=True)

    df["ret"] = df["close"].pct_change()
    thr = df["lstm_pred_fwd30"].rolling(TRAIL, min_periods=20).mean()
    df["pos"] = (df["lstm_pred_fwd30"] > thr).astype(float)
    df["strat_ret"] = df["pos"].shift(1) * df["ret"]      # enter next day

    # OOS tail only
    oos = df.iloc[int(len(df) * (1 - VAL_SPLIT)):].copy()
    m_strat = metrics(oos["strat_ret"])
    m_hold = metrics(oos["ret"])
    if not m_strat or not m_hold:
        return None
    return {
        "coin": coin,
        "oos_from": oos["date"].iloc[0].date(),
        "oos_to": oos["date"].iloc[-1].date(),
        "days": len(oos),
        "in_mkt": oos["pos"].shift(1).mean(),
        "strat_cagr": m_strat["cagr"], "hold_cagr": m_hold["cagr"],
        "strat_sharpe": m_strat["sharpe"], "hold_sharpe": m_hold["sharpe"],
        "strat_dd": m_strat["maxdd"], "hold_dd": m_hold["maxdd"],
    }


def main():
    rows = [r for r in (run_coin(c) for c in COINS) if r]
    print(f"\n=== LSTM signal backtest (OOS tail, long/flat vs buy&hold) ===\n")
    hdr = f"{'coin':>4} {'OOS window':>23} {'days':>5} {'in%':>5} | {'CAGR':>8} {'B&H':>8} | {'Shrp':>6} {'B&H':>6} | {'maxDD':>7} {'B&H':>7}"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{r['coin']:>4} {str(r['oos_from'])+'..'+str(r['oos_to']):>23} {r['days']:>5} "
              f"{r['in_mkt']*100:>4.0f}% | {r['strat_cagr']*100:>7.1f}% {r['hold_cagr']*100:>7.1f}% | "
              f"{r['strat_sharpe']:>6.2f} {r['hold_sharpe']:>6.2f} | "
              f"{r['strat_dd']*100:>6.1f}% {r['hold_dd']*100:>6.1f}%")
    # summary
    beat_cagr = sum(r["strat_cagr"] > r["hold_cagr"] for r in rows)
    beat_sharpe = sum(r["strat_sharpe"] > r["hold_sharpe"] for r in rows)
    print(f"\nStrat beats buy&hold: CAGR {beat_cagr}/{len(rows)} | Sharpe {beat_sharpe}/{len(rows)}")
    print(f"Mean strat Sharpe {np.mean([r['strat_sharpe'] for r in rows]):+.2f} "
          f"vs B&H {np.mean([r['hold_sharpe'] for r in rows]):+.2f}")


if __name__ == "__main__":
    main()
