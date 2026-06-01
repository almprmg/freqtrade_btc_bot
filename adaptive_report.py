"""Adaptive strategy sweep — 12 variants over 5 years."""
from __future__ import annotations
import io, json, sys, zipfile
from pathlib import Path
import pandas as pd

MODES = [
    "ADAPT_AGGR_BASELINE", "ADAPT_AGGR_TIGHT", "ADAPT_AGGR_LOOSE", "ADAPT_AGGR_NOSTOP",
    "ADAPT_BAL_BASELINE",  "ADAPT_BAL_TIGHT",  "ADAPT_BAL_LOOSE",  "ADAPT_BAL_NOSTOP",
    "ADAPT_DEF_BASELINE",  "ADAPT_DEF_TIGHT",  "ADAPT_DEF_LOOSE",  "ADAPT_DEF_NOSTOP",
]
RESULTS_DIR = Path("user_data/backtest_results")
START_WALLET = 10000.0


def latest_n_zips(n):
    return sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)[-n:]


def headline(zpath, mode):
    with zipfile.ZipFile(zpath) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and "market_change" not in n]
        if not names: return {}
        with z.open(names[0]) as f:
            payload = json.load(io.TextIOWrapper(f, encoding="utf-8"))
    strat_key = next(iter(payload.get("strategy", {})), None)
    if not strat_key: return {}
    s = payload["strategy"][strat_key]
    final = float(s.get("final_balance", 0) or 0)
    profit = final - START_WALLET
    roi = profit / START_WALLET * 100
    # Annualized: (1 + roi)^(1/5) - 1
    mult = max(final / START_WALLET, 0.001)
    annual = (mult ** 0.2 - 1) * 100
    return {
        "mode": mode,
        "final_$": round(final, 0),
        "profit_$": round(profit, 0),
        "roi_5y_%": round(roi, 1),
        "annual_%": round(annual, 1),
        "trades": int(s.get("total_trades", 0)),
        "max_dd_%": round(float(s.get("max_drawdown_account", 0) or 0) * 100, 1),
    }


def main():
    zips = latest_n_zips(len(MODES))
    rows = [headline(z, m) for m, z in zip(MODES, zips)]
    rows = [r for r in rows if r]
    df = pd.DataFrame(rows).sort_values("roi_5y_%", ascending=False).reset_index(drop=True)
    print("\n" + "=" * 100)
    print("ADAPTIVE SWEEP — sorted by ROI (5-year, $10k starting wallet)")
    print("=" * 100)
    print(df.to_string(index=False))
    Path("adaptive_results").mkdir(exist_ok=True)
    df.to_csv("adaptive_results/summary.csv", index=False)
    print()
    w = df.iloc[0]
    print(f">>> WINNER: {w['mode']} — ROI {w['roi_5y_%']}% (~{w['annual_%']}%/yr) | trades {w['trades']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
