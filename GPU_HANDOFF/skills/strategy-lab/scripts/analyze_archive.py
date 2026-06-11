"""analyze_archive.py — Run the per-asset audit + portfolio simulator.

Two analyses:

1. Per-asset audit: scan research/experiments/INDEX.csv + freqtrade native
   backtest zips. For each coin, rank strategies by robust score:
       robust = median_roi - 2*median_dd
   Flag if the live strategy is NOT in top-3.

2. Portfolio simulator: take yearly ROI matrix, compare allocators
   (equal-weight, top-3-trailing-Sharpe, hindsight). Output the
   realistic ceiling on RL-style improvements.

Usage:
  python -m strategy_lab.analyze_archive

Both analyses are READ-ONLY. Output goes to research/per_asset_audit_summary.md
and console.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path("d:/pythone/freqtrade_btc_bot")


def main():
    if not REPO.exists():
        print(f"ERROR: repo not found at {REPO}")
        return 1

    print("=== Running per-asset audit ===")
    p1 = subprocess.run(
        [sys.executable, "-m", "research.ai.per_asset_audit"],
        cwd=REPO, capture_output=True, text=True
    )
    print(p1.stdout[-2000:])
    if p1.returncode != 0:
        print(f"WARN: audit exited {p1.returncode}")
        print(p1.stderr[-500:])

    print("\n=== Running portfolio simulator ===")
    p2 = subprocess.run(
        [sys.executable, "-m", "research.ai.portfolio_simulator"],
        cwd=REPO, capture_output=True, text=True
    )
    print(p2.stdout[-2000:])
    if p2.returncode != 0:
        print(f"WARN: simulator exited {p2.returncode}")
        print(p2.stderr[-500:])

    print("\n=== Outputs ===")
    print(f"  {REPO}/research/per_asset_audit.csv")
    print(f"  {REPO}/research/per_asset_audit_summary.md")
    print("\nInterpret the audit BEFORE proposing new deployments.")
    print("Read the 'Honest finding' section — it tells you which comparisons are reliable.")


if __name__ == "__main__":
    sys.exit(main() or 0)
