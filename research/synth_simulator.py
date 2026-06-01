"""In-code simulator for the rebalance-style strategies on synthetic data.

Avoids the Freqtrade infrastructure overhead — we already validated the
strategies match Freqtrade output via the multipair sweep. This lets us
hammer them across many adversarial regimes quickly.

Strategies simulated:
  REBAL_75    — fixed-target daily rebalance at 75% BTC
  DYN_P20     — rebalance only when |portfolio gain| since last rebalance ≥ 20%
  HOLD_BTC    — buy and hold (control)
  HOLD_USDT   — stay flat (control, capital preservation)

Each is run on:
  REAL_FULL   — actual BTC 2021-2026
  SYN_BEAR    — synthetic bear+crash 18mo
  SYN_CHOP    — synthetic sideways 18mo
  SYN_BLEED   — synthetic slow bleed 18mo
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "user_data" / "data" / "binance"

START_WALLET = 10000.0


def load_series(symbol: str) -> pd.Series:
    df = pd.read_feather(DATA / f"{symbol}-1d.feather")
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df.set_index("date")["close"].astype(float)


def simulate_rebalance(prices: pd.Series, target: float = 0.75, threshold: float = 0.0,
                       fee: float = 0.001) -> dict:
    cash = START_WALLET * (1.0 - target)
    btc = (START_WALLET * target) / prices.iloc[0]
    cash -= START_WALLET * target * fee  # initial fee
    series = []
    trades = 0
    for p in prices.iloc[1:]:
        port = cash + btc * p
        target_btc_val = target * port
        drift = btc * p - target_btc_val
        if abs(drift) / max(port, 1e-9) >= threshold:
            if drift > 0:
                sell = min(drift, btc * p * 0.99)
                qty = sell / p
                btc -= qty
                cash += sell * (1 - fee)
                trades += 1
            elif drift < 0 and cash > 1:
                buy = min(-drift, cash * 0.99)
                qty = (buy * (1 - fee)) / p
                btc += qty
                cash -= buy
                trades += 1
        series.append(cash + btc * p)
    return _stats(series, trades)


def simulate_dyn_profit(prices: pd.Series, target: float = 0.75, profit_trigger: float = 0.20,
                       fee: float = 0.001) -> dict:
    cash = START_WALLET * (1.0 - target)
    btc = (START_WALLET * target) / prices.iloc[0]
    cash -= START_WALLET * target * fee
    anchor = START_WALLET
    series = []
    trades = 0
    for p in prices.iloc[1:]:
        port = cash + btc * p
        gain = (port - anchor) / anchor if anchor > 0 else 0
        if abs(gain) >= profit_trigger:
            target_btc_val = target * port
            drift = btc * p - target_btc_val
            if drift > 0:
                sell = min(drift, btc * p * 0.99)
                qty = sell / p
                btc -= qty
                cash += sell * (1 - fee)
                trades += 1
            elif drift < 0 and cash > 1:
                buy = min(-drift, cash * 0.99)
                qty = (buy * (1 - fee)) / p
                btc += qty
                cash -= buy
                trades += 1
            anchor = port
        series.append(cash + btc * p)
    return _stats(series, trades)


def simulate_hold(prices: pd.Series, in_btc: bool, fee: float = 0.001) -> dict:
    if in_btc:
        btc = (START_WALLET * (1 - fee)) / prices.iloc[0]
        series = [btc * p for p in prices.iloc[1:]]
    else:
        series = [START_WALLET] * (len(prices) - 1)
    return _stats(series, 1 if in_btc else 0)


def _stats(series: list[float], trades: int) -> dict:
    if not series:
        return {"final": 0, "roi_%": -100, "max_dd_%": 100, "sharpe": 0, "trades": trades}
    s = pd.Series(series)
    final = s.iloc[-1]
    roi = (final / START_WALLET - 1) * 100
    peak = s.cummax()
    dd = ((peak - s) / peak).max() * 100
    rets = s.pct_change().dropna()
    sharpe = (rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0
    return {
        "final": round(final, 0), "roi_%": round(roi, 1),
        "max_dd_%": round(dd, 1), "sharpe": round(sharpe, 2),
        "trades": trades,
    }


def main() -> int:
    scenarios = {
        "REAL_BTC_5Y":  load_series("BTC_USDT").loc["2021-01-01":"2026-01-01"],
        "SYN_BEAR":     load_series("SYN_BEAR_USDT"),
        "SYN_CHOP":     load_series("SYN_CHOP_USDT"),
        "SYN_BLEED":    load_series("SYN_BLEED_USDT"),
    }
    strategies = {
        "REBAL_75":  lambda px: simulate_rebalance(px, target=0.75, threshold=0.0),
        "DYN_P20":   lambda px: simulate_dyn_profit(px, target=0.75, profit_trigger=0.20),
        "HOLD_BTC":  lambda px: simulate_hold(px, in_btc=True),
        "HOLD_USDT": lambda px: simulate_hold(px, in_btc=False),
    }

    rows = []
    for scen_name, prices in scenarios.items():
        period_yr = (prices.index[-1] - prices.index[0]).days / 365.25
        for strat_name, fn in strategies.items():
            r = fn(prices)
            mult = max(r["final"] / START_WALLET, 1e-6)
            annual = (mult ** (1.0 / max(period_yr, 0.01)) - 1) * 100
            rows.append({
                "scenario": scen_name, "strategy": strat_name,
                "period_yr": round(period_yr, 1),
                **r,
                "annual_%": round(annual, 1),
            })

    df = pd.DataFrame(rows)
    print("\n" + "=" * 110)
    print("SYNTHETIC STRESS TEST — strategy x scenario  ($10k wallet)")
    print("=" * 110)
    # Pivot for readability
    piv_roi = df.pivot(index="strategy", columns="scenario", values="roi_%")
    piv_dd  = df.pivot(index="strategy", columns="scenario", values="max_dd_%")
    print("\nROI %:")
    print(piv_roi.to_string())
    print("\nMax DD %:")
    print(piv_dd.to_string())

    save = REPO / "research" / "synth_results.csv"
    df.to_csv(save, index=False)
    print(f"\nSaved: {save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
