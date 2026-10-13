"""Behavioural tests — BtcMetaAdaptiveStrategy (freqtrade_avax MA_RELAX, freqtrade_ada MA_BAL).

State machine CASH/DEF/BAL/AGGR; ANY -> CASH when price DD from the rolling 60d
high >= cash_dd; CASH is sticky for `cooldown` bars; exit only in CASH.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests._ft_helpers import (
    ROI_XFAIL_REASON, SIZING_XFAIL_REASON, FakeTrade, adjust, allocation_after_trim,
    assert_no_lookahead, attach_runtime, bull_ohlcv, col, load_strategy, make_strategy,
    ohlcv_from_returns, roi_would_exit, run_pipeline,
)

FILE = "btc_meta_adaptive_strategy.py"
MODES = {"MA_RELAX": (0.20, 7), "MA_BAL": (0.15, 14)}


@pytest.fixture(params=list(MODES))
def mode(request):
    return request.param


@pytest.fixture
def mod(mode):
    return load_strategy(FILE, {"MA_MODE": mode})


@pytest.fixture
def strat(mod):
    return make_strategy(mod.BtcMetaAdaptiveStrategy, pair="AVAX/USDT")


def _path(*legs, noise=0.0):
    return ohlcv_from_returns(np.concatenate([np.full(n, r) for n, r in legs]), noise=noise)


def crash_and_recover():
    return _path((300, 0.006), (20, -0.015), (15, 0.03), (60, 0.01))


def test_mode_params(mod, mode):
    assert (mod.CASH_DD, mod.COOLDOWN) == MODES[mode]


def test_indicators(strat):
    out = run_pipeline(strat, bull_ohlcv(), "AVAX/USDT")
    for c in ("ema200", "ema50", "adx", "ret_30d", "ret_60d", "dd_from_peak", "meta_state"):
        assert c in out.columns
    assert set(out["meta_state"]) <= {"CASH", "DEF", "BAL", "AGGR"}


def test_no_lookahead(strat):
    assert_no_lookahead(strat, crash_and_recover(), cuts=[250, 310, 330, 360], pair="AVAX/USDT")


def test_bull_upshifts_and_enters(strat):
    out = run_pipeline(strat, bull_ohlcv(), "AVAX/USDT")
    assert out["meta_state"].iloc[-1] in ("BAL", "AGGR")
    assert col(out, "enter_long").iloc[-1] == 1 and col(out, "exit_long").iloc[-1] == 0


def test_moderate_drawdown_threshold_differs_by_mode(strat, mode):
    out = run_pipeline(strat, _path((300, 0.006), (30, -0.006)), "AVAX/USDT")
    dd = out["dd_from_peak"].iloc[-1]
    assert 0.15 < dd < 0.20
    if mode == "MA_BAL":
        assert out["meta_state"].iloc[-1] == "CASH"
        assert col(out, "exit_long").iloc[-1] == 1 and col(out, "enter_long").iloc[-1] == 0
    else:
        assert out["meta_state"].iloc[-1] != "CASH"
        assert col(out, "exit_long").iloc[-1] == 0


def test_cash_is_sticky_for_cooldown_then_reenters(strat, mod):
    out = run_pipeline(strat, crash_and_recover(), "AVAX/USDT")
    states = out["meta_state"].tolist()
    first_cash = states.index("CASH")
    assert all(s == "CASH" for s in states[first_cash:first_cash + mod.COOLDOWN])
    # strong recovery afterwards -> back out of CASH and entering again
    assert states[-1] != "CASH" and col(out, "enter_long").iloc[-1] == 1


# ------------------------------------------------------------- sizing
def _state(strat, state, free):
    attach_runtime(strat, pd.DataFrame([{"meta_state": state}]), free)


def test_adjust_buys_to_state_target(strat, mod):
    _state(strat, "AGGR", 1000.0)
    assert adjust(strat, FakeTrade(0.0001, 100.0), 100.0) == pytest.approx(mod.AGGR_T * 1000.01 - 0.01)


def test_adjust_noop_in_cash(strat):
    _state(strat, "CASH", 1000.0)
    assert adjust(strat, FakeTrade(0.0001, 100.0), 100.0) is None


def test_adjust_trims_on_downshift(strat, mod):
    _state(strat, "DEF", 0.0)
    assert adjust(strat, FakeTrade(10.0, 100.0), 100.0) == pytest.approx(-(1000 - mod.DEF_T * 1000))


def test_adjust_inside_band_noop(strat, mod):
    _state(strat, "BAL", 1000 * (1 - mod.BAL_T))
    assert adjust(strat, FakeTrade(mod.BAL_T * 10, 100.0), 100.0) is None


def test_custom_stake_by_state(strat, mod):
    _state(strat, "DEF", 0.0)
    assert strat.custom_stake_amount("AVAX/USDT", None, 1, 10, 5, 1000, 1, None, "long") == pytest.approx(1000 * mod.DEF_T)


# C14b regression (was strict xfail): trims are sized by cost basis via _position_sizing.
def test_trim_in_profit_lands_on_target(strat, mod):
    _state(strat, "BAL", 0.0)
    trade = FakeTrade(1.0, 100.0)
    stake = adjust(strat, trade, 200.0)
    assert allocation_after_trim(stake, trade, 200.0, 0.0) == pytest.approx(mod.BAL_T, abs=0.01)


# Regression (was strict xfail): never-ROI strategies use minimal_roi = {}.
def test_roi_never_exits(strat):
    assert not roi_would_exit(strat, FakeTrade(1.0, 100.0), profit=12.0)
