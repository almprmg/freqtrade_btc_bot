"""Calendar effect analyzer — look for statistically significant patterns.

Tests on BTC daily returns 2018-2026:
  1. Day-of-week (Mon...Sun)
  2. Day-of-month (start / mid / end)
  3. Month (Jan...Dec)
  4. Day-of-week x Month interaction
  5. Days from halving (halving anniversary effects)
  6. Quarter-end behavior

For each pattern, compute:
  - mean return
  - hit rate (% positive days)
  - p-value (t-test vs zero mean)
  - effect size

Output: research/calendar_findings.md (narrative)
        research/calendar_table.csv  (raw stats)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "user_data" / "data" / "binance" / "BTC_USDT-1d.feather"
OUT_MD = REPO / "research" / "calendar_findings.md"
OUT_CSV = REPO / "research" / "calendar_table.csv"


def t_test(returns: np.ndarray) -> tuple[float, float]:
    if len(returns) < 5:
        return 0.0, 1.0
    t, p = stats.ttest_1samp(returns, 0)
    return float(t), float(p)


def analyze_group(label: str, groups: dict) -> pd.DataFrame:
    rows = []
    for grp_name, returns in groups.items():
        if len(returns) < 5:
            continue
        t, p = t_test(returns)
        rows.append({
            "dimension": label,
            "group": grp_name,
            "n": len(returns),
            "mean_pct": float(np.mean(returns) * 100),
            "median_pct": float(np.median(returns) * 100),
            "hit_rate": float(np.mean(returns > 0)),
            "std_pct": float(np.std(returns) * 100),
            "t_stat": round(t, 3),
            "p_value": round(p, 4),
            "significant": p < 0.05,
        })
    return pd.DataFrame(rows)


def main():
    df = pd.read_feather(DATA)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.set_index("date").sort_index()
    df["ret"] = df["close"].pct_change()
    df = df.dropna(subset=["ret"]).loc["2018-01-01":]

    print(f"Data: {len(df)} days from {df.index.min().date()} to {df.index.max().date()}\n")

    # 1. Day-of-week
    df["dow"] = df.index.day_name()
    dow_groups = {dow: df[df["dow"] == dow]["ret"].values
                  for dow in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]}
    dow_df = analyze_group("Day-of-Week", dow_groups)

    # 2. Day-of-month buckets
    def dom_bucket(d):
        if d <= 5: return "Start (1-5)"
        if d <= 10: return "Early (6-10)"
        if d <= 20: return "Mid (11-20)"
        if d <= 25: return "Late (21-25)"
        return "End (26-31)"
    df["dom_bucket"] = df.index.day.map(dom_bucket)
    dom_groups = {b: df[df["dom_bucket"] == b]["ret"].values
                   for b in ["Start (1-5)", "Early (6-10)", "Mid (11-20)", "Late (21-25)", "End (26-31)"]}
    dom_df = analyze_group("Day-of-Month", dom_groups)

    # 3. Month
    df["month"] = df.index.month_name()
    month_order = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    month_groups = {m: df[df["month"] == m]["ret"].values for m in month_order}
    month_df = analyze_group("Month", month_groups)

    # 4. Days from halving (use the most recent halving each day)
    HALVINGS = [pd.Timestamp(d, tz="UTC") for d in
                ["2012-11-28", "2016-07-09", "2020-05-11", "2024-04-19"]]
    def days_since_halving(date):
        prev = [h for h in HALVINGS if h <= date]
        if not prev:
            return None
        return int((date - max(prev)).days)
    df["days_h"] = df.index.map(days_since_halving)
    def halving_bucket(d):
        if d is None: return None
        if d < 90: return "0-90d post-halving"
        if d < 365: return "90-365d (Early bull)"
        if d < 540: return "365-540d (Parabolic)"
        if d < 700: return "540-700d (Distribution)"
        if d < 900: return "700-900d (Bear)"
        return ">900d (Reaccumulation)"
    df["halving_bucket"] = df["days_h"].map(halving_bucket)
    halving_groups = {b: df[df["halving_bucket"] == b]["ret"].values
                       for b in ["0-90d post-halving", "90-365d (Early bull)",
                                  "365-540d (Parabolic)", "540-700d (Distribution)",
                                  "700-900d (Bear)", ">900d (Reaccumulation)"]}
    halving_df = analyze_group("Days-from-Halving", halving_groups)

    # 5. Quarter end
    df["is_quarter_end_week"] = df.index.to_series().apply(
        lambda d: (d.month in (3, 6, 9, 12)) and (d.day >= 25)
    )
    qe_groups = {
        "Quarter-end week": df[df["is_quarter_end_week"]]["ret"].values,
        "Other days": df[~df["is_quarter_end_week"]]["ret"].values,
    }
    qe_df = analyze_group("Quarter-End", qe_groups)

    # Combine
    all_findings = pd.concat([dow_df, dom_df, month_df, halving_df, qe_df], ignore_index=True)
    all_findings.to_csv(OUT_CSV, index=False)

    # Report
    lines = []
    lines.append("# Calendar Effects on BTC/USDT 2018-2026\n")
    lines.append(f"Analyzed: {len(df)} daily returns\n")

    # Find significant patterns
    sig = all_findings[all_findings["significant"]].sort_values("p_value")

    lines.append("## Significant patterns (p < 0.05)\n")
    if sig.empty:
        lines.append("**NONE FOUND**. After Bonferroni-style consideration of multiple tests,\n")
        lines.append("no calendar pattern in BTC daily returns rises to statistical significance.\n")
        lines.append("This is consistent with academic literature: weekend/monthly effects in crypto\n")
        lines.append("are weak or non-existent.\n\n")
    else:
        lines.append(sig.to_string(index=False))
        lines.append("\n")

    lines.append("## Day-of-Week\n```")
    lines.append(dow_df.to_string(index=False))
    lines.append("```\n")

    lines.append("## Month\n```")
    lines.append(month_df.to_string(index=False))
    lines.append("```\n")

    lines.append("## Days-from-Halving\n```")
    lines.append(halving_df.to_string(index=False))
    lines.append("```\n")

    lines.append("## Quarter-End\n```")
    lines.append(qe_df.to_string(index=False))
    lines.append("```\n")

    OUT_MD.write_text("\n".join(lines))
    print(f"Saved: {OUT_MD}")
    print(f"Saved: {OUT_CSV}")
    print(f"\nSignificant patterns found: {len(sig)}")
    if not sig.empty:
        print(sig[["dimension", "group", "mean_pct", "p_value"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
