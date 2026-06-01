"""Synthetic stress test — generate adversarial regime scenarios and re-run.

We use bootstrap-style resampling of historical daily returns to build
3 synthetic 18-month series that the strategies have NEVER seen:

  1. BEAR_CRASH    — bias toward 2022-like distribution: mean_ret < 0,
                     fat-tail down-days, occasional -10% crashes injected.
  2. CHOPPY        — bias toward 2025-like sideways: low |mean_ret|,
                     mean-reverting random walk.
  3. SLOW_BLEED    — small persistent negative drift, low volatility
                     (the worst case for trend strategies — no recovery).

Saves each synthetic price series as a feather file in user_data/data/binance/
under symbols SYN_BEAR, SYN_CHOP, SYN_BLEED, then runs each strategy on
each synthetic series.

NOTE: synthetic data is not "the future". It probes specific weaknesses.
A strategy that loses on all 3 syntheses is fragile to those regimes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "user_data" / "data" / "binance"
SEED = 42


def _btc_daily_returns() -> pd.Series:
    df = pd.read_feather(DATA / "BTC_USDT-1d.feather")
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.set_index("date").sort_index()
    return df["close"].astype(float).pct_change().dropna()


def synth_bear_crash(rng: np.random.Generator, n_days: int = 547) -> pd.DataFrame:
    """547 days = 18 months. Bias toward negative drift + injected crashes."""
    rets = _btc_daily_returns()
    bear_days = rets.loc["2022-01-01":"2022-12-31"]
    sample = rng.choice(bear_days.values, size=n_days, replace=True)
    # Inject 3 random -12% crash days.
    crash_pos = rng.choice(n_days, size=3, replace=False)
    sample[crash_pos] = -0.12
    return _price_from_returns(sample, start_price=40000.0, start_date="2030-01-01")


def synth_choppy(rng: np.random.Generator, n_days: int = 547) -> pd.DataFrame:
    """Mean-reverting AR(1) with low vol — classic chop."""
    base = rng.normal(0, 0.015, size=n_days)
    # Slight mean-reversion on the level (anchor toward 0).
    for i in range(1, n_days):
        base[i] = 0.6 * base[i] - 0.2 * base[i - 1]
    return _price_from_returns(base, start_price=50000.0, start_date="2031-01-01")


def synth_slow_bleed(rng: np.random.Generator, n_days: int = 547) -> pd.DataFrame:
    """Constant -0.05% daily drift + low vol — the killer scenario for trend."""
    drift = -0.0005
    rets = drift + rng.normal(0, 0.012, size=n_days)
    return _price_from_returns(rets, start_price=60000.0, start_date="2032-01-01")


def _price_from_returns(rets: np.ndarray, start_price: float, start_date: str) -> pd.DataFrame:
    prices = start_price * np.cumprod(1.0 + rets)
    dates = pd.date_range(start_date, periods=len(rets), freq="D", tz="UTC")
    df = pd.DataFrame({
        "date": dates,
        "open": prices,
        "high": prices * (1 + np.abs(rets) * 0.5),
        "low":  prices * (1 - np.abs(rets) * 0.5),
        "close": prices,
        "volume": np.full(len(rets), 1_000_000.0),
    })
    # Synthesize sane OHLC by ensuring high >= max(open, close) and low <= min.
    df["high"] = np.maximum(df["high"], np.maximum(df["open"], df["close"]))
    df["low"]  = np.minimum(df["low"],  np.minimum(df["open"], df["close"]))
    return df


def summarize(name: str, df: pd.DataFrame) -> None:
    rets = df["close"].pct_change().dropna()
    print(f"{name}: total_ret={(df['close'].iloc[-1]/df['close'].iloc[0]-1)*100:+.1f}% | "
          f"vol_daily={rets.std()*100:.2f}% | max_dd={_max_dd(df['close'])*100:.1f}% | days={len(df)}")


def _max_dd(s: pd.Series) -> float:
    peak = s.cummax()
    return ((peak - s) / peak).max()


def main() -> int:
    rng = np.random.default_rng(SEED)
    scenarios = {
        "SYN_BEAR":  synth_bear_crash(rng),
        "SYN_CHOP":  synth_choppy(rng),
        "SYN_BLEED": synth_slow_bleed(rng),
    }
    print("=== Synthetic scenarios summary ===")
    for name, df in scenarios.items():
        summarize(name, df)
        # Write as a fake BTC_USDT-1d.feather under a renamed symbol so freqtrade
        # backtest can read it. Each scenario gets its own feather and timerange.
        sym = f"{name}_USDT-1d.feather"
        out = DATA / sym
        df.to_feather(out)
        print(f"  saved {out}")

    print("\nNow re-run any strategy with --pairs SYN_BEAR/USDT (etc.) and a")
    print("timerange covering 2030-2032 to evaluate synthetic resilience.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
