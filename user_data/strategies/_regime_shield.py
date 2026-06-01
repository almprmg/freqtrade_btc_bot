"""Shared regime-shield helper. Plug into any strategy to gate entries on
BULL regime and force full exits on BEAR regime.

Usage in a strategy:
    from ._regime_shield import shield_indicators, apply_shield

    def populate_indicators(self, df, metadata):
        ...  # existing
        df = shield_indicators(df)
        return df

    def populate_entry_trend(self, df, metadata):
        ...  # existing — set enter_long where you want
        if SHIELD_ENABLED:
            df = apply_shield(df, "entry")
        return df

    def populate_exit_trend(self, df, metadata):
        ...  # existing
        if SHIELD_ENABLED:
            df = apply_shield(df, "exit")
        return df

`apply_shield(df, "entry")` zeroes enter_long when confirmed BEAR.
`apply_shield(df, "exit")`  sets exit_long=1 when confirmed BEAR.
"""
from __future__ import annotations

from typing import Literal

import pandas as pd
import talib.abstract as ta


SHIELD_CONFIG = {
    "ema_period": 200,
    "ret_period": 30,
    "bull_ret": 0.05,
    "bear_ret": -0.10,
    "adx_period": 14,
    "adx_min": 20,
    "confirm_bars": 3,
}


def shield_indicators(df: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """Add regime_confirmed column to a dataframe.

    Adds:
      regime_ema200, regime_adx, regime_ret_period, regime_code,
      regime_confirmed_code, regime_confirmed (BULL/BEAR/NEUTRAL string).
    """
    c = {**SHIELD_CONFIG, **(cfg or {})}
    df = df.copy()
    if "regime_confirmed" in df.columns:
        return df  # already computed (don't double-compute if multiple modules call this)

    df["regime_ema200"] = ta.EMA(df, timeperiod=c["ema_period"])
    df["regime_adx"] = ta.ADX(df, timeperiod=c["adx_period"])
    df["regime_ret_period"] = df["close"].pct_change(c["ret_period"])

    bull = (
        (df["close"] > df["regime_ema200"])
        & (df["regime_ret_period"] > c["bull_ret"])
        & (df["regime_adx"] > c["adx_min"])
    )
    bear = (df["close"] < df["regime_ema200"]) & (df["regime_ret_period"] < c["bear_ret"])

    code = pd.Series(0.0, index=df.index)
    code[bull] = 1.0
    code[bear] = -1.0
    df["regime_code"] = code

    n = c["confirm_bars"]
    rolled_min = code.rolling(n, min_periods=n).min()
    rolled_max = code.rolling(n, min_periods=n).max()
    stable = rolled_min == rolled_max
    confirmed = code.where(stable, other=pd.NA).ffill().fillna(0)
    df["regime_confirmed_code"] = confirmed
    df["regime_confirmed"] = confirmed.map({1.0: "BULL", -1.0: "BEAR", 0.0: "NEUTRAL"})
    return df


def apply_shield(df: pd.DataFrame, kind: Literal["entry", "exit"]) -> pd.DataFrame:
    """Mutates enter_long/exit_long based on regime_confirmed."""
    if "regime_confirmed" not in df.columns:
        return df  # caller forgot to add indicators; no-op rather than crash
    if kind == "entry":
        # Forbid new entries in BEAR. Allow NEUTRAL and BULL through unchanged.
        if "enter_long" in df.columns:
            df.loc[df["regime_confirmed"] == "BEAR", "enter_long"] = 0
    elif kind == "exit":
        # Force full exit during BEAR (override whatever exit_long the strategy set).
        if "exit_long" not in df.columns:
            df["exit_long"] = 0
        df.loc[df["regime_confirmed"] == "BEAR", "exit_long"] = 1
    return df


def regime_allows_add(last_row: pd.Series) -> bool:
    """For position_adjustment_enable strategies — return False when in BEAR
    so adjust_trade_position skips additions during the down regime."""
    if "regime_confirmed" not in last_row:
        return True
    return last_row["regime_confirmed"] != "BEAR"


__all__ = ["shield_indicators", "apply_shield", "regime_allows_add", "SHIELD_CONFIG"]
