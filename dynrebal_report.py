"""Comparison of the 12 dynamic-rebalance variants."""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

MODES = [
    "DR_PROFIT_10", "DR_PROFIT_20", "DR_PROFIT_30",
    "DR_RSI_70_30", "DR_RSI_75_25",
    "DR_BB", "DR_VOL_HIGH", "DR_DD_20", "DR_EMA50",
    "DR_RSI_AND_PROFIT", "DR_RSI_OR_BB", "DR_REGIME",
]
RESULTS_DIR = Path("user_data/backtest_results")
START_WALLET = 10000.0


def latest_n_zips(n: int) -> list[Path]:
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    return zips[-n:]


def headline(zpath: Path, mode: str) -> dict:
    with zipfile.ZipFile(zpath) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and "market_change" not in n]
        if not names:
            return {}
        with z.open(names[0]) as f:
            payload = json.load(io.TextIOWrapper(f, encoding="utf-8"))
    strat_key = next(iter(payload.get("strategy", {})), None)
    if not strat_key:
        return {}
    strat = payload["strategy"][strat_key]
    final = float(strat.get("final_balance", 0) or 0)
    profit = final - START_WALLET
    return {
        "mode": mode,
        "final_$": round(final, 0),
        "profit_$": round(profit, 0),
        "roi_%": round(profit / START_WALLET * 100, 1),
        "trades": int(strat.get("total_trades", 0)),
        "wr_%": round(float(strat.get("wins", 0)) / max(int(strat.get("total_trades", 0)), 1) * 100, 1),
        "sharpe": round(float(strat.get("sharpe", 0) or 0), 2),
        "max_dd_%": round(float(strat.get("max_drawdown_account", 0) or 0) * 100, 1),
    }


def main() -> int:
    zips = latest_n_zips(len(MODES))
    rows = [headline(z, m) for m, z in zip(MODES, zips) if z.exists()]
    rows = [r for r in rows if r]
    if not rows:
        print("No data.")
        return 1
    df = pd.DataFrame(rows).sort_values("roi_%", ascending=False).reset_index(drop=True)
    print("\n" + "=" * 110)
    print("DYNAMIC REBALANCE SWEEP — sorted by ROI (5-year, $10k starting wallet)")
    print("=" * 110)
    print(df.to_string(index=False))

    Path("dynrebal_results").mkdir(exist_ok=True)
    df.to_csv("dynrebal_results/summary.csv", index=False)
    print("\nSaved: dynrebal_results/summary.csv")
    winner = df.iloc[0]
    print(f"\n>>> WINNER: {winner['mode']} — ROI {winner['roi_%']}% | trades {winner['trades']} | WR {winner['wr_%']}% | MaxDD {winner['max_dd_%']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
