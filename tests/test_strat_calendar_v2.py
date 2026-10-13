"""Behavioural tests — BtcCalendarV2Strategy (freqtrade_btc_calendar_v2).

Deployed env: ANOMALY_FLAGS_FILE=anomaly_flags_wf.feather, CAL_W_JUL=-0.05,
CAL_W_JAN=0.10 (other CAL_* at defaults, CAL_COIN=BTC, CAL_EXIT_THR=0.20).
"""
from __future__ import annotations

import pytest

from tests._ft_ai_cases import *  # noqa: F401,F403  (shared AI-target cases)
from tests._ft_ai_cases import install_aux
from tests._ft_helpers import bull_ohlcv, load_strategy, make_strategy, run_pipeline

FILE = "btc_calendar_v2_strategy.py"
ENV = {"ANOMALY_FLAGS_FILE": "anomaly_flags_wf.feather", "CAL_W_JUL": "-0.05", "CAL_W_JAN": "0.10"}


@pytest.fixture
def pair():
    return "BTC/USDT"


@pytest.fixture
def mod():
    return load_strategy(FILE, ENV)


@pytest.fixture
def strat(mod):
    return make_strategy(mod.BtcCalendarV2Strategy)


@pytest.fixture
def inject(monkeypatch, mod):
    return lambda df, **kw: install_aux(monkeypatch, mod, df, **kw)


def test_env_weights_applied(mod):
    assert mod.W_JUL == -0.05 and mod.W_JAN == 0.10 and mod.W_OCT == 0.15
    assert mod.EXIT_THR == 0.20 and mod.COIN == "BTC"


def test_env_defaults_without_overrides():
    m = load_strategy(FILE, {})
    assert m.W_JUL == 0.05 and m.W_JAN == 0.0


def test_bad_env_value_falls_back_to_default():
    m = load_strategy(FILE, {"CAL_W_OCT": "not-a-number"})
    assert m.W_OCT == 0.15


def test_january_and_july_tilts(strat):
    out = run_pipeline(strat, bull_ohlcv())
    d = out["date"]
    jan_plain = out[(d.dt.month == 1) & d.dt.day_name().isin(["Tuesday", "Thursday"]) & (d.dt.day < 26)]
    jul_plain = out[(d.dt.month == 7) & d.dt.day_name().isin(["Tuesday", "Thursday"]) & (d.dt.day < 26)]
    assert len(jan_plain) and len(jul_plain)
    assert jan_plain["calendar_tilt"].tolist() == pytest.approx([0.10] * len(jan_plain))
    assert jul_plain["calendar_tilt"].tolist() == pytest.approx([-0.05] * len(jul_plain))
