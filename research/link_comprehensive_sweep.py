"""Comprehensive LINK/USDT strategy sweep — 6 strategies x top modes x 6 years.

Goals:
  1. Year-by-year ROI per strategy/mode
  2. Max yearly drawdown
  3. Best mode per strategy
  4. Overall winner for LINK

Strategies tested (top modes from BTC sweeps):
  Rebalance:   R1_DAILY_FULL, R5_75_BTC, R6_HALFWAY                 (3 modes)
  DynRebal:    DR_PROFIT_10, DR_PROFIT_20, DR_PROFIT_30,
               DR_REGIME, DR_RSI_70_30                              (5 modes)
  3Layer:      L3_AGGR_BASELINE, L3_AGGR_WIDE_GRID,
               L3_AGGR_TIGHT_GRID, L3_BAL_WIDE_GRID                 (4 modes)
  Adaptive:    ADAPT_AGGR_NOSTOP, ADAPT_BAL_NOSTOP,
               ADAPT_DEF_NOSTOP, ADAPT_AGGR_LOOSE                   (4 modes)
  Shield:      RS_FAST, RS_MED, RS_SLOW, RS_AGGR, RS_DEFENSIVE      (5 modes)
  DCA:         V1_BLIND, V5_TIERED                                  (2 modes)

SKIP: BtcOnChainStrategy (needs BTC on-chain data, not LINK).

Total: 23 modes x 6 years = 138 backtests.
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
CFG = "config.link.json"

# (display_name, strategy_class, env_var, env_val, strategy_family)
COMBOS = [
    # Rebalance
    ("Rebal_R1",   "BtcRebalanceStrategy",        "REBALANCE_MODE", "R1_DAILY_FULL",     "Rebalance"),
    ("Rebal_R5",   "BtcRebalanceStrategy",        "REBALANCE_MODE", "R5_75_BTC",         "Rebalance"),
    ("Rebal_R6",   "BtcRebalanceStrategy",        "REBALANCE_MODE", "R6_HALFWAY",        "Rebalance"),
    # DynRebal
    ("Dyn_P10",    "BtcDynamicRebalanceStrategy", "DR_MODE",        "DR_PROFIT_10",      "DynRebal"),
    ("Dyn_P20",    "BtcDynamicRebalanceStrategy", "DR_MODE",        "DR_PROFIT_20",      "DynRebal"),
    ("Dyn_P30",    "BtcDynamicRebalanceStrategy", "DR_MODE",        "DR_PROFIT_30",      "DynRebal"),
    ("Dyn_REG",    "BtcDynamicRebalanceStrategy", "DR_MODE",        "DR_REGIME",         "DynRebal"),
    ("Dyn_RSI",    "BtcDynamicRebalanceStrategy", "DR_MODE",        "DR_RSI_70_30",      "DynRebal"),
    # 3Layer
    ("L3_AGGR_BL", "Btc3LayerStrategy",           "L3_MODE",        "L3_AGGR_BASELINE",  "3Layer"),
    ("L3_AGGR_WG", "Btc3LayerStrategy",           "L3_MODE",        "L3_AGGR_WIDE_GRID", "3Layer"),
    ("L3_AGGR_TG", "Btc3LayerStrategy",           "L3_MODE",        "L3_AGGR_TIGHT_GRID","3Layer"),
    ("L3_BAL_WG",  "Btc3LayerStrategy",           "L3_MODE",        "L3_BAL_WIDE_GRID",  "3Layer"),
    # Adaptive
    ("Ad_AGGR",    "BtcAdaptiveStrategy",         "AD_MODE",        "ADAPT_AGGR_NOSTOP", "Adaptive"),
    ("Ad_BAL",     "BtcAdaptiveStrategy",         "AD_MODE",        "ADAPT_BAL_NOSTOP",  "Adaptive"),
    ("Ad_DEF",     "BtcAdaptiveStrategy",         "AD_MODE",        "ADAPT_DEF_NOSTOP",  "Adaptive"),
    ("Ad_AGGR_LO", "BtcAdaptiveStrategy",         "AD_MODE",        "ADAPT_AGGR_LOOSE",  "Adaptive"),
    # Shield
    ("Sh_FAST",    "BtcRegimeShieldStrategy",     "RS_MODE",        "RS_FAST",           "Shield"),
    ("Sh_MED",     "BtcRegimeShieldStrategy",     "RS_MODE",        "RS_MED",            "Shield"),
    ("Sh_SLOW",   "BtcRegimeShieldStrategy",      "RS_MODE",        "RS_SLOW",           "Shield"),
    ("Sh_AGGR",    "BtcRegimeShieldStrategy",     "RS_MODE",        "RS_AGGR",           "Shield"),
    ("Sh_DEF",     "BtcRegimeShieldStrategy",     "RS_MODE",        "RS_DEFENSIVE",      "Shield"),
    # DCA
    ("DCA_V1",     "BtcDcaHoldStrategy",          "DCA_MODE",       "V1_BLIND",          "DCA"),
    ("DCA_V5",     "BtcDcaHoldStrategy",          "DCA_MODE",       "V5_TIERED",         "DCA"),
]

YEARS = {
    "2021": "20210101-20220101",
    "2022": "20220101-20230101",
    "2023": "20230101-20240101",
    "2024": "20240101-20250101",
    "2025": "20250101-20260101",
    "2026Q12": "20260101-20260601",
}


def run(strategy, env_var, env_val, tr, wallet=10000):
    env = os.environ.copy()
    env[env_var] = env_val
    venv = str(REPO / ".venv" / "Scripts" / "freqtrade.exe")
    subprocess.run([
        venv, "backtesting", "--userdir", str(REPO / "user_data"),
        "--config", str(REPO / CFG), "--strategy", strategy,
        "--timerange", tr, "--dry-run-wallet", str(wallet), "--cache", "none",
    ], env=env, capture_output=True, text=True, cwd=REPO)
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips: return None, None
    try:
        with zipfile.ZipFile(zips[-1]) as z:
            names = [n for n in z.namelist() if n.endswith(".json") and "market_change" not in n]
            with z.open(names[0]) as f:
                payload = json.load(io.TextIOWrapper(f, encoding="utf-8"))
        sk = next(iter(payload.get("strategy", {})), None)
        if not sk: return None, None
        s = payload["strategy"][sk]
        final = float(s.get("final_balance", 0) or 0)
        roi = (final - wallet) / wallet * 100
        # Max drawdown from backtest
        max_dd = float(s.get("max_drawdown_account", 0) or 0) * 100
        return round(roi, 1), round(max_dd, 1)
    except Exception:
        return None, None


def main():
    total = len(COMBOS) * len(YEARS)
    n = 0
    rows = []
    for label, klass, env_var, env_val, family in COMBOS:
        for year, tr in YEARS.items():
            n += 1
            print(f"  [{n}/{total}] {label} ({family}) on {year}...", end=" ", flush=True)
            roi, dd = run(klass, env_var, env_val, tr)
            print(f"ROI={roi}%, MaxDD={dd}%")
            rows.append({
                "family": family, "variant": label, "year": year,
                "roi_%": roi, "max_dd_%": dd
            })

    df = pd.DataFrame(rows)
    piv_roi = df.pivot(index="variant", columns="year", values="roi_%")
    piv_dd = df.pivot(index="variant", columns="year", values="max_dd_%")

    # Stats per variant
    stats = []
    for v in piv_roi.index:
        row = piv_roi.loc[v].dropna()
        dds = piv_dd.loc[v].dropna()
        compound = 1.0
        for r in row: compound *= (1 + r / 100)
        annual = compound ** (1 / max(len(row), 1)) - 1
        family = df[df["variant"] == v]["family"].iloc[0]
        stats.append({
            "family": family,
            "variant": v,
            "compound_$10k": round(compound * 10000, 0),
            "annual_%": round(annual * 100, 1),
            "avg_yr_%": round(row.mean(), 1),
            "best_yr_%": round(row.max(), 1),
            "worst_yr_%": round(row.min(), 1),
            "worst_yr_DD_%": round(dds.max(), 1),  # max dd across years
            "positive_yrs": int((row > 0).sum()),
        })
    stats_df = pd.DataFrame(stats).sort_values("annual_%", ascending=False).reset_index(drop=True)

    print("\n" + "=" * 110)
    print("LINK/USDT — YEAR-BY-YEAR ROI %  ($10k wallet)")
    print("=" * 110)
    print(piv_roi.to_string())

    print("\n" + "=" * 110)
    print("OVERALL RANKING (compound annual)")
    print("=" * 110)
    print(stats_df.to_string(index=False))

    # Best per family
    print("\n=== Best mode per strategy family ===")
    best_per_family = stats_df.loc[stats_df.groupby("family")["annual_%"].idxmax()]
    print(best_per_family.to_string(index=False))

    Path("research").mkdir(exist_ok=True)
    df.to_csv("research/link_results_raw.csv", index=False)
    stats_df.to_csv("research/link_summary.csv", index=False)
    piv_roi.to_csv("research/link_roi_pivot.csv")
    piv_dd.to_csv("research/link_dd_pivot.csv")
    print("\nSaved: research/link_results_raw.csv, link_summary.csv, link_roi_pivot.csv, link_dd_pivot.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
