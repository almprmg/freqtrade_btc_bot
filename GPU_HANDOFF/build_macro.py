"""build_macro.py — Reconstruct macro_signals.feather from Yahoo Finance.

The original macro_signals.feather lives on the CPU machine (no SSH access
here). This rebuilds the same four columns the LSTM expects from public data:

    dxy_zscore       rolling 200d z-score of the US Dollar Index
    vix              CBOE volatility index level
    spy_above_ema50  1.0 if SPY close > its EMA50 else 0.0
    macro_risk_on    1.0 if (spy_above_ema50 and VIX < 20) else 0.0

Output dates are tz-aware UTC midnight + forward-filled to a continuous
daily index, so they align exactly with the OHLCV `date` column the
training script normalizes against.

USAGE:  python GPU_HANDOFF/build_macro.py
"""
from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "user_data" / "data" / "macro_signals.feather"
START = "2017-07-01"


def close_series(ticker: str) -> pd.Series:
    d = yf.download(ticker, start=START, progress=False, auto_adjust=True)
    s = d["Close"]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    s.index = pd.to_datetime(s.index).tz_localize("UTC")
    return s.astype("float64")


def main():
    print("Downloading DXY / VIX / SPY from Yahoo Finance ...")
    dxy = close_series("DX-Y.NYB")
    vix = close_series("^VIX")
    spy = close_series("SPY")

    # Continuous daily UTC index, forward-filled across weekends/holidays.
    start = min(dxy.index.min(), vix.index.min(), spy.index.min())
    end = max(dxy.index.max(), vix.index.max(), spy.index.max())
    idx = pd.date_range(start=start.normalize(), end=end.normalize(), freq="D", tz="UTC")

    dxy = dxy.reindex(idx).ffill()
    vix = vix.reindex(idx).ffill()
    spy = spy.reindex(idx).ffill()

    dxy_z = (dxy - dxy.rolling(200, min_periods=50).mean()) / dxy.rolling(200, min_periods=50).std()
    spy_ema50 = spy.ewm(span=50, adjust=False).mean()
    spy_above = (spy > spy_ema50).astype("float64")
    risk_on = ((spy_above == 1.0) & (vix < 20)).astype("float64")

    out = pd.DataFrame({
        "date": idx,
        "dxy_zscore": dxy_z.values,
        "vix": vix.values,
        "spy_above_ema50": spy_above.values,
        "macro_risk_on": risk_on.values,
    }).fillna(0.0)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_feather(OUT)
    print(f"Saved {len(out)} rows -> {OUT}")
    print(f"Range: {out['date'].min().date()} .. {out['date'].max().date()}")
    print(out.tail(3).to_string(index=False))


if __name__ == "__main__":
    main()
