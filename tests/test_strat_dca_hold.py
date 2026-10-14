"""Behavioural tests — BtcDcaHoldStrategy (freqtrade_dca, DCA_MODE=V1_BLIND).

V1_BLIND: "add $100 every daily close, never sell". One growing trade; DCA
via adjust_trade_position; no exit signals.
"""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import pytest

from tests._ft_helpers import (
    START, FakeTrade, adjust, assert_no_lookahead, attach_runtime, bear_ohlcv, bull_ohlcv,
    col, load_strategy, make_strategy, roi_would_exit, run_pipeline,
)

FILE = "btc_dca_hold_strategy.py"


@pytest.fixture
def mod():
    return load_strategy(FILE, {"DCA_MODE": "V1_BLIND"})


@pytest.fixture
def strat(mod):
    return make_strategy(mod.BtcDcaHoldStrategy, stake_amount=100, max_open_trades=-1)


def test_mode(mod, strat):
    assert mod.MODE == "V1_BLIND"
    assert strat.use_exit_signal is False and strat.position_adjustment_enable is True


def test_indicators(strat):
    out = run_pipeline(strat, bull_ohlcv())
    for c in ("rsi", "ema200", "high_90d", "dd_from_90d_high"):
        assert c in out.columns


def test_no_lookahead(strat):
    assert_no_lookahead(strat, bear_ohlcv(), cuts=[230, 300, 340])


@pytest.mark.parametrize("df_fn", [bull_ohlcv, bear_ohlcv])
def test_blind_entry_in_any_regime_never_exit(strat, df_fn):
    out = run_pipeline(strat, df_fn())
    assert col(out, "enter_long").iloc[-1] == 1
    assert (col(out, "exit_long") == 0).all()
    assert (col(out, "enter_long")[out["ema200"].isna()] == 0).all()


def test_initial_stake_is_100(strat):
    assert strat.custom_stake_amount("BTC/USDT", None, 1, 10, 5, 1000, 1, None, "long") == 100.0


def test_adjust_adds_100_regardless_of_rsi(strat):
    attach_runtime(strat, pd.DataFrame([{"rsi": 85.0, "close": 100.0, "ema200": 50.0,
                                         "dd_from_90d_high": 0.0}]), free=10_000)
    assert adjust(strat, FakeTrade(1.0, 100.0), 100.0) == 100.0


def test_adjust_capped_by_max_stake(strat):
    attach_runtime(strat, pd.DataFrame([{"rsi": 50.0, "close": 100.0, "ema200": 50.0,
                                         "dd_from_90d_high": 0.0}]), free=40)
    assert adjust(strat, FakeTrade(1.0, 100.0), 100.0, max_stake=40.0) == 40.0


# Regression (was strict xfail): one DCA per analysed daily candle.
def test_one_dca_per_daily_candle(strat):
    attach_runtime(strat, pd.DataFrame([{"rsi": 50.0, "close": 100.0, "ema200": 50.0,
                                         "dd_from_90d_high": 0.0}]), free=10_000)
    trade = FakeTrade(1.0, 100.0)
    t0 = START + timedelta(days=300, hours=1)
    assert adjust(strat, trade, 100.0, now=t0) == 100.0
    trade.amount += 1.0  # first order filled
    trade.stake_amount += 100.0
    trade.nr_of_successful_entries += 1
    assert adjust(strat, trade, 100.0, now=t0 + timedelta(minutes=1)) is None


# Regression (was strict xfail): never-ROI strategies use minimal_roi = {}.
def test_v1_never_roi_exits(strat):
    assert not roi_would_exit(strat, FakeTrade(1.0, 100.0), profit=12.0)


def _flat_row(**extra):
    return pd.DataFrame([{"rsi": 50.0, "close": 100.0, "ema200": 50.0,
                          "dd_from_90d_high": 0.0, **extra}])


def test_60_loop_calls_in_one_day_buy_once(strat):
    """Live loop: adjust_trade_position runs every ~30s. 60 consecutive calls
    within one daily candle (each buy filling immediately) -> exactly 1 buy."""
    attach_runtime(strat, _flat_row(date=START + timedelta(days=299)), free=200_000)
    trade = FakeTrade(1.0, 100.0)
    t0 = START + timedelta(days=300, hours=1)
    buys = 0
    for i in range(60):
        out = adjust(strat, trade, 100.0, now=t0 + timedelta(seconds=30 * i))
        if out:
            buys += 1
            trade.amount += out / 100.0
            trade.stake_amount += out
            trade.nr_of_successful_entries += 1
    assert buys == 1
    # next closed candle -> the next DCA
    attach_runtime(strat, _flat_row(date=START + timedelta(days=300)), free=200_000)
    assert adjust(strat, trade, 100.0, now=t0 + timedelta(days=1)) == 100.0


def test_no_dca_while_order_open(strat):
    attach_runtime(strat, _flat_row(), free=10_000)
    trade = FakeTrade(1.0, 100.0)
    trade.has_open_orders = True
    assert adjust(strat, trade, 100.0) is None


def test_no_extra_dca_on_the_opening_day(strat):
    """The initial entry already bought on the day the trade opened."""
    candle = START + timedelta(days=299)
    attach_runtime(strat, _flat_row(date=candle), free=10_000)
    trade = FakeTrade(1.0, 100.0, open_date=candle + timedelta(days=1, hours=2))
    assert adjust(strat, trade, 100.0, now=candle + timedelta(days=1, hours=3)) is None
    attach_runtime(strat, _flat_row(date=candle + timedelta(days=1)), free=10_000)
    assert adjust(strat, trade, 100.0, now=candle + timedelta(days=2, hours=1)) == 100.0
