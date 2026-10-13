"""Shared helpers for the behavioural tests of the deployed freqtrade strategies.

Hermeticity rules (every test_strat_* file relies on these):
  * Strategy modules read their mode from env vars AT IMPORT TIME, so each
    (file, env) combination is loaded as its own module object via
    `load_strategy`, never via the normal import cache.
  * Several modules read side-data feathers (halving cycle, anomaly flags,
    analogs, macro, rotation signal) at import time from user_data/data.
    During the load `pandas.read_feather` is patched to raise
    FileNotFoundError, so every loader falls back to its "empty" branch and
    NO real data file is ever read. Tests then inject small synthetic frames
    with `monkeypatch.setattr(mod, "_HALVING", ...)` etc.
  * Nothing touches the network, the exchange or a database.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
STRAT_DIR = REPO / "user_data" / "strategies"

# Every env var any covered strategy reads at import time. Unlisted ones are
# removed while loading so a developer's shell cannot change the mode.
_STRATEGY_ENV_VARS = (
    "RS_MODE", "REBALANCE_MODE", "WITH_SHIELD", "AD_MODE", "L3_MODE", "MA_MODE",
    "DCA_MODE", "ANOMALY_FLAGS_FILE",
    "MV_W_MACRO", "MV_W_DXY", "MV_W_VIX", "MV_W_SPY", "MV_W_QQQ", "MV_W_RATES",
    "MV_W_CALENDAR", "MV_W_CYCLE", "MV_TILT_CLAMP", "MV_EXIT_THR", "MV_MODE",
    "MV_COIN", "MV_N_CONFIRM", "MV_BASE",
    "CAL_W_JAN", "CAL_W_FEB", "CAL_W_JUL", "CAL_W_OCT", "CAL_W_NOV", "CAL_W_DEC",
    "CAL_W_MON", "CAL_W_WED", "CAL_W_EOM", "CAL_EXIT_THR", "CAL_TILT_CLAMP", "CAL_COIN",
)

_MODULE_CACHE: dict[tuple, object] = {}


def _no_feather(*_a, **_k):
    raise FileNotFoundError("hermetic test: real side-data feathers are never read")


def load_strategy(filename: str, env: dict[str, str] | None = None):
    """Import user_data/strategies/<filename> as a fresh module under `env`."""
    env = dict(env or {})
    key = (filename, tuple(sorted(env.items())))
    if key in _MODULE_CACHE:
        return _MODULE_CACHE[key]

    saved = {k: os.environ.get(k) for k in _STRATEGY_ENV_VARS + tuple(env)}
    try:
        for k in _STRATEGY_ENV_VARS:
            os.environ.pop(k, None)
        os.environ.update(env)
        name = "ftt_" + Path(filename).stem + "__" + "_".join(
            f"{k}-{v}" for k, v in sorted(env.items())).replace(".", "p").replace("-", "_")
        spec = importlib.util.spec_from_file_location(name, STRAT_DIR / filename)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        with patch.object(pd, "read_feather", _no_feather):
            spec.loader.exec_module(mod)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    _MODULE_CACHE[key] = mod
    return mod


def ft_config(pair: str = "BTC/USDT", **over) -> dict:
    cfg = {
        "stake_currency": "USDT", "stake_amount": "unlimited", "max_open_trades": 1,
        "timeframe": "1d", "dry_run": True, "dry_run_wallet": 10_000,
        "trading_mode": "spot",
        "exchange": {"name": "binance", "pair_whitelist": [pair]},
        "runmode": "backtest", "datadir": "/tmp", "user_data_dir": "/tmp",
        "strategy_path": "user_data/strategies",
    }
    cfg.update(over)
    return cfg


def make_strategy(cls, pair: str = "BTC/USDT", **cfg_over):
    return cls(ft_config(pair, **cfg_over))


# ------------------------------------------------------------- OHLCV builders
START = datetime(2023, 1, 2, tzinfo=timezone.utc)  # a Monday


def ohlcv_from_returns(rets, *, start: datetime = START, base: float = 100.0,
                       noise: float = 0.002, seed: int = 0) -> pd.DataFrame:
    """Deterministic daily OHLCV from per-bar log returns (+ small seeded noise)."""
    rets = np.asarray(rets, dtype=float)
    rng = np.random.default_rng(seed)
    r = rets + rng.normal(0.0, noise, len(rets)) if noise else rets
    close = base * np.exp(np.cumsum(r))
    open_ = np.concatenate([[base], close[:-1]])
    high = np.maximum(open_, close) * 1.01
    low = np.minimum(open_, close) * 0.99
    vol = 1000.0 + rng.uniform(0, 100, len(rets))
    dates = pd.date_range(start, periods=len(rets), freq="1D", tz="UTC")
    return pd.DataFrame({"date": dates, "open": open_, "high": high, "low": low,
                         "close": close, "volume": vol})


def bull_ohlcv(n: int = 400, **kw) -> pd.DataFrame:
    """Steady uptrend: close > EMA200, 30d return ~ +18%, strong ADX."""
    return ohlcv_from_returns(np.full(n, 0.006), **kw)


def bear_ohlcv(n_up: int = 300, n_down: int = 100, **kw) -> pd.DataFrame:
    """Long uptrend then a sustained -1.5%/day slide: close < EMA200, 30d ret << -10%."""
    return ohlcv_from_returns(np.concatenate([np.full(n_up, 0.006), np.full(n_down, -0.015)]), **kw)


def flat_ohlcv(n: int = 400, **kw) -> pd.DataFrame:
    return ohlcv_from_returns(np.zeros(n), **kw)


# ------------------------------------------------------------- signal helpers
def col(df: pd.DataFrame, name: str) -> pd.Series:
    """Signal column with missing -> 0 (freqtrade leaves it absent when never set)."""
    if name not in df.columns:
        return pd.Series(0, index=df.index)
    return df[name].fillna(0)


def run_pipeline(strat, df: pd.DataFrame, pair: str = "BTC/USDT") -> pd.DataFrame:
    md = {"pair": pair}
    out = strat.populate_indicators(df.copy(), md)
    out = strat.populate_entry_trend(out, md)
    out = strat.populate_exit_trend(out, md)
    return out


def assert_no_lookahead(strat, df: pd.DataFrame, cuts, pair: str = "BTC/USDT",
                        seed: int = 123) -> None:
    """Row i of every derived column (indicators + entry/exit signals) must be
    identical when (a) rows > i are removed and (b) rows > i are scrambled."""
    full = run_pipeline(strat, df, pair)
    derived = [c for c in full.columns if c not in df.columns]
    for c in ("enter_long", "exit_long"):
        if c not in derived:
            derived.append(c)

    def norm(x: pd.DataFrame, i: int) -> pd.DataFrame:
        out = pd.DataFrame({c: (col(x, c) if c in ("enter_long", "exit_long") else x[c])
                            for c in derived}).iloc[: i + 1]
        return out.astype(object).where(out.notna(), None)

    rng = np.random.default_rng(seed)
    for i in cuts:
        trunc = run_pipeline(strat, df.iloc[: i + 1].copy(), pair)
        pd.testing.assert_frame_equal(norm(full, i), norm(trunc, i), check_dtype=False,
                                      obj=f"truncated-at-{i}")
        alt = df.copy()
        k = len(alt) - (i + 1)
        if k > 0:
            f = np.exp(rng.normal(0, 0.2, k))
            for c in ("open", "high", "low", "close"):
                alt.loc[alt.index[i + 1:], c] = alt[c].iloc[i + 1:].to_numpy() * f
            alt.loc[alt.index[i + 1:], "volume"] = alt["volume"].iloc[i + 1:].to_numpy() * f
        scrambled = run_pipeline(strat, alt, pair)
        pd.testing.assert_frame_equal(norm(full, i), norm(scrambled, i), check_dtype=False,
                                      obj=f"scrambled-after-{i}")


# ------------------------------------------------------------- side-data frames
def date_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(df["date"], utc=True).dt.normalize(), name="date")


def halving_frame(df: pd.DataFrame, bias: float = 0.0, phase: str = "NEUTRAL") -> pd.DataFrame:
    idx = date_index(df)
    return pd.DataFrame({"cycle_bias": bias, "phase": phase}, index=idx)


def anomaly_frame(df: pd.DataFrame, flagged_dates=(), coin: str = "BTC") -> pd.DataFrame:
    idx = date_index(df)
    flags = pd.Series(0, index=idx)
    for d in flagged_dates:
        flags.loc[pd.Timestamp(d).tz_convert("UTC").normalize()] = 1
    return pd.DataFrame({"coin": coin, "is_anomaly": flags.to_numpy()}, index=idx)


def macro_frame(df: pd.DataFrame, risk_on: float = 0.0, spy_up: int = 1, **extra) -> pd.DataFrame:
    idx = date_index(df)
    data = {"macro_risk_on": risk_on, "spy_above_ema50": spy_up}
    data.update(extra)
    return pd.DataFrame(data, index=idx)


# ------------------------------------------------------------- trade / wallet fakes
class FakeTrade:
    """Just enough of freqtrade's Trade for adjust_trade_position / ROI checks."""

    def __init__(self, amount: float, open_rate: float, *, pair: str = "BTC/USDT",
                 enter_tag: str = "", open_date: datetime = START):
        self.pair = pair
        self.stake_currency = "USDT"
        self.amount = float(amount)
        self.open_rate = float(open_rate)
        self.stake_amount = float(amount) * float(open_rate)  # cost basis
        self.enter_tag = enter_tag
        self.open_date_utc = open_date
        self.has_open_orders = False
        self.nr_of_successful_entries = 1
        self.trade_direction = "long"


