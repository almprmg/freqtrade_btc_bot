"""Test BtcMetaAdaptiveStrategy on LINK year-by-year — must cap yearly loss."""
from __future__ import annotations
import json, os, subprocess, sys, zipfile, io
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO / "user_data" / "backtest_results"
CFG = "config.meta-LINK.json"

MODES = ["MA_STRICT", "MA_BAL", "MA_RELAX", "MA_VSTRICT"]
YEARS = {
    "2021": "20210101-20220101", "2022": "20220101-20230101",
    "2023": "20230101-20240101", "2024": "20240101-20250101",
    "2025": "20250101-20260101", "2026Q12": "20260101-20260601",
}


def run(mode, tr, wallet=10000):
    env = os.environ.copy()
    env["MA_MODE"] = mode
    venv = str(REPO / ".venv" / "Scripts" / "freqtrade.exe")
    subprocess.run([
        venv, "backtesting", "--userdir", str(REPO / "user_data"),
        "--config", str(REPO / CFG), "--strategy", "BtcMetaAdaptiveStrategy",
        "--timerange", tr, "--dry-run-wallet", str(wallet), "--cache", "none",
    ], env=env, capture_output=True, text=True, cwd=REPO)
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips: return None, None
    try:
        with zipfile.ZipFile(zips[-1]) as z:
            names = [n for n in z.namelist() if n.endswith(".json") and "market_change" not in n]
            with z.open(names[0]) as f: payload = json.load(io.TextIOWrapper(f, encoding="utf-8"))
        sk = next(iter(payload.get("strategy", {})), None)
        if not sk: return None, None
        s = payload["strategy"][sk]
        final = float(s.get("final_balance", 0) or 0)
        roi = (final - wallet) / wallet * 100
        dd = float(s.get("max_drawdown_account", 0) or 0) * 100
        return round(roi, 1), round(dd, 1)
    except Exception:
        return None, None


def main():
    rows = []
    for mode in MODES:
        for year, tr in YEARS.items():
            print(f"  {mode} on {year}...", end=" ", flush=True)
            roi, dd = run(mode, tr)
            print(f"ROI={roi}% DD={dd}%")
            rows.append({"variant": mode, "year": year, "roi_%": roi, "max_dd_%": dd})
    df = pd.DataFrame(rows)
    piv_roi = df.pivot(index="variant", columns="year", values="roi_%")
    piv_dd = df.pivot(index="variant", columns="year", values="max_dd_%")
    print("\n=== ROI year-by-year ===")
    print(piv_roi.to_string())
    print("\n=== Max DD year-by-year ===")
    print(piv_dd.to_string())
    stats = []
    for v in piv_roi.index:
        row = piv_roi.loc[v].dropna()
        dds = piv_dd.loc[v].dropna()
        compound = 1.0
        for r in row: compound *= (1 + r / 100)
        annual = compound ** (1 / max(len(row), 1)) - 1
        stats.append({
            "variant": v,
            "compound_$10k": round(compound * 10000, 0),
            "annual_%": round(annual * 100, 1),
            "best_yr_%": round(row.max(), 1),
            "worst_yr_%": round(row.min(), 1),
            "max_yearly_DD_%": round(dds.max(), 1),
            "positive_yrs": int((row > 0).sum()),
        })
    print("\n=== Summary ===")
    print(pd.DataFrame(stats).to_string(index=False))
    df.to_csv(REPO / "research" / "meta_link_results.csv", index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
