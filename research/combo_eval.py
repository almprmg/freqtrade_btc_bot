"""Year-by-year test of BtcPairComboStrategy vs AI Shield + Pure Shield."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "ai"))
import json, os, subprocess, zipfile, io
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO / "user_data" / "backtest_results"

COMBOS = [
    ("Pair_Combo",  "BtcPairComboStrategy",    None,      None,        "config.combo.json"),
    ("AI_Shield",   "BtcAiShieldStrategy",     None,      None,        "config.ai_shield.json"),
    ("Pure_Shield", "BtcRegimeShieldStrategy", "RS_MODE", "RS_AGGR",   "config.shield.json"),
]
YEARS = {
    "2021": "20210101-20220101", "2022": "20220101-20230101",
    "2023": "20230101-20240101", "2024": "20240101-20250101",
    "2025": "20250101-20260101", "2026Q12": "20260101-20260601",
}


def run(strategy, env_var, env_val, cfg, tr, wallet=10000):
    env = os.environ.copy()
    if env_var: env[env_var] = env_val
    venv = str(REPO / ".venv" / "Scripts" / "freqtrade.exe")
    subprocess.run([
        venv, "backtesting", "--userdir", str(REPO / "user_data"),
        "--config", str(REPO / cfg), "--strategy", strategy,
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
        # Also archive via experiment_logger
        from experiment_logger import log_experiment
        log_experiment(strategy=strategy, mode=env_val or "default",
                       pair="BTC/USDT", timerange=tr, wallet=wallet,
                       zip_path=zips[-1], notes="combo eval")
        return round(roi, 1), round(dd, 1)
    except Exception:
        return None, None


def main():
    rows = []
    for label, klass, env_var, env_val, cfg in COMBOS:
        for year, tr in YEARS.items():
            print(f"  {label} on {year}...", end=" ", flush=True)
            roi, dd = run(klass, env_var, env_val, cfg, tr)
            print(f"ROI={roi}% DD={dd}%")
            rows.append({"variant": label, "year": year, "roi_%": roi, "max_dd_%": dd})
    df = pd.DataFrame(rows)
    piv = df.pivot(index="variant", columns="year", values="roi_%")
    piv_dd = df.pivot(index="variant", columns="year", values="max_dd_%")
    print("\n=== ROI year-by-year ===")
    print(piv.to_string())
    print("\n=== Max DD year-by-year ===")
    print(piv_dd.to_string())
    stats = []
    for v in piv.index:
        row = piv.loc[v].dropna()
        dds = piv_dd.loc[v].dropna()
        compound = 1.0
        for r in row: compound *= (1 + r / 100)
        annual = (compound ** (1 / max(len(row), 1)) - 1) * 100
        stats.append({"variant": v,
                      "compound_$10k": round(compound * 10000, 0),
                      "annual_%": round(annual, 1),
                      "best_yr_%": round(row.max(), 1),
                      "worst_yr_%": round(row.min(), 1),
                      "max_yearly_DD_%": round(dds.max(), 1),
                      "positive_yrs": int((row > 0).sum())})
    print("\n=== Summary ===")
    print(pd.DataFrame(stats).sort_values("annual_%", ascending=False).to_string(index=False))
    df.to_csv(REPO / "research" / "combo_results.csv", index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
