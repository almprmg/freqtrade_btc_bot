"""Apply the 5-factor composite robustness score over walk-forward results.

Robustness Score (0-100) =
  0.25 * multi_regime_consistency  (% of periods with positive ROI)
+ 0.25 * low_drawdown_behavior     (1 - clamp(max_dd / 0.40))
+ 0.20 * stability_low_variance    (1 - clamp(std(annual)/mean(annual)))
+ 0.15 * out_of_sample_performance (clamp(avg(VAL,TEST) / TRAIN, 0, 1))
+ 0.15 * crash_survival            (proxy: 1 - max_dd_in_worst_period / 0.50)

A higher score = more robust. We then rank strategies by score, not by raw
backtest ROI, to avoid rewarding curve-fit performance.

Reads walk_forward_results.csv (written by walk_forward.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import numpy as np

REPO = Path(__file__).resolve().parents[1]


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, x)))


def score_one(rows: pd.DataFrame) -> dict:
    """rows = subset for ONE strategy across all periods (TRAIN, VAL, TEST)."""
    by_period = rows.set_index("period")
    train = by_period.loc["TRAIN"]
    val   = by_period.loc["VAL"]
    test  = by_period.loc["TEST"]

    # 1. multi_regime_consistency: % periods with positive ROI.
    positive_count = int((rows["roi_%"] > 0).sum())
    consistency = positive_count / len(rows)

    # 2. low_drawdown_behavior: 1 - clamp(max_dd / 0.40). DD given as % already.
    max_dd_pct = rows["max_dd_%"].abs().max() / 100.0
    low_dd = 1.0 - clamp(max_dd_pct / 0.40)

    # 3. stability: 1 - (std/mean) of annual returns. Negative mean kills it.
    ann = rows["annual_%"]
    if ann.mean() > 0:
        cv = ann.std() / ann.mean()
        stability = 1.0 - clamp(cv)
    else:
        stability = 0.0  # mean negative or zero = unstable

    # 4. OOS performance: avg(VAL, TEST) annual / TRAIN annual.
    train_ann = float(train["annual_%"])
    oos_ann = (float(val["annual_%"]) + float(test["annual_%"])) / 2.0
    if train_ann > 0:
        oos_score = clamp(oos_ann / train_ann)
    else:
        oos_score = 1.0 if oos_ann > 0 else 0.0

    # 5. crash_survival: 1 - max_dd_in_worst_period / 0.50.
    worst_dd = rows["max_dd_%"].abs().max() / 100.0
    crash = 1.0 - clamp(worst_dd / 0.50)

    score = (
        0.25 * consistency
        + 0.25 * low_dd
        + 0.20 * stability
        + 0.15 * oos_score
        + 0.15 * crash
    )
    return {
        "consistency": round(consistency, 3),
        "low_dd": round(low_dd, 3),
        "stability": round(stability, 3),
        "oos": round(oos_score, 3),
        "crash_survival": round(crash, 3),
        "score": round(score * 100, 1),
    }


def main() -> int:
    wf_path = REPO / "research" / "walk_forward_results.csv"
    if not wf_path.exists():
        print(f"missing {wf_path} — run walk_forward.py first", file=sys.stderr)
        return 1

    df = pd.read_csv(wf_path)
    rows = []
    for strat, sub in df.groupby("strategy"):
        s = score_one(sub)
        s["strategy"] = strat
        s["roi_train_%"] = float(sub.set_index("period").loc["TRAIN", "roi_%"])
        s["roi_val_%"]   = float(sub.set_index("period").loc["VAL", "roi_%"])
        s["roi_test_%"]  = float(sub.set_index("period").loc["TEST", "roi_%"])
        rows.append(s)

    out = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
    cols = ["strategy", "score", "consistency", "low_dd", "stability", "oos",
            "crash_survival", "roi_train_%", "roi_val_%", "roi_test_%"]
    out = out[cols]
    print("\n" + "=" * 110)
    print("ROBUSTNESS SCOREBOARD  (5-factor composite, 0-100)")
    print("=" * 110)
    print(out.to_string(index=False))

    save = REPO / "research" / "robustness_results.csv"
    out.to_csv(save, index=False)
    print(f"\nSaved: {save}")
    winner = out.iloc[0]
    print(f"\n>>> MOST ROBUST: {winner['strategy']} (score={winner['score']}/100)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
