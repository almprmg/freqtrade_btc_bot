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


@pytest.mark.xfail(strict=True, reason=(
    "No once-per-candle guard: btc_dca_hold_strategy.py adjust_trade_position says 'Run only "
    "on a new daily bar (one DCA per day)' but returns PER_BUY_USD on EVERY call. Live "
    "freqtrade calls adjust_trade_position on every process loop "
    "(freqtradebot.process -> process_open_trade_positions, throttle 30s in config.dca.json), "
    "not once per candle as in backtesting, so V1_BLIND buys $100 per filled loop until the "
    "wallet is drained instead of $100/day. Input: two calls 1 minute apart within the same "
    "daily candle. Expected second call None, actual 100.0."))
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


@pytest.mark.xfail(strict=True, reason=(
    "V1_BLIND is documented 'never sell' but minimal_roi = {'0': 10.0} (non-TP modes) closes "
    "the whole accumulated position at +1000% vs average cost. Fix: minimal_roi = {} for "
    "non-TP modes."))
def test_v1_never_roi_exits(strat):
    assert not roi_would_exit(strat, FakeTrade(1.0, 100.0), profit=12.0)
