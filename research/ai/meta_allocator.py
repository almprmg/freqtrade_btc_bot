"""Meta-Allocator — dynamically reallocate capital across the 20-bot fleet.

Each week, read each subscription's recent rolling performance from
trad_pg.trades, score them, and adjust `allocated_capital` to favor
winners. Losers shrink, winners grow — within configurable bounds.

Score per bot:
  s = sharpe * sqrt(win_rate) * (1 - clamp(max_dd, 0, 0.5))

  This rewards high Sharpe, high win rate, low DD. Negative-Sharpe
  bots get score ~0 → minimum allocation.

Allocation rule:
  - Compute fleet-total budget (sum of current allocations)
  - Rank bots by score
  - TOP 30% of bots get 70% of total budget (split by score weight)
  - REST get 30% (split equally for diversification)
  - Each bot floor: 5% of its current; ceiling: 200% of current
    (gradual changes, no whiplash)

Run mode:
  --dry-run     : compute new allocations, print, don't write
  --apply       : write new allocations to user_strategy_subscriptions

Schedule: cron weekly (Sundays). For testing, run manually.

Env:
  TRAD_PG_DSN  (postgres connection string)
  LOOKBACK_DAYS (default 90)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import psycopg


LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "90"))
DSN = os.environ.get("TRAD_PG_DSN", "")

TOP_TIER_FRAC = 0.30      # fraction of bots considered "top"
TOP_BUDGET_FRAC = 0.70    # fraction of budget given to top tier
BOTTOM_BUDGET_FRAC = 0.30
MIN_FACTOR = 0.05         # never reduce below 5% of current (prevent zeroing)
MAX_FACTOR = 2.00         # never grow above 2x current


def fetch_active_bots(conn) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute("""
        SELECT s.id AS sub_id, s.allocated_capital, s.trading_symbol,
               s.custom_parameters->>'source' AS bot, st.name AS strategy
        FROM user_strategy_subscriptions s
        JOIN strategies st ON st.id = s.strategy_id
        WHERE s.status = 'active'
          AND s.custom_parameters->>'externally_managed' = 'true'
        ORDER BY s.id
    """)
    rows = cur.fetchall()
    cols = [d.name for d in cur.description]
    return pd.DataFrame(rows, columns=cols)


def fetch_trades(conn, sub_id: int, since: datetime) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute("""
        SELECT id, symbol, status, entry_price, exit_price, quantity, pnl,
               opened_at, closed_at, fees
        FROM trades
        WHERE subscription_id = %s AND opened_at >= %s
        ORDER BY opened_at
    """, (sub_id, since))
    rows = cur.fetchall()
    cols = [d.name for d in cur.description]
    return pd.DataFrame(rows, columns=cols)


def score_bot(trades: pd.DataFrame, allocated: float) -> dict:
    if trades.empty:
        return {"score": 0.0, "sharpe": 0.0, "win_rate": 0.0,
                "max_dd": 0.0, "total_pnl": 0.0, "n_trades": 0}
    closed = trades[trades["status"] == "closed"].copy()
    if closed.empty:
        return {"score": 0.0, "sharpe": 0.0, "win_rate": 0.0,
                "max_dd": 0.0, "total_pnl": 0.0, "n_trades": 0}

    closed["ret"] = closed["pnl"].astype(float) / allocated
    rets = closed["ret"].values
    sharpe = (rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0
    win_rate = (rets > 0).mean()

    # Running equity curve → max DD
    eq = np.cumsum(rets * float(allocated))
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / np.maximum(peak, 1.0)
    max_dd = float(dd.max()) if len(dd) else 0.0

    score = max(sharpe, 0.0) * np.sqrt(max(win_rate, 0.0)) * (1 - min(max_dd, 0.5))
    return {
        "score": round(score, 3),
        "sharpe": round(float(sharpe), 2),
        "win_rate": round(float(win_rate), 3),
        "max_dd": round(max_dd, 3),
        "total_pnl": round(float(closed["pnl"].sum()), 2),
        "n_trades": int(len(closed)),
    }


def compute_new_allocations(df: pd.DataFrame) -> pd.DataFrame:
    """Given a DF with sub_id, allocated_capital, score → compute new_allocated."""
    df = df.copy()
    total_budget = df["allocated_capital"].astype(float).sum()
    n = len(df)

    # If no scores meaningful, keep current allocations.
    if df["score"].sum() <= 0:
        df["new_allocated"] = df["allocated_capital"]
        df["change_pct"] = 0.0
        return df

    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    top_n = max(1, int(np.ceil(n * TOP_TIER_FRAC)))
    df["tier"] = ["TOP" if i < top_n else "REST" for i in range(n)]

    top = df[df["tier"] == "TOP"].copy()
    rest = df[df["tier"] == "REST"].copy()

    top_budget = total_budget * TOP_BUDGET_FRAC
    rest_budget = total_budget * BOTTOM_BUDGET_FRAC

    # Top: weight by score
    top["raw"] = top_budget * top["score"] / max(top["score"].sum(), 1e-9)
    # Rest: equal share
    rest["raw"] = rest_budget / max(len(rest), 1)

    proposed = pd.concat([top, rest])
    # Apply bounds: [min_factor, max_factor] * current
    proposed["new_allocated"] = proposed.apply(
        lambda r: float(np.clip(
            r["raw"],
            r["allocated_capital"] * MIN_FACTOR,
            r["allocated_capital"] * MAX_FACTOR,
        )),
        axis=1,
    )
    # Rescale to preserve total budget after clipping
    scale = total_budget / proposed["new_allocated"].sum()
    proposed["new_allocated"] = (proposed["new_allocated"] * scale).round(2)
    proposed["change_pct"] = (
        (proposed["new_allocated"] - proposed["allocated_capital"])
        / proposed["allocated_capital"].replace(0, 1) * 100
    ).round(1)
    return proposed.sort_values("score", ascending=False).reset_index(drop=True)


def apply_allocations(conn, allocations: pd.DataFrame) -> None:
    cur = conn.cursor()
    for _, row in allocations.iterrows():
        cur.execute(
            "UPDATE user_strategy_subscriptions SET allocated_capital = %s WHERE id = %s",
            (float(row["new_allocated"]), int(row["sub_id"])),
        )
    conn.commit()
    print(f"Applied {len(allocations)} updates.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Write new allocations to DB (default: dry-run)")
    parser.add_argument("--lookback", type=int, default=LOOKBACK_DAYS)
    args = parser.parse_args()

    if not DSN:
        print("ERROR: TRAD_PG_DSN env not set", file=sys.stderr)
        return 1

    since = datetime.now(timezone.utc) - timedelta(days=args.lookback)
    print(f"Lookback window: {args.lookback} days (since {since.date()})")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}\n")

    with psycopg.connect(DSN, autocommit=False) as conn:
        bots = fetch_active_bots(conn)
        print(f"Found {len(bots)} active externally-managed bots\n")
        # Score each
        scored = []
        for _, b in bots.iterrows():
            trades = fetch_trades(conn, int(b["sub_id"]), since)
            stats = score_bot(trades, float(b["allocated_capital"]))
            scored.append({**b.to_dict(), **stats})
        df = pd.DataFrame(scored)
        allocations = compute_new_allocations(df)
        print("=" * 120)
        cols = ["sub_id", "bot", "strategy", "allocated_capital",
                "n_trades", "total_pnl", "sharpe", "win_rate", "max_dd",
                "score", "tier", "new_allocated", "change_pct"]
        present = [c for c in cols if c in allocations.columns]
        print(allocations[present].to_string(index=False))
        print("=" * 120)
        old_total = allocations["allocated_capital"].sum()
        new_total = allocations["new_allocated"].sum()
        print(f"\nOld total budget: ${old_total:.2f}")
        print(f"New total budget: ${new_total:.2f}")

        if args.apply:
            apply_allocations(conn, allocations)
        else:
            print("\n(Dry-run: re-run with --apply to write to DB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
