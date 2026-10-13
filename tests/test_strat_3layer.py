"""Behavioural tests — Btc3LayerStrategy (2 bots).

Deployed: freqtrade_3layer (L3_MODE=L3_AGGR_WIDE_GRID) and freqtrade_3layer_v2
(L3_AGGR_WIDE_GRID + WITH_SHIELD=true). config.3layer.json: max_open_trades=-1.
Layers: CORE 70% / GRID 25% in 3 legs (-6% step, +10% take) / CASH 5% crash hedge.
position_adjustment is OFF: every layer action is a separate trade sized by
custom_stake_amount.
"""
from __future__ import annotations

import pandas as pd
import pytest

from tests._ft_helpers import (
    FakeTrade, assert_no_lookahead, attach_runtime, bear_ohlcv, bull_ohlcv, col,
    load_strategy, make_strategy, roi_would_exit, run_pipeline,
)

FILE = "btc_3layer_strategy.py"


@pytest.fixture(params=["false", "true"], ids=["plain", "shield"])
def shield(request):
    return request.param == "true"


@pytest.fixture
def mod(shield):
    return load_strategy(FILE, {"L3_MODE": "L3_AGGR_WIDE_GRID", "WITH_SHIELD": str(shield).lower()})


@pytest.fixture
def strat(mod):
    return make_strategy(mod.Btc3LayerStrategy, max_open_trades=-1)


@pytest.fixture
def open_trades(monkeypatch, mod):
    trades: list = []
    monkeypatch.setattr(mod.Trade, "get_open_trades", staticmethod(lambda: list(trades)))
    return trades


def _stake(strat, rate, free, dd=0.0):
    attach_runtime(strat, pd.DataFrame([{"dd_from_high": dd}]), free)
    return strat.custom_stake_amount("BTC/USDT", None, rate, 10.0, 5.0, free, 1.0, "layer:auto", "long")


def test_mode_params(mod, shield):
    assert (mod.CORE_PCT, mod.GRID_PCT, mod.CASH_PCT) == (0.70, 0.25, 0.05)
    assert (mod.GRID_STEP, mod.GRID_TAKE, mod.GRID_LEVELS) == (0.06, 0.10, 3)
    assert mod.WITH_SHIELD is shield
    assert mod.Btc3LayerStrategy.position_adjustment_enable is False


def test_indicators(strat):
    out = run_pipeline(strat, bull_ohlcv())
    for c in ("ema200", "rolling_high", "dd_from_high"):
        assert c in out.columns
    assert (out["dd_from_high"] >= 0).all()


def test_no_lookahead(strat):
    assert_no_lookahead(strat, bear_ohlcv(), cuts=[230, 300, 340])


def test_entry_signal(strat, shield):
    bull = run_pipeline(strat, bull_ohlcv())
    assert col(bull, "enter_long").iloc[-1] == 1 and bull["enter_tag"].iloc[-1] == "layer:auto"
    bear = run_pipeline(strat, bear_ohlcv())
    if shield:
        assert col(bear, "enter_long").iloc[-1] == 0 and col(bear, "exit_long").iloc[-1] == 1
    else:
        assert col(bear, "enter_long").iloc[-1] == 1 and col(bear, "exit_long").iloc[-1] == 0


def test_bootstrap_core(strat, open_trades):
    assert _stake(strat, 100.0, free=1000.0) == pytest.approx(700.0)


def test_grid_leg_after_step_drop(strat, open_trades):
    open_trades.append(FakeTrade(7.5, 100.0, enter_tag="layer:auto"))
    assert _stake(strat, 94.0, free=250.0) == pytest.approx(1000 * 0.25 / 3)


def test_no_grid_leg_before_step(strat, open_trades):
    open_trades.append(FakeTrade(7.5, 100.0, enter_tag="layer:auto"))
    assert _stake(strat, 97.0, free=250.0) == 0.0


def test_crash_deploys_cash(strat, open_trades):
    open_trades.append(FakeTrade(7.5, 100.0, enter_tag="layer:auto"))
    assert _stake(strat, 100.0, free=250.0, dd=0.35) == pytest.approx(250.0)
    assert _stake(strat, 100.0, free=250.0, dd=0.10) == 0.0


@pytest.mark.xfail(strict=True, reason=(
    "Grid layer bookkeeping is dead: populate_entry_trend tags EVERY entry 'layer:auto' "
    "(btc_3layer_strategy.py populate_entry_trend) and confirm_trade_entry cannot retag, but "
    "_layer_of() only recognises 'grid:'/'hedge:' prefixes. So grid legs are counted as CORE: "
    "the GRID_LEVELS cap is never enforced (max_open_trades=-1 in config.3layer.json), the "
    "grid anchor is always the first core trade, and grid legs inflate core value. Input: "
    "one core + 3 grid legs opened by the strategy. Expected 3 grid trades, actual 0."))
def test_grid_legs_are_classified_as_grid(strat, open_trades):
    tag = run_pipeline(strat, bull_ohlcv())["enter_tag"].iloc[-1]
    open_trades.append(FakeTrade(7.5, 100.0, enter_tag=tag))
    for px in (94.0, 88.4, 83.1):
        open_trades.append(FakeTrade(83.3 / px, px, enter_tag=tag))
    assert len(strat._portfolio_state("BTC/USDT", 80.0)["grid_trades"]) == 3


def test_grid_trade_takes_profit_via_roi(strat):
    assert roi_would_exit(strat, FakeTrade(1.0, 100.0, enter_tag="grid:buy_1"), profit=0.11)


# Regression (was strict xfail): ROI applies to grid legs only (custom_roi).
def test_core_trade_never_roi_exits(strat):
    assert not roi_would_exit(strat, FakeTrade(7.0, 100.0, enter_tag="layer:auto"), profit=0.12)
