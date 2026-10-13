"""Behavioural tests — BtcRotationStrategy (freqtrade_rotation; BTC/ETH/SOL/BNB, max_open_trades=1).

Hold the coin named by rotation_signal.feather's winner_pair; exit when it is
another coin or CASH. The signal is injected synthetically (module globals
_SIG_DF / _SIG_LOADED); the real feather is never read.
"""
from __future__ import annotations

import pandas as pd
import pytest

from tests._ft_helpers import (
    ROI_XFAIL_REASON, FakeTrade, assert_no_lookahead, bull_ohlcv, col, date_index,
    load_strategy, make_strategy, roi_would_exit, run_pipeline,
)

FILE = "btc_rotation_strategy.py"


@pytest.fixture
def mod():
    return load_strategy(FILE, {})


@pytest.fixture
def df():
    return bull_ohlcv()


@pytest.fixture
def signal(monkeypatch, mod, df):
    """BTC rows 0-299, ETH 300-349, CASH 350-379, BTC 380-389; no rows for 390-399 (stale)."""
    idx = date_index(df)[:390]
    winners = ["BTC"] * 300 + ["ETH"] * 50 + ["CASH"] * 30 + ["BTC"] * 10
    sig = pd.DataFrame({"winner_pair": winners, "winner_score": 0.1}, index=idx)
    monkeypatch.setattr(mod, "_SIG_DF", sig)
    monkeypatch.setattr(mod, "_SIG_LOADED", True)
    return sig


def strat_for(mod, pair):
    return make_strategy(mod.BtcRotationStrategy, pair=pair)


def test_hermetic_load_has_no_signal(mod):
    assert mod._SIG_LOADED is False and mod._SIG_DF.empty


def test_no_signal_means_cash_never_enters(mod, df):
    out = run_pipeline(strat_for(mod, "BTC/USDT"), df, "BTC/USDT")
    assert (out["winner"] == "CASH").all()
    assert (col(out, "enter_long") == 0).all() and (col(out, "exit_long") == 1).all()


@pytest.mark.parametrize("pair,row,enter", [
    ("BTC/USDT", 250, 1), ("ETH/USDT", 250, 0),
    ("BTC/USDT", 320, 0), ("ETH/USDT", 320, 1),
    ("BTC/USDT", 360, 0), ("ETH/USDT", 360, 0), ("SOL/USDT", 360, 0),
    ("BTC/USDT", 385, 1),
])
def test_enter_only_on_my_turn_exit_otherwise(mod, df, signal, pair, row, enter):
    out = run_pipeline(strat_for(mod, pair), df, pair)
    assert col(out, "enter_long").iloc[row] == enter
    assert col(out, "exit_long").iloc[row] == 1 - enter


def test_no_entry_before_ema_ready(mod, df, signal):
    out = run_pipeline(strat_for(mod, "BTC/USDT"), df, "BTC/USDT")
    assert (col(out, "enter_long")[out["ema200"].isna()] == 0).all()


def test_stale_signal_is_forward_filled(mod, df, signal):
    """Pins current behaviour (risk, not a test failure): when the feather is not
    refreshed, the last winner is held indefinitely (ffill), there is no staleness
    fallback to CASH."""
    out = run_pipeline(strat_for(mod, "BTC/USDT"), df, "BTC/USDT")
    assert (out["winner"].iloc[390:] == "BTC").all()
    assert col(out, "enter_long").iloc[-1] == 1


def test_no_lookahead(mod, df, signal):
    assert_no_lookahead(strat_for(mod, "ETH/USDT"), df, cuts=[299, 330, 360], pair="ETH/USDT")


def test_stake_is_95pct(mod):
    s = strat_for(mod, "BTC/USDT")
    assert s.custom_stake_amount("BTC/USDT", None, 1, 10, 5, 1000, 1, None, "long") == pytest.approx(950)
    assert s.position_adjustment_enable is False


# Regression (was strict xfail): never-ROI strategies use minimal_roi = {}.
def test_roi_never_exits(mod):
    assert not roi_would_exit(strat_for(mod, "SOL/USDT"), FakeTrade(1.0, 100.0, pair="SOL/USDT"), profit=12.0)
