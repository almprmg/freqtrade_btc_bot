"""Year-by-year backtest of BtcRotationStrategy vs Pure Shield."""
from __future__ import annotations
import json, os, subprocess, sys, zipfile, io
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO / "user_data" / "backtest_results"

COMBOS = [
    ("Rotation",    "BtcRotationStrategy",      None,      None,       "config.rotation.json"),
    ("Pure_Shield", "BtcRegimeShieldStrategy",  "RS_MODE", "RS_AGGR",  "config.shield.json"),
]
YEARS = {
    "2021": "20210101-20220101", "2022": "20220101-20230101",
    "2023": "20230101-20240101", "2024": "20240101-20250101",
    "2025": "20250101-20260101", "2026Q12": "20260101-20260601",
}


def run(strategy, env_var, env_val, cfg, tr, wallet=10000):
    env = os.environ.copy()
    if env_var:
        env[env_var] = env_val
    venv = str(REPO / ".venv" / "Scripts" / "freqtrade.exe")
    subprocess.run([
        venv, "backtesting", "--userdir", str(REPO / "user_data"),
        "--config", str(REPO / cfg), "--strategy", strategy,
        "--timerange", tr, "--dry-run-wallet", str(wallet), "--cache", "none",
    ], env=env, capture_output=True, text=True, cwd=REPO)
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips: return None, None, None
    try:
        with zipfile.ZipFile(zips[-1]) as z:
            names = [n for n in z.namelist() if n.endswith(".json") and "market_change" not in n]
            with z.open(names[0]) as f: payload = json.load(io.TextIOWrapper(f, encoding="utf-8"))
        sk = next(iter(payload.get("strategy", {})), None)
        if not sk: return None, None, None
        s = payload["strategy"][sk]
        final = float(s.get("final_balance", 0) or 0)
        roi = (final - wallet) / wallet * 100
        dd = float(s.get("max_drawdown_account", 0) or 0) * 100
        trades = int(s.get("total_trades", 0))
        return round(roi, 1), round(dd, 1), trades
    except Exception:
        return None, None, None


def main():
    rows = []
    for label, klass, env_var, env_val, cfg in COMBOS:
        for year, tr in YEARS.items():
            print(f"  {label} on {year}...", end=" ", flush=True)
            roi, dd, n = run(klass, env_var, env_val, cfg, tr)
            print(f"ROI={roi}% DD={dd}% trades={n}")
            rows.append({"variant": label, "year": year, "roi_%": roi, "max_dd_%": dd, "trades": n})
    df = pd.DataFrame(rows)
    piv_roi = df.pivot(index="variant", columns="year", values="roi_%")
    piv_dd = df.pivot(index="variant", columns="year", values="max_dd_%")
    piv_tr = df.pivot(index="variant", columns="year", values="trades")

    print("\n=== ROI year-by-year ===")
    print(piv_roi.to_string())
    print("\n=== Max DD year-by-year ===")
    print(piv_dd.to_string())
    print("\n=== Trades year-by-year ===")
    print(piv_tr.to_string())

    stats = []
    for v in piv_roi.index:
        row = piv_roi.loc[v].dropna()
        dds = piv_dd.loc[v].dropna()
        compound = 1.0
        for r in row: compound *= (1 + r / 100)
        annual = (compound ** (1 / max(len(row), 1)) - 1) * 100
        stats.append({
            "variant": v,
            "compound_$10k": round(compound * 10000, 0),
            "annual_%": round(annual, 1),
            "best_yr_%": round(row.max(), 1),
            "worst_yr_%": round(row.min(), 1),
            "max_yearly_DD_%": round(dds.max(), 1),
        })
    print("\n=== Summary ===")
    print(pd.DataFrame(stats).to_string(index=False))
    df.to_csv(REPO / "research" / "rotation_results.csv", index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
