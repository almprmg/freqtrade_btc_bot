"""Behavioural tests — BtcAnalogShieldStrategy (freqtrade_btc_analog_shield).

Deployed env: ANOMALY_FLAGS_FILE=anomaly_flags_wf.feather. Adds analog tilt
(analog_fwd_30d_mean / calendar_5y_mean side data) on top of Calendar Shield.
"""
from __future__ import annotations

import pytest

from tests._ft_ai_cases import *  # noqa: F401,F403  (shared AI-target cases)
from tests._ft_ai_cases import install_aux
from tests._ft_helpers import bull_ohlcv, load_strategy, make_strategy, run_pipeline

FILE = "btc_analog_shield_strategy.py"


@pytest.fixture
def pair():
    return "BTC/USDT"


@pytest.fixture
def mod():
    return load_strategy(FILE, {"ANOMALY_FLAGS_FILE": "anomaly_flags_wf.feather"})


@pytest.fixture
def strat(mod):
    return make_strategy(mod.BtcAnalogShieldStrategy)


@pytest.fixture
def inject(monkeypatch, mod):
    return lambda df, **kw: install_aux(monkeypatch, mod, df, **kw)


def test_analog_columns_and_clamp(strat, inject):
    df = bull_ohlcv()
    inject(df, analog=5.0)  # absurd analog mean -> clipped to 0.5, times W=0.30
    out = run_pipeline(strat, df)
    for c in ("analog_mean", "analog_winrate", "calendar_5y_mean", "analog_tilt_total", "total_tilt"):
        assert c in out.columns
    assert out["analog_tilt_total"].max() == pytest.approx(0.15)
    assert out["total_tilt"].max() <= 0.40 + 1e-12


def test_bullish_analog_raises_target(strat, inject):
    df = bull_ohlcv()
    inject(df, analog=0.0)
    base = run_pipeline(strat, df)["ai_target"].iloc[-1]
    inject(df, analog=0.3)
    assert run_pipeline(strat, df)["ai_target"].iloc[-1] > base
