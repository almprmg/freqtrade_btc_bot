"""Bridge visibility: bot_deployments heartbeat + strategy_logs trade events.

Unit tests run everywhere. The DB tests need a scratch Postgres with the
visibility_phase0 schema and the trading_backend tests/sql fixture
(subs 9003/9004, user 9001); point BRIDGE_TEST_PG_DSN at it. Each DB test
runs in one transaction that is rolled back.
"""
from __future__ import annotations

import os
import sys
import types
from datetime import datetime, timezone

import pytest

os.environ.setdefault("BRIDGE_SUBSCRIPTION_ID", "1")
os.environ.setdefault("BRIDGE_USER_ID", "1")
os.environ.setdefault("TRAD_PG_DSN", "postgresql://unused")

if "psycopg" not in sys.modules:
    try:
        import psycopg  # noqa: F401
    except ImportError:
        stub = types.ModuleType("psycopg")
        stub.Cursor = object
        stub.Connection = object
        sys.modules["psycopg"] = stub

from bridge import freqtrade_to_trad_bridge as br  # noqa: E402


def _ft(**kw):
    base = {"id": 7, "pair": "BTC/USDT", "is_open": 1, "open_date": "2026-10-14 10:00:00",
            "close_date": None, "amount": 0.05, "open_rate": 80000.0, "close_rate": None,
            "close_profit_abs": None, "stake_amount": 4000.0, "fee_open_cost": 4.0,
            "fee_close_cost": 0.0, "exit_reason": None, "realized_profit": 0.0,
            "enter_tag": "shield:bull_rs_aggr", "orders": []}
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# unit
# --------------------------------------------------------------------------- #
def test_trade_opened_event_carries_enter_tag():
    msg, meta = br.trade_opened_event(_ft(), 42, "BTCUSDT")
    assert "enter_tag shield:bull_rs_aggr" in msg
    assert meta["enter_tag"] == "shield:bull_rs_aggr"
    assert meta["trade_id"] == 42 and meta["freqtrade_id"] == 7


def test_trade_opened_event_without_tag_has_no_tag_text():
    msg, meta = br.trade_opened_event(_ft(enter_tag=""), 1, "BTCUSDT")
    assert "enter_tag" not in msg and meta["enter_tag"] is None


def test_trade_closed_event_keeps_raw_freqtrade_reason():
    ft = _ft(is_open=0, close_rate=82000.0, close_profit_abs=96.5, exit_reason="roi",
             close_date="2026-10-14 12:00:00")
    msg, meta = br.trade_closed_event(ft, 42, "BTCUSDT", "take_profit")
    assert "exit_reason roi" in msg and "pnl 96.5000" in msg
    assert meta["exit_reason_raw"] == "roi" and meta["exit_reason"] == "take_profit"


class _FakeCursor:
    def __init__(self, log):
        self.log = log
        self._row = (1,)

    def execute(self, sql, params=None):
        self.log.append((" ".join(sql.split())[:40], params))

    def fetchone(self):
        return self._row

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConn:
    def __init__(self):
        self.log: list = []

    def transaction(self):
        return _NullCtx()

    def cursor(self):
        return _FakeCursor(self.log)


class _NullCtx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _events(conn):
    return [p for s, p in conn.log if s.startswith("INSERT INTO strategy_logs")]


def test_reporter_logs_each_distinct_error_once_and_rearms_after_recovery():
    rep, conn = br.Reporter(), _FakeConn()
    rep.report(conn, "boom", None)
    rep.report(conn, "boom", None)
    assert len(_events(conn)) == 1
    rep.report(conn, None, datetime.now(timezone.utc))
    rep.report(conn, "boom", None)
    assert len(_events(conn)) == 2


def test_reporter_heartbeats_every_cycle():
    rep, conn = br.Reporter(), _FakeConn()
    for _ in range(3):
        rep.report(conn, None, None)
    beats = [s for s, _ in conn.log if s.startswith("INSERT INTO bot_deployments")]
    assert len(beats) == 3
    assert _events(conn) == []  # healthy cycles write nothing to strategy_logs


def test_reporter_survives_missing_table():
    class _Boom(_FakeConn):
        def cursor(self):
            raise RuntimeError('relation "bot_deployments" does not exist')

    rep = br.Reporter()
    rep.report(_Boom(), None, None)  # must not raise
    assert rep.heartbeat_warned


# --------------------------------------------------------------------------- #
# DB
# --------------------------------------------------------------------------- #
DSN = os.environ.get("BRIDGE_TEST_PG_DSN")
db = pytest.mark.skipif(not DSN, reason="BRIDGE_TEST_PG_DSN not set")


@pytest.fixture
def cur(monkeypatch):
    import psycopg

    monkeypatch.setattr(br, "SUBSCRIPTION_ID", 9003)
    monkeypatch.setattr(br, "USER_ID", 9001)
    monkeypatch.setattr(br, "FREQTRADE_DB", "/data/freqtrade/tradesv3_test.sqlite")
    monkeypatch.setattr(br, "BOT_NAME", "freqtrade_test")
    conn = psycopg.connect(DSN)
    try:
        with conn.cursor() as c:
            yield c
    finally:
        conn.rollback()
        conn.close()


@db
def test_heartbeat_inserts_then_updates_one_row(cur):
    assert br.heartbeat(cur, None, datetime.now(timezone.utc))
    assert br.heartbeat(cur, "x failed", None)
    cur.execute("SELECT count(*), max(status::text), max(last_error), "
                "bool_and(last_trade_sync_at IS NOT NULL) FROM bot_deployments "
                "WHERE sqlite_path = '/data/freqtrade/tradesv3_test.sqlite'")
    assert cur.fetchone() == (1, "error", "x failed", True)


@db
def test_heartbeat_refuses_trade_db_owned_by_another_subscription(cur, monkeypatch):
    assert br.heartbeat(cur, None, None)
    monkeypatch.setattr(br, "SUBSCRIPTION_ID", 9004)
    monkeypatch.setattr(br, "BOT_NAME", "freqtrade_test_dup")
    assert br.heartbeat(cur, None, None) is False
    cur.execute("SELECT subscription_id FROM bot_deployments "
                "WHERE sqlite_path = '/data/freqtrade/tradesv3_test.sqlite'")
    assert cur.fetchone() == (9003,)


@db
def test_upsert_trade_logs_open_then_close_events(cur):
    br.upsert_trade(cur, _ft(id=901))
    br.upsert_trade(cur, _ft(id=901, is_open=0, close_rate=82000.0, close_profit_abs=96.5,
                             exit_reason="exit_signal", close_date="2026-10-14 12:00:00"))
    cur.execute("SELECT event_type, metadata->>'enter_tag', metadata->>'exit_reason_raw' "
                "FROM strategy_logs WHERE subscription_id = 9003 "
                "AND metadata->>'freqtrade_id' = '901' ORDER BY id")
    assert cur.fetchall() == [
        ("trade_opened", "shield:bull_rs_aggr", None),
        ("trade_closed", "shield:bull_rs_aggr", "exit_signal"),
    ]


@db
def test_resync_of_known_trade_writes_no_duplicate_events(cur):
    for _ in range(3):
        br.upsert_trade(cur, _ft(id=902))
    cur.execute("SELECT count(*) FROM strategy_logs WHERE subscription_id = 9003 "
                "AND metadata->>'freqtrade_id' = '902'")
    assert cur.fetchone() == (1,)
