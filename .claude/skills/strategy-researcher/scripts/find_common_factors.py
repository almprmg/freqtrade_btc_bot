"""find_common_factors.py — Playbook 1: what do winners share?

Reads:
  research/experiments/INDEX.csv
  research/adversarial/*.csv (verdicts)
  user_data/strategies/*.py (source extraction)

Extracts features from each strategy file via simple regex:
  - N_CONFIRM value
  - ADX threshold
  - ret_30d / ret_60d thresholds
  - atr_pct ceiling (if any)
  - Has PHASE_SHIFTS? CALENDAR_TILTS?
  - Has BEAR exit logic? Anomaly circuit breaker?

Groups by adversarial verdict (PASS/WARN/FAIL/CATASTROPHIC) and computes:
  - Per-feature presence rate
  - Diff: PRESENT in winners but ABSENT in losers (or vice versa)

Usage:
  python -m scripts.find_common_factors

Output:
  research/factor_analysis.md
"""
from __future__ import annotations

import re
from pathlib import Path
from collections import defaultdict

import pandas as pd

REPO = Path("d:/pythone/freqtrade_btc_bot")
STRATEGIES = REPO / "user_data" / "strategies"
ADV_DIR = REPO / "research" / "adversarial"
OUT = REPO / "research" / "factor_analysis.md"


FEATURE_PATTERNS = {
    "has_phase_shifts": r"PHASE_SHIFTS\s*=",
    "has_calendar_tilts": r"CALENDAR_TILTS\s*=",
    "has_anomaly_filter": r"_ANOMALY",
    "has_atr_pct_filter": r"atr_pct\s*<",
    "has_ema50_filter": r"ema50",
    "has_ret_60d_filter": r"ret_60d",
    "has_bear_exit": r"(BEAR|bear)",
    "has_sigmoid_sizing": r"_sigmoid",
    "has_donchian": r"dc_high|dc_low",
    "has_macd": r"MACD\(",
    "uses_triple_consensus": r"det1.*&.*det2.*&.*det3",
}


def extract_threshold(content: str, pattern: str) -> float | None:
    """Extract a numeric threshold from source (e.g. ADX > 30)."""
    m = re.search(pattern, content)
    if not m:
        return None
    try:
        return float(m.group(1))
    except (ValueError, IndexError):
        return None


def analyze_strategy_file(path: Path) -> dict:
    content = path.read_text(encoding="utf-8", errors="ignore")
    features = {}
    for name, pattern in FEATURE_PATTERNS.items():
        features[name] = bool(re.search(pattern, content))

    features["n_confirm"] = extract_threshold(content, r"N_CONFIRM\s*=\s*(\d+)")
    features["adx_min"] = extract_threshold(content, r"adx[\"'\]]*\s*>\s*(\d+)")
    features["ret_30d_min"] = extract_threshold(content, r"ret_30d[\"'\]]*\s*>\s*([\d.]+)")
    features["atr_pct_max"] = extract_threshold(content, r"atr_pct[\"'\]]*\s*<\s*([\d.]+)")

    return features


def load_adversarial_verdicts() -> dict[str, str]:
    """Returns dict of strategy_name -> verdict from latest adversarial runs."""
    verdicts = {}
    if not ADV_DIR.exists():
        return verdicts
    for csv in ADV_DIR.glob("*.csv"):
        try:
            df = pd.read_csv(csv)
            for _, row in df.iterrows():
                # The 'candidate' column has the strategy name
                name = str(row.get("candidate", ""))
                verdict = str(row.get("verdict", ""))
                if name and verdict in ("PASS", "WARN", "FAIL", "CATASTROPHIC"):
                    verdicts[name] = verdict
        except Exception:
            continue
    return verdicts


def main():
    print("Scanning strategy files...")
    strategy_features = {}
    for p in STRATEGIES.glob("*_strategy.py"):
        try:
            features = analyze_strategy_file(p)
            strategy_features[p.stem.replace("_strategy", "")] = features
        except Exception as e:
            print(f"  skip {p.name}: {e}")
    print(f"  analyzed {len(strategy_features)} strategies")

    print("Loading adversarial verdicts...")
    verdicts = load_adversarial_verdicts()
    print(f"  found {len(verdicts)} verdicts")

    # Group strategies by verdict (best-effort matching by name)
    by_verdict = defaultdict(list)
    for strat, feats in strategy_features.items():
        # Try to match strat name against verdicts dict
        match = None
        for v_name, v_verdict in verdicts.items():
            if strat.lower() in v_name.lower() or v_name.lower() in strat.lower():
                match = v_verdict
                break
        if match:
            by_verdict[match].append((strat, feats))
        else:
            by_verdict["UNKNOWN"].append((strat, feats))

    # Compute feature presence rate per verdict group
    lines = [
        "# Factor Analysis — What Winners Share",
        f"\nAnalyzed {len(strategy_features)} strategies, {len(verdicts)} adversarial verdicts.\n",
        "## Feature presence by verdict group\n",
    ]
    feature_names = list(FEATURE_PATTERNS.keys())

    lines.append("| Feature | PASS | WARN | FAIL | CATASTROPHIC |")
    lines.append("|---|---|---|---|---|")
    for fname in feature_names:
        row = [f"`{fname}`"]
        for v in ["PASS", "WARN", "FAIL", "CATASTROPHIC"]:
            group = by_verdict.get(v, [])
            if not group:
                row.append("—")
                continue
            present = sum(1 for _, feats in group if feats.get(fname))
            row.append(f"{present}/{len(group)} ({present/len(group)*100:.0f}%)")
        lines.append("| " + " | ".join(row) + " |")

    # Differentiating features (PASS - FAIL diff)
    lines.append("\n## Differentiating features (PASS rate − FAIL rate)\n")
    pass_g = by_verdict.get("PASS", [])
    fail_g = by_verdict.get("FAIL", []) + by_verdict.get("CATASTROPHIC", [])
    diffs = []
    for fname in feature_names:
        if not pass_g or not fail_g:
            continue
        pass_rate = sum(1 for _, f in pass_g if f.get(fname)) / len(pass_g)
        fail_rate = sum(1 for _, f in fail_g if f.get(fname)) / len(fail_g)
        diff = pass_rate - fail_rate
        diffs.append((fname, diff, pass_rate, fail_rate))
    diffs.sort(key=lambda x: abs(x[1]), reverse=True)
    for fname, diff, pr, fr in diffs:
        direction = "↑ helps" if diff > 0.2 else ("↓ hurts" if diff < -0.2 else "≈ neutral")
        lines.append(f"- `{fname}`: PASS={pr*100:.0f}%, FAIL={fr*100:.0f}%, diff={diff*100:+.0f}pp  {direction}")

    # Threshold distributions
    lines.append("\n## Threshold distributions (numeric features)\n")
    for tname in ["n_confirm", "adx_min", "ret_30d_min", "atr_pct_max"]:
        for v in ["PASS", "WARN", "FAIL"]:
            group = by_verdict.get(v, [])
            vals = [f[tname] for _, f in group if f.get(tname) is not None]
            if vals:
                lines.append(f"- `{tname}` in {v}: {vals}")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSaved: {OUT}")


if __name__ == "__main__":
    main()
