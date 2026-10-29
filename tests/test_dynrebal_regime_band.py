"""DR_REGIME_BAND: 85/50 regime target, rebalanced only on a regime flip or a
+-20% portfolio move since the last fill (DR_REGIME rebalanced every loop).
"""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tests.test_dynrebal_anchor import FakeTrade as _FakeTrade


class FakeTrade(_FakeTrade):
    """custom_data round-trips through JSON text, like freqtrade (None -> 'null')."""

    def get_custom_data(self, key, default=None):
        import json
        raw = self._cd.get(key)
        return default if raw is None else json.loads(raw) if raw != "null" else "null"

    def set_custom_data(self, key, value):
        import json
        self._cd[key] = json.dumps(value)

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def dr(monkeypatch):
    """The strategy module re-imported with DR_MODE=DR_REGIME_BAND (restored afterwards)."""
    from user_data.strategies import btc_dynamic_rebalance_strategy as mod
    monkeypatch.setenv("DR_MODE", "DR_REGIME_BAND")
    importlib.reload(mod)
    yield mod
    monkeypatch.undo()
    importlib.reload(mod)


def _strategy(mod, close: float, ema: float, free: float):
    s = mod.BtcDynamicRebalanceStrategy({
        "stake_currency": "USDT", "stake_amount": "unlimited", "max_open_trades": 1,
        "timeframe": "1d", "dry_run": True, "dry_run_wallet": 10_000,
        "trading_mode": "spot", "exchange": {"name": "binance", "pair_whitelist": ["BTC/USDT"]},
        "runmode": "backtest", "datadir": "/tmp", "user_data_dir": "/tmp",
        "strategy_path": "user_data/strategies",
    })
    s.dp = MagicMock()
    s.set_market = lambda c, e: s.dp.get_analyzed_dataframe.configure_mock(
        return_value=(pd.DataFrame([{"close": c, "rsi": 50.0, "ema_long": e, "ema_short": e}]), None))
    s.set_market(close, ema)
    s.free = free
    s.wallets = SimpleNamespace(get_free=lambda cur: s.free)
    return s


def _adj(s, trade, rate, now):
    return s.adjust_trade_position(
        trade, now, rate, current_profit=0.0, min_stake=1.0, max_stake=10_000.0,
        current_entry_rate=rate, current_exit_rate=rate,
        current_entry_profit=0.0, current_exit_profit=0.0,
    )


def test_pure_helpers(dr):
    assert dr.regime_target(110, 100, 0.85, 0.5) == 0.85
    assert dr.regime_target(90, 100, 0.85, 0.5) == 0.5
    assert dr.regime_band_fires(0.85, 0.85, 0.05, 0.20) is False
    assert dr.regime_band_fires(0.85, 0.50, 0.00, 0.20) is True     # regime flipped
    assert dr.regime_band_fires(0.85, 0.85, -0.20, 0.20) is True    # band left
    assert dr.P["trigger_type"] == "regime_band"


def test_quiet_inside_band_and_same_regime(dr):
    # Bull: 0.85 coin @100 + 15 USDT = 100. Price 110 -> 108.5 (+8.5%), still bull.
    s = _strategy(dr, close=110, ema=100, free=15.0)
    trade = FakeTrade(0.85, [(100.0, T0)])
    assert _adj(s, trade, 110.0, T0 + timedelta(days=2)) is None
    assert trade.get_custom_data(dr.APPLIED_TARGET_KEY) == 0.85


def test_regime_flip_sells_to_50pct_and_retries_until_filled(dr):
    s = _strategy(dr, close=110, ema=100, free=15.0)
    trade = FakeTrade(0.85, [(100.0, T0)])
    _adj(s, trade, 100.0, T0 + timedelta(days=1))           # learns applied=0.85 (bull)
    s.set_market(95, 100)                                     # close below EMA200 -> bear
    out = _adj(s, trade, 95.0, T0 + timedelta(days=2))
    assert out is not None and out < 0                        # sell toward 50%
    # Sized so freqtrade sells exactly the overweight: 0.85*95 - 0.5*(0.85*95+15)
    sold = dr.freqtrade_exit_amount(out, trade.amount, trade.stake_amount)
    total = 0.85 * 95 + 15
    assert sold * 95 == pytest.approx(0.85 * 95 - 0.5 * total)
    # Order cancelled, never filled: the flip is not applied, so it retries.
    assert trade.get_custom_data(dr.APPLIED_TARGET_KEY) == 0.85
    assert _adj(s, trade, 95.0, T0 + timedelta(days=2, hours=2)) is not None
    # Now it fills: position is 50/50; next loop is quiet.
    trade.amount = 0.5 * total / 95
    s.free = 0.5 * total
    trade._fills.append((95.0, T0 + timedelta(days=2, hours=3)))
    assert _adj(s, trade, 95.0, T0 + timedelta(days=2, hours=5)) is None
    assert trade.get_custom_data(dr.APPLIED_TARGET_KEY) == 0.5


def test_band_move_rebalances_within_regime(dr):
    # Bull, price 125 -> portfolio 0.85*125+15 = 121.25 (+21%): trim back to 85%.
    s = _strategy(dr, close=125, ema=100, free=15.0)
    trade = FakeTrade(0.85, [(100.0, T0)])
    out = _adj(s, trade, 125.0, T0 + timedelta(days=3))
    assert out is not None and out < 0


def test_does_not_churn_on_small_drift(dr):
    """The old DR_REGIME rebalanced every loop; this mode must not."""
    s = _strategy(dr, close=101, ema=100, free=15.0)
    trade = FakeTrade(0.85, [(100.0, T0)])
    for h in range(1, 48):
        price = 100 + (h % 7) - 3    # +-3% wiggle, regime unchanged
        s.set_market(price if price > 100 else 101, 100)
        assert _adj(s, trade, float(price), T0 + timedelta(hours=h)) is None