def attach_runtime(strat, analyzed: pd.DataFrame, free: float):
    """Fake DataProvider + Wallets so adjust_trade_position/custom_stake_amount run."""
    strat.dp = MagicMock()
    strat.dp.get_analyzed_dataframe = MagicMock(return_value=(analyzed, None))
    strat.wallets = SimpleNamespace(get_free=lambda _cur: free)
    return strat


def adjust(strat, trade: FakeTrade, rate: float, *, min_stake: float = 5.0,
           max_stake: float = 1e9, now: datetime | None = None):
    now = now or (START + timedelta(days=400))
    return strat.adjust_trade_position(
        trade, now, rate, current_profit=rate / trade.open_rate - 1,
        min_stake=min_stake, max_stake=max_stake,
        current_entry_rate=rate, current_exit_rate=rate,
        current_entry_profit=rate / trade.open_rate - 1,
        current_exit_profit=rate / trade.open_rate - 1,
    )


def freqtrade_exit_amount(stake: float, trade: FakeTrade) -> float:
    """freqtrade 2026.4 freqtradebot.process_open_trade_positions (lines ~805-815):
    a negative adjust_trade_position return becomes
        amount = |stake| * trade.amount / trade.stake_amount
    i.e. a fraction of the COST BASIS, not stake/current_rate."""
    return abs(float(stake)) * trade.amount / trade.stake_amount


