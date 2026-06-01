"""Year-by-year + per-layer breakdown of the 16 3-layer sweep results."""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

MODES = [
    "L3_AGGR_BASELINE", "L3_AGGR_TIGHT_GRID", "L3_AGGR_WIDE_GRID", "L3_AGGR_WEEKLY",
    "L3_BAL_BASELINE", "L3_BAL_TIGHT_GRID", "L3_BAL_WIDE_GRID", "L3_BAL_WEEKLY",
    "L3_BAL_QUARTERLY", "L3_BAL_CRASH_SOFT", "L3_BAL_CRASH_HARD",
    "L3_DEF_BASELINE", "L3_DEF_TIGHT_GRID", "L3_DEF_WIDE_GRID",
    "L3_DEF_CRASH_SOFT", "L3_DEF_PARTIAL_DEPLOY",
]
RESULTS_DIR = Path("user_data/backtest_results")
START_WALLET = 10000.0


def latest_n_zips(n: int) -> list[Path]:
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    return zips[-n:]


def trades_from_zip(p: Path) -> tuple[pd.DataFrame, dict]:
    with zipfile.ZipFile(p) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and "market_change" not in n]
        if not names:
            return pd.DataFrame(), {}
        with z.open(names[0]) as f:
            payload = json.load(io.TextIOWrapper(f, encoding="utf-8"))
    strat_key = next(iter(payload.get("strategy", {})), None)
    if strat_key is None:
        return pd.DataFrame(), {}
    strat = payload["strategy"][strat_key]
    trades = strat.get("trades", [])
    if not trades:
        return pd.DataFrame(), strat
    df = pd.DataFrame(trades)
    df["open_date"] = pd.to_datetime(df["open_date"], utc=True)
    df["close_date"] = pd.to_datetime(df["close_date"], utc=True, errors="coerce")
    return df, strat


def headline_per_mode(zpath: Path, mode: str) -> dict:
    df, strat = trades_from_zip(zpath)
    if strat is None:
        return {}
    final_balance = float(strat.get("final_balance", 0) or 0)
    profit_total = final_balance - START_WALLET
    profit_pct = profit_total / START_WALLET * 100
    trades_count = int(strat.get("total_trades", 0))
    wins = int(strat.get("wins", 0))
    losses = int(strat.get("losses", 0))
    sharpe = float(strat.get("sharpe", 0) or 0)
    max_dd = float(strat.get("max_drawdown_account", strat.get("max_drawdown_abs", 0)) or 0)

    # Per-layer attribution from enter_tag/orders (best effort).
    if not df.empty:
        df["layer"] = df.get("enter_tag", "").fillna("").astype(str).str.split(":").str[0]
    return {
        "mode": mode,
        "final_$": round(final_balance, 0),
        "profit_$": round(profit_total, 0),
        "roi_%": round(profit_pct, 1),
        "trades": trades_count,
        "wins": wins,
        "losses": losses,
        "wr_%": round(wins / trades_count * 100, 1) if trades_count else 0.0,
        "sharpe": round(sharpe, 2),
        "max_dd_%": round(max_dd * 100, 1) if max_dd < 1 else round(max_dd, 1),
    }


def main() -> int:
    zips = latest_n_zips(len(MODES))
    if len(zips) < len(MODES):
        print(f"WARN: expected {len(MODES)} zips, found {len(zips)}", file=sys.stderr)

    rows = []
    for mode, zpath in zip(MODES, zips):
        row = headline_per_mode(zpath, mode)
        if not row:
            continue
        row["zip"] = zpath.name
        rows.append(row)

    if not rows:
        print("No data.")
        return 1

    df = pd.DataFrame(rows)
    df = df.sort_values("roi_%", ascending=False).reset_index(drop=True)
    print("\n" + "=" * 110)
    print("3-LAYER SWEEP — sorted by ROI (5-year, $10k starting wallet)")
    print("=" * 110)
    print(df[["mode", "final_$", "profit_$", "roi_%", "trades", "wr_%", "sharpe", "max_dd_%"]].to_string(index=False))

    Path("3layer_results").mkdir(exist_ok=True)
    df.to_csv("3layer_results/summary.csv", index=False)
    print("\nSaved: 3layer_results/summary.csv")

    winner = df.iloc[0]
    print(f"\n>>> WINNER: {winner['mode']} — ROI {winner['roi_%']}% on ${START_WALLET:.0f}")
    print(f"    Trades: {winner['trades']} | WR {winner['wr_%']}% | Sharpe {winner['sharpe']} | MaxDD {winner['max_dd_%']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
