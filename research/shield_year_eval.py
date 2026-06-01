"""Test BtcRegimeShieldStrategy year-by-year. The critical test is 2022 —
if the shield can turn -47% into something near 0%, this design wins.
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

MODES = ["RS_FAST", "RS_MED", "RS_SLOW", "RS_AGGR", "RS_DEFENSIVE"]
YEARS = {
    "2021": "20210101-20220101",
    "2022": "20220101-20230101",
    "2023": "20230101-20240101",
    "2024": "20240101-20250101",
    "2025": "20250101-20260101",
    "2026Q12": "20260101-20260601",
}


def run(mode, timerange, wallet):
    env = os.environ.copy()
    env["RS_MODE"] = mode
    venv = str(REPO / ".venv" / "Scripts" / "freqtrade.exe")
    cmd = [
        venv, "backtesting", "--userdir", str(REPO / "user_data"),
        "--config", str(REPO / "config.shield.json"),
        "--strategy", "BtcRegimeShieldStrategy",
        "--timerange", timerange, "--dry-run-wallet", str(wallet),
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
    sk = next(iter(payload.get("strategy", {})), None)
    if not sk:
        return None
    s = payload["strategy"][sk]
    final = float(s.get("final_balance", 0) or 0)
    return round((final - wallet) / wallet * 100, 1)


def main():
    print("Testing Shield (5 modes x 6 years = 30 backtests)...")
    rows = []
    for mode in MODES:
        for year, tr in YEARS.items():
            print(f"  {mode} on {year}...", end=" ", flush=True)
            roi = run(mode, tr, 10000)
            print(f"ROI={roi}%")
            rows.append({"mode": mode, "year": year, "roi_%": roi})

    df = pd.DataFrame(rows)
    piv = df.pivot(index="mode", columns="year", values="roi_%")
    print("\n" + "=" * 95)
    print("SHIELD YEAR-BY-YEAR ROI %")
    print("=" * 95)
    print(piv.to_string())

    # Add benchmarks from per_year_results.csv if available
    pyr = REPO / "research" / "per_year_results.csv"
    if pyr.exists():
        bench = pd.read_csv(pyr)
        bench_piv = bench.pivot(index="strategy", columns="year", values="roi_%")
        print("\n=== BENCHMARK (existing strategies) ===")
        print(bench_piv.to_string())

    stats = []
    for mode in piv.index:
        row = piv.loc[mode].dropna()
        positive = int((row > 0).sum())
        stats.append({
            "mode": mode,
            "avg_per_year": round(row.mean(), 1),
            "best_year": round(row.max(), 1),
            "worst_year": round(row.min(), 1),
            "positive_years": f"{positive}/{len(row)}",
        })
    print("\n=== Shield modes stats ===")
    print(pd.DataFrame(stats).to_string(index=False))

    out = REPO / "research" / "shield_year_results.csv"
    df.to_csv(out, index=False)
    print(f"\nSaved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
