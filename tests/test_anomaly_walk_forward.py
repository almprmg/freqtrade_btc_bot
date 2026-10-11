"""C12 regression tests — walk-forward anomaly flags must not leak the future.

The legacy detector fit one IsolationForest on 2019-2023 and scored the same
years (in-sample). The walk-forward mode refits per calendar year on rows
strictly before Y-01-01. These tests pin that contract.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "anomaly_detector", REPO / "research" / "ai" / "anomaly_detector.py")
ad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ad)


def _synthetic_ohlcv(start="2017-01-01", end="2023-12-31", seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, end, freq="1D", tz="UTC")
    ret = rng.standard_t(df=3, size=len(idx)) * 0.03
    close = 1000 * np.exp(np.cumsum(ret))
    high = close * (1 + np.abs(rng.normal(0, 0.02, len(idx))))
    low = close * (1 - np.abs(rng.normal(0, 0.02, len(idx))))
    vol = rng.lognormal(10, 0.5, len(idx))
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": vol}, index=idx)


@pytest.fixture(scope="module")
def feats():
    return ad.features(_synthetic_ohlcv())


@pytest.fixture(scope="module")
def wf(feats):
    return ad.walk_forward_flags(feats, "TEST")


def test_schema(wf):
    assert list(wf.columns) == ["date", "coin", "anomaly_score", "is_anomaly", "train_end"]
    assert set(wf["is_anomaly"].unique()) <= {0, 1}
    assert not wf.duplicated(["coin", "date"]).any()


def test_every_flag_trained_strictly_before_its_date(wf):
    """Core no-leakage invariant: model for row d saw only data < d."""
    assert len(wf) > 0
    assert (wf["train_end"] < wf["date"]).all()
    # and the training cut is the year boundary, not just "earlier"
    year_start = pd.to_datetime(wf["date"].dt.year.astype(str) + "-01-01", utc=True)
    assert (wf["train_end"] < year_start).all()


def test_min_training_window_respected(feats, wf):
    for year, g in wf.groupby(wf["date"].dt.year):
        n_train = (feats.index < pd.Timestamp(f"{year}-01-01", tz="UTC")).sum()
        assert n_train >= ad.MIN_TRAIN_ROWS
    first_year = feats.index.year.min()
    assert first_year not in set(wf["date"].dt.year)  # nothing to train on


def test_future_data_cannot_change_past_flags(feats, wf):
    """Corrupt everything from 2022 on: flags for years <= 2021 must be identical."""
    poisoned = feats.copy()
    poisoned.loc[poisoned.index >= "2022-01-01"] *= 50.0
    wf2 = ad.walk_forward_flags(poisoned, "TEST")
    past = lambda d: d[d["date"] < pd.Timestamp("2022-01-01", tz="UTC")].reset_index(drop=True)
    pd.testing.assert_frame_equal(past(wf), past(wf2))
    # sanity: the poisoning did change later years, so the test has teeth
    fut = lambda d: d[d["date"] >= pd.Timestamp("2022-01-01", tz="UTC")]
    assert not np.allclose(fut(wf)["anomaly_score"].values, fut(wf2)["anomaly_score"].values)


def test_truncated_history_gives_same_flags(feats, wf):
    """Running WF on data that ends at 2021-12-31 reproduces those rows exactly."""
    cut = feats[feats.index < "2022-01-01"]
    wf_cut = ad.walk_forward_flags(cut, "TEST")
    full = wf[wf["date"] < pd.Timestamp("2022-01-01", tz="UTC")].reset_index(drop=True)
    pd.testing.assert_frame_equal(full, wf_cut.reset_index(drop=True))


def test_generated_wf_file_has_no_leakage_if_present():
    p = REPO / "user_data" / "data" / "anomaly_flags_wf.feather"
    if not p.exists():
        pytest.skip("anomaly_flags_wf.feather not generated")
    df = pd.read_feather(p)
    d = pd.to_datetime(df["date"], utc=True)
    te = pd.to_datetime(df["train_end"], utc=True)
    assert (te < d).all()
    assert (te.dt.year < d.dt.year).all()


def test_strategy_env_switch_defaults_to_live_file(monkeypatch):
    src = (REPO / "user_data" / "strategies" / "btc_calendar_shield_strategy.py").read_text(encoding="utf-8")
    assert 'os.environ.get("ANOMALY_FLAGS_FILE", "anomaly_flags.feather")' in src
