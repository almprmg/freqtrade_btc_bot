from __future__ import annotations

import os
import sys
import types

import pytest

# The bridge reads its wiring from env at import time.
os.environ.setdefault("BRIDGE_SUBSCRIPTION_ID", "1")
os.environ.setdefault("BRIDGE_USER_ID", "1")
os.environ.setdefault("TRAD_PG_DSN", "postgresql://unused")

# The pure helpers under test never touch the DB; psycopg only lives in the
# bridge image, so stub it when it isn't installed locally.
if "psycopg" not in sys.modules:
    try:
        import psycopg  # noqa: F401
    except ImportError:
        stub = types.ModuleType("psycopg")
        stub.Cursor = object
        sys.modules["psycopg"] = stub

from bridge.freqtrade_to_trad_bridge import adjustment_orders, realized_of  # noqa: E402


def _o(oid: int, side: str) -> dict:
    return {"id": oid, "ft_order_side": side}


def test_open_trade_mirrors_everything_but_the_initial_entry():
    # entry buy, DCA buy, DCA buy, partial sell — the dynrebal ETH pattern
    orders = [_o(1, "buy"), _o(3, "buy"), _o(4, "buy"), _o(7, "sell")]
    assert [o["id"] for o in adjustment_orders(orders, is_open=True)] == [3, 4, 7]


def test_closed_trade_also_skips_the_final_exit():
    orders = [_o(1, "buy"), _o(2, "buy"), _o(5, "sell"), _o(6, "sell")]
    assert [o["id"] for o in adjustment_orders(orders, is_open=False)] == [2, 5]


def test_plain_trade_has_no_adjustments():
    assert adjustment_orders([_o(1, "buy")], is_open=True) == []
    assert adjustment_orders([_o(1, "buy"), _o(2, "sell")], is_open=False) == []
    assert adjustment_orders([], is_open=True) == []


def test_realized_of_handles_missing():
    assert realized_of({"realized_profit": -1.20742141}) == pytest.approx(-1.20742141)
    assert realized_of({"realized_profit": None}) == 0.0
    assert realized_of({}) == 0.0
