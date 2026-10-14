"""Behavioural tests — BtcCalendarShieldStrategy (deployed on BTC, ETH, BNB, XRP).

Deployed env: ANOMALY_FLAGS_FILE=anomaly_flags_wf.feather (ETH/BNB bots) or
unset (BTC/XRP bots). Side data is synthetic (see tests/_ft_helpers.py).
"""
from __future__ import annotations

import pytest

from tests._ft_ai_cases import *  # noqa: F401,F403  (shared AI-target cases)
from tests._ft_ai_cases import install_aux
from tests._ft_helpers import anomaly_frame, bull_ohlcv, col, load_strategy, make_strategy, run_pipeline

FILE = "btc_calendar_shield_strategy.py"


@pytest.fixture(params=["BTC/USDT", "ETH/USDT"])
def pair(request):
    return request.param


@pytest.fixture
def mod():
    return load_strategy(FILE, {"ANOMALY_FLAGS_FILE": "anomaly_flags_wf.feather"})


@pytest.fixture
def strat(mod, pair):
    return make_strategy(mod.BtcCalendarShieldStrategy, pair=pair)


@pytest.fixture
def inject(monkeypatch, mod):
    return lambda df, **kw: install_aux(monkeypatch, mod, df, **kw)


def test_default_anomaly_file_mode_loads():
    m = load_strategy(FILE, {})
    assert m._ANOMALY.empty and m._HALVING.empty  # hermetic: nothing real was read


def test_calendar_tilt_values(strat, pair):
    out = run_pipeline(strat, bull_ohlcv(), pair)
    d = out["date"]
    oct_mon_eom = out[(d.dt.month == 10) & (d.dt.day_name() == "Monday") & (d.dt.day >= 26)]
    assert len(oct_mon_eom) >= 1
    assert oct_mon_eom["calendar_tilt"].tolist() == pytest.approx([0.25] * len(oct_mon_eom))
    plain = out[(d.dt.month == 3) & (d.dt.day_name() == "Friday") & (d.dt.day < 26)]
    assert len(plain) >= 1 and (plain["calendar_tilt"] == 0).all()


# Regression (was strict xfail): anomaly flags of the traded coin (metadata['pair']).
def test_anomaly_uses_traded_coin(monkeypatch, mod):
    s = make_strategy(mod.BtcCalendarShieldStrategy, pair="ETH/USDT")
    df = bull_ohlcv()
    install_aux(monkeypatch, mod, df)
    monkeypatch.setattr(mod, "_ANOMALY", anomaly_frame(df, [df["date"].iloc[-1]], coin="ETH"))
    out = run_pipeline(s, df, "ETH/USDT")
    assert out["anomaly"].iloc[-1] == 1
    assert col(out, "exit_long").iloc[-1] == 1


def test_anomaly_ignores_other_coins_flags(monkeypatch, mod):
    """ETH bot must not react to BTC-only anomalies when ETH has its own flags."""
    import pandas as pd
    s = make_strategy(mod.BtcCalendarShieldStrategy, pair="ETH/USDT")
    df = bull_ohlcv()
    install_aux(monkeypatch, mod, df)
    flags = pd.concat([anomaly_frame(df, [df["date"].iloc[-1]], coin="BTC"),
                       anomaly_frame(df, [], coin="ETH")])
    monkeypatch.setattr(mod, "_ANOMALY", flags)
    out = run_pipeline(s, df, "ETH/USDT")
    assert out["anomaly"].iloc[-1] == 0


def test_anomaly_falls_back_to_btc_for_unflagged_coin(monkeypatch, mod):
    """XRP has no rows in the flags files: BTC flags are the market proxy."""
    s = make_strategy(mod.BtcCalendarShieldStrategy, pair="XRP/USDT")
    df = bull_ohlcv()
    install_aux(monkeypatch, mod, df)
    monkeypatch.setattr(mod, "_ANOMALY", anomaly_frame(df, [df["date"].iloc[-1]], coin="BTC"))
    out = run_pipeline(s, df, "XRP/USDT")
    assert out["anomaly"].iloc[-1] == 1