def allocation_after_trim(stake: float, trade: FakeTrade, rate: float, free: float) -> float:
    """Coin share of the portfolio after freqtrade executes the negative `stake`."""
    sold = freqtrade_exit_amount(stake, trade)
    coin_val = (trade.amount - sold) * rate
    return coin_val / (coin_val + free + sold * rate)


def roi_would_exit(strat, trade: FakeTrade, profit: float, days_open: int = 200) -> bool:
    """IStrategy.min_roi_reached with the int-keyed ROI table StrategyResolver builds."""
    strat.minimal_roi = {int(k): float(v) for k, v in dict(strat.minimal_roi).items()}
    return bool(strat.min_roi_reached(trade, profit, trade.open_date_utc + timedelta(days=days_open)))


SIZING_XFAIL_REASON = (
    "C14b sizing pitfall: adjust_trade_position returns the MARKET-VALUE overweight as a "
    "negative stake, but freqtrade 2026.4 (freqtradebot.py ~L805-815) sells "
    "|stake|*trade.amount/trade.stake_amount coins (cost-basis fraction). In profit this "
    "over-sells: e.g. 1 coin bought @100, price 200, free 0 -> trim leaves the coin share "
    "well below target. Fix pattern: partial_exit_stake() on fix/dynrebal-sizing."
)

ROI_XFAIL_REASON = (
    "minimal_roi {'0': 10.0} is used as a 'never ROI-exit' sentinel (exits are "
    "signal/regime-driven) but +1000% vs avg entry is reachable (C14b precedent: closed "
    "the SOL dynrebal trade in 2021; DOGE/SOL/ADA/AVAX did 10x+ in 2021). Fix: minimal_roi = {}."
)
