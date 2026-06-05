"""macro_data.py — Fetch and store macro economic indicators for crypto strategies.

Pulls daily data via yfinance for indicators that historically affect BTC:

  DXY  — US Dollar Index (inverse correlation with BTC)
  VIX  — CBOE Volatility Index (fear gauge; high = risk-off)
  SPY  — S&P 500 ETF (broad market correlation)
  TNX  — 10-Year Treasury Yield (rates affect risk appetite)
  GC=F — Gold futures (alternative store of value)
  QQQ  — NASDAQ ETF (tech-heavy, correlates with crypto)

Outputs:
  user_data/data/macro_daily.feather  — wide-format daily data
  user_data/data/macro_signals.feather — derived signals ready for strategies

Computed signals:
  - dxy_zscore        — DXY's 30-day z-score (>1 = strong dollar, bearish crypto)
  - vix_regime        — "calm" / "elevated" / "panic"
  - spy_trend         — S&P 500 above/below 50d EMA
  - rates_change_5d   — recent 10y yield direction
  - macro_risk_on     — composite [-1, +1] risk appetite score

Usage:
  python -m research.ai.macro_data fetch
  python -m research.ai.macro_data signals
  python -m research.ai.macro_data analyze   # correlation with BTC
"""
from __future__ import annotations

import sys
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore", category=FutureWarning)

REPO = Path(__file__).resolve().parents[2]
RAW_OUT = REPO / "user_data" / "data" / "macro_daily.feather"
SIG_OUT = REPO / "user_data" / "data" / "macro_signals.feather"

# Yahoo symbols + friendly names
SYMBOLS = {
    "DX-Y.NYB":  "dxy",      # US Dollar Index (correct Yahoo symbol)
    "^VIX":  "vix",          # Volatility Index
    "SPY":   "spy",          # S&P 500
    "^TNX":  "tnx",          # 10Y Treasury Yield
    "GC=F":  "gold",         # Gold futures
    "QQQ":   "qqq",          # NASDAQ-100
}


def fetch_all(start="2017-01-01") -> pd.DataFrame:
    """Fetch all macro symbols from Yahoo. Returns wide DataFrame indexed by date."""
    print(f"Fetching {len(SYMBOLS)} macro symbols from {start}...")
    all_data = {}
    for sym, name in SYMBOLS.items():
        try:
            df = yf.download(sym, start=start, progress=False, auto_adjust=True)
            if df.empty:
                # Try fallback variants
                if sym == "^DXY":
                    df = yf.download("DX-Y.NYB", start=start, progress=False, auto_adjust=True)
            if df.empty:
                print(f"  {sym}: EMPTY (skipped)")
                continue
            # Multi-level columns -> flatten
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            close_col = df["Close"] if "Close" in df.columns else df.iloc[:, 0]
            all_data[name] = close_col
            print(f"  {sym} ({name}): {len(close_col)} rows, range {close_col.index[0].date()} -> {close_col.index[-1].date()}")
        except Exception as e:
            print(f"  {sym}: ERROR — {e}")

    if not all_data:
        raise RuntimeError("No data fetched!")

    df = pd.DataFrame(all_data)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert("UTC") if df.index.tz is None else df.index.tz_convert("UTC")
    df.index.name = "date"
    # Forward-fill weekends/holidays (macro markets closed; crypto runs 24/7)
    df = df.ffill()
    return df


def compute_signals(macro: pd.DataFrame) -> pd.DataFrame:
    """Derive crypto-relevant signals from raw macro series."""
    sig = pd.DataFrame(index=macro.index)

    if "dxy" in macro.columns:
        sig["dxy"] = macro["dxy"]
        # DXY 30-day z-score: positive = strong dollar = bearish crypto
        rolling_mean = macro["dxy"].rolling(30, min_periods=10).mean()
        rolling_std = macro["dxy"].rolling(30, min_periods=10).std()
        sig["dxy_zscore"] = (macro["dxy"] - rolling_mean) / rolling_std
        sig["dxy_ret_30d"] = macro["dxy"].pct_change(30)

    if "vix" in macro.columns:
        sig["vix"] = macro["vix"]
        # VIX regime: <20 calm, 20-30 elevated, >30 panic
        sig["vix_regime"] = pd.cut(
            macro["vix"],
            bins=[0, 20, 30, 200],
            labels=["calm", "elevated", "panic"]
        )
        sig["vix_is_panic"] = (macro["vix"] > 30).astype(int)

    if "spy" in macro.columns:
        ema50 = macro["spy"].ewm(span=50, min_periods=20).mean()
        sig["spy"] = macro["spy"]
        sig["spy_above_ema50"] = (macro["spy"] > ema50).astype(int)
        sig["spy_ret_30d"] = macro["spy"].pct_change(30)

    if "tnx" in macro.columns:
        sig["tnx"] = macro["tnx"]
        sig["tnx_change_5d"] = macro["tnx"].diff(5)
        # Rising rates >0.2 over 5d -> flag bearish for risk
        sig["rates_rising"] = (sig["tnx_change_5d"] > 0.2).astype(int)

    if "gold" in macro.columns:
        sig["gold"] = macro["gold"]
        sig["gold_ret_30d"] = macro["gold"].pct_change(30)

    if "qqq" in macro.columns:
        ema50_q = macro["qqq"].ewm(span=50, min_periods=20).mean()
        sig["qqq_above_ema50"] = (macro["qqq"] > ema50_q).astype(int)

    # Composite risk-on score in [-1, +1]
    # +1 = full risk-on (bullish crypto): dollar weak + SPY/QQQ bull + low VIX + falling rates
    # -1 = risk-off
    components = []
    if "dxy_zscore" in sig:
        components.append(-sig["dxy_zscore"].clip(-2, 2) / 2)  # -dollar => +risk-on
    if "vix_regime" in sig:
        vix_score = pd.Series(0.0, index=sig.index)
        vix_score[sig["vix_regime"] == "calm"] = 1.0
        vix_score[sig["vix_regime"] == "elevated"] = 0.0
        vix_score[sig["vix_regime"] == "panic"] = -1.0
        components.append(vix_score)
    if "spy_above_ema50" in sig:
        components.append((sig["spy_above_ema50"] * 2 - 1).astype(float))
    if "qqq_above_ema50" in sig:
        components.append((sig["qqq_above_ema50"] * 2 - 1).astype(float))
    if "rates_rising" in sig:
        components.append(-(sig["rates_rising"] * 2 - 1).astype(float) * 0.5)

    if components:
        # Average all components
        risk_on = sum(components) / len(components)
        sig["macro_risk_on"] = risk_on.clip(-1, 1)

    return sig


