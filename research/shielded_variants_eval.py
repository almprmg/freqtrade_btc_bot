"""Compare WITH_SHIELD=true vs WITH_SHIELD=false for the top 2 strategies."""
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

# (display_name, strategy_class, env_var, env_val, config)
COMBOS = [
    ("Rebalance_R5",         "BtcRebalanceStrategy",        "REBALANCE_MODE", "R5_75_BTC",    "config.rebalance.json", False),
    ("Rebalance_R5_SHIELD",  "BtcRebalanceStrategy",        "REBALANCE_MODE", "R5_75_BTC",    "config.rebalance.json", True),
    ("DynRebal_P20",         "BtcDynamicRebalanceStrategy", "DR_MODE",        "DR_PROFIT_20", "config.dynrebal.json",  False),
    ("DynRebal_P20_SHIELD",  "BtcDynamicRebalanceStrategy", "DR_MODE",        "DR_PROFIT_20", "config.dynrebal.json",  True),
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
    print("Testing 4 combos x 6 years = 24 backtests...")
    rows = []
    for label, klass, env_var, env_val, cfg, shield in COMBOS:
        for year, tr in YEARS.items():
            print(f"  {label} on {year}...", end=" ", flush=True)
            roi = run(klass, env_var, env_val, shield, cfg, tr, 10000)
            print(f"ROI={roi}%")
            rows.append({"variant": label, "year": year, "roi_%": roi})

    df = pd.DataFrame(rows)
    piv = df.pivot(index="variant", columns="year", values="roi_%")
    print("\n" + "=" * 95)
    print("SHIELDED vs UNSHIELDED — YEAR-BY-YEAR ROI")
    print("=" * 95)
    print(piv.to_string())

    stats = []
    for v in piv.index:
        row = piv.loc[v].dropna()
        # Compound growth
        compound = 1.0
        for r in row: compound *= (1 + r / 100)
        annual = compound ** (1 / len(row)) - 1
        stats.append({
            "variant": v,
            "avg_per_year": round(row.mean(), 1),
            "compound_$10k": round(compound * 10000, 0),
            "annual_compound_%": round(annual * 100, 1),
            "best_year": round(row.max(), 1),
            "worst_year": round(row.min(), 1),
            "positive_yrs": int((row > 0).sum()),
        })
    print("\n=== Stats ===")
    print(pd.DataFrame(stats).to_string(index=False))

    out = REPO / "research" / "shielded_variants.csv"
    df.to_csv(out, index=False)
    print(f"\nSaved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
