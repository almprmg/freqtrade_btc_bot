"""Market-regime classifier used by `BtcRegimeStrategy`.

Why a separate module:
    The classification logic is the most safety-critical part of the bot —
    one wrong flip toggles the entire strategy choice — so it lives in its
    own module that can be unit-tested in isolation (no Freqtrade needed)
    and reused across strategies / backtests.

The detector reads an OHLCV DataFrame (the same shape Freqtrade hands the
strategy in `populate_indicators`) and tags every bar with two columns:

    * ``regime_raw``       — single-bar classification: ``TRENDING`` /
                              ``RANGING`` / ``NEUTRAL`` based on
                              ADX vs. its thresholds + ATR vs. its rolling mean.
    * ``regime_confirmed`` — same domain, but only flips after
                              ``confirm_bars`` consecutive bars agree on the
                              new state (whipsaw guard). Otherwise it carries
                              the previous confirmed value. This is the value
                              the strategy should branch on.

The carry-forward is stateful by definition (`confirmed[i]` depends on
`confirmed[i-1]`), so we use a small loop instead of forcing a vectorized
expression. For multi-year backtests this is still negligible vs. the rest
of the indicator pipeline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import talib.abstract as ta


class RegimeDetector:
    """Classifies each bar of an OHLCV DataFrame into a market regime.

    The detector is a pure function of the input DataFrame plus its
    configuration — no hidden state on the instance, so a single detector is
    safe to share across pairs, backtests, and tests.

    Args:
        adx_period: ADX lookback in bars. Default 14 (Wilder standard).
        atr_period: ATR lookback in bars. Default 14.
        atr_avg_period: Lookback for the ATR moving average used as the
            "noisy / quiet" baseline. Default 20.
        adx_trending_threshold: ADX must exceed this for a TRENDING bar.
            Default 25 — Wilder's classic strong-trend line.
        adx_ranging_threshold: ADX must be BELOW this for a RANGING bar.
            Default 20 — below the no-trend line.
        atr_range_multiplier: For RANGING we additionally require
            ``atr < atr_avg * multiplier`` (default 1.1 — i.e. the current
            range is no more than 10% above average noise). This filters out
            quiet-bar-with-fat-tail false positives.
        confirm_bars: How many consecutive bars must agree before
            ``regime_confirmed`` flips to the new state. Default 3.
    """

    TRENDING: str = "TRENDING"
    RANGING: str = "RANGING"
    NEUTRAL: str = "NEUTRAL"

    def __init__(
        self,
        adx_period: int = 14,
        atr_period: int = 14,
        atr_avg_period: int = 20,
        adx_trending_threshold: float = 25.0,
        adx_ranging_threshold: float = 20.0,
        atr_range_multiplier: float = 1.1,
        confirm_bars: int = 3,
    ) -> None:
        if confirm_bars < 1:
            raise ValueError("confirm_bars must be >= 1")
        if adx_trending_threshold <= adx_ranging_threshold:
            raise ValueError(
                "adx_trending_threshold must be > adx_ranging_threshold "
                "(otherwise the two regimes overlap)"
            )

        self.adx_period = adx_period
        self.atr_period = atr_period
        self.atr_avg_period = atr_avg_period
        self.adx_trending_threshold = adx_trending_threshold
        self.adx_ranging_threshold = adx_ranging_threshold
        self.atr_range_multiplier = atr_range_multiplier
        self.confirm_bars = confirm_bars

    # ------------------------------------------------------------------ #
    # public API                                                         #
    # ------------------------------------------------------------------ #
    def annotate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Append ``adx``, ``atr``, ``atr_avg``, ``regime_raw``, and
        ``regime_confirmed`` columns to ``df`` and return it.

        Mutates ``df`` in place (and returns the same object) so it fits the
        Freqtrade `populate_indicators` chaining style.
        """
        required = {"high", "low", "close"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame missing required columns: {sorted(missing)}")

        # Step 1 — indicators. ADX is direction-agnostic; we couple it with
        # ATR vs. its rolling mean to ensure a "trending" bar is also moving
        # (otherwise a quiet drift can score a high ADX without volatility).
        df["adx"] = ta.ADX(df, timeperiod=self.adx_period)
        df["atr"] = ta.ATR(df, timeperiod=self.atr_period)
        df["atr_avg"] = (
            df["atr"]
            .rolling(self.atr_avg_period, min_periods=self.atr_avg_period)
            .mean()
        )

        # Step 2 — per-bar raw classification. np.select cascades the
        # conditions in order; the first match wins, else default.
        df["regime_raw"] = np.select(
            condlist=[
                (df["adx"] > self.adx_trending_threshold) & (df["atr"] > df["atr_avg"]),
                (df["adx"] < self.adx_ranging_threshold)
                & (df["atr"] < df["atr_avg"] * self.atr_range_multiplier),
            ],
            choicelist=[self.TRENDING, self.RANGING],
            default=self.NEUTRAL,
        )
        # Warm-up bars (NaN ADX/ATR/ATR_AVG) propagate as NEUTRAL via the
        # comparisons returning False — np.select picks the default.

        # Step 3 — whipsaw guard with carry-forward of the prior confirmed
        # state. Inherently sequential (confirmed[i] depends on
        # confirmed[i-1]) so a tight numpy loop is the clean expression.
        df["regime_confirmed"] = self._apply_confirm(df["regime_raw"].to_numpy())
        return df

    def latest(self, df: pd.DataFrame) -> str:
        """Confirmed regime at the most recent bar.

        Returns NEUTRAL if `annotate` hasn't been called or the DataFrame is
        empty / still in warmup — never raises, so callers can treat it as a
        safe-by-default decision input.
        """
        if df is None or df.empty or "regime_confirmed" not in df.columns:
            return self.NEUTRAL
        val = df["regime_confirmed"].iat[-1]
        return val if isinstance(val, str) and val else self.NEUTRAL

    # ------------------------------------------------------------------ #
    # internals                                                          #
    # ------------------------------------------------------------------ #
    def _apply_confirm(self, raw: np.ndarray) -> np.ndarray:
        """Carry-forward whipsaw guard.

        For each bar i:
          * if the last ``confirm_bars`` raw values are ALL equal → set
            ``confirmed[i] = raw[i]`` (the agreed state, possibly a flip).
          * else carry ``confirmed[i] = confirmed[i-1]`` (NEUTRAL at i=0).
        """
        n = self.confirm_bars
        confirmed: np.ndarray = np.full(len(raw), self.NEUTRAL, dtype=object)
        for i in range(len(raw)):
            if i < n - 1:
                # Not enough history yet — stay NEUTRAL.
                continue
            window = raw[i - n + 1 : i + 1]
            if all(w == window[0] for w in window):
                confirmed[i] = window[0]
            else:
                confirmed[i] = confirmed[i - 1] if i > 0 else self.NEUTRAL
        return confirmed


__all__ = ["RegimeDetector"]
