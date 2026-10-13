"""Behavioural tests — BtcAdaptiveStrategy (2 bots).

Deployed: freqtrade_adaptive (AD_MODE=ADAPT_AGGR_NOSTOP) and freqtrade_adaptive_v2
(ADAPT_AGGR_NOSTOP + WITH_SHIELD=true). NOSTOP's documented intent: all three
stop rules (STOP_GRID, TRIM_RALLY, VOL_PUSH) are disabled.
"""
from __future__ import annotations

import pandas as pd
import pytest

from tests._ft_helpers import (
    ROI_XFAIL_REASON, SIZING_XFAIL_REASON, FakeTrade, adjust, allocation_after_trim,
    assert_no_lookahead, attach_runtime, bear_ohlcv, bull_ohlcv, col,
    load_strategy, make_strategy, roi_would_exit, run_pipeline,
)

FILE = "btc_adaptive_strategy.py"


@pytest.fixture(params=["false", "true"], ids=["plain", "shield"])
def shield(request):
    return request.param == "true"


@pytest.fixture
def mod(shield):
    return load_strategy(FILE, {"AD_MODE": "ADAPT_AGGR_NOSTOP", "WITH_SHIELD": str(shield).lower()})


@pytest.fixture
def strat(mod):
    return make_strategy(mod.BtcAdaptiveStrategy)


def row(**over) -> pd.DataFrame:
    """One analysed row: TREND_UP, no stop rule active, shield BULL."""
    base = dict(close=100.0, ema_short=90.0, adx=30.0, atr_z=0.0, bb_width=0.1,
                bb_width_avg=0.1, change_2d_pct=0.0, rally_from_low=0.10,
                regime_confirmed="BULL")
    base.update(over)
    return pd.DataFrame([base])


def test_mode_params(mod, shield):
    p = mod.P
    assert (p["target_trend_up"], p["target_trend_dn"], p["target_range"]) == (0.85, 0.40, 0.60)
    assert p["stop_grid_drop_pct"] == 1.0 and p["vol_zscore_threshold"] == 100.0
    assert mod.WITH_SHIELD is shield


def test_indicators(strat):
    out = run_pipeline(strat, bull_ohlcv())
    for c in ("adx", "atr", "atr_z", "ema_short", "ema_long", "bb_width", "change_2d_pct", "rally_from_low"):
        assert c in out.columns


def test_no_lookahead(strat):
    assert_no_lookahead(strat, bear_ohlcv(), cuts=[230, 300, 340])


def test_entry_when_ready(strat):
    out = run_pipeline(strat, bull_ohlcv())
    assert col(out, "enter_long").iloc[-1] == 1
    assert (col(out, "enter_long")[out["ema_long"].isna()] == 0).all()


def test_bear(strat, shield):
    out = run_pipeline(strat, bear_ohlcv())
    if shield:
        assert col(out, "enter_long").iloc[-1] == 0 and col(out, "exit_long").iloc[-1] == 1
    else:
        assert col(out, "enter_long").iloc[-1] == 1 and col(out, "exit_long").iloc[-1] == 0


@pytest.mark.parametrize("over,expected", [
    ({}, "TREND_UP"),
    ({"close": 80.0}, "TREND_DN"),
    ({"adx": 15.0}, "RANGE"),
    ({"adx": 22.0, "bb_width": 0.05}, "RANGE"),
    ({"atr_z": 50.0}, "TREND_UP"),       # NOSTOP: VOL_PUSH threshold 100 -> never VOLATILE
    ({"atr_z": 150.0}, "VOLATILE"),
])
def test_regime_classifier(strat, over, expected):
    assert strat._regime(row(**over).iloc[0]) == expected


def test_adjust_buys_toward_trend_up_target(strat):
    attach_runtime(strat, row(), free=1000.0)
    assert adjust(strat, FakeTrade(0.0001, 100.0), 100.0) == pytest.approx(0.85 * 1000.01 - 0.01)


