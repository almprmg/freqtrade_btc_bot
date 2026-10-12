"""C14 regression tests — BtcDynamicRebalanceStrategy profit anchor + cooldown.

Before the fix, DR_PROFIT_* fired whenever |current_profit| (vs the average
entry rate) >= threshold, i.e. on EVERY loop once past it -> churn. Now the
trigger measures the portfolio move vs an anchor re-set at each fill.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

os.environ.setdefault("DR_MODE", "DR_PROFIT_20")

from user_data.strategies import btc_dynamic_rebalance_strategy as dr  # noqa: E402

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------- pure fns
def test_anchor_value_marks_position_at_fill_price():
    assert dr.anchor_value(0.75, 100.0, 25.0) == pytest.approx(100.0)


@pytest.mark.parametrize("total,fires", [
    (100.0, False), (119.9, False), (120.0, True), (130.0, True),
    (80.1, False), (80.0, True), (50.0, True),
])
def test_profit_trigger_symmetric_threshold(total, fires):
    assert dr.profit_trigger_fires(100.0, total, 0.20) is fires


def test_portfolio_move_guards_bad_anchor():
    assert dr.portfolio_move(0.0, 123.0) == 0.0
    assert dr.portfolio_move(None, 123.0) == 0.0


def test_cooldown():
    assert dr.in_cooldown(True, None, T0, 60) is True               # open order
    assert dr.in_cooldown(False, None, T0, 60) is False
    assert dr.in_cooldown(False, T0 - timedelta(minutes=5), T0, 60) is True
    assert dr.in_cooldown(False, T0 - timedelta(minutes=61), T0, 60) is False
    naive = (T0 - timedelta(seconds=1)).replace(tzinfo=None)
    assert dr.in_cooldown(False, naive, T0, 60) is True
    assert dr.in_cooldown(False, T0, T0, 0) is False                # disabled


# ------------------------------------------------- adjust_trade_position
class FakeTrade:
    """Just enough of freqtrade's Trade for adjust_trade_position."""

    def __init__(self, amount, fills):
        self.pair = "BTC/USDT"
        self.stake_currency = "USDT"
        self.amount = amount
        self.has_open_orders = False
        self._fills = fills  # list of (price, filled_at)
        self._cd: dict = {}

    def select_filled_orders(self, side=None):
        return [SimpleNamespace(safe_price=p, order_filled_utc=t) for p, t in self._fills]

    def get_custom_data(self, key, default=None):
        return self._cd.get(key, default)

    def set_custom_data(self, key, value):
        self._cd[key] = value


@pytest.fixture
def strat():
    if dr.P["trigger_type"] != "profit_only":
        pytest.skip("requires DR_MODE=DR_PROFIT_*")
    s = dr.BtcDynamicRebalanceStrategy({
        "stake_currency": "USDT", "stake_amount": "unlimited", "max_open_trades": 1,
        "timeframe": "1d", "dry_run": True, "dry_run_wallet": 10_000,
        "trading_mode": "spot", "exchange": {"name": "binance", "pair_whitelist": ["BTC/USDT"]},
        "runmode": "backtest", "datadir": "/tmp", "user_data_dir": "/tmp",
        "strategy_path": "user_data/strategies",
    })
    df = pd.DataFrame([{"close": 100.0, "rsi": 50.0, "ema_long": 90.0, "ema_short": 95.0}])
    s.dp = MagicMock()
    s.dp.get_analyzed_dataframe = MagicMock(return_value=(df, None))
    s.free = 25.0
    s.wallets = SimpleNamespace(get_free=lambda cur: s.free)
    return s


def _adj(s, trade, rate, now):
    # current_profit deliberately huge: the old code fired on this alone.
    return s.adjust_trade_position(
        trade, now, rate, current_profit=5.0, min_stake=1.0, max_stake=10_000.0,
        current_entry_rate=rate, current_exit_rate=rate,
        current_entry_profit=5.0, current_exit_profit=5.0,
    )


def test_no_rebalance_inside_band_even_with_large_trade_profit(strat):
    # 0.75 coin @100 + 25 free = 100 anchor. Price 110 -> portfolio 107.5 (+7.5%).
    trade = FakeTrade(0.75, [(100.0, T0)])
    assert _adj(strat, trade, 110.0, T0 + timedelta(days=1)) is None
    assert trade.get_custom_data(dr.ANCHOR_KEY) == pytest.approx(100.0)


def test_fires_once_then_rearms_after_fill(strat):
    trade = FakeTrade(0.75, [(100.0, T0)])
    # Price 130 -> portfolio 122.5 (+22.5%) -> sell back to 75%.
    out = _adj(strat, trade, 130.0, T0 + timedelta(days=1))
    assert out is not None and out < 0
    # Simulate the sell fill: amount/free move to 75/25 at 130.
    total = 0.75 * 130 + 25
    trade.amount = 0.75 * total / 130
    strat.free = 0.25 * total
    trade._fills.append((130.0, T0 + timedelta(days=1)))
    # Next loop, same price, past the old (avg-entry) threshold: must NOT fire.
    assert _adj(strat, trade, 131.0, T0 + timedelta(days=1, hours=2)) is None
    assert trade.get_custom_data(dr.ANCHOR_KEY) == pytest.approx(total)


def test_cooldown_blocks_duplicate_fill(strat):
    trade = FakeTrade(0.75, [(100.0, T0)])
    trade.has_open_orders = True
    assert _adj(strat, trade, 130.0, T0 + timedelta(days=1)) is None
    trade.has_open_orders = False
    # Last fill 1 second ago -> still cooling down.
    assert _adj(strat, trade, 130.0, T0 + timedelta(seconds=1)) is None
