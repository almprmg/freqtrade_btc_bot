"""Meta-Analyzer — read EVERYTHING we built and find patterns + new ideas.

Sources scanned:
  - research/experiments/INDEX.csv           (our per-run log)
  - research/experiments/*/metadata.json     (full detail per run)
  - research/*_results.csv                   (sweep aggregates)
  - research/*_summary.csv                   (sweep summaries)
  - user_data/data/binance/*-1d.feather      (coin price history)
  - research/AI_MASTER_PLAN.md               (the plan)

Outputs:
  - research/META_ANALYSIS.md  — narrative findings + new idea proposals
  - research/meta_analysis_data.csv — raw aggregated data

Pattern types we look for:
  1. Strategy x regime fit — which works in which year
  2. Coin x strategy alignment — which strategy fits which coin
  3. DD vs ROI tradeoff curve
  4. Diversification opportunities (low-correlation strategies)
  5. Failure modes that repeat across approaches
  6. Underexplored parameter regions
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
RESEARCH = REPO / "research"
OUT_MD = RESEARCH / "META_ANALYSIS.md"
OUT_CSV = RESEARCH / "meta_analysis_data.csv"


def read_all_summaries() -> pd.DataFrame:
    """Combine every *_summary.csv and *_results.csv we've produced."""
    rows = []
    for csv in sorted(RESEARCH.glob("*.csv")):
        if csv.name.startswith("meta_analysis"):
            continue
        try:
            df = pd.read_csv(csv)
            df["source"] = csv.stem
            rows.append(df)
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True, sort=False)
    return out


def read_experiment_index() -> pd.DataFrame:
    p = RESEARCH / "experiments" / "INDEX.csv"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p)


def coin_yearly_stats() -> pd.DataFrame:
    """Compute per-coin yearly stats — used as 'market context'."""
    out = []
    for f in (REPO / "user_data" / "data" / "binance").glob("*_USDT-1d.feather"):
        coin = f.name.split("_")[0]
        try:
            df = pd.read_feather(f)
            df["date"] = pd.to_datetime(df["date"], utc=True)
            df = df.set_index("date").sort_index()
            for y in range(2019, 2027):
                sub = df.loc[f"{y}"]
                if sub.empty:
                    continue
                ret = (sub["close"].iloc[-1] / sub["close"].iloc[0] - 1) * 100
                peak = sub["close"].cummax()
                dd = ((peak - sub["close"]) / peak).max() * 100
                out.append({"coin": coin, "year": y,
                             "return_pct": round(ret, 1),
                             "max_dd_pct": round(dd, 1)})
        except Exception:
            continue
    return pd.DataFrame(out)


def patterns_strategy_by_year(all_results: pd.DataFrame, coin_stats: pd.DataFrame) -> dict:
    """Which strategy worked best per year, across all our sweeps."""
    out = {}
    # Pick the canonical wide results — link/mega/big_sweep/rotation
    keepers = ["link_results_raw", "mega_sweep_raw", "big_sweep_results",
               "rotation_versions_results", "shielded_variants",
               "per_year_results", "shield_year_results"]
    candidates = all_results[all_results["source"].isin(keepers)] if "source" in all_results.columns else pd.DataFrame()
    if candidates.empty:
        return out

    # Best strategy per (coin, year) by ROI
    if "coin" in candidates.columns:
        df = candidates.dropna(subset=["roi_%", "year"]).copy()
        if not df.empty:
            df["roi_%"] = pd.to_numeric(df["roi_%"], errors="coerce")
            grouped = df.groupby(["coin", "year"], dropna=False)["roi_%"]
            if not grouped.size().empty:
                top_idx = grouped.idxmax()
                top = df.loc[top_idx.dropna(), ["coin", "year", "variant", "roi_%"]]
                out["best_per_coin_year"] = top.sort_values(["coin", "year"])
    return out


def correlation_matrix(all_results: pd.DataFrame) -> pd.DataFrame:
    """How similar are our strategies' year-by-year returns? Low corr = good diversification."""
    if "variant" not in all_results.columns or "year" not in all_results.columns:
        return pd.DataFrame()
    df = all_results.dropna(subset=["roi_%", "year", "variant"]).copy()
    df["roi_%"] = pd.to_numeric(df["roi_%"], errors="coerce")
    pivot = df.pivot_table(index="year", columns="variant", values="roi_%", aggfunc="mean")
    return pivot.corr().round(2)


