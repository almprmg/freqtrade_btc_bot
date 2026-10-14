"""Shared behavioural cases for the "AI target" family (Calendar Shield, Calendar
V2, Analog Shield, Analog V2, Macro V2). They share one design:

  ai_target = BASE * sigmoid(4 * (cycle_bias + phase_shift + tilts)), forced to 0
  on anomaly / confirmed BEAR (/ macro risk-off). Entry: confirmed BULL and
  ai_target > 0.15. Exit: BEAR | anomaly | ai_target < exit threshold.
  adjust_trade_position drifts toward ai_target (buy band 5%, trim band 10%).

A test module imports these functions (pytest collects them) and provides the
fixtures `mod`, `strat`, `pair`, `inject` (callable that installs synthetic side
data into the module globals).
"""
from __future__ import annotations

import pytest

from tests._ft_helpers import (
    ROI_XFAIL_REASON, SIZING_XFAIL_REASON, FakeTrade, adjust, allocation_after_trim,
    anomaly_frame, assert_no_lookahead, attach_runtime, bear_ohlcv, bull_ohlcv, col,
    halving_frame, macro_frame, roi_would_exit, run_pipeline,
)

AI_COLS = ("ema200", "adx", "ret_30d", "regime_confirmed", "cycle_bias", "cycle_phase",
           "anomaly", "ai_target")


def install_aux(monkeypatch, mod, df, *, anomaly_dates=(), anomaly_coin="BTC", phase="NEUTRAL",
                bias=0.0, risk_on=0.0, spy_up=1, analog=0.0):
    """Install synthetic side-data covering every date of `df` into `mod`."""
    if hasattr(mod, "_HALVING"):
        monkeypatch.setattr(mod, "_HALVING", halving_frame(df, bias, phase))
    if hasattr(mod, "_ANOMALY"):
        monkeypatch.setattr(mod, "_ANOMALY", anomaly_frame(df, anomaly_dates, anomaly_coin))
    if hasattr(mod, "_MACRO"):
        monkeypatch.setattr(mod, "_MACRO", macro_frame(df, risk_on, spy_up))
    if hasattr(mod, "_ANALOG_V2"):
        f = halving_frame(df)[[]].assign(analog_v2_mean=analog)
        monkeypatch.setattr(mod, "_ANALOG_V2", f)
    if hasattr(mod, "_ANALOGS"):
        f = halving_frame(df)[[]].assign(analog_fwd_30d_mean=analog, analog_fwd_30d_winrate=0.5,
                                         calendar_5y_mean=0.0)
        monkeypatch.setattr(mod, "_ANALOGS", f)


def _analyzed(strat, inject, df, pair, **aux):
    inject(df, **aux)
    return run_pipeline(strat, df, pair)


def test_indicator_columns(strat, inject, pair):
    out = _analyzed(strat, inject, bull_ohlcv(), pair)
    for c in AI_COLS:
        assert c in out.columns, c
    assert out["ai_target"].between(0.0, 0.85 + 1e-9).all()


def test_runs_without_side_data(strat, pair):
    # Module globals stay empty (hermetic load) -> neutral defaults, no crash.
    out = run_pipeline(strat, bull_ohlcv(), pair)
    assert (out["cycle_bias"] == 0).all() and (out["anomaly"] == 0).all()
    assert col(out, "enter_long").iloc[-1] == 1


def test_no_lookahead(strat, inject, pair):
    df = bear_ohlcv()
    inject(df, anomaly_dates=[df["date"].iloc[260], df["date"].iloc[335]])
    assert_no_lookahead(strat, df, cuts=[230, 300, 340], pair=pair)


def test_bull_enters_no_exit(strat, inject, pair):
    out = _analyzed(strat, inject, bull_ohlcv(), pair)
    last = out.iloc[-1]
    assert last["regime_confirmed"] == "BULL" and last["ai_target"] > 0.20
    assert col(out, "enter_long").iloc[-1] == 1
    assert col(out, "exit_long").iloc[-1] == 0


