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


@pytest.mark.xfail(strict=True, reason=(
    "Anomaly coin hard-coded to 'BTC' (btc_calendar_shield_strategy.py populate_indicators: "
    "_ANOMALY[_ANOMALY['coin'] == 'BTC']) regardless of metadata['pair']. The ETH/BNB/XRP "
    "Calendar Shield bots therefore never react to their OWN coin's anomaly flags (and do "
    "react to BTC's). Input: ETH/USDT, flags coin='ETH' is_anomaly=1 on the last day; "
    "expected anomaly=1 + exit_long=1, actual anomaly=0 and enter_long=1."))
def test_anomaly_uses_traded_coin(monkeypatch, mod):
    s = make_strategy(mod.BtcCalendarShieldStrategy, pair="ETH/USDT")
    df = bull_ohlcv()
    install_aux(monkeypatch, mod, df)
    monkeypatch.setattr(mod, "_ANOMALY", anomaly_frame(df, [df["date"].iloc[-1]], coin="ETH"))
    out = run_pipeline(s, df, "ETH/USDT")
    assert out["anomaly"].iloc[-1] == 1
    assert col(out, "exit_long").iloc[-1] == 1
