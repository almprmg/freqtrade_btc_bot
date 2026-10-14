"""Behavioural tests — BtcAnalogV2Strategy (freqtrade_btc_analogv2, freqtrade_eth_analogv2).

Deployed env: ANOMALY_FLAGS_FILE=anomaly_flags_wf.feather on both bots.
Adds analog_v2 tilt + macro tilt and a hard macro risk-off exit (< -0.70).
"""
from __future__ import annotations

import pytest

from tests._ft_ai_cases import *  # noqa: F401,F403  (shared AI-target cases)
from tests._ft_ai_cases import install_aux
from tests._ft_helpers import anomaly_frame, bull_ohlcv, col, load_strategy, make_strategy, run_pipeline

FILE = "btc_analog_v2_strategy.py"


@pytest.fixture(params=["BTC/USDT", "ETH/USDT"])
def pair(request):
    return request.param


@pytest.fixture
def mod():
    return load_strategy(FILE, {"ANOMALY_FLAGS_FILE": "anomaly_flags_wf.feather"})


@pytest.fixture
def strat(mod, pair):
    return make_strategy(mod.BtcAnalogV2Strategy, pair=pair)


@pytest.fixture
def inject(monkeypatch, mod):
    return lambda df, **kw: install_aux(monkeypatch, mod, df, **kw)


def test_macro_risk_off_forces_exit(strat, inject, pair):
    df = bull_ohlcv()
    inject(df, risk_on=-0.8)
    out = run_pipeline(strat, df, pair)
    assert out["ai_target"].iloc[-1] == 0.0
    assert col(out, "enter_long").iloc[-1] == 0
    assert col(out, "exit_long").iloc[-1] == 1


def test_macro_mild_risk_off_does_not_exit(strat, inject, pair):
    df = bull_ohlcv()
    inject(df, risk_on=-0.5)
    out = run_pipeline(strat, df, pair)
    assert col(out, "exit_long").iloc[-1] == 0


def test_total_tilt_clamped(strat, inject, pair):
    df = bull_ohlcv()
    inject(df, analog=10.0, risk_on=1.0)
    out = run_pipeline(strat, df, pair)
    assert out["total_tilt"].max() == pytest.approx(0.45)


@pytest.mark.xfail(strict=True, reason=(
    "Anomaly coin hard-coded to 'BTC' (btc_analog_v2_strategy.py populate_indicators: "
    "_ANOMALY[_ANOMALY['coin'] == 'BTC']) regardless of metadata['pair']; the deployed ETH "
    "AnalogV2 bot ignores ETH anomaly flags. Input: ETH/USDT, coin='ETH' is_anomaly=1 on the "
    "last day; expected anomaly=1 + exit_long=1, actual anomaly=0."))
def test_anomaly_uses_traded_coin(monkeypatch, mod):
    s = make_strategy(mod.BtcAnalogV2Strategy, pair="ETH/USDT")
    df = bull_ohlcv()
    install_aux(monkeypatch, mod, df)
    monkeypatch.setattr(mod, "_ANOMALY", anomaly_frame(df, [df["date"].iloc[-1]], coin="ETH"))
    out = run_pipeline(s, df, "ETH/USDT")
    assert out["anomaly"].iloc[-1] == 1
    assert col(out, "exit_long").iloc[-1] == 1