def test_bear_exits_target_zero(strat, inject, pair):
    out = _analyzed(strat, inject, bear_ohlcv(), pair)
    assert out["regime_confirmed"].iloc[-1] == "BEAR"
    assert out["ai_target"].iloc[-1] == 0.0
    assert col(out, "enter_long").iloc[-1] == 0
    assert col(out, "exit_long").iloc[-1] == 1


def test_anomaly_forces_exit(strat, inject, pair):
    df = bull_ohlcv()
    out = _analyzed(strat, inject, df, pair, anomaly_dates=[df["date"].iloc[-1]])
    assert out["anomaly"].iloc[-1] == 1 and out["ai_target"].iloc[-1] == 0.0
    assert col(out, "enter_long").iloc[-1] == 0
    assert col(out, "exit_long").iloc[-1] == 1
    # the day before is unaffected
    assert out["anomaly"].iloc[-2] == 0 and col(out, "enter_long").iloc[-2] == 1


def test_halving_bear_phase_exits_even_in_price_bull(strat, inject, pair):
    out = _analyzed(strat, inject, bull_ohlcv(), pair, phase="BEAR", bias=-0.5)
    assert out["regime_confirmed"].iloc[-1] == "BULL"
    assert out["ai_target"].iloc[-1] < 0.15
    assert col(out, "enter_long").iloc[-1] == 0
    assert col(out, "exit_long").iloc[-1] == 1


def test_accumulation_phase_raises_target(strat, inject, pair):
    neutral = _analyzed(strat, inject, bull_ohlcv(), pair)["ai_target"].iloc[-1]
    accum = _analyzed(strat, inject, bull_ohlcv(), pair, phase="ACCUMULATION", bias=0.3)["ai_target"].iloc[-1]
    assert accum > neutral


# ------------------------------------------------------------------ sizing
def _runtime(strat, inject, pair, free, df_fn=bull_ohlcv, **aux):
    out = _analyzed(strat, inject, df_fn(), pair, **aux)
    attach_runtime(strat, out, free)
    return float(out["ai_target"].iloc[-1])


def test_initial_stake_is_ai_target(strat, inject, pair):
    target = _runtime(strat, inject, pair, 0.0)
    assert strat.custom_stake_amount(pair, None, 100, 10, 5, 1000, 1, None, "long") == pytest.approx(1000 * target)


def test_adjust_buys_toward_target(strat, inject, pair):
    target = _runtime(strat, inject, pair, free=1000.0)
    out = adjust(strat, FakeTrade(0.0001, 100.0, pair=pair), 100.0)
    assert out == pytest.approx(target * 1000.01 - 0.01, rel=1e-6)


def test_adjust_inside_band_noop(strat, inject, pair):
    target = _runtime(strat, inject, pair, free=0.0)
    total = 1000.0
    strat.wallets.get_free = lambda _c: total * (1 - target)
    assert adjust(strat, FakeTrade(total * target / 100, 100.0, pair=pair), 100.0) is None


def test_adjust_trims_overweight(strat, inject, pair):
    target = _runtime(strat, inject, pair, free=0.0)
    out = adjust(strat, FakeTrade(10.0, 100.0, pair=pair), 100.0)
    assert out == pytest.approx(-(1000 - target * 1000))


def test_adjust_noop_when_target_off(strat, inject, pair):
    _runtime(strat, inject, pair, free=1000.0, df_fn=bear_ohlcv)
    assert adjust(strat, FakeTrade(0.0001, 100.0, pair=pair), 100.0) is None


@pytest.mark.xfail(strict=True, reason=SIZING_XFAIL_REASON)
def test_trim_in_profit_lands_on_target(strat, inject, pair):
    target = _runtime(strat, inject, pair, free=0.0)
    trade = FakeTrade(1.0, 100.0, pair=pair)
    stake = adjust(strat, trade, 200.0)
    assert stake is not None and stake < 0
    assert allocation_after_trim(stake, trade, 200.0, 0.0) == pytest.approx(target, abs=0.01)


@pytest.mark.xfail(strict=True, reason=ROI_XFAIL_REASON)
def test_roi_never_exits(strat, pair):
    assert not roi_would_exit(strat, FakeTrade(1.0, 100.0, pair=pair), profit=12.0)


def test_stoploss_disabled(strat):
    assert strat.stoploss <= -0.99
