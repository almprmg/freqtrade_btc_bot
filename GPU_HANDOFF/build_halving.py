"""build_halving.py — Reconstruct halving_cycle.feather (deterministic).

The training script maps a `phase` string per day to an ordinal code. The
original file lives on the CPU machine; this regenerates it purely from the
known BTC halving dates + a days-since-halving phase model.

Phase model (days into the ~4yr cycle), tuned to the historical pattern of
post-halving accumulation -> bull -> blow-off top ~1.0-1.5yr later -> bear:

    0-150     REACCUMULATION
    150-400   ACCUMULATION
    400-550   EARLY_BULL
    550-730   PARABOLIC
    730-880   DISTRIBUTION
    880-1200  BEAR
    1200+     ACCUMULATION   (pre-halving recovery)

NOTE: This is a transparent reconstruction, not the exact CPU-machine labels.
It feeds the model an ordinal cycle-position feature; relabel ranges if the
production definition is recovered.

USAGE:  python GPU_HANDOFF/build_halving.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "user_data" / "data" / "halving_cycle.feather"
START = "2017-07-01"

HALVINGS = [
    pd.Timestamp("2012-11-28", tz="UTC"),
    pd.Timestamp("2016-07-09", tz="UTC"),
    pd.Timestamp("2020-05-11", tz="UTC"),
    pd.Timestamp("2024-04-20", tz="UTC"),
]


def phase_for(days: int) -> str:
    if days < 150:
        return "REACCUMULATION"
    if days < 400:
        return "ACCUMULATION"
    if days < 550:
        return "EARLY_BULL"
    if days < 730:
        return "PARABOLIC"
    if days < 880:
        return "DISTRIBUTION"
    if days < 1200:
        return "BEAR"
    return "ACCUMULATION"


def main():
    idx = pd.date_range(start=pd.Timestamp(START, tz="UTC"),
                        end=pd.Timestamp.utcnow().normalize(), freq="D", tz="UTC")
    phases = []
    for d in idx:
        prior = [h for h in HALVINGS if h <= d]
        last = prior[-1] if prior else HALVINGS[0]
        phases.append(phase_for((d - last).days))

    out = pd.DataFrame({"date": idx, "phase": phases})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_feather(OUT)
    print(f"Saved {len(out)} rows -> {OUT}")
    print(out["phase"].value_counts().to_string())


if __name__ == "__main__":
    main()
