"""Run each top strategy on each calendar year independently, $10k wallet,
so we see the full year-by-year story instead of a single bad TEST window.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
import io
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO / "user_data" / "backtest_results"

STRATEGIES = [
    ("Rebalance_R5",  "BtcRebalanceStrategy",         "REBALANCE_MODE", "R5_75_BTC",       "config.rebalance.json"),
    ("DynRebal_P20",  "BtcDynamicRebalanceStrategy",  "DR_MODE",        "DR_PROFIT_20",    "config.dynrebal.json"),
    ("3Layer_AGGR",   "Btc3LayerStrategy",            "L3_MODE",        "L3_AGGR_WIDE_GRID","config.3layer.json"),
    ("Adaptive_AGGR", "BtcAdaptiveStrategy",          "AD_MODE",        "ADAPT_AGGR_NOSTOP","config.adaptive.json"),
]

YEARS = {
    "2021": "20210101-20220101",
    "2022": "20220101-20230101",
    "2023": "20230101-20240101",
    "2024": "20240101-20250101",
    "2025": "20250101-20260101",
    "2026Q12": "20260101-20260601",
}


def run(strategy, env_var, env_val, cfg, timerange, wallet):
    env = os.environ.copy()
    env[env_var] = env_val
    venv_freqtrade = str(REPO / ".venv" / "Scripts" / "freqtrade.exe")
    cmd = [
        venv_freqtrade, "backtesting",
        "--userdir", str(REPO / "user_data"),
        "--config", str(REPO / cfg),
        "--strategy", strategy,
        "--timerange", timerange,
        "--dry-run-wallet", str(wallet),
        "--cache", "none",
    ]
    subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=REPO)
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        return None
    with zipfile.ZipFile(zips[-1]) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and "market_change" not in n]
        with z.open(names[0]) as f:
            payload = json.load(io.TextIOWrapper(f, encoding="utf-8"))
    strat_key = next(iter(payload.get("strategy", {})), None)
    if not strat_key:
        return None
    s = payload["strategy"][strat_key]
    final = float(s.get("final_balance", 0) or 0)
    roi = (final - wallet) / wallet * 100
    return round(roi, 1)


def btc_year_change():
    df = pd.read_feather(REPO / "user_data" / "data" / "binance" / "BTC_USDT-1d.feather")
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.set_index("date").sort_index()
    out = {}
    for year, tr in YEARS.items():
        start, end = tr.split("-")
        ssub = df.loc[start[:4]+"-"+start[4:6]+"-"+start[6:8] : end[:4]+"-"+end[4:6]+"-"+end[6:8]]
        if ssub.empty: out[year] = None; continue
        out[year] = round((ssub["close"].iloc[-1] / ssub["close"].iloc[0] - 1) * 100, 1)
    return out


def main():
    print("Running year-by-year (4 strategies x 6 years = 24 backtests)...")
    btc = btc_year_change()
    print(f"BTC per-year change: {btc}\n")

    rows = []
    for label, klass, env_var, env_val, cfg in STRATEGIES:
        for year, tr in YEARS.items():
            print(f"  {label} on {year}...", end=" ", flush=True)
            roi = run(klass, env_var, env_val, cfg, tr, 10000)
            print(f"ROI={roi}%")
            rows.append({"strategy": label, "year": year, "roi_%": roi})

    df = pd.DataFrame(rows)
    piv = df.pivot(index="strategy", columns="year", values="roi_%")
    # Add BTC reference row
    piv.loc["_BTC_HOLD"] = pd.Series(btc)
    print("\n" + "=" * 110)
    print("YEAR-BY-YEAR ROI %  ($10k wallet, fresh start each year)")
    print("=" * 110)
    print(piv.to_string())

    # Stats per strategy
    stats = []
    for strat in piv.index:
        row = piv.loc[strat].dropna()
        positive_yrs = int((row > 0).sum())
        total_yrs = len(row)
        mean_roi = row.mean()
        worst = row.min()
        best = row.max()
        stats.append({
            "strategy": strat,
            "avg_roi_per_year": round(mean_roi, 1),
            "best_year": round(best, 1),
            "worst_year": round(worst, 1),
            "positive_years": f"{positive_yrs}/{total_yrs}",
        })
    stats_df = pd.DataFrame(stats)
    print("\n=== Per-year stats ===")
    print(stats_df.to_string(index=False))

    out = REPO / "research" / "per_year_results.csv"
    df.to_csv(out, index=False)
    print(f"\nSaved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