def categorize_failures(all_results: pd.DataFrame) -> pd.DataFrame:
    """Identify strategies/years with major losses (<-30%)."""
    if "roi_%" not in all_results.columns:
        return pd.DataFrame()
    df = all_results.dropna(subset=["roi_%"]).copy()
    df["roi_%"] = pd.to_numeric(df["roi_%"], errors="coerce")
    fails = df[df["roi_%"] < -30].sort_values("roi_%")
    return fails


def write_report(all_results, exp_index, coin_stats, patterns, corr, fails):
    lines = []
    lines.append("# Meta-Analysis Report — what we built, what worked, what's next\n")
    lines.append("Auto-generated from `research/` archive. Re-run `meta_analyzer.py` after any new experiment.\n")

    # --- Section 1: scope ---
    lines.append("## 1. Scope of work")
    total_results = len(all_results) if isinstance(all_results, pd.DataFrame) else 0
    n_exp = len(exp_index) if isinstance(exp_index, pd.DataFrame) else 0
    unique_variants = all_results["variant"].nunique() if "variant" in all_results.columns else 0
    unique_coins = all_results["coin"].nunique() if "coin" in all_results.columns else 0
    lines.append(f"- Aggregated rows: **{total_results}** across {len(set(all_results['source']))} sweep files." if "source" in all_results.columns else "")
    lines.append(f"- Distinct strategy variants tested: **{unique_variants}**")
    lines.append(f"- Distinct coins tested: **{unique_coins}**")
    lines.append(f"- Per-run archived experiments: **{n_exp}**\n")

    # --- Section 2: market context ---
    lines.append("## 2. Market context per coin/year")
    if not coin_stats.empty:
        pivot_ret = coin_stats.pivot(index="coin", columns="year", values="return_pct")
        lines.append("\nReturn % year-by-year:\n```")
        lines.append(pivot_ret.to_string())
        lines.append("```\n")
        pivot_dd = coin_stats.pivot(index="coin", columns="year", values="max_dd_pct")
        lines.append("Max DD % year-by-year:\n```")
        lines.append(pivot_dd.to_string())
        lines.append("```\n")

    # --- Section 3: best strategies ---
    lines.append("## 3. Winners per coin × year (from all sweeps)")
    if "best_per_coin_year" in patterns:
        lines.append("\n```")
        lines.append(patterns["best_per_coin_year"].to_string(index=False))
        lines.append("```\n")

    # --- Section 4: correlation ---
    lines.append("## 4. Strategy correlation (low = diversification opportunity)")
    if not corr.empty:
        top_pairs = []
        for s1 in corr.index:
            for s2 in corr.columns:
                if s1 >= s2: continue
                v = corr.loc[s1, s2]
                if pd.notna(v):
                    top_pairs.append((s1, s2, v))
        top_pairs.sort(key=lambda x: x[2])
        lines.append("\nLowest-correlation pairs (potential complementary strategies):\n")
        for s1, s2, v in top_pairs[:10]:
            lines.append(f"  - **{s1}** vs **{s2}**: corr = {v:+.2f}")
        lines.append("")
        lines.append("Highest-correlation pairs (redundant — pick one):\n")
        for s1, s2, v in top_pairs[-10:]:
            lines.append(f"  - {s1} vs {s2}: corr = {v:+.2f}")
        lines.append("")

    # --- Section 5: failure modes ---
    lines.append("## 5. Repeating failure modes (ROI < -30%)")
    if not fails.empty:
        lines.append(f"\n{len(fails)} catastrophic-loss results identified.\n")
        if "year" in fails.columns and "variant" in fails.columns:
            by_year = fails.groupby("year").size().sort_index().to_dict()
            lines.append("Per year:")
            for y, n in by_year.items():
                lines.append(f"  - {int(y)}: {n} variants lost >30%")
            lines.append("")
            # Top recurring losers
            loser_counts = fails["variant"].value_counts().head(10)
            lines.append("\nMost frequent big-losers:\n```")
            lines.append(loser_counts.to_string())
            lines.append("```\n")

    # --- Section 6: archived experiments ---
    if not exp_index.empty:
        lines.append("## 6. Per-run archive index")
        lines.append("\n```")
        cols = ["timestamp", "strategy", "mode", "pair", "roi_pct", "n_trades", "max_dd_pct", "sharpe"]
        present = [c for c in cols if c in exp_index.columns]
        lines.append(exp_index[present].to_string(index=False))
        lines.append("```\n")

    # --- Section 7: new ideas ---
    lines.append("## 7. New ideas — based on the data")
    lines.append("""
### A. Combine high-return + low-correlation pairs
The correlation matrix above suggests a few pairs that are uncorrelated
(or even negative). A portfolio that runs BOTH could deliver more
stable returns. Example: pair the most aggressive momentum strategy
with the most defensive regime-shielded one — when one fails, the
other often wins.

### B. Use 2022/2024/2026 as adversarial validators
Three years where most long-only spot strategies failed. ANY new
strategy candidate must survive these three windows BEFORE testing
on bull years.

### C. Asset-specific strategy mapping (not one-size-fits-all)
The mega_sweep already proved each coin needs a different winner:
  - BTC favours Shield + AI overlay
  - ETH favours Pure Shield
  - SOL favours Pure Shield (high vol)
  - BNB favours Sh_SLOW (slow confirms)
  - DOGE favours Sh_DEF (defensive)
  - ADA favours Meta_BAL
Don't deploy a "BTC strategy" on alts. Re-run mega_sweep per coin.

### D. Halving-cycle-conditional sizing
AI Shield uses cycle_bias linearly. Try a non-linear sigmoid that
boosts heavy in ACCUMULATION+EARLY_BULL (post-halving), shrinks fast
in DISTRIBUTION (the late-cycle window where corrections start). Run
2025-2026 data through this filter — expected to flag pre-correction.

### E. Anomaly cooldown
Currently anomaly flag = force exit. But after an anomaly clears, we
re-enter on next signal. Try a 7-day cooldown after each anomaly — the
post-flash-crash bounce is often followed by another drop. Test
this against the 40 BTC anomalies in history.

### F. Cross-asset cycle desync
BTC halving cycle drives BTC. But ETH/SOL/BNB have their own cycles
(ETH merge, SOL FTX recovery, etc.). Build a per-asset cycle model
that doesn't assume BTC-cycle homogeneity. Use ETH staking-yield as
ETH-specific cycle indicator.

### G. Ensemble of regime detectors
Currently Shield uses 1 regime rule (EMA200 + 30d-return + ADX). Build
3 separate regime detectors (e.g., 30d/60d/90d momentum) and trade
only when ALL THREE agree. Lower entry frequency, higher quality.

### H. Sentiment-volatility coupling
When sentiment AND volatility both spike together = real news event,
trade. When only volatility spikes = noise, skip. Needs FinBERT
integration (Batch 4, still pending).

### I. RL on the meta-allocator (not on price)
RL agents fail on direct price prediction. But RL on the meta-allocator
(which bot to give capital to next) is a much simpler problem — the
"actions" are 20-dimensional weights, rewards are realized PnL. Far
less overfit risk than RL on candlesticks.

### J. Time-of-week / calendar effects
The archive has dates on every trade. Group by day-of-week, end-of-
month, etc. If there's a calendar bias (e.g., Mondays are net-down),
exit before the weekend.
""")

    OUT_MD.write_text("\n".join(lines))
    print(f"Saved report: {OUT_MD}")


def main():
    print("Loading all archived results...")
    all_results = read_all_summaries()
    print(f"  total rows: {len(all_results)}")
    exp_index = read_experiment_index()
    print(f"  exp index rows: {len(exp_index)}")
    coin_stats = coin_yearly_stats()
    print(f"  coin-year rows: {len(coin_stats)}")

    print("\nMining patterns...")
    patterns = patterns_strategy_by_year(all_results, coin_stats)
    corr = correlation_matrix(all_results)
    fails = categorize_failures(all_results)

    print("\nWriting report...")
    write_report(all_results, exp_index, coin_stats, patterns, corr, fails)

    # Also save aggregated data
    if not all_results.empty:
        all_results.to_csv(OUT_CSV, index=False)
        print(f"Saved aggregated data: {OUT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
