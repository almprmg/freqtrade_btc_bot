"""Run a Freqtrade backtest AND auto-log the result to experiments/.

Use this instead of calling freqtrade directly when you want full archival.

Example:
  python research/ai/logged_backtest.py \
      --strategy BtcRotationStrategy --mode default \
      --config config.rotation.json \
      --pair "BTC/USDT" --timerange 20210101-20260101 \
      --wallet 10000

Sets env vars from --env-pairs key=val key=val (for strategy mode selection).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO / "user_data" / "backtest_results"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", required=True)
    p.add_argument("--config", required=True, help="config json filename in repo root")
    p.add_argument("--mode", default="default")
    p.add_argument("--pair", default="BTC/USDT", help="display pair label")
    p.add_argument("--timerange", required=True)
    p.add_argument("--wallet", type=float, default=10000)
    p.add_argument("--env", action="append", default=[],
                   help="extra env var KEY=VAL (e.g. --env DR_MODE=DR_PROFIT_20)")
    p.add_argument("--notes", default="")
    args = p.parse_args()

    env = os.environ.copy()
    for kv in args.env:
        k, v = kv.split("=", 1)
        env[k] = v
        print(f"  env {k}={v}")

    venv = str(REPO / ".venv" / "Scripts" / "freqtrade.exe")
    cmd = [
        venv, "backtesting",
        "--userdir", str(REPO / "user_data"),
        "--config", str(REPO / args.config),
        "--strategy", args.strategy,
        "--timerange", args.timerange,
        "--dry-run-wallet", str(args.wallet),
        "--cache", "none",
    ]
    print(f"\nRunning: {' '.join(cmd[1:])}")
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=REPO)
    if result.returncode != 0:
        print("STDERR:", result.stderr[-2000:])

    # Find latest zip
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        print("ERROR: no backtest result produced", file=sys.stderr)
        return 1
    latest = zips[-1]
    print(f"\nResult zip: {latest.name}")

    # Log to experiments
    sys.path.insert(0, str(Path(__file__).parent))
    from experiment_logger import log_experiment
    row = log_experiment(
        strategy=args.strategy, mode=args.mode, pair=args.pair,
        timerange=args.timerange, wallet=args.wallet,
        zip_path=latest, notes=args.notes,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
