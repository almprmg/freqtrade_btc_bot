"""Behavioural tests — BtcRebalanceStrategy (2 bots).

Deployed: freqtrade_rebalance (REBALANCE_MODE=R5_75_BTC, no shield) and
freqtrade_rebalance_v2 (R5_75_BTC + WITH_SHIELD=true). Rules: hold 75% BTC,
rebalance every bar (threshold 0, full fraction); with the shield, no entries
and a forced exit in confirmed BEAR, and no adds while BEAR.
"""
from __future__ import annotations

import pytest

from tests._ft_helpers import (
    ROI_XFAIL_REASON, SIZING_XFAIL_REASON, FakeTrade, adjust, allocation_after_trim,
    assert_no_lookahead, attach_runtime, bear_ohlcv, bull_ohlcv, col,
    load_strategy, make_strategy, roi_would_exit, run_pipeline,
)

FILE = "btc_rebalance_strategy.py"


@pytest.fixture(params=["false", "true"], ids=["plain", "shield"])
def shield(request):
    return request.param == "true"


@pytest.fixture
def mod(shield):
    return load_strategy(FILE, {"REBALANCE_MODE": "R5_75_BTC", "WITH_SHIELD": str(shield).lower()})


@pytest.fixture
def strat(mod):
    return make_strategy(mod.BtcRebalanceStrategy)


def test_mode_constants(mod, shield):
    assert mod.TARGET_PCT == 0.75 and mod.THRESHOLD_PCT == 0.0 and mod.REBALANCE_FRACTION == 1.0
    assert mod.WITH_SHIELD is shield


def test_indicators(strat, shield):
    out = run_pipeline(strat, bull_ohlcv())
    assert "ema200" in out.columns
    assert ("regime_confirmed" in out.columns) is shield


def test_no_lookahead(strat):
    assert_no_lookahead(strat, bear_ohlcv(), cuts=[230, 300, 340])


def test_bull_enters(strat):
    out = run_pipeline(strat, bull_ohlcv())
    assert col(out, "enter_long").iloc[-1] == 1
    assert col(out, "exit_long").iloc[-1] == 0
    assert (col(out, "enter_long")[out["ema200"].isna()] == 0).all()


def test_bear_behaviour(strat, shield):
    out = run_pipeline(strat, bear_ohlcv())
    if shield:
        assert out["regime_confirmed"].iloc[-1] == "BEAR"
        assert col(out, "enter_long").iloc[-1] == 0
        assert col(out, "exit_long").iloc[-1] == 1
    else:  # plain rebalance is regime-blind by design
        assert col(out, "enter_long").iloc[-1] == 1
        assert col(out, "exit_long").iloc[-1] == 0


def test_initial_stake(strat):
    assert strat.custom_stake_amount("BTC/USDT", None, 100, 10, 5, 1000, 1, None, "long") == pytest.approx(750)


def test_adjust_buys_when_underweight(strat):
    attach_runtime(strat, run_pipeline(strat, bull_ohlcv()), free=500.0)
    assert adjust(strat, FakeTrade(5.0, 100.0), 100.0) == pytest.approx(250.0)


def test_adjust_sells_when_overweight(strat):
    attach_runtime(strat, run_pipeline(strat, bull_ohlcv()), free=100.0)
    assert adjust(strat, FakeTrade(9.0, 100.0), 100.0) == pytest.approx(-150.0)


def test_adjust_on_target_is_noop(strat):
    attach_runtime(strat, run_pipeline(strat, bull_ohlcv()), free=250.0)
    assert adjust(strat, FakeTrade(7.5, 100.0), 100.0) is None


def test_adjust_in_bear(strat, shield):
    attach_runtime(strat, run_pipeline(strat, bear_ohlcv()), free=500.0)
    out = adjust(strat, FakeTrade(5.0, 100.0), 100.0)
    if shield:
        assert out is None  # regime_allows_add -> no adds in BEAR
    else:
        assert out == pytest.approx(250.0)


# C14b regression (was strict xfail): trims are sized by cost basis via _position_sizing.
def test_trim_in_profit_lands_on_target(strat):
    attach_runtime(strat, run_pipeline(strat, bull_ohlcv()), free=0.0)
    trade = FakeTrade(1.0, 100.0)
    stake = adjust(strat, trade, 200.0)        # wants to sell $50 (market) of $200
    assert stake == pytest.approx(-25.0)  # $50 market value = 25% of the $100 cost basis
    assert allocation_after_trim(stake, trade, 200.0, 0.0) == pytest.approx(0.75, abs=0.01)


@pytest.mark.xfail(strict=True, reason=ROI_XFAIL_REASON + " The class comment says explicitly "
                   "'Rebalancing never wants Freqtrade's auto-exit to trigger'.")
def test_roi_never_exits(strat):
    assert not roi_would_exit(strat, FakeTrade(1.0, 100.0), profit=12.0)
