"""Year-by-year eval of BtcOnChainStrategy (4 modes) vs Pure Shield."""
from __future__ import annotations
import json, os, subprocess, sys, zipfile, io
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO / "user_data" / "backtest_results"

COMBOS = [
    ("OC_BAL",        "BtcOnChainStrategy",       "OC_MODE", "OC_BAL",       "config.onchain.json"),
    ("OC_AGGR",       "BtcOnChainStrategy",       "OC_MODE", "OC_AGGR",      "config.onchain.json"),
    ("OC_TIGHT",      "BtcOnChainStrategy",       "OC_MODE", "OC_TIGHT",     "config.onchain.json"),
    ("OC_NOSHIELD",   "BtcOnChainStrategy",       "OC_MODE", "OC_NOSHIELD",  "config.onchain.json"),
    ("Pure_Shield",   "BtcRegimeShieldStrategy",  "RS_MODE", "RS_AGGR",      "config.shield.json"),
]
YEARS = {
    "2021": "20210101-20220101", "2022": "20220101-20230101",
    "2023": "20230101-20240101", "2024": "20240101-20250101",
    "2025": "20250101-20260101", "2026Q12": "20260101-20260601",
}


def run(strategy, env_var, env_val, cfg, tr, wallet=10000):
    env = os.environ.copy()
    env[env_var] = env_val
    venv = str(REPO / ".venv" / "Scripts" / "freqtrade.exe")
    subprocess.run([
        venv, "backtesting", "--userdir", str(REPO / "user_data"),
        "--config", str(REPO / cfg), "--strategy", strategy,
        "--timerange", tr, "--dry-run-wallet", str(wallet), "--cache", "none",
    ], env=env, capture_output=True, text=True, cwd=REPO)
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips: return None
    with zipfile.ZipFile(zips[-1]) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and "market_change" not in n]
        with z.open(names[0]) as f: payload = json.load(io.TextIOWrapper(f, encoding="utf-8"))
    sk = next(iter(payload.get("strategy", {})), None)
    if not sk: return None
    s = payload["strategy"][sk]
    final = float(s.get("final_balance", 0) or 0)
    return round((final - wallet) / wallet * 100, 1)


def main():
    print(f"Running {len(COMBOS)} variants x {len(YEARS)} years...")
    rows = []
    for label, klass, env_var, env_val, cfg in COMBOS:
        for year, tr in YEARS.items():
            print(f"  {label} on {year}...", end=" ", flush=True)
            roi = run(klass, env_var, env_val, cfg, tr)
            print(f"ROI={roi}%")
            rows.append({"variant": label, "year": year, "roi_%": roi})

    df = pd.DataFrame(rows)
    piv = df.pivot(index="variant", columns="year", values="roi_%")
    print("\n" + "=" * 95)
    print("ON-CHAIN STRATEGY year-by-year ROI %")
    print("=" * 95)
    print(piv.to_string())

    stats = []
    for v in piv.index:
        row = piv.loc[v].dropna()
        compound = 1.0
        for r in row: compound *= (1 + r / 100)
        annual = compound ** (1 / len(row)) - 1
        stats.append({
            "variant": v,
            "compound_$10k": round(compound * 10000, 0),
            "annual_%": round(annual * 100, 1),
            "avg_yr_%": round(row.mean(), 1),
            "best_yr_%": round(row.max(), 1),
            "worst_yr_%": round(row.min(), 1),
            "positive_yrs": int((row > 0).sum()),
        })
    print("\n=== Stats sorted by annual compound ===")
    stats_df = pd.DataFrame(stats).sort_values("annual_%", ascending=False).reset_index(drop=True)
    print(stats_df.to_string(index=False))

    out = REPO / "research" / "onchain_year_results.csv"
    df.to_csv(out, index=False)
    print(f"\nSaved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
