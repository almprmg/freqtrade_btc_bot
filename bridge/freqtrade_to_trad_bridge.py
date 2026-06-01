"""Mirror Freqtrade SQLite trades into the trad_pg `trades` table.

The Freqtrade bot (`freqtrade_rebalance` container) is the authoritative
executor for the rebalance strategy — running the exact `BtcRebalanceStrategy`
code that produced the +166% backtest. The admin's dashboard reads from
trad_pg, so this bridge polls the bot's SQLite every POLL_INTERVAL seconds
and writes new/updated trades to the matching admin `trades` table.

Mapping is one-way (Freqtrade is source of truth):
  Freqtrade trade.id        → trades.exchange_order_id-ish key (we map via
                              a fresh client_order_id per Freqtrade id)
  Freqtrade trade.amount    → trades.quantity
  Freqtrade trade.open_rate → trades.entry_price
  Freqtrade trade.close_rate→ trades.exit_price
  Freqtrade close_profit_abs → trades.pnl
  Freqtrade is_open == false → trades.status='closed', set exit_order_id

Idempotency: we keep `bridge_meta` in trad_pg (a JSONB blob inside
admin_audit_logs[type=bridge_state]) tracking the highest Freqtrade trade
id we've imported per subscription. On every poll we only fetch
Freqtrade trades with id > last_seen and trades that are still open (so
their close gets picked up).
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg

SUBSCRIPTION_ID = int(os.environ["BRIDGE_SUBSCRIPTION_ID"])
USER_ID = int(os.environ["BRIDGE_USER_ID"])
FREQTRADE_DB = os.environ.get(
    "FREQTRADE_SQLITE_PATH", "/data/freqtrade/tradesv3_rebalance.sqlite"
)
TRAD_PG_DSN = os.environ["TRAD_PG_DSN"]
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "30"))
SYMBOL_DEFAULT = os.environ.get("BRIDGE_SYMBOL", "BTCUSDT")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [bridge] %(message)s")
log = logging.getLogger("bridge")


def fmt_symbol(pair: str) -> str:
    # Freqtrade uses BTC/USDT; trad uses BTCUSDT.
    return pair.replace("/", "") if "/" in pair else pair


def to_dt(s: Any) -> datetime | None:
    if not s:
        return None
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    # SQLite returns text — '2026-06-01 11:56:26.109155'
    try:
        return datetime.fromisoformat(str(s)).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def fetch_freqtrade_trades(sqlite_path: str) -> list[dict]:
    if not os.path.exists(sqlite_path):
        return []
    con = sqlite3.connect(sqlite_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT id, pair, is_open, open_date, close_date, amount, open_rate,
               close_rate, close_profit_abs, stake_amount, fee_open_cost,
               fee_close_cost, exit_reason
        FROM trades
        ORDER BY id ASC
        """
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def upsert_trade(cur: psycopg.Cursor, ft: dict) -> None:
    """Idempotent upsert keyed on (subscription_id, freqtrade_trade_id).
    The Freqtrade id lives in trades.fees_breakdown.freqtrade_id so we can
    identify already-imported rows without a schema change.
    """
    ft_id = int(ft["id"])
    symbol = fmt_symbol(ft["pair"])
    is_open = bool(ft["is_open"])
    open_dt = to_dt(ft["open_date"])
    close_dt = to_dt(ft["close_date"])
    qty = float(ft["amount"] or 0)
    entry_px = float(ft["open_rate"] or 0)
    exit_px = float(ft["close_rate"]) if ft.get("close_rate") else None
    pnl = float(ft["close_profit_abs"]) if ft.get("close_profit_abs") is not None else None
    stake = float(ft.get("stake_amount") or qty * entry_px)
    fee_total = float(ft.get("fee_open_cost") or 0) + float(ft.get("fee_close_cost") or 0)
    exit_reason_ft = (ft.get("exit_reason") or "").lower()
    exit_reason = "manual"  # rebalance has no real "stop_loss" / "take_profit" mapping
    if "roi" in exit_reason_ft or "take_profit" in exit_reason_ft:
        exit_reason = "take_profit"
    elif "stop" in exit_reason_ft:
        exit_reason = "stop_loss"

    # Look up existing trade row by the bridge marker.
    cur.execute(
        """
        SELECT id, status FROM trades
        WHERE subscription_id = %s
          AND (fees_breakdown ->> 'freqtrade_id')::int = %s
        """,
        (SUBSCRIPTION_ID, ft_id),
    )
    existing = cur.fetchone()

    if existing is None:
        # New trade — also need to insert an entry order row (FK NOT NULL).
        client_oid = f"bridge-{ft_id}-entry-{uuid.uuid4().hex[:8]}"
        cur.execute(
            """
            INSERT INTO orders (subscription_id, user_id, client_order_id, symbol,
                                side, type, quantity, price, filled_qty, avg_fill_price,
                                status, quote_quantity, commission, placed_at, filled_at,
                                strategy_signal)
            VALUES (%s, %s, %s, %s, 'buy', 'limit', %s, %s, %s, %s, 'filled', %s, %s, %s, %s, 'freqtrade:rebalance')
            RETURNING id
            """,
            (SUBSCRIPTION_ID, USER_ID, client_oid, symbol, qty, entry_px,
             qty, entry_px, stake, fee_total / 2, open_dt, open_dt),
        )
        entry_order_id = cur.fetchone()[0]

        exit_order_id = None
        if not is_open and exit_px is not None:
            client_oid2 = f"bridge-{ft_id}-exit-{uuid.uuid4().hex[:8]}"
            cur.execute(
                """
                INSERT INTO orders (subscription_id, user_id, client_order_id, symbol,
                                    side, type, quantity, price, filled_qty, avg_fill_price,
                                    status, quote_quantity, commission, placed_at, filled_at,
                                    strategy_signal)
                VALUES (%s, %s, %s, %s, 'sell', 'limit', %s, %s, %s, %s, 'filled', %s, %s, %s, %s, 'freqtrade:rebalance')
                RETURNING id
                """,
                (SUBSCRIPTION_ID, USER_ID, client_oid2, symbol, qty, exit_px,
                 qty, exit_px, qty * exit_px, fee_total / 2, close_dt, close_dt),
            )
            exit_order_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO trades (subscription_id, entry_order_id, exit_order_id, symbol,
                                direction, entry_price, exit_price, quantity, pnl, fees,
                                fees_breakdown, exit_reason, status, opened_at, closed_at)
            VALUES (%s, %s, %s, %s, 'long', %s, %s, %s, %s, %s,
                    jsonb_build_object('freqtrade_id', %s::int, 'source', 'freqtrade_rebalance'),
                    %s, %s, %s, %s)
            RETURNING id
            """,
            (SUBSCRIPTION_ID, entry_order_id, exit_order_id, symbol,
             entry_px, exit_px, qty, pnl, fee_total,
             ft_id,
             exit_reason if not is_open else None,
             "open" if is_open else "closed",
             open_dt, close_dt),
        )
        new_id = cur.fetchone()[0]
        log.info(
            "INSERT trade ft=%s -> trad=%s (%s, %s, qty=%.6f)",
            ft_id, new_id, symbol, "open" if is_open else "closed", qty,
        )
        return

    trad_id, current_status = existing
    # Update only if state changed (open → closed) or numbers changed.
    if current_status == "open" and not is_open:
        # Close the trade.
        client_oid2 = f"bridge-{ft_id}-exit-{uuid.uuid4().hex[:8]}"
        cur.execute(
            """
            INSERT INTO orders (subscription_id, user_id, client_order_id, symbol,
                                side, type, quantity, price, filled_qty, avg_fill_price,
                                status, quote_quantity, commission, placed_at, filled_at,
                                strategy_signal)
            VALUES (%s, %s, %s, %s, 'sell', 'limit', %s, %s, %s, %s, 'filled', %s, %s, %s, %s, 'freqtrade:rebalance')
            RETURNING id
            """,
            (SUBSCRIPTION_ID, USER_ID, client_oid2, symbol, qty, exit_px,
             qty, exit_px, qty * exit_px, fee_total / 2, close_dt, close_dt),
        )
        exit_order_id = cur.fetchone()[0]
        cur.execute(
            """
            UPDATE trades
            SET exit_order_id = %s, exit_price = %s, pnl = %s, fees = %s,
                exit_reason = %s::trade_exit_reason, status = 'closed', closed_at = %s
            WHERE id = %s
            """,
            (exit_order_id, exit_px, pnl, fee_total, exit_reason, close_dt, trad_id),
        )
        log.info("CLOSE trade ft=%s -> trad=%s pnl=%s", ft_id, trad_id, pnl)


def update_subscription_stats(cur: psycopg.Cursor) -> None:
    cur.execute(
        """
        WITH s AS (
          SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE pnl > 0) AS wins,
            COALESCE(SUM(pnl), 0) AS pnl_sum
          FROM trades
          WHERE subscription_id = %s AND status = 'closed'
        )
        UPDATE user_strategy_subscriptions
        SET total_trades = s.total, winning_trades = s.wins, total_pnl = s.pnl_sum
        FROM s
        WHERE user_strategy_subscriptions.id = %s
        """,
        (SUBSCRIPTION_ID, SUBSCRIPTION_ID),
    )


def main_loop() -> None:
    log.info(
        "starting: sub_id=%s user_id=%s ft_db=%s poll=%ss",
        SUBSCRIPTION_ID, USER_ID, FREQTRADE_DB, POLL_INTERVAL,
    )
    while True:
        try:
            fts = fetch_freqtrade_trades(FREQTRADE_DB)
            if fts:
                with psycopg.connect(TRAD_PG_DSN, autocommit=False) as conn:
                    with conn.cursor() as cur:
                        for ft in fts:
                            upsert_trade(cur, ft)
                        update_subscription_stats(cur)
                    conn.commit()
                log.info("synced %d freqtrade trades", len(fts))
            else:
                log.info("no freqtrade trades yet")
        except Exception as exc:
            log.exception("bridge cycle failed: %s", exc)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main_loop()
