"""Per-asset audit — Idea C.

Goal: from EVERY archived backtest (both freqtrade native + our experiment
logger), build a matrix of:

    coin x strategy x timerange -> (roi, sharpe, max_dd, trades)

Then for each coin, identify the historical best-performer per year-window
and flag mismatches with the current live deployment.

This is a READ-ONLY analysis. Outputs a markdown report + CSV.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
BT_DIR = REPO / "user_data" / "backtest_results"
EXP_DIR = REPO / "research" / "experiments"
OUT_MD = REPO / "research" / "per_asset_audit.md"
OUT_CSV = REPO / "research" / "per_asset_audit.csv"

# Current live deployment (from MEMORY + SQL):
# BTC: AI Shield V2 + Calendar Shield (NEW)
# ETH: Pure Shield, SOL: Pure Shield, BNB: Sh_SLOW
# DOGE: Sh_DEF, AVAX: Meta_REL, ADA: Meta_BAL
CURRENT_LIVE = {
    "BTC": "BtcAiShieldV2Strategy / BtcCalendarShieldStrategy",
    "ETH": "EthRegimeShieldStrategy (Pure)",
    "SOL": "SolRegimeShieldStrategy (Pure)",
    "BNB": "BnbShieldSlowStrategy",
    "DOGE": "DogeShieldDefensiveStrategy",
    "AVAX": "AvaxMetaReliableStrategy",
    "ADA": "AdaMetaBalancedStrategy",
}

COIN_RE = re.compile(r"(BTC|ETH|SOL|BNB|AVAX|DOGE|ADA)/USDT|"
                     r"(BTC|ETH|SOL|BNB|AVAX|DOGE|ADA)_USDT", re.I)


def coin_from_pair(pair: str) -> str | None:
    if not pair:
        return None
    m = COIN_RE.search(pair.upper())
    if not m:
        return None
    return m.group(1) or m.group(2)


def parse_freqtrade_zip(zip_path: Path) -> list[dict]:
    """Read backtest zip, extract one row per (strategy, pair)."""
    rows = []
    try:
        with zipfile.ZipFile(zip_path) as z:
            json_files = [n for n in z.namelist() if n.endswith(".json")]
            if not json_files:
                return []
            with z.open(json_files[0]) as f:
                data = json.load(f)
    except Exception:
        return []
    strategies = data.get("strategy") or {}
    for strat_name, strat in strategies.items():
        # results_per_pair has per-coin breakdown
        per_pair = strat.get("results_per_pair") or []
        for p in per_pair:
            pair = p.get("key") or ""
            coin = coin_from_pair(pair)
            if not coin:
                continue
            rows.append({
                "source": "freqtrade_zip",
                "file": zip_path.name,
                "strategy": strat_name,
                "coin": coin,
                "pair": pair,
                "n_trades": p.get("trades") or 0,
                "roi_pct": (p.get("profit_total_pct") or 0),
                "win_rate_pct": (p.get("wins") or 0) / max(p.get("trades", 1) or 1, 1) * 100,
                "max_dd_pct": strat.get("max_drawdown_account") or strat.get("max_drawdown") or 0,
                "sharpe": strat.get("sharpe") or 0,
                "sortino": strat.get("sortino") or 0,
                "profit_factor": strat.get("profit_factor") or 0,
                "timerange": f"{strat.get('backtest_start')}~{strat.get('backtest_end')}",
            })
    return rows


def parse_experiment_index() -> list[dict]:
    idx = EXP_DIR / "INDEX.csv"
    if not idx.exists():
        return []
    df = pd.read_csv(idx)
    rows = []
    for _, r in df.iterrows():
        coin = coin_from_pair(str(r.get("pair", "")))
        if not coin:
            continue
        rows.append({
            "source": "experiment_logger",
            "file": str(r.get("run_dir", "")),
            "strategy": str(r.get("strategy", "")),
            "coin": coin,
            "pair": str(r.get("pair", "")),
            "n_trades": int(r.get("n_trades", 0) or 0),
            "roi_pct": float(r.get("roi_pct", 0) or 0),
            "win_rate_pct": float(r.get("win_rate_pct", 0) or 0),
            "max_dd_pct": float(r.get("max_dd_pct", 0) or 0),
            "sharpe": float(r.get("sharpe", 0) or 0),
            "sortino": float(r.get("sortino", 0) or 0),
            "profit_factor": float(r.get("profit_factor", 0) or 0),
            "timerange": str(r.get("timerange", "")),
        })
    return rows


def score(row: dict) -> float:
    roi = row.get("roi_pct", 0) or 0
    dd = abs(row.get("max_dd_pct", 0) or 0)
    sharpe = row.get("sharpe", 0) or 0
    n = row.get("n_trades", 0) or 0
    if n < 2:
        return -999
    if dd >= 100:
        return -999
    return roi - 2 * dd + 10 * sharpe


def main():
    print("Scanning freqtrade zips...")
    rows = []
    zips = sorted(BT_DIR.glob("backtest-result-*.zip"))
    print(f"  {len(zips)} zip files")
    for z in zips:
        rows.extend(parse_freqtrade_zip(z))
    print(f"  {len(rows)} per-(strategy,coin) records from zips")

    print("Scanning experiment_logger index...")
    exp_rows = parse_experiment_index()
    print(f"  {len(exp_rows)} records from INDEX.csv")
    rows.extend(exp_rows)

    df = pd.DataFrame(rows)
    if df.empty:
        print("No data found.")
        return 1

    df["score"] = df.apply(score, axis=1)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}  ({len(df)} rows)")

    # Best per (coin, strategy) — take best score
    per_coin_strat = df.groupby(["coin", "strategy"]).agg(
        n_runs=("score", "size"),
        best_score=("score", "max"),
        median_roi=("roi_pct", "median"),
        median_dd=("max_dd_pct", "median"),
        best_roi=("roi_pct", "max"),
        worst_roi=("roi_pct", "min"),
        median_sharpe=("sharpe", "median"),
        median_trades=("n_trades", "median"),
    ).reset_index()

    # Top 3 strategies per coin by best_score
    out_lines = ["# Per-Asset Audit\n",
                 "Idea C — scanning all archived backtests to identify the historically best-performing strategy per coin.\n",
                 f"Total records scanned: **{len(df)}**\n"]

    for coin in ["BTC", "ETH", "SOL", "BNB", "AVAX", "DOGE", "ADA"]:
        sub = per_coin_strat[per_coin_strat["coin"] == coin].sort_values("best_score", ascending=False)
        if sub.empty:
            continue
        out_lines.append(f"\n## {coin}")
        out_lines.append(f"**Currently live:** `{CURRENT_LIVE.get(coin, '?')}`\n")
        out_lines.append("Top 8 strategies by best_score (roi - 2×dd + 10×sharpe):\n")
        out_lines.append("| Strategy | Runs | Best ROI | Worst ROI | Median ROI | Median DD | Median Sharpe | Best Score |")
        out_lines.append("|---|---|---|---|---|---|---|---|")
        for _, r in sub.head(8).iterrows():
            out_lines.append(
                f"| `{r['strategy']}` | {int(r['n_runs'])} | "
                f"{r['best_roi']:.1f}% | {r['worst_roi']:.1f}% | {r['median_roi']:.1f}% | "
                f"{abs(r['median_dd']):.1f}% | {r['median_sharpe']:.3f} | {r['best_score']:.1f} |"
            )

        # Flag if current live is NOT in top 3
        live = CURRENT_LIVE.get(coin, "")
        top3 = set(sub.head(3)["strategy"].tolist())
        live_clean = re.sub(r"[() ]", "", live).upper()
        matched = any(re.sub(r"[() ]", "", s).upper() in live_clean or
                      live_clean in re.sub(r"[() ]", "", s).upper()
                      for s in top3)
        if not matched and len(top3) > 0:
            out_lines.append(f"\n⚠️ **Potential upgrade**: live `{live}` not in top 3 by audit score.")
        else:
            out_lines.append(f"\n✅ Live `{live}` is in top 3 (audit aligned).")

    OUT_MD.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"Saved: {OUT_MD}")

    # Console summary
    print("\n=== Audit summary ===")
    for coin in ["BTC", "ETH", "SOL", "BNB", "AVAX", "DOGE", "ADA"]:
        sub = per_coin_strat[per_coin_strat["coin"] == coin].sort_values("best_score", ascending=False)
        if sub.empty:
            print(f"{coin}: no data")
            continue
        top = sub.iloc[0]
        print(f"{coin}: top = {top['strategy']} (score {top['best_score']:.1f}, best ROI {top['best_roi']:.1f}%) | live = {CURRENT_LIVE.get(coin, '?')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
