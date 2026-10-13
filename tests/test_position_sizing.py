"""Shared cost-basis partial-exit sizing (user_data/strategies/_position_sizing.py)."""
from __future__ import annotations

import pytest

from tests._ft_helpers import FakeTrade, freqtrade_exit_amount
from user_data.strategies import _position_sizing as ps
from user_data.strategies import btc_dynamic_rebalance_strategy as dr


def test_dynrebal_reexports_shared_helper():
    assert dr.partial_exit_stake is ps.partial_exit_stake


@pytest.mark.parametrize("open_rate,rate", [(100.0, 100.0), (100.0, 250.0), (100.0, 40.0)])
def test_exit_stake_sells_exact_market_value(open_rate, rate):
    trade = FakeTrade(2.0, open_rate)
    stake = ps.exit_stake(trade, 60.0, rate)
    assert stake < 0
    assert freqtrade_exit_amount(stake, trade) * rate == pytest.approx(60.0)


def test_exit_stake_caps_at_whole_position_and_guards():
    trade = FakeTrade(1.0, 100.0)
    assert ps.exit_stake(trade, 10_000.0, 200.0) == pytest.approx(-100.0)
    assert ps.exit_stake(trade, 0.0, 200.0) is None
    assert ps.exit_stake(FakeTrade(0.0, 100.0), 10.0, 200.0) is None
