"""Adversarial Validator — gate for new strategies.

Runs a strategy on the THREE worst regime windows for long-only spot:
  - 2022 full year (BTC -65%, the FTX/Luna bear)
  - 2025 full year (BTC -6% but volatile, with -33% mid-year correction)
  - 2026-Q12 (current ongoing bear from $124K to $73K)

Verdict:
  PASS  — annual loss <= 5% in EACH adversarial window AND max yearly DD <= 25%
  WARN  — any single window losing 5-15% OR max DD 25-35%
  FAIL  — any window losing >15% OR max DD >35%
  CATASTROPHIC — any window losing >30%

This is meant to be a CI gate: any new strategy candidate MUST run this
before being approved for deployment. The framework also writes a
verdict file per candidate at research/adversarial/<strategy>__<mode>.json.

Usage:
  python research/ai/adversarial_validator.py \
      --strategy BtcTripleRegimeStrategy \
      --config config.triple.json \
      --env TR_MODE=TR_BAL

Also auto-tests Pure Shield + AI Shield as baseline reference each run.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import zipfile
import io
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO / "user_data" / "backtest_results"
OUT_DIR = REPO / "research" / "adversarial"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ADVERSARIAL_WINDOWS = {
    "BEAR_2022":     "20220101-20230101",
    "SIDEWAYS_2025": "20250101-20260101",
    "BEAR_2026Q12":  "20260101-20260601",
}

REFERENCE_STRATS = [
    ("Pure_Shield",  "BtcRegimeShieldStrategy", "config.shield.json", [("RS_MODE", "RS_AGGR")]),
    ("AI_Shield",    "BtcAiShieldStrategy",     "config.ai_shield.json", []),
]


def run_backtest(strategy, config, env_pairs, timerange, wallet=10000):
    env = os.environ.copy()
    for k, v in env_pairs:
        env[k] = v
    venv = str(REPO / ".venv" / "Scripts" / "freqtrade.exe")
    subprocess.run([
        venv, "backtesting", "--userdir", str(REPO / "user_data"),
        "--config", str(REPO / config), "--strategy", strategy,
        "--timerange", timerange, "--dry-run-wallet", str(wallet), "--cache", "none",
    ], env=env, capture_output=True, text=True, cwd=REPO)
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        return None, None, None
    try:
        with zipfile.ZipFile(zips[-1]) as z:
            names = [n for n in z.namelist() if n.endswith(".json") and "market_change" not in n]
            with z.open(names[0]) as f:
                payload = json.load(io.TextIOWrapper(f, encoding="utf-8"))
        sk = next(iter(payload.get("strategy", {})), None)
        if not sk:
            return None, None, None
        s = payload["strategy"][sk]
        final = float(s.get("final_balance", 0) or 0)
        roi = (final - wallet) / wallet * 100
        dd = float(s.get("max_drawdown_account", 0) or 0) * 100
        n_trades = int(s.get("total_trades", 0))
        return round(roi, 2), round(dd, 2), n_trades
    except Exception as e:
        print(f"  parse error: {e}", file=sys.stderr)
        return None, None, None


def verdict(window_results: dict) -> str:
    """Map per-window results to one of PASS/WARN/FAIL/CATASTROPHIC."""
    worst_roi = min(r["roi"] for r in window_results.values() if r["roi"] is not None)
    worst_dd = max(r["max_dd"] for r in window_results.values() if r["max_dd"] is not None)

    if worst_roi < -30:
        return "CATASTROPHIC"
    if worst_roi < -15 or worst_dd > 35:
        return "FAIL"
    if worst_roi < -5 or worst_dd > 25:
        return "WARN"
    return "PASS"


def evaluate_candidate(name, strategy, config, env_pairs):
    print(f"\n=== Evaluating: {name} ({strategy}) ===")
    results = {}
    for win_name, tr in ADVERSARIAL_WINDOWS.items():
        roi, dd, n = run_backtest(strategy, config, env_pairs, tr)
        results[win_name] = {"roi": roi, "max_dd": dd, "n_trades": n,
                              "timerange": tr}
        print(f"  {win_name:20s} ROI={roi}% DD={dd}% trades={n}")

    v = verdict(results)
    print(f"  >>> VERDICT: {v}")
    return {
        "candidate": name,
        "strategy": strategy,
        "env": dict(env_pairs),
        "windows": results,
        "verdict": v,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--env", action="append", default=[],
                   help="KEY=VAL env var (repeatable)")
    p.add_argument("--name", default=None)
    p.add_argument("--skip-baselines", action="store_true",
                   help="Don't re-run Pure Shield + AI Shield references")
    args = p.parse_args()

    env_pairs = []
    for e in args.env:
        k, v = e.split("=", 1)
        env_pairs.append((k, v))
    name = args.name or args.strategy + ("__" + "_".join(v for k, v in env_pairs)
                                          if env_pairs else "")

    all_results = []
    if not args.skip_baselines:
        for ref_name, ref_strat, ref_cfg, ref_env in REFERENCE_STRATS:
            ref_results = evaluate_candidate(ref_name, ref_strat, ref_cfg, ref_env)
            all_results.append(ref_results)
            out_file = OUT_DIR / f"{ref_name}.json"
            out_file.write_text(json.dumps(ref_results, indent=2, default=str))

    candidate = evaluate_candidate(name, args.strategy, args.config, env_pairs)
    all_results.append(candidate)
    out_file = OUT_DIR / f"{name}.json"
    out_file.write_text(json.dumps(candidate, indent=2, default=str))

    # Summary table
    print("\n" + "=" * 100)
    print("ADVERSARIAL SUMMARY")
    print("=" * 100)
    rows = []
    for r in all_results:
        row = {"candidate": r["candidate"]}
        for win in ADVERSARIAL_WINDOWS:
            row[f"{win}_ROI"] = r["windows"][win]["roi"]
            row[f"{win}_DD"] = r["windows"][win]["max_dd"]
        row["verdict"] = r["verdict"]
        rows.append(row)
    print(pd.DataFrame(rows).to_string(index=False))
    print()

    # Append to master CSV
    master = OUT_DIR / "MASTER.csv"
    df = pd.DataFrame(rows)
    if master.exists():
        old = pd.read_csv(master)
        df = pd.concat([old, df], ignore_index=True).drop_duplicates(subset=["candidate"], keep="last")
    df.to_csv(master, index=False)
    print(f"\nResults saved to: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
