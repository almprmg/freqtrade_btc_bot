"""Halving Cycle Predictor — model BTC's 4-year cycle pattern.

Each Bitcoin halving (approx every 4 years) has historically been followed
by a multi-month bull run. Halving dates:
  H1: 2012-11-28
  H2: 2016-07-09
  H3: 2020-05-11
  H4: 2024-04-19 (most recent)
  H5: ~2028 (projected)

Cycle phases (days since most recent halving):
  Accumulation:    0-180   (post-halving consolidation)
  Early bull:    180-365   (initial rally)
  Parabolic:     365-540   (mania)
  Distribution:  540-700   (top + early correction)
  Bear:          700-900   (capitulation)
  Reaccumulation: 900-1460 (re-stacking pre-next-halving)

This module emits a "cycle_bias" -1.0 to +1.0:
  +1.0 = early-bull phase, MAX allocation
   0.0 = bear phase, AVOID
  -1.0 = distribution, EXIT signal

Save to user_data/data/halving_cycle.feather for strategies to consume.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "user_data" / "data" / "halving_cycle.feather"

HALVINGS = [
    pd.Timestamp("2012-11-28", tz="UTC"),
    pd.Timestamp("2016-07-09", tz="UTC"),
    pd.Timestamp("2020-05-11", tz="UTC"),
    pd.Timestamp("2024-04-19", tz="UTC"),
    pd.Timestamp("2028-04-01", tz="UTC"),  # projected
]


def days_since_last_halving(date: pd.Timestamp) -> int:
    last = max((h for h in HALVINGS if h <= date), default=HALVINGS[0])
    return int((date - last).days)


def cycle_phase(d: int) -> str:
    if d < 180: return "ACCUMULATION"
    if d < 365: return "EARLY_BULL"
    if d < 540: return "PARABOLIC"
    if d < 700: return "DISTRIBUTION"
    if d < 900: return "BEAR"
    return "REACCUMULATION"


def cycle_bias(d: int) -> float:
    """Smooth bias function based on cycle phase. -1.0 (sell) to +1.0 (max buy)."""
    # Peaks around day 365-540, valleys around day 700-900.
    # Use sinusoidal + biased shape.
    if d < 180:
        return 0.2  # accumulation: modest bull bias
    if d < 365:
        return 0.6 + 0.3 * (d - 180) / 185  # ramping up
    if d < 540:
        return 0.9 - 0.3 * (d - 365) / 175  # peak parabolic, starting to taper
    if d < 700:
        return 0.5 - 1.0 * (d - 540) / 160  # distribution, becoming negative
    if d < 900:
        return -0.5 + 0.5 * (d - 700) / 200  # bear, gradually recovering
    return -0.1 + 0.5 * min((d - 900) / 560, 1.0)  # reaccumulation


def main():
    print("=== Halving Cycle Predictor ===")
    print("Halving dates:")
    for h in HALVINGS:
        print(f"  {h.date()}")

    # Generate per-day cycle bias from 2019 to 2027
    dates = pd.date_range("2019-01-01", "2027-12-31", freq="D", tz="UTC")
    rows = []
    for d in dates:
        days = days_since_last_halving(d)
        phase = cycle_phase(days)
        bias = cycle_bias(days)
        rows.append({"date": d, "days_since_halving": days, "phase": phase, "cycle_bias": bias})

    df = pd.DataFrame(rows)
    df.to_feather(OUT)
    print(f"\nSaved: {OUT} ({len(df)} days)")

    # Quick stats
    today = pd.Timestamp.now(tz="UTC").normalize()
    sub = df[df["date"] <= today].iloc[-1]
    print(f"\n=== Current state (as of {today.date()}) ===")
    print(f"  days since H4 (2024-04-19): {sub['days_since_halving']}")
    print(f"  phase: {sub['phase']}")
    print(f"  bias: {sub['cycle_bias']:+.2f}")

    # Per-year summary
    df["year"] = df["date"].dt.year
    summary = df.groupby("year").agg(
        avg_bias=("cycle_bias", "mean"),
        min_bias=("cycle_bias", "min"),
        max_bias=("cycle_bias", "max"),
        dominant_phase=("phase", lambda s: s.value_counts().idxmax()),
    )
    print("\n=== Year-by-year cycle stats ===")
    print(summary.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