def test_adjust_inside_trend_threshold_noop(strat):
    attach_runtime(strat, row(), free=200.0)      # 80% vs 85% target: |drift| 5% < 8%
    assert adjust(strat, FakeTrade(8.0, 100.0), 100.0) is None


def test_adjust_range_uses_tighter_grid_threshold(strat):
    attach_runtime(strat, row(adx=15.0), free=450.0)   # 55% vs 60%: 5% >= 3% grid threshold
    assert adjust(strat, FakeTrade(5.5, 100.0), 100.0) == pytest.approx(50.0)


def test_adjust_trims_overweight(strat):
    attach_runtime(strat, row(close=80.0), free=0.0)   # TREND_DN target 40%, holding 100%
    assert adjust(strat, FakeTrade(10.0, 100.0), 100.0) == pytest.approx(-600.0)


# Regression (was strict xfail): NOSTOP really disables TRIM_RALLY (trim_rally_pct = inf).
def test_nostop_never_rally_trims(strat):
    attach_runtime(strat, row(rally_from_low=1.5), free=150.0)
    assert adjust(strat, FakeTrade(8.5, 100.0), 100.0) is None


def test_adjust_in_shield_bear(strat, shield, request):
    """WITH_SHIELD: _regime_shield.regime_allows_add says no adds in confirmed BEAR."""
    attach_runtime(strat, row(close=80.0, regime_confirmed="BEAR"), free=1000.0)
    out = adjust(strat, FakeTrade(0.0001, 100.0), 100.0)
    if not shield:
        assert out == pytest.approx(0.40 * 1000.01 - 0.01)   # regime-blind by design
        return
    request.applymarker(pytest.mark.xfail(strict=True, reason=(
        "WITH_SHIELD adaptive imports regime_allows_add but never calls it "
        "(btc_adaptive_strategy.py adjust_trade_position), unlike BtcRebalanceStrategy. In "
        "confirmed BEAR it still BUYS toward the TREND_DN target while the shield's exit "
        "signal tries to close the trade. Input: BEAR, 0 coin, 1000 free. Expected None, "
        "actual +400.")))
    assert out is None


# C14b regression (was strict xfail): trims are sized by cost basis via _position_sizing.
def test_trim_in_profit_lands_on_target(strat):
    attach_runtime(strat, row(), free=0.0)
    trade = FakeTrade(1.0, 100.0)
    stake = adjust(strat, trade, 200.0)
    assert stake == pytest.approx(-15.0)  # $30 market value = 15% of the $100 cost basis
    assert allocation_after_trim(stake, trade, 200.0, 0.0) == pytest.approx(0.85, abs=0.01)


# Regression (was strict xfail): never-ROI strategies use minimal_roi = {}.
def test_roi_never_exits(strat):
    assert not roi_would_exit(strat, FakeTrade(1.0, 100.0), profit=12.0)


def test_rally_trim_once_per_candle():
    """Modes with TRIM_RALLY enabled trim at most once per analysed candle
    (adjust_trade_position runs on every process loop), and not while an
    order is open."""
    m = load_strategy(FILE, {"AD_MODE": "ADAPT_AGGR_BASELINE"})
    s = make_strategy(m.BtcAdaptiveStrategy)
    day1 = row(rally_from_low=0.5).assign(date=pd.Timestamp("2024-03-01", tz="UTC"))
    attach_runtime(s, day1, free=150.0)               # at the 85% target
    trade = FakeTrade(8.5, 100.0)
    first = adjust(s, trade, 100.0)
    assert first == pytest.approx(-0.20 * 850.0)
    assert all(adjust(s, trade, 100.0) is None for _ in range(60))   # same candle
    day2 = day1.assign(date=pd.Timestamp("2024-03-02", tz="UTC"))
    attach_runtime(s, day2, free=150.0)
    trade.has_open_orders = True
    assert adjust(s, trade, 100.0) is None            # order still open
    trade.has_open_orders = False
    assert adjust(s, trade, 100.0) == pytest.approx(-0.20 * 850.0)
