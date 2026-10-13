"""Behavioural tests — BtcRegimeShieldStrategy (4 bots).

Deployed modes: RS_AGGR (BTC shield, ETH shield, SOL shield), RS_SLOW (BNB),
RS_DEFENSIVE (DOGE). Rules: enter only on confirmed BULL, full exit on
confirmed BEAR, adjust_trade_position keeps TARGET allocation while BULL.
"""
from __future__ import annotations

import pytest

from tests._ft_helpers import (
    ROI_XFAIL_REASON, SIZING_XFAIL_REASON, FakeTrade, adjust, allocation_after_trim,
    assert_no_lookahead, attach_runtime, bear_ohlcv, bull_ohlcv, col, flat_ohlcv,
    load_strategy, make_strategy, roi_would_exit, run_pipeline,
)

MODES = {"RS_AGGR": 0.85, "RS_SLOW": 0.75, "RS_DEFENSIVE": 0.60}


@pytest.fixture(params=list(MODES), scope="module")
def mode(request):
    return request.param


@pytest.fixture
def mod(mode):
    return load_strategy("btc_regime_shield_strategy.py", {"RS_MODE": mode})


@pytest.fixture
def strat(mod):
    return make_strategy(mod.BtcRegimeShieldStrategy)


def test_mode_constants(mod, mode):
    assert mod.MODE == mode
    assert mod.TARGET == pytest.approx(MODES[mode])


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        load_strategy("btc_regime_shield_strategy.py", {"RS_MODE": "RS_NOPE"})


def test_indicators_present(strat):
    out = run_pipeline(strat, bull_ohlcv())
    for c in ("ema200", "adx", "ret_30d", "regime_code", "regime_confirmed_code", "regime_confirmed"):
        assert c in out.columns
    assert len(out) == 400


def test_no_lookahead(strat):
    assert_no_lookahead(strat, bear_ohlcv(), cuts=[230, 300, 340])


def test_bull_enters_no_exit(strat):
    out = run_pipeline(strat, bull_ohlcv())
    assert out["regime_confirmed"].iloc[-1] == "BULL"
    assert col(out, "enter_long").iloc[-1] == 1
    assert col(out, "exit_long").iloc[-1] == 0


def test_bear_exits_no_entry(strat):
    out = run_pipeline(strat, bear_ohlcv())
    assert out["regime_confirmed"].iloc[-1] == "BEAR"
    assert col(out, "enter_long").iloc[-1] == 0
    assert col(out, "exit_long").iloc[-1] == 1
    assert out["exit_tag"].iloc[-1].startswith("shield:bear_")


def test_neutral_neither(strat):
    out = run_pipeline(strat, flat_ohlcv())
    assert out["regime_confirmed"].iloc[-1] == "NEUTRAL"
    assert col(out, "enter_long").iloc[-1] == 0
    assert col(out, "exit_long").iloc[-1] == 0


def test_no_entry_before_ema_ready(strat):
    out = run_pipeline(strat, bull_ohlcv())
    assert (col(out, "enter_long")[out["ema200"].isna()] == 0).all()


def test_regime_needs_confirm_bars(mod, strat):
    out = run_pipeline(strat, bear_ohlcv())
    first_bear_code = (out["regime_code"] == -1).idxmax()
    first_bear_conf = (out["regime_confirmed"] == "BEAR").idxmax()
    assert first_bear_conf - first_bear_code == mod.CONFIRM - 1


# ---------------------------------------------------------------- stake / adjust
def _bull_runtime(strat, free):
    return attach_runtime(strat, run_pipeline(strat, bull_ohlcv()), free)


def test_initial_stake_is_target_fraction(mod, strat):
    _bull_runtime(strat, 0)
    st = strat.custom_stake_amount("BTC/USDT", None, 100, 10, 5, 1000, 1, None, "long")
    assert st == pytest.approx(1000 * mod.TARGET)


def test_adjust_buys_up_to_target_when_underweight(mod, strat):
    _bull_runtime(strat, free=900.0)
    trade = FakeTrade(1.0, 100.0)               # 100 coin value, total 1000
    out = adjust(strat, trade, 100.0)
    assert out == pytest.approx(mod.TARGET * 1000 - 100)


def test_adjust_inside_band_noop(mod, strat):
    total = 1000.0
    _bull_runtime(strat, free=total * (1 - mod.TARGET))
    trade = FakeTrade(mod.TARGET * total / 100, 100.0)
    assert adjust(strat, trade, 100.0) is None


def test_adjust_trims_when_overweight(strat):
    _bull_runtime(strat, free=0.0)
    trade = FakeTrade(10.0, 100.0)              # 100% coin
    out = adjust(strat, trade, 100.0)
    assert out is not None and out < 0


@pytest.mark.parametrize("df_fn", [bear_ohlcv, flat_ohlcv])
def test_adjust_noop_outside_bull(strat, df_fn):
    attach_runtime(strat, run_pipeline(strat, df_fn()), free=900.0)
    assert adjust(strat, FakeTrade(1.0, 100.0), 100.0) is None


def test_adjust_respects_min_stake(strat):
    _bull_runtime(strat, free=900.0)
    assert adjust(strat, FakeTrade(1.0, 100.0), 100.0, min_stake=10_000) is None


# C14b regression (was strict xfail): trims are sized by cost basis via _position_sizing.
def test_trim_in_profit_lands_on_target(mod, strat):
    # 1 coin bought @100, now @200, no free cash -> 100% coin; drift > 10% band.
    _bull_runtime(strat, free=0.0)
    trade = FakeTrade(1.0, 100.0)
    stake = adjust(strat, trade, 200.0)
    assert stake is not None and stake < 0
    assert allocation_after_trim(stake, trade, 200.0, 0.0) == pytest.approx(mod.TARGET, abs=0.01)


def test_stoploss_effectively_disabled(strat):
    assert strat.stoploss <= -0.99 and not strat.use_custom_stoploss


# Regression (was strict xfail): never-ROI strategies use minimal_roi = {}.
def test_roi_never_exits(strat):
    assert not roi_would_exit(strat, FakeTrade(1.0, 100.0), profit=12.0)