def analyze_correlation(signals: pd.DataFrame):
    """Compute correlation of macro signals with BTC daily returns."""
    btc = pd.read_feather(REPO / "user_data" / "data" / "binance" / "BTC_USDT-1d.feather")
    btc["date"] = pd.to_datetime(btc["date"], utc=True)
    btc = btc.set_index("date").sort_index()
    btc["ret_1d"] = btc["close"].pct_change()
    btc["ret_7d"] = btc["close"].pct_change(7)
    btc["ret_30d"] = btc["close"].pct_change(30)

    df = btc[["ret_1d", "ret_7d", "ret_30d"]].join(signals, how="inner")
    print(f"\nMerged {len(df)} rows (BTC × macro signals)")
    print(f"Range: {df.index.min().date()} -> {df.index.max().date()}")

    # Correlations of each signal with BTC fwd returns
    print("\n=== Correlation of macro signals with BTC returns ===")
    cols_to_test = ["dxy_zscore", "dxy_ret_30d", "vix", "vix_is_panic",
                    "spy_above_ema50", "spy_ret_30d", "tnx", "tnx_change_5d",
                    "rates_rising", "gold_ret_30d", "qqq_above_ema50", "macro_risk_on"]
    print(f"{'Signal':<25}{'corr(ret_1d)':>15}{'corr(ret_7d)':>15}{'corr(ret_30d)':>15}")
    print("-" * 70)
    for col in cols_to_test:
        if col not in df.columns:
            continue
        c1 = df[col].corr(df["ret_1d"])
        c7 = df[col].corr(df["ret_7d"])
        c30 = df[col].corr(df["ret_30d"])
        flag = ""
        if abs(c30) > 0.10:
            flag = " ★"
        elif abs(c30) > 0.05:
            flag = " ·"
        print(f"{col:<25}{c1:>+15.4f}{c7:>+15.4f}{c30:>+15.4f}{flag}")

    # Compare BTC 30d returns by macro_risk_on quintile
    if "macro_risk_on" in df.columns:
        df["risk_quintile"] = pd.qcut(df["macro_risk_on"].dropna(), q=5, labels=["Q1 (risk-off)", "Q2", "Q3", "Q4", "Q5 (risk-on)"], duplicates="drop")
        print("\n=== BTC 30d return by macro_risk_on quintile ===")
        for q, sub in df.dropna(subset=["risk_quintile", "ret_30d"]).groupby("risk_quintile", observed=True):
            print(f"  {q}: n={len(sub)}, mean_30d_ret={sub['ret_30d'].mean()*100:+.2f}%, win_rate={(sub['ret_30d']>0).mean()*100:.0f}%")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd in ("fetch", "all"):
        macro = fetch_all()
        macro_reset = macro.reset_index()
        macro_reset.to_feather(RAW_OUT)
        print(f"\nSaved raw: {RAW_OUT}  ({len(macro)} rows × {len(macro.columns)} cols)")
    else:
        macro = pd.read_feather(RAW_OUT)
        macro["date"] = pd.to_datetime(macro["date"], utc=True)
        macro = macro.set_index("date").sort_index()

    if cmd in ("signals", "all"):
        sig = compute_signals(macro)
        sig_reset = sig.reset_index()
        # Drop columns that aren't feather-compatible (categorical -> string)
        if "vix_regime" in sig_reset.columns:
            sig_reset["vix_regime"] = sig_reset["vix_regime"].astype(str)
        sig_reset.to_feather(SIG_OUT)
        print(f"Saved signals: {SIG_OUT}  ({len(sig)} rows × {len(sig.columns)} signals)")

    if cmd in ("analyze", "all"):
        sig = pd.read_feather(SIG_OUT)
        sig["date"] = pd.to_datetime(sig["date"], utc=True)
        sig = sig.set_index("date").sort_index()
        analyze_correlation(sig)


if __name__ == "__main__":
    main()
