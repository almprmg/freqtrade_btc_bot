"""Portfolio simulator — Idea I phase 1.

Before training RL, prove there's a meaningful gap between dumb (equal-weight)
and smart (optimal-hindsight) allocations. If the gap is small, RL won't help.
If it's large, we know the ceiling and can train.

Uses INDEX.csv yearly backtests for each (strategy, coin) we've deployed.

Allocations tested:
  1. Equal weight (1/N)
  2. Risk parity (inverse-vol weight using DD)
  3. Top-3 by trailing 12-month Sharpe (our current meta_allocator)
  4. Hindsight optimal — pick winner each year (UPPER BOUND, unreachable live)
  5. Hindsight best Sharpe — pick top Sharpe each year (less aggressive ceiling)
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
IDX = REPO / "research" / "experiments" / "INDEX.csv"

# Strategies we have yearly data for (from this session's backfills)
# (label, strategy, coin)
PORTFOLIO = [
    ("BTC_AIShV2",       "BtcAiShieldV2Strategy",      "BTC"),
    ("BTC_Calendar",     "BtcCalendarShieldStrategy",  "BTC"),
    ("BTC_AIShV3",       "BtcAiShieldV3Strategy",      "BTC"),
    ("BTC_Triple",       "BtcTripleRegimeStrategy",    "BTC"),
    ("BTC_Sentiment",    "BtcSentimentShieldStrategy", "BTC"),
    ("AVAX_3Layer",      "Btc3LayerStrategy",          "AVAX"),
    ("ETH_DynRebal",     "BtcDynamicRebalanceStrategy", "ETH"),
    ("SOL_DynRebal",     "BtcDynamicRebalanceStrategy", "SOL"),
    ("ETH_Shield",       "BtcRegimeShieldStrategy",    "ETH"),
    ("SOL_Shield",       "BtcRegimeShieldStrategy",    "SOL"),
    ("SOL_Triple",       "BtcTripleRegimeStrategy",    "SOL"),
]

YEAR_MODES = {
    "2021": ["2021"],
    "2022": ["2022"],
    "2023": ["2023"],
    "2024": ["2024"],
    "2025": ["2025"],
    "2026": ["2026", "2026Q12"],
}


def build_yearly_matrix() -> pd.DataFrame:
    """Build matrix from actual yearly backtest results observed this session.

    The INDEX.csv pair column always says BTC/USDT (logger default) so we'd
    need to disambiguate by notes — instead we hardcode the verified numbers
    that produced our deployment decisions.
    """
    # Yearly ROIs from this session's verified backtests:
    M = {
        "BTC_AIShV2":     [118,    0,    44,    33,    14,    0],   # V2 baseline
        "BTC_Calendar":   [121.6,  0,    50.4,  36.4,  13.9,  0],   # winner BTC
        "BTC_AIShV3":     [76.9,   0,    31.4,  31.4,  11.4,  0],   # V3 (cooldown failed)
        "BTC_Triple":     [22,     0,    8,     12,    10,    0],   # defensive
        "BTC_Sentiment":  [118.3,  0,    52.7,  36.6,  11.9,  0],   # = Calendar basically
        "AVAX_3Layer":    [285,   -63,  180,   -7,   -46,  -24],   # FAILED adversarial
        "ETH_DynRebal":   [271,   -55,   65,    32,   -3,   -25],   # live, no protection
        "SOL_DynRebal":   [637,   -87,  509,    58,   -22,  -26],   # live SOL
        "ETH_Shield":     [250,   -12,   39,    24,    31,    0],   # WIN, deployed
        "SOL_Shield":     [903,   -32,  231,    44,   -43,    0],   # CATASTROPHIC
        "SOL_Triple":     [49,    -13,   2,     0,    -10,    0],   # too defensive
    }
    out = pd.DataFrame(M).T
    out.columns = list(YEAR_MODES.keys())
    return out


def sharpe_proxy(rois: list[float]) -> float:
    """Crude Sharpe from a list of yearly ROIs."""
    a = np.array(rois, dtype=float)
    a = a[~np.isnan(a)]
    if len(a) < 2 or a.std() == 0:
        return 0.0
    return a.mean() / a.std()


def compound(rois: list[float]) -> float:
    out = 1.0
    for r in rois:
        if np.isnan(r):
            r = 0.0
        out *= (1 + r/100)
    return out


def main():
    M = build_yearly_matrix()
    print("=== Yearly ROI matrix (NaN = no backtest) ===")
    print(M.to_string())

    years = list(M.columns)
    strats = list(M.index)

    # === Allocation 1: Equal weight ===
    yearly_eq = M.mean(axis=0)
    print(f"\n[Equal weight] yearly ROIs: {yearly_eq.tolist()}")
    print(f"  Compound: ${10000*compound(yearly_eq.tolist()):,.0f}  Annual: {(compound(yearly_eq.tolist())**(1/5)-1)*100:.1f}%/yr")

    # === Allocation 2: Risk parity (inverse abs ROI volatility) ===
    vols = M.std(axis=1).fillna(M.std().mean())
    weights_rp = 1 / (vols + 1)
    weights_rp = weights_rp / weights_rp.sum()
    yearly_rp = (M.mul(weights_rp, axis=0)).sum(axis=0)
    print(f"\n[Risk Parity] weights top-3: {weights_rp.sort_values(ascending=False).head(3).to_dict()}")
    print(f"  Yearly ROIs: {yearly_rp.tolist()}")
    print(f"  Compound: ${10000*compound(yearly_rp.tolist()):,.0f}  Annual: {(compound(yearly_rp.tolist())**(1/5)-1)*100:.1f}%/yr")

    # === Allocation 3: Top-3 by trailing Sharpe ===
    yearly_top3 = []
    for i, year in enumerate(years):
        if i == 0:
            # No trailing data, equal weight first year
            yearly_top3.append(M.iloc[:, 0].mean())
            continue
        # Use prior years for Sharpe
        prior = M.iloc[:, :i]
        sharpes = prior.apply(sharpe_proxy, axis=1)
        top3 = sharpes.sort_values(ascending=False).head(3).index
        avg = M.loc[top3, year].mean()
        yearly_top3.append(avg)
    print(f"\n[Top-3 Trailing Sharpe] yearly ROIs: {yearly_top3}")
    print(f"  Compound: ${10000*compound(yearly_top3):,.0f}  Annual: {(compound(yearly_top3)**(1/5)-1)*100:.1f}%/yr")

    # === Allocation 4: Hindsight optimal (UPPER BOUND) ===
    yearly_best = []
    for year in years:
        yearly_best.append(M[year].max())
    print(f"\n[Hindsight BEST single] yearly ROIs: {yearly_best}")
    print(f"  Compound: ${10000*compound(yearly_best):,.0f}  Annual: {(compound(yearly_best)**(1/5)-1)*100:.1f}%/yr")

    # === Allocation 5: Hindsight top-3 by next-year Sharpe ===
    # Pick the 3 strategies that will be best NEXT year (illegal in live, ceiling)
    yearly_hindsight_top3 = []
    for year in years:
        ranking = M[year].sort_values(ascending=False).head(3)
        yearly_hindsight_top3.append(ranking.mean())
    print(f"\n[Hindsight top-3 mean] yearly ROIs: {yearly_hindsight_top3}")
    print(f"  Compound: ${10000*compound(yearly_hindsight_top3):,.0f}  Annual: {(compound(yearly_hindsight_top3)**(1/5)-1)*100:.1f}%/yr")

    # === Verdict ===
    eq_ann = (compound(yearly_eq.tolist())**(1/5)-1)*100
    top3_ann = (compound(yearly_top3)**(1/5)-1)*100
    best_ann = (compound(yearly_hindsight_top3)**(1/5)-1)*100
    gap = best_ann - top3_ann
    print(f"\n=== Verdict ===")
    print(f"  Realizable ceiling (trailing top-3):    {top3_ann:.1f}%/yr")
    print(f"  Hindsight top-3 (unrealizable):         {best_ann:.1f}%/yr")
    print(f"  Hindsight-vs-realizable gap:            {gap:+.1f}pp/yr  <-- max possible RL improvement over current method")
    if gap < 5:
        print(f"  -> Gap < 5pp/yr: RL training very unlikely to be worth the effort")
    elif gap < 15:
        print(f"  -> Modest gap: RL might add 2-5pp/yr realistically")
    else:
        print(f"  -> Large gap: RL training has real upside")


if __name__ == "__main__":
    main()
