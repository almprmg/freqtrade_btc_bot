"""C14b regression tests — BtcDynamicRebalanceStrategy partial-sell sizing + ROI.

1. freqtrade (2026.4) converts a NEGATIVE adjust_trade_position return into a
   coin amount against the COST BASIS:
       amount = |stake| * trade.amount / trade.stake_amount
   (freqtradebot.py process_open_trade_positions, optimize/backtesting.py
   _get_adjust_trade_entry_for_candle). The strategy used to return the
   market-value overweight, which over-sold positions in profit
   (BTC 2021-02-12: 49% BTC after a "rebalance to 75%").
2. minimal_roi {"0": 10.0} was reachable (SOL 2021 ROI exit). It is now {}.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

os.environ.setdefault("DR_MODE", "DR_PROFIT_20")

from freqtrade.resolvers.strategy_resolver import StrategyResolver  # noqa: E402

from user_data.strategies import btc_dynamic_rebalance_strategy as dr  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
CONFIG = {
    "stake_currency": "USDT", "stake_amount": "unlimited", "max_open_trades": 1,
    "timeframe": "1d", "dry_run": True, "dry_run_wallet": 10_000,
    "trading_mode": "spot", "exchange": {"name": "binance", "pair_whitelist": ["BTC/USDT"]},
    "runmode": "backtest", "datadir": "/tmp", "user_data_dir": "/tmp",
    "strategy_path": "user_data/strategies",
}


def ft_exit_amount(stake, trade_amount, trade_stake_amount):
    """freqtrade 2026.4 negative-stake -> amount (inlined so it is independent of the fix)."""
    return abs(stake) * trade_amount / trade_stake_amount


class FakeTrade:
    def __init__(self, amount, stake_amount, fills):
        self.pair = "BTC/USDT"
        self.stake_currency = "USDT"
        self.amount = amount
        self.stake_amount = stake_amount
        self.has_open_orders = False
        self.open_date_utc = T0
        self._fills = fills
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
    s = dr.BtcDynamicRebalanceStrategy(dict(CONFIG))
    df = pd.DataFrame([{"close": 1.0, "rsi": 50.0, "ema_long": 1.0, "ema_short": 1.0}])
    s.dp = MagicMock()
    s.dp.get_analyzed_dataframe = MagicMock(return_value=(df, None))
    s.wallets = SimpleNamespace(get_free=lambda cur: s.free)
    return s


def _alloc_after_trim(s, trade, free, rate):
    s.free = free
    out = s.adjust_trade_position(
        trade, T0 + timedelta(days=30), rate, current_profit=0.0, min_stake=5.0,
        max_stake=1e9, current_entry_rate=rate, current_exit_rate=rate,
        current_entry_profit=0.0, current_exit_profit=0.0,
    )
    assert out is not None and out < 0, "expected a trim"
    sold = ft_exit_amount(out, trade.amount, trade.stake_amount)
    coin = trade.amount - sold
    cash = free + sold * rate
    return coin * rate / (coin * rate + cash)


# ------------------------------------------------------------ pure helpers
def test_partial_exit_stake_roundtrips_through_freqtrade_conversion():
    # 0.5 BTC, cost basis 5000 (avg 10k), price 40k. Want to sell $2000 = 0.05 BTC.
    stake = dr.partial_exit_stake(2000.0, 40_000.0, 0.5, 5000.0)
    assert stake == pytest.approx(500.0)  # 10% of the position -> 10% of cost basis
    assert ft_exit_amount(-stake, 0.5, 5000.0) == pytest.approx(0.05)
    assert dr.freqtrade_exit_amount(-stake, 0.5, 5000.0) == pytest.approx(0.05)


def test_partial_exit_stake_at_cost_equals_market_value():
    # price == avg cost -> stake == market value (the old behaviour was right only here)
    assert dr.partial_exit_stake(300.0, 100.0, 10.0, 1000.0) == pytest.approx(300.0)


def test_partial_exit_stake_caps_and_guards():
    assert dr.partial_exit_stake(1e9, 100.0, 1.0, 50.0) == pytest.approx(50.0)  # never > whole position
    for bad in [(0, 100, 1, 50), (10, 0, 1, 50), (10, 100, 0, 50), (10, 100, 1, 0)]:
        assert dr.partial_exit_stake(*bad) == 0.0


# --------------------------------------------- adjust_trade_position sizing
def test_trim_in_profit_lands_on_target(strat):
    # 2021-02-12 shape: 0.5 BTC with avg cost 10k, last fill (anchor) at 32k,
    # free 4000 -> anchor 20000. Price 41k -> 24500 (+22.5%) -> trim to 75%.
    trade = FakeTrade(0.5, 5000.0, [(32_000.0, T0)])
    alloc = _alloc_after_trim(strat, trade, 4000.0, 41_000.0)
    assert alloc == pytest.approx(0.75, abs=0.005)  # old code: 0.50


def test_trim_at_loss_lands_on_target(strat):
    # avg cost 200 > price 130: old code under-sold (left > 75%).
    trade = FakeTrade(0.75, 150.0, [(100.0, T0)])
    alloc = _alloc_after_trim(strat, trade, 25.0, 130.0)
    assert alloc == pytest.approx(0.75, abs=0.005)


def test_buy_side_unchanged(strat):
    # Positive stake is quote currency at market (amount = stake / rate) -> unchanged.
    trade = FakeTrade(0.75, 75.0, [(100.0, T0)])
    strat.free = 25.0
    out = strat.adjust_trade_position(
        trade, T0 + timedelta(days=30), 70.0, current_profit=0.0, min_stake=1.0,
        max_stake=1e9, current_entry_rate=70.0, current_exit_rate=70.0,
        current_entry_profit=0.0, current_exit_profit=0.0,
    )
    total = 0.75 * 70 + 25
    assert out == pytest.approx(0.75 * total - 0.75 * 70)


# ----------------------------------------------------------------- ROI
def _loaded_strategy():
    """Apply the same attribute resolution freqtrade's StrategyResolver does."""
    s = dr.BtcDynamicRebalanceStrategy(dict(CONFIG))
    cfg = dict(CONFIG)
    StrategyResolver._override_attribute_helper(s, cfg, "minimal_roi", {"0": 10.0})
    StrategyResolver._normalize_attributes(s)
    return s


@pytest.mark.parametrize("profit", [0.5, 5.0, 10.5, 50.0, 165.0, 1000.0])
def test_roi_never_triggers(profit):
    s = _loaded_strategy()
    trade = SimpleNamespace(open_date_utc=T0, pair="SOL/USDT", enter_tag="x", trade_direction="long")
    for days in (0, 1, 365, 3000):
        assert s.min_roi_reached(trade, profit, T0 + timedelta(days=days)) is False


@pytest.mark.parametrize("cfg", ["config.dynrebal.json", "config.dynrebal-ETH.json", "config.dynrebal-SOL.json"])
def test_deployed_configs_do_not_override_roi(cfg):
    path = REPO / cfg
    if not path.exists():
        pytest.skip(f"{cfg} not present")
    assert "minimal_roi" not in json.loads(path.read_text(encoding="utf-8"))
