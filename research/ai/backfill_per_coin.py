"""Backfill per-coin backtests via experiment_logger.

Goal: produce comparable yearly backtests for the strategies that are
deployed live but missing from the archive (ETH/SOL DynRebal), plus the
AVAX 3Layer A/B candidate.

This wraps freqtrade's `backtesting` CLI per (strategy, pair, timerange)
and logs each run via experiment_logger.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

YEARLY = [
    ("2021", "20210101-20220101"),
    ("2022", "20220101-20230101"),
    ("2023", "20230101-20240101"),
    ("2024", "20240101-20250101"),
    ("2025", "20250101-20260101"),
    ("2026Q12", "20260101-20260601"),
]
ADV = [
    ("ADV_BEAR2022", "20220101-20230101"),
    ("ADV_SIDE2025", "20250101-20260101"),
    ("ADV_BEAR26Q12", "20260101-20260601"),
]

# (label, config_relpath, strategy, pair)
RUNS = [
    ("ETH_DynRebal",  "config.dynrebal-ETH.json", "BtcDynamicRebalanceStrategy", "ETH/USDT"),
    ("SOL_DynRebal",  "config.dynrebal-SOL.json", "BtcDynamicRebalanceStrategy", "SOL/USDT"),
    ("AVAX_3Layer",   "config.AVAX.json",         "Btc3LayerStrategy",           "AVAX/USDT"),
    # Idea K — Shield port to ETH/SOL
    ("ETH_Shield",    "config.shield-ETH.json",   "BtcRegimeShieldStrategy",     "ETH/USDT"),
    ("SOL_Shield",    "config.shield-SOL.json",   "BtcRegimeShieldStrategy",     "SOL/USDT"),
]


def run_one(label: str, config: str, strategy: str, pair: str, mode: str, timerange: str):
    cmd = [
        sys.executable, "-m", "research.ai.logged_backtest",
        "--config", config,
        "--strategy", strategy,
        "--timerange", timerange,
        "--mode", mode,
        "--notes", f"Idea C backfill — {label}",
    ]
    print(f"\n>>> {label} {mode} {timerange}")
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if p.returncode != 0:
        print(f"  FAIL: {p.stderr[-400:]}")
        return None
    # Parse summary line
    for line in p.stdout.splitlines()[-25:]:
        if "ROI" in line or "Trades" in line or "Sharpe" in line:
            print(f"  {line.strip()}")
    return True


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    targets = [r for r in RUNS if not only or only.upper() in r[0].upper()]
    print(f"Targets: {[r[0] for r in targets]}")
    for label, config, strat, pair in targets:
        for tag, tr in YEARLY:
            run_one(label, config, strat, pair, tag, tr)
        for tag, tr in ADV:
            run_one(label, config, strat, pair, tag, tr)
    print("\nDone. See research/experiments/INDEX.csv for new rows.")


if __name__ == "__main__":
    main()
