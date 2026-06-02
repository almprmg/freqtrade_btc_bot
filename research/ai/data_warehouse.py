"""Data warehouse — export EVERYTHING for archival + future analysis.

Exports:
  research/archive/<timestamp>/
    trades_full.csv         — every trade from trad_pg, all columns
    orders_full.csv         — every order (entries + exits) joined to trades
    subscriptions.csv       — current state of all subs
    strategies.csv          — strategies table
    backtest_summary.csv    — every backtest result we have (from research/*.csv)
    backtest_year_pivot.csv — wide year-by-year pivot per strategy
    coin_stats.csv          — per-coin price stats (return, vol, DD) per year
    fleet_snapshot.json     — point-in-time snapshot of fleet state

Plus a versioned `latest/` symlink-style folder updated each run.

Run periodically (weekly recommended) to keep history forever.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import psycopg


REPO = Path(__file__).resolve().parents[2]
ARCHIVE = REPO / "research" / "archive"
DSN = os.environ.get("TRAD_PG_DSN", "")


def export_db_tables(conn, out_dir: Path):
    queries = {
        "trades_full.csv": """
            SELECT t.*, s.trading_symbol AS sub_symbol,
                   s.custom_parameters->>'source' AS bot,
                   st.name AS strategy_name, st.display_name
            FROM trades t
            JOIN user_strategy_subscriptions s ON s.id = t.subscription_id
            JOIN strategies st ON st.id = s.strategy_id
            ORDER BY t.opened_at
        """,
        "orders_full.csv": """
            SELECT o.*, s.trading_symbol AS sub_symbol,
                   s.custom_parameters->>'source' AS bot,
                   st.name AS strategy_name
            FROM orders o
            JOIN user_strategy_subscriptions s ON s.id = o.subscription_id
            JOIN strategies st ON st.id = s.strategy_id
            ORDER BY o.placed_at
        """,
        "subscriptions.csv": """
            SELECT s.*, st.name AS strategy_name, st.display_name AS strategy_display
            FROM user_strategy_subscriptions s
            JOIN strategies st ON st.id = s.strategy_id
            ORDER BY s.id
        """,
        "strategies.csv": """
            SELECT * FROM strategies ORDER BY id
        """,
    }
    for fname, sql in queries.items():
        df = pd.read_sql_query(sql, conn)
        df.to_csv(out_dir / fname, index=False)
        print(f"  wrote {fname}: {len(df)} rows")
    return df


def aggregate_backtests(out_dir: Path):
    """Walk research/ for any *_results.csv and combine into archive."""
    backtest_files = []
    for csv in sorted((REPO / "research").glob("*_results.csv")):
        try:
            df = pd.read_csv(csv)
            df["source_file"] = csv.name
            backtest_files.append(df)
        except Exception as e:
            print(f"  skip {csv.name}: {e}")
    if backtest_files:
        all_bt = pd.concat(backtest_files, ignore_index=True, sort=False)
        all_bt.to_csv(out_dir / "backtest_summary.csv", index=False)
        print(f"  wrote backtest_summary.csv: {len(all_bt)} rows")

    # Also copy individual research CSVs
    for csv in sorted((REPO / "research").glob("*.csv")):
        shutil.copy2(csv, out_dir / f"research_{csv.name}")


def coin_stats(out_dir: Path):
    """Per-coin yearly stats."""
    rows = []
    for feather in (REPO / "user_data" / "data" / "binance").glob("*_USDT-1d.feather"):
        coin = feather.name.split("_")[0]
        try:
            df = pd.read_feather(feather)
            df["date"] = pd.to_datetime(df["date"], utc=True)
            df = df.set_index("date").sort_index()
            for year in range(2019, 2027):
                sub = df.loc[f"{year}"]
                if sub.empty or len(sub) < 30:
                    continue
                ret = (sub["close"].iloc[-1] / sub["close"].iloc[0] - 1) * 100
                peak = sub["close"].cummax()
                dd_series = ((peak - sub["close"]) / peak) * 100
                max_dd = float(dd_series.max())
                vol = float(sub["close"].pct_change().std() * 100)
                rows.append({
                    "coin": coin, "year": year, "start_price": float(sub["close"].iloc[0]),
                    "end_price": float(sub["close"].iloc[-1]),
                    "high": float(sub["close"].max()), "low": float(sub["close"].min()),
                    "return_pct": round(ret, 1), "max_dd_pct": round(max_dd, 1),
                    "daily_vol_pct": round(vol, 2), "days": len(sub),
                })
        except Exception as e:
            print(f"  skip {coin}: {e}")
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "coin_stats.csv", index=False)
    print(f"  wrote coin_stats.csv: {len(df)} rows")


def fleet_snapshot(conn, out_dir: Path):
    """One-pass snapshot of fleet state."""
    cur = conn.cursor()
    cur.execute("""
        SELECT s.id AS sub_id, s.trading_symbol, s.allocated_capital,
               s.custom_parameters->>'source' AS bot, st.name AS strategy,
               s.status, s.total_trades, s.winning_trades, s.total_pnl,
               s.started_at
        FROM user_strategy_subscriptions s
        JOIN strategies st ON st.id = s.strategy_id
        WHERE s.custom_parameters->>'externally_managed' = 'true'
        ORDER BY s.id
    """)
    rows = cur.fetchall()
    cols = [d.name for d in cur.description]
    fleet = [dict(zip(cols, r)) for r in rows]

    # Also count trades and open trades
    cur.execute("""
        SELECT subscription_id,
               COUNT(*) FILTER (WHERE status='open') AS open_trades,
               COUNT(*) FILTER (WHERE status='closed') AS closed_trades,
               COALESCE(SUM(pnl) FILTER (WHERE status='closed'), 0) AS realized_pnl
        FROM trades GROUP BY subscription_id
    """)
    trade_stats = {r[0]: {"open": r[1], "closed": r[2], "realized_pnl": float(r[3])}
                   for r in cur.fetchall()}

    for b in fleet:
        ts = trade_stats.get(b["sub_id"], {"open": 0, "closed": 0, "realized_pnl": 0.0})
        b.update(ts)
        # Serialize datetimes
        for k, v in list(b.items()):
            if hasattr(v, "isoformat"):
                b[k] = v.isoformat()
            elif isinstance(v, (int, float)) or v is None:
                pass
            else:
                b[k] = str(v)

    snap = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "n_bots": len(fleet),
        "total_capital": float(sum(b["allocated_capital"] for b in fleet)),
        "total_open_trades": sum(b.get("open", 0) for b in fleet),
        "total_closed_trades": sum(b.get("closed", 0) for b in fleet),
        "total_realized_pnl": round(sum(b.get("realized_pnl", 0) for b in fleet), 2),
        "fleet": fleet,
    }
    (out_dir / "fleet_snapshot.json").write_text(json.dumps(snap, indent=2, default=float))
    print(f"  wrote fleet_snapshot.json (n_bots={snap['n_bots']}, capital=${snap['total_capital']:.0f})")


def main():
    if not DSN:
        print("ERROR: TRAD_PG_DSN not set", file=sys.stderr)
        return 1

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = ARCHIVE / ts
    latest = ARCHIVE / "latest"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Archive folder: {out_dir}\n")

    with psycopg.connect(DSN) as conn:
        print("Exporting DB tables...")
        export_db_tables(conn, out_dir)
        print("\nAggregating backtests...")
        aggregate_backtests(out_dir)
        print("\nComputing coin stats...")
        coin_stats(out_dir)
        print("\nFleet snapshot...")
        fleet_snapshot(conn, out_dir)

    # Update latest pointer
    if latest.exists() and latest.is_dir():
        shutil.rmtree(latest)
    latest.mkdir(exist_ok=True)
    for f in out_dir.iterdir():
        if f.is_file():
            shutil.copy2(f, latest / f.name)

    print(f"\n✓ Archive complete: {out_dir}")
    print(f"  latest pointer:    {latest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
