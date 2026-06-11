"""live_vs_backtest.py — Playbook 3: detect live vs backtest divergence.

For each currently-deployed bot, compare:
  - Backtest expectation: latest 2025 or 2026 mode from INDEX.csv
  - Live actual: trades from trad_pg.trades over recent 90 days
Flag divergence > 50%.

Reads:
  research/experiments/INDEX.csv
  trad_pg.trades  (via psycopg, needs TRAD_PG_DSN env)

Output:
  research/live_vs_backtest_report.md

Usage:
  TRAD_PG_DSN=postgresql://trading:e763ad7f2c4924e949913f58@trad_pg:5432/trading \
    python -m scripts.live_vs_backtest
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

REPO = Path("d:/pythone/freqtrade_btc_bot")
IDX = REPO / "research" / "experiments" / "INDEX.csv"
OUT = REPO / "research" / "live_vs_backtest_report.md"

LOOKBACK_DAYS = 90


def get_backtest_expectation(strategy: str, pair_substr: str) -> dict | None:
    """Most recent 2025/2026 mode row for (strategy, pair)."""
    if not IDX.exists():
        return None
    df = pd.read_csv(IDX)
    df = df[df["strategy"] == strategy]
    df = df[df["pair"].astype(str).str.contains(pair_substr, na=False, case=False)]
    df = df[df["mode"].astype(str).str.contains("2025|2026", na=False, regex=True)]
    if df.empty:
        return None
    last = df.sort_values("timestamp").iloc[-1]
    return {
        "roi_pct": float(last["roi_pct"]),
        "n_trades_expected": int(last["n_trades"]),
        "max_dd": float(last["max_dd_pct"]),
        "win_rate": float(last["win_rate_pct"]),
        "mode": str(last["mode"]),
    }


def get_live_actual(dsn: str, subscription_id: int, days: int) -> dict | None:
    try:
        import psycopg
    except ImportError:
        print("WARN: psycopg not installed; run on a host that has it")
        return None
    sql = f"""
    SELECT
      COUNT(*) AS n_trades,
      COALESCE(AVG(pnl), 0) AS avg_pnl,
      COALESCE(SUM(pnl), 0) AS total_pnl,
      COUNT(*) FILTER (WHERE pnl > 0) * 100.0 / NULLIF(COUNT(*), 0) AS win_rate
    FROM trades
    WHERE subscription_id = {subscription_id}
      AND closed_at >= NOW() - INTERVAL '{days} days'
      AND status = 'closed';
    """
    with psycopg.connect(dsn) as conn:
        df = pd.read_sql(sql, conn)
    if df.empty or df["n_trades"].iloc[0] == 0:
        return None
    return {
        "n_trades": int(df["n_trades"].iloc[0]),
        "total_pnl": float(df["total_pnl"].iloc[0]),
        "win_rate": float(df["win_rate"].iloc[0] or 0),
    }


def list_active_subs(dsn: str) -> list[dict]:
    try:
        import psycopg
    except ImportError:
        return []
    sql = """
    SELECT id, trading_symbol, allocated_capital,
           custom_parameters->>'source' AS source
    FROM user_strategy_subscriptions
    WHERE user_id = 10 AND status = 'active'
      AND custom_parameters->>'source' LIKE 'freqtrade_%'
    ORDER BY id;
    """
    with psycopg.connect(dsn) as conn:
        df = pd.read_sql(sql, conn)
    return df.to_dict("records")


# Map bot source name to (strategy_class, coin)
BOT_TO_STRATEGY = {
    "freqtrade_ai_shield_v2": ("BtcAiShieldV2Strategy", "BTC"),
    "freqtrade_triple": ("BtcTripleRegimeStrategy", "BTC"),
    "freqtrade_calendar": ("BtcCalendarShieldStrategy", "BTC"),
    "freqtrade_eth_shield": ("BtcRegimeShieldStrategy", "ETH"),
    "freqtrade_sol_vol_shield": ("SolVolShieldStrategy", "SOL"),
    "freqtrade_bnb_triple": ("BtcTripleRegimeStrategy", "BNB"),
    "freqtrade_ada_triple": ("BtcTripleRegimeStrategy", "ADA"),
    "freqtrade_eth_calendar": ("BtcCalendarShieldStrategy", "ETH"),
    # Add as new bots deploy
}


def main():
    dsn = os.environ.get("TRAD_PG_DSN", "")
    if not dsn:
        print("ERROR: set TRAD_PG_DSN env var")
        return 1

    print(f"Pulling active subscriptions...")
    subs = list_active_subs(dsn)
    print(f"  found {len(subs)} active bots")

    rows = []
    for sub in subs:
        source = sub["source"]
        if source not in BOT_TO_STRATEGY:
            rows.append({"bot": source, "status": "unknown_bot_mapping"})
            continue
        strategy, coin = BOT_TO_STRATEGY[source]

        bt = get_backtest_expectation(strategy, coin)
        live = get_live_actual(dsn, int(sub["id"]), LOOKBACK_DAYS)

        if bt is None:
            rows.append({"bot": source, "status": "no_backtest_data"})
            continue
        if live is None:
            rows.append({
                "bot": source,
                "status": "no_live_trades_yet",
                "bt_roi_pct": bt["roi_pct"],
                "bt_n_trades": bt["n_trades_expected"],
            })
            continue

        # Compute divergence
        live_roi_pct = (live["total_pnl"] / float(sub["allocated_capital"])) * 100 \
                       if sub["allocated_capital"] else 0
        bt_yearly = bt["roi_pct"]
        live_yearly = live_roi_pct * (365 / LOOKBACK_DAYS)  # annualize
        if abs(bt_yearly) > 0.1:
            divergence = (live_yearly - bt_yearly) / abs(bt_yearly)
        else:
            divergence = float("inf") if abs(live_yearly) > 0.1 else 0

        flag = "OK"
        if abs(divergence) > 0.5:
            flag = "⚠️ DIVERGED"

        rows.append({
            "bot": source,
            "status": flag,
            "bt_roi_pct": bt["roi_pct"],
            "bt_n_trades": bt["n_trades_expected"],
            "live_n_trades": live["n_trades"],
            "live_roi_pct_annualized": round(live_yearly, 1),
            "divergence_pct": round(divergence * 100, 1),
            "live_win_rate": round(live["win_rate"], 1),
        })

    # Markdown report
    lines = ["# Live vs Backtest Divergence Report\n",
             f"Lookback: {LOOKBACK_DAYS} days\n",
             f"Active bots scanned: {len(subs)}\n",
             "\n## Results\n",
             "| Bot | Status | BT ROI | BT n_trades | Live n | Live ROI ann | Diverge % | Win% |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| `{r.get('bot', '?')}` | {r.get('status', '?')} | "
            f"{r.get('bt_roi_pct', '—')}% | {r.get('bt_n_trades', '—')} | "
            f"{r.get('live_n_trades', '—')} | {r.get('live_roi_pct_annualized', '—')}% | "
            f"{r.get('divergence_pct', '—')}% | {r.get('live_win_rate', '—')}% |"
        )

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSaved: {OUT}")
    # Print summary
    diverged = [r for r in rows if "DIVERGED" in str(r.get("status", ""))]
    print(f"\nDiverged bots: {len(diverged)}")
    for r in diverged:
        print(f"  {r['bot']}: BT={r['bt_roi_pct']}% Live={r.get('live_roi_pct_annualized', '?')}%/yr "
              f"({r['divergence_pct']}% off)")


if __name__ == "__main__":
    sys.exit(main() or 0)
