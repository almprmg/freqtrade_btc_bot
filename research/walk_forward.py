"""Walk-forward analysis for our 4 top strategies.

Split:
  TRAIN      2021-01-01 -> 2023-12-31  (bull 2021 + bear 2022 + recovery 2023)
  VALIDATE   2024-01-01 -> 2024-12-31  (bull 2024)
  TEST       2025-01-01 -> 2026-06-01  (sideways + recent bear)

For each strategy mode, run Freqtrade backtest on each period and compute:
  - final balance (from $10k starting wallet, scaled)
  - period return %
  - annualized return %
  - max drawdown %
  - sharpe (closed trades or daily wallet)

Then compute degradation:
  TRAIN_ROI -> VAL_ROI -> TEST_ROI

A robust strategy keeps positive ROI across all three. A curve-fit shows
strong TRAIN but weak VAL/TEST.

Strategies evaluated (using their winning mode):
  Rebalance       R5_75_BTC
  DynRebal        DR_PROFIT_20
  3Layer          L3_AGGR_WIDE_GRID
  Adaptive        ADAPT_AGGR_NOSTOP
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

PERIODS = {
    "TRAIN": "20210101-20240101",
    "VAL":   "20240101-20250101",
    "TEST":  "20250101-20260601",
}

STRATEGIES = [
    # (display name, strategy class, env var name, env var value, config file)
    ("Rebalance_R5",  "BtcRebalanceStrategy",         "REBALANCE_MODE", "R5_75_BTC",       "config.rebalance.json"),
    ("DynRebal_P20",  "BtcDynamicRebalanceStrategy",  "DR_MODE",        "DR_PROFIT_20",    "config.dynrebal.json"),
    ("3Layer_AGGR",   "Btc3LayerStrategy",            "L3_MODE",        "L3_AGGR_WIDE_GRID","config.3layer.json"),
    ("Adaptive_AGGR", "BtcAdaptiveStrategy",          "AD_MODE",        "ADAPT_AGGR_NOSTOP","config.adaptive.json"),
]


def run_backtest(strategy: str, env_var: str, env_val: str, cfg: str, timerange: str, wallet: float) -> dict:
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
        "--export", "trades",
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=REPO)
    return parse_latest_zip(wallet)


def parse_latest_zip(wallet: float) -> dict:
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        return {"final": None}
    with zipfile.ZipFile(zips[-1]) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and "market_change" not in n]
        if not names:
            return {"final": None}
        with z.open(names[0]) as f:
            payload = json.load(io.TextIOWrapper(f, encoding="utf-8"))
    strat_key = next(iter(payload.get("strategy", {})), None)
    if not strat_key:
        return {"final": None}
    s = payload["strategy"][strat_key]
    final = float(s.get("final_balance", 0) or 0)
    profit = final - wallet
    roi = profit / wallet * 100
    return {
        "final": round(final, 2),
        "profit": round(profit, 2),
        "roi_%": round(roi, 1),
        "trades": int(s.get("total_trades", 0)),
        "max_dd_%": round(float(s.get("max_drawdown_account", 0) or 0) * 100, 2),
        "sharpe": round(float(s.get("sharpe", 0) or 0), 2),
    }


def annualize(roi_pct: float, period_years: float) -> float:
    if period_years <= 0:
        return 0.0
    mult = max(1.0 + roi_pct / 100.0, 1e-6)
    return (mult ** (1.0 / period_years) - 1.0) * 100.0


def main() -> int:
    WALLET = 10000.0
    rows = []
    print(f"Running walk-forward over {len(STRATEGIES)} strategies x {len(PERIODS)} periods...")
    for label, klass, env_var, env_val, cfg in STRATEGIES:
        for period, tr in PERIODS.items():
            print(f"  - {label} on {period}({tr})...", end=" ", flush=True)
            stats = run_backtest(klass, env_var, env_val, cfg, tr, WALLET)
            rows.append({"strategy": label, "period": period, **stats})
            print(f"ROI={stats.get('roi_%','?')}%")

    df = pd.DataFrame(rows)
    years_map = {"TRAIN": 3.0, "VAL": 1.0, "TEST": 1.4}
    df["annual_%"] = df.apply(lambda r: round(annualize(r["roi_%"], years_map[r["period"]]), 1), axis=1)

    print("\n" + "=" * 95)
    print("WALK-FORWARD RESULTS  (each row = strategy x period, $10k wallet)")
    print("=" * 95)
    show = df.pivot(index="strategy", columns="period", values=["roi_%", "annual_%", "max_dd_%"])
    print(show.to_string())

    # Out-of-sample degradation: TRAIN vs (VAL + TEST) average.
    pivot = df.pivot(index="strategy", columns="period", values="annual_%")
    oos_avg = (pivot["VAL"] + pivot["TEST"]) / 2
    degrade = (pivot["TRAIN"] - oos_avg).round(1)
    print("\n=== OUT-OF-SAMPLE DEGRADATION  (TRAIN annual % - OOS avg annual %) ===")
    print("Positive = strategy worked better in train. Large positive = potential overfit.")
    print(degrade.to_string())

    out = REPO / "research" / "walk_forward_results.csv"
    df.to_csv(out, index=False)
    print(f"\nSaved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
