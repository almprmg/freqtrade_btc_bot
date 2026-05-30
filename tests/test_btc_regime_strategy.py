"""Tests for `BtcRegimeStrategy` — focused on the parts that don't need a
running Freqtrade bot: indicator-pipeline shape, entry/exit column wiring,
custom_stoploss branching, and Maker-offset pricing.

We mock Freqtrade's `DataProvider` so `populate_indicators` can run without
a real exchange. The strategy is instantiated with a minimal config dict.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from user_data.strategies.btc_regime_strategy import BtcRegimeStrategy
from user_data.strategies.regime_detector import RegimeDetector


# ---------------------------------------------------------------------- #
# fixtures                                                               #
# ---------------------------------------------------------------------- #
def _ohlcv(n: int = 350, *, base: float = 50_000.0, drift: float = 0.0,
           seed: int = 7) -> pd.DataFrame:
    """Synthetic 4h OHLCV. drift in % per bar."""
    rng = np.random.default_rng(seed)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    dates = [start + timedelta(hours=4 * i) for i in range(n)]
    walk = rng.normal(0, 0.005, size=n).cumsum()
    closes = base * (1.0 + walk + np.arange(n) * drift)
    highs = closes * (1.0 + np.abs(rng.normal(0, 0.003, n)))
    lows = closes * (1.0 - np.abs(rng.normal(0, 0.003, n)))
    opens = closes + rng.normal(0, base * 0.001, n)
    vols = np.full(n, 1000.0) + rng.normal(0, 50, n)
    return pd.DataFrame(
        {"date": dates, "open": opens, "high": highs, "low": lows,
         "close": closes, "volume": np.abs(vols)}
    )


@pytest.fixture
def minimal_config() -> dict:
    return {
        "stake_currency": "USDT",
        "stake_amount": 100,
        "max_open_trades": 3,
        "timeframe": "4h",
        "dry_run": True,
        "dry_run_wallet": 10_000,
        "trading_mode": "spot",
        "exchange": {"name": "binance", "pair_whitelist": ["BTC/USDT"]},
        "runmode": "backtest",
        "datadir": "/tmp",
        "user_data_dir": "/tmp",
        "strategy_path": "user_data/strategies",
    }


@pytest.fixture
def strategy(minimal_config: dict, monkeypatch: pytest.MonkeyPatch) -> BtcRegimeStrategy:
    """Instantiate the strategy with a faked DataProvider returning
    deterministic 4h + 1h + 1d frames."""
    df_4h = _ohlcv(n=350, base=50_000.0, drift=0.0001)
    df_1h = _ohlcv(n=1400, base=50_000.0, drift=0.000025, seed=8)
    df_1d = _ohlcv(n=60, base=50_000.0, drift=0.001, seed=9)

    dp = MagicMock()
    dp.current_whitelist = MagicMock(return_value=["BTC/USDT"])
    dp.get_pair_dataframe = MagicMock(
        side_effect=lambda pair, timeframe: {
            "1h": df_1h.copy(),
            "1d": df_1d.copy(),
        }.get(timeframe, df_4h.copy())
    )
    dp.send_msg = MagicMock()

    strat = BtcRegimeStrategy(minimal_config)
    strat.dp = dp
    # Wallets: also faked — return a known total for custom_stake_amount.
    strat.wallets = SimpleNamespace(get_total_stake_amount=lambda: 10_000.0)
    return strat


# ---------------------------------------------------------------------- #
# populate_indicators                                                    #
# ---------------------------------------------------------------------- #
def test_populate_indicators_emits_expected_columns(
    strategy: BtcRegimeStrategy,
) -> None:
    df = _ohlcv(n=350)
    out = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
    for col in (
        "bb_middle", "bb_lower", "bb_upper",
        "rsi", "stoch_k",
        "ema21", "ema50", "ema200",
        "macd", "macd_signal", "macd_hist",
        "volume_sma", "volume_ratio",
        "adx", "atr", "atr_avg",
        "regime_raw", "regime_confirmed",
        "expected_move_pct",
        "ema200_1d", "rsi_1h",
    ):
        assert col in out.columns, f"missing column: {col}"


# ---------------------------------------------------------------------- #
# populate_entry_trend — wiring                                          #
# ---------------------------------------------------------------------- #
def test_populate_entry_trend_emits_required_columns(
    strategy: BtcRegimeStrategy,
) -> None:
    df = _ohlcv(n=350)
    df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
    df = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
    assert "enter_long" in df.columns
    assert "enter_tag" in df.columns
    # Tag is "" except where enter_long==1.
    fired = df[df["enter_long"] == 1]
    assert fired["enter_tag"].isin({"mean_reversion", "trend_pullback"}).all()


def test_no_entries_during_warmup(strategy: BtcRegimeStrategy) -> None:
    df = _ohlcv(n=350)
    df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
    df = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
    # First 200+ bars need at least the EMA200 / regime warmup; entries
    # must be zero there.
    assert df["enter_long"].iloc[:50].sum() == 0


# ---------------------------------------------------------------------- #
# custom_stoploss branching                                              #
# ---------------------------------------------------------------------- #
def test_stoploss_mean_reversion_fixed_minus_3pct(
    strategy: BtcRegimeStrategy,
) -> None:
    trade = SimpleNamespace(enter_tag="mean_reversion")
    sl = strategy.custom_stoploss(
        pair="BTC/USDT", trade=trade,
        current_time=datetime.now(tz=timezone.utc),
        current_rate=50_000.0, current_profit=-0.01,
    )
    assert sl == pytest.approx(-0.03, abs=1e-9)


def test_stoploss_trend_initial_minus_4pct_when_negative_profit(
    strategy: BtcRegimeStrategy,
) -> None:
    trade = SimpleNamespace(enter_tag="trend_pullback")
    sl = strategy.custom_stoploss(
        pair="BTC/USDT", trade=trade,
        current_time=datetime.now(tz=timezone.utc),
        current_rate=50_000.0, current_profit=-0.005,
    )
    assert sl == pytest.approx(-0.04, abs=1e-9)


def test_stoploss_trend_tightens_after_3pct_profit(
    strategy: BtcRegimeStrategy,
) -> None:
    """At +4% profit the trail should lock in roughly +1%, i.e. drop by ≤ 3%.

    Convention: custom_stoploss returns the MAX ALLOWED DRAWDOWN from
    entry, as a negative fraction. -(current_profit - 0.01) at +4% profit
    means -0.03 — the stop sits 3% below the current rate, which equals
    entry × 1.01.
    """
    trade = SimpleNamespace(enter_tag="trend_pullback")
    sl = strategy.custom_stoploss(
        pair="BTC/USDT", trade=trade,
        current_time=datetime.now(tz=timezone.utc),
        current_rate=52_000.0, current_profit=0.04,
    )
    assert sl == pytest.approx(-0.03, abs=1e-9)


# ---------------------------------------------------------------------- #
# custom_stake_amount per-tag                                            #
# ---------------------------------------------------------------------- #
def test_stake_mean_reversion_is_15pct_of_wallet(
    strategy: BtcRegimeStrategy,
) -> None:
    stake = strategy.custom_stake_amount(
        pair="BTC/USDT", current_time=datetime.now(tz=timezone.utc),
        current_rate=50_000.0, proposed_stake=100.0,
        min_stake=10.0, max_stake=10_000.0, leverage=1.0,
        entry_tag="mean_reversion", side="long",
    )
    assert stake == pytest.approx(1_500.0, abs=1e-6)


def test_stake_trend_pullback_is_20pct_of_wallet(
    strategy: BtcRegimeStrategy,
) -> None:
    stake = strategy.custom_stake_amount(
        pair="BTC/USDT", current_time=datetime.now(tz=timezone.utc),
        current_rate=50_000.0, proposed_stake=100.0,
        min_stake=10.0, max_stake=10_000.0, leverage=1.0,
        entry_tag="trend_pullback", side="long",
    )
    assert stake == pytest.approx(2_000.0, abs=1e-6)


def test_stake_floor_10_usdt_enforced(strategy: BtcRegimeStrategy) -> None:
    """If both per-tag share and proposed stake fall below 10 USDT, lift to floor."""
    strategy.wallets = SimpleNamespace(get_total_stake_amount=lambda: 5.0)
    stake = strategy.custom_stake_amount(
        pair="BTC/USDT", current_time=datetime.now(tz=timezone.utc),
        current_rate=50_000.0, proposed_stake=1.0,
        min_stake=None, max_stake=10.0, leverage=1.0,
        entry_tag="mean_reversion", side="long",
    )
    assert stake == pytest.approx(10.0, abs=1e-6)


# ---------------------------------------------------------------------- #
# Maker-only LIMIT pricing                                               #
# ---------------------------------------------------------------------- #
def test_custom_entry_price_below_proposed(strategy: BtcRegimeStrategy) -> None:
    p = strategy.custom_entry_price(
        pair="BTC/USDT", trade=None,
        current_time=datetime.now(tz=timezone.utc),
        proposed_rate=50_000.0, entry_tag="trend_pullback", side="long",
    )
    assert p < 50_000.0
    # 0.05% offset.
    assert p == pytest.approx(50_000.0 * 0.9995, rel=1e-9)


def test_custom_exit_price_above_proposed(strategy: BtcRegimeStrategy) -> None:
    p = strategy.custom_exit_price(
        pair="BTC/USDT",
        trade=SimpleNamespace(enter_tag="trend_pullback"),
        current_time=datetime.now(tz=timezone.utc),
        proposed_rate=50_000.0, current_profit=0.02,
        exit_tag="trend_macd_negative", side="long",
    )
    assert p > 50_000.0
    assert p == pytest.approx(50_000.0 * 1.0005, rel=1e-9)


# ---------------------------------------------------------------------- #
# protections                                                            #
# ---------------------------------------------------------------------- #
def test_protections_include_daily_and_monthly_drawdown(
    strategy: BtcRegimeStrategy,
) -> None:
    methods = [p["method"] for p in strategy.protections]
    assert methods.count("MaxDrawdown") == 2
    assert "CooldownPeriod" in methods


def test_protections_daily_drawdown_is_5pct(strategy: BtcRegimeStrategy) -> None:
    daily = next(
        p for p in strategy.protections
        if p["method"] == "MaxDrawdown" and p["lookback_period"] == 1440
    )
    assert daily["max_allowed_drawdown"] == pytest.approx(0.05)


def test_protections_monthly_drawdown_is_15pct(strategy: BtcRegimeStrategy) -> None:
    monthly = next(
        p for p in strategy.protections
        if p["method"] == "MaxDrawdown" and p["lookback_period"] == 43200
    )
    assert monthly["max_allowed_drawdown"] == pytest.approx(0.15)


# ---------------------------------------------------------------------- #
# RegimeDetector wired into strategy                                     #
# ---------------------------------------------------------------------- #
def test_strategy_owns_regime_detector(strategy: BtcRegimeStrategy) -> None:
    assert isinstance(strategy.regime, RegimeDetector)
    assert strategy.regime.confirm_bars == 3
