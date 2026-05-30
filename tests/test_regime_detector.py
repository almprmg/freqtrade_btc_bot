"""Tests for `RegimeDetector` — synthetic OHLCV, no live data, no Freqtrade."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from user_data.strategies.regime_detector import RegimeDetector


def _make_df(closes: list[float], *, start: datetime | None = None) -> pd.DataFrame:
    """Build a DataFrame with the columns talib's ADX/ATR need.

    High/low are derived as +/- 0.5% of close so true_range > 0 and
    volume is constant (not used by the detector but Freqtrade-shape).
    """
    start = start or datetime(2024, 1, 1, tzinfo=timezone.utc)
    dates = [start + timedelta(hours=4 * i) for i in range(len(closes))]
    closes_arr = np.array(closes, dtype=float)
    return pd.DataFrame(
        {
            "date": dates,
            "open": closes_arr,
            "high": closes_arr * 1.005,
            "low": closes_arr * 0.995,
            "close": closes_arr,
            "volume": np.ones_like(closes_arr) * 100.0,
        }
    )


# ---------------------------------------------------------------------- #
# constructor validation                                                 #
# ---------------------------------------------------------------------- #
def test_rejects_overlapping_thresholds() -> None:
    with pytest.raises(ValueError):
        RegimeDetector(adx_trending_threshold=20.0, adx_ranging_threshold=25.0)


def test_rejects_zero_confirm_bars() -> None:
    with pytest.raises(ValueError):
        RegimeDetector(confirm_bars=0)


# ---------------------------------------------------------------------- #
# annotate: columns + warmup                                             #
# ---------------------------------------------------------------------- #
def test_annotate_adds_expected_columns() -> None:
    df = _make_df([100.0] * 100)
    out = RegimeDetector().annotate(df)
    for col in ("adx", "atr", "atr_avg", "regime_raw", "regime_confirmed"):
        assert col in out.columns


def test_warmup_bars_are_neutral() -> None:
    df = _make_df([100.0] * 60)
    out = RegimeDetector(confirm_bars=3).annotate(df)
    # Until ADX+ATR+ATR_AVG warm up, regime_raw is NEUTRAL and so is
    # regime_confirmed.
    assert out["regime_confirmed"].iloc[:25].eq(RegimeDetector.NEUTRAL).all()


def test_annotate_rejects_missing_columns() -> None:
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})  # missing high+low
    with pytest.raises(ValueError):
        RegimeDetector().annotate(df)


# ---------------------------------------------------------------------- #
# whipsaw guard                                                          #
# ---------------------------------------------------------------------- #
def test_whipsaw_guard_blocks_single_flip() -> None:
    """A 1-bar flip should NOT change the confirmed regime."""
    det = RegimeDetector(confirm_bars=3)
    # Build a raw stream by hand and exercise the internal apply.
    raw = np.array(
        ["RANGING", "RANGING", "RANGING", "TRENDING", "RANGING", "RANGING", "RANGING"],
        dtype=object,
    )
    confirmed = det._apply_confirm(raw)
    # Index 0–2: RANGING confirmed after 3 in a row.
    assert confirmed[2] == "RANGING"
    # Index 3: single TRENDING bar — must NOT flip; carry RANGING.
    assert confirmed[3] == "RANGING"
    # Index 4–6: back to RANGING streak, still RANGING.
    assert list(confirmed[4:7]) == ["RANGING", "RANGING", "RANGING"]


def test_confirmed_flip_requires_n_in_a_row() -> None:
    det = RegimeDetector(confirm_bars=3)
    raw = np.array(
        ["RANGING", "RANGING", "RANGING", "TRENDING", "TRENDING", "TRENDING"],
        dtype=object,
    )
    confirmed = det._apply_confirm(raw)
    assert confirmed[2] == "RANGING"
    assert confirmed[3] == "RANGING"  # only 1 trending — carry
    assert confirmed[4] == "RANGING"  # only 2 trending — carry
    assert confirmed[5] == "TRENDING"  # 3rd trending — flip!


# ---------------------------------------------------------------------- #
# latest convenience                                                     #
# ---------------------------------------------------------------------- #
def test_latest_safe_on_empty_dataframe() -> None:
    det = RegimeDetector()
    assert det.latest(pd.DataFrame()) == RegimeDetector.NEUTRAL


def test_latest_returns_confirmed_value() -> None:
    df = _make_df([100.0] * 100)
    out = RegimeDetector().annotate(df)
    # Match what the column actually says — synthetic flat data → NEUTRAL
    # (no trend, no volatility above its own mean by design).
    assert out["regime_confirmed"].iat[-1] == RegimeDetector().latest(out)
