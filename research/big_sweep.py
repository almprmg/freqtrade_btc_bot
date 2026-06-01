"""Comprehensive comparison sweep — ALL existing strategies, original and
shielded variants, on BTC + ETH + SOL, year-by-year for 5+ years.

OUTPUT IS REVIEW-ONLY. No deployment until user approves.

Variants tested:
  BTC pair:
    01 Rebalance R5_75       (original)
    02 Rebalance R5_75 + SHIELD
    03 DynRebal P20          (original)
    04 DynRebal P20 + SHIELD
    05 3Layer AGGR_WIDE_GRID (original)
    06 3Layer AGGR_WIDE_GRID + SHIELD
    07 Adaptive AGGR_NOSTOP  (original)
    08 Adaptive AGGR_NOSTOP + SHIELD
    09 Pure Shield RS_AGGR   (baseline winner)

  ETH pair:
    10 DynRebal P20 on ETH      (original)
    11 Pure Shield on ETH (RS_AGGR)

  SOL pair:
    12 DynRebal P20 on SOL      (original)
    13 Pure Shield on SOL (RS_AGGR)
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

# (label, strategy_class, env_var, env_val, config, with_shield, wallet)
COMBOS = [
    ("01 Rebal_R5",              "BtcRebalanceStrategy",         "REBALANCE_MODE", "R5_75_BTC",        "config.rebalance.json", False, 10000),
    ("02 Rebal_R5_SHIELD",       "BtcRebalanceStrategy",         "REBALANCE_MODE", "R5_75_BTC",        "config.rebalance.json", True,  10000),
    ("03 DynRebal_P20",          "BtcDynamicRebalanceStrategy",  "DR_MODE",        "DR_PROFIT_20",     "config.dynrebal.json",  False, 10000),
    ("04 DynRebal_P20_SHIELD",   "BtcDynamicRebalanceStrategy",  "DR_MODE",        "DR_PROFIT_20",     "config.dynrebal.json",  True,  10000),
    ("05 3Layer_AGGR",           "Btc3LayerStrategy",            "L3_MODE",        "L3_AGGR_WIDE_GRID","config.3layer.json",    False, 10000),
    ("06 3Layer_AGGR_SHIELD",    "Btc3LayerStrategy",            "L3_MODE",        "L3_AGGR_WIDE_GRID","config.3layer.json",    True,  10000),
    ("07 Adaptive_AGGR",         "BtcAdaptiveStrategy",          "AD_MODE",        "ADAPT_AGGR_NOSTOP","config.adaptive.json",  False, 10000),
    ("08 Adaptive_AGGR_SHIELD",  "BtcAdaptiveStrategy",          "AD_MODE",        "ADAPT_AGGR_NOSTOP","config.adaptive.json",  True,  10000),
    ("09 PURE_Shield_RS_AGGR",   "BtcRegimeShieldStrategy",      "RS_MODE",        "RS_AGGR",          "config.shield.json",    False, 10000),
    ("10 ETH_DynRebal_P20",      "BtcDynamicRebalanceStrategy",  "DR_MODE",        "DR_PROFIT_20",     "config.dynrebal-ETH.json", False, 1000),
    ("11 ETH_Shield_RS_AGGR",    "BtcRegimeShieldStrategy",      "RS_MODE",        "RS_AGGR",          "config.shield-ETH.json",   False, 1000),
    ("12 SOL_DynRebal_P20",      "BtcDynamicRebalanceStrategy",  "DR_MODE",        "DR_PROFIT_20",     "config.dynrebal-SOL.json", False, 500),
    ("13 SOL_Shield_RS_AGGR",    "BtcRegimeShieldStrategy",      "RS_MODE",        "RS_AGGR",          "config.shield-SOL.json",   False, 500),
]

YEARS = {
    "2021": "20210101-20220101",
    "2022": "20220101-20230101",
    "2023": "20230101-20240101",
    "2024": "20240101-20250101",
    "2025": "20250101-20260101",
    "2026Q12": "20260101-20260601",
}


def run(strategy, env_var, env_val, with_shield, cfg, tr, wallet):
    env = os.environ.copy()
    env[env_var] = env_val
    env["WITH_SHIELD"] = "true" if with_shield else "false"
    venv = str(REPO / ".venv" / "Scripts" / "freqtrade.exe")
    cmd = [
        venv, "backtesting", "--userdir", str(REPO / "user_data"),
        "--config", str(REPO / cfg), "--strategy", strategy,
        "--timerange", tr, "--dry-run-wallet", str(wallet), "--cache", "none",
    ]
    subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=REPO)
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        return None
    with zipfile.ZipFile(zips[-1]) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and "market_change" not in n]
        with z.open(names[0]) as f:
            payload = json.load(io.TextIOWrapper(f, encoding="utf-8"))
    sk = next(iter(payload.get("strategy", {})), None)
    if not sk: return None
    s = payload["strategy"][sk]
    final = float(s.get("final_balance", 0) or 0)
    return round((final - wallet) / wallet * 100, 1)


def main():
    rows = []
    total = len(COMBOS) * len(YEARS)
    n = 0
    for label, klass, env_var, env_val, cfg, shield, wallet in COMBOS:
        for year, tr in YEARS.items():
            n += 1
            print(f"  [{n}/{total}] {label} on {year}...", end=" ", flush=True)
            roi = run(klass, env_var, env_val, shield, cfg, tr, wallet)
            print(f"ROI={roi}%")
            rows.append({"variant": label, "year": year, "roi_%": roi, "wallet_$": wallet})

    df = pd.DataFrame(rows)
    piv = df.pivot(index="variant", columns="year", values="roi_%")
    print("\n" + "=" * 110)
    print("YEAR-BY-YEAR ROI %  — review BEFORE deploying anything")
    print("=" * 110)
    print(piv.to_string())

    stats = []
    wallet_map = {r["variant"]: r["wallet_$"] for r in rows}
    for v in piv.index:
        row = piv.loc[v].dropna()
        compound = 1.0
        for r in row: compound *= (1 + r / 100)
        annual = compound ** (1 / len(row)) - 1
        wallet = wallet_map[v]
        stats.append({
            "variant": v,
            "wallet_$": wallet,
            "compound_end_$": round(compound * wallet, 0),
            "annual_%": round(annual * 100, 1),
            "avg_per_year_%": round(row.mean(), 1),
            "best_yr_%": round(row.max(), 1),
            "worst_yr_%": round(row.min(), 1),
            "positive_yrs": int((row > 0).sum()),
        })
    print("\n=== SUMMARY (sorted by annual compound %) ===")
    stats_df = pd.DataFrame(stats).sort_values("annual_%", ascending=False).reset_index(drop=True)
    print(stats_df.to_string(index=False))

    out = REPO / "research" / "big_sweep_results.csv"
    df.to_csv(out, index=False)
    out2 = REPO / "research" / "big_sweep_summary.csv"
    stats_df.to_csv(out2, index=False)
    print(f"\nSaved: {out} / {out2}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
