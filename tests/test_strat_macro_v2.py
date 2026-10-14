"""Behavioural tests — BtcMacroV2Strategy (freqtrade_btc_macro_v2).

Deployed env (docker-compose.macro-v2.yml): ANOMALY_FLAGS_FILE=anomaly_flags_wf.feather,
MV_W_MACRO=0.20, MV_W_SPY=0.10, MV_W_VIX/QQQ/DXY/RATES=0, MV_EXIT_THR=-0.70,
MV_MODE=tilt, MV_COIN=BTC.
"""
from __future__ import annotations

import pytest

from tests._ft_ai_cases import *  # noqa: F401,F403  (shared AI-target cases)
from tests._ft_ai_cases import install_aux
from tests._ft_helpers import bull_ohlcv, col, load_strategy, make_strategy, run_pipeline

FILE = "btc_macro_v2_strategy.py"
ENV = {
    "ANOMALY_FLAGS_FILE": "anomaly_flags_wf.feather", "MV_W_MACRO": "0.20", "MV_W_VIX": "0.00",
    "MV_W_SPY": "0.10", "MV_W_QQQ": "0.00", "MV_W_DXY": "0.00", "MV_W_RATES": "0.00",
    "MV_EXIT_THR": "-0.70", "MV_MODE": "tilt", "MV_COIN": "BTC",
}


@pytest.fixture
def pair():
    return "BTC/USDT"


@pytest.fixture
def mod():
    return load_strategy(FILE, ENV)


@pytest.fixture
def strat(mod):
    return make_strategy(mod.BtcMacroV2Strategy)


@pytest.fixture
def inject(monkeypatch, mod):
    return lambda df, **kw: install_aux(monkeypatch, mod, df, **kw)


def test_env_applied(mod):
    assert (mod.W_MACRO, mod.W_SPY, mod.EXIT_THR, mod.MODE, mod.COIN) == (0.2, 0.1, -0.7, "tilt", "BTC")
    assert mod.W_VIX == mod.W_QQQ == mod.W_DXY == mod.W_RATES == 0.0


def test_macro_risk_off_forces_exit(strat, inject):
    df = bull_ohlcv()
    inject(df, risk_on=-0.75)
    out = run_pipeline(strat, df)
    assert out["ai_target"].iloc[-1] == 0.0
    assert col(out, "enter_long").iloc[-1] == 0 and col(out, "exit_long").iloc[-1] == 1


def test_macro_risk_on_raises_target(strat, inject):
    df = bull_ohlcv()
    inject(df, risk_on=0.0, spy_up=0)
    low = run_pipeline(strat, df)["ai_target"].iloc[-1]
    inject(df, risk_on=1.0, spy_up=1)
    high = run_pipeline(strat, df)["ai_target"].iloc[-1]
    assert high > low


def test_total_tilt_clamped(strat, inject):
    df = bull_ohlcv()
    inject(df, risk_on=5.0, spy_up=1)
    assert run_pipeline(strat, df)["total_tilt"].max() == pytest.approx(0.30)
