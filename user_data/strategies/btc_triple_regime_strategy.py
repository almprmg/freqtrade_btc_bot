"""BtcTripleRegimeStrategy — three independent regime detectors must agree.

Idea from meta-analysis (G): Pure Shield uses ONE regime rule
(EMA200 + 30d-ret + ADX). One rule has false positives. Three
independent detectors agreeing is much higher conviction.

Detectors (independent):
  D1 — Momentum: 30d return > +5% AND price > EMA200
  D2 — Trend strength: ADX > 25 AND +DI > -DI AND price > EMA50
  D3 — Volatility regime: ATR z-score < 1 (not in vol-spike) AND
                          close > rolling 60d midpoint

ENTRY: all three say BULL for CONFIRM bars (default 3)
EXIT:  any one says BEAR (more reactive on exits than entries)

Sizing:
  3/3 agree → 85% target (full conviction)
  2/3 + bull bias → 50% target
  1/3 or less → 0% (cash)

Modes (env TR_MODE):
  TR_BAL      — confirm 3 bars (default)
  TR_FAST     — confirm 2 bars (earlier entries, more false starts)
  TR_SLOW     — confirm 5 bars (very high conviction)
  TR_STRICT   — confirm 3, only enter when ALL 3 agree (no 2/3 entries)
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


MODE = os.environ.get("TR_MODE", "TR_BAL").upper()

MODE_PARAMS: dict[str, dict] = {
    "TR_BAL":    {"confirm_bars": 3, "two_of_three": True,  "full_target": 0.85, "half_target": 0.50},
    "TR_FAST":   {"confirm_bars": 2, "two_of_three": True,  "full_target": 0.85, "half_target": 0.50},
    "TR_SLOW":   {"confirm_bars": 5, "two_of_three": True,  "full_target": 0.85, "half_target": 0.50},
    "TR_STRICT": {"confirm_bars": 3, "two_of_three": False, "full_target": 0.85, "half_target": 0.0},
}
if MODE not in MODE_PARAMS:
    raise ValueError(f"unknown TR_MODE: {MODE}; valid: {list(MODE_PARAMS)}")
P = MODE_PARAMS[MODE]
CONFIRM = int(P["confirm_bars"])
TWO_OF_THREE_OK = bool(P["two_of_three"])
FULL_TARGET = float(P["full_target"])
HALF_TARGET = float(P["half_target"])


class BtcTripleRegimeStrategy(IStrategy):
    INTERFACE_VERSION: int = 3
    timeframe: str = "1d"
    can_short: bool = False
    process_only_new_candles: bool = True

    minimal_roi: dict = {"0": 10.0}
    stoploss: float = -0.99
    use_custom_stoploss: bool = False
    position_adjustment_enable: bool = True
    max_entry_position_adjustment: int = 5000
    use_exit_signal: bool = True
    exit_profit_only: bool = False
    startup_candle_count: int = 220

    order_types = {"entry": "limit", "exit": "limit",
                   "stoploss": "limit", "stoploss_on_exchange": False}

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe.copy()
        df["ema50"] = ta.EMA(df, timeperiod=50)
        df["ema200"] = ta.EMA(df, timeperiod=200)
        df["adx"] = ta.ADX(df, timeperiod=14)
        df["plus_di"] = ta.PLUS_DI(df, timeperiod=14)
        df["minus_di"] = ta.MINUS_DI(df, timeperiod=14)
        df["ret_30d"] = df["close"].pct_change(30)
        df["atr"] = ta.ATR(df, timeperiod=14)
        df["atr_avg"] = df["atr"].rolling(50, min_periods=10).mean()
        df["atr_std"] = df["atr"].rolling(50, min_periods=10).std().replace(0, np.nan)
        df["atr_z"] = (df["atr"] - df["atr_avg"]) / df["atr_std"]
        df["mid_60d"] = (df["high"].rolling(60, min_periods=1).max() +
                        df["low"].rolling(60, min_periods=1).min()) / 2

        # Three detectors
        d1 = (df["ret_30d"] > 0.05) & (df["close"] > df["ema200"])
        d2 = (df["adx"] > 25) & (df["plus_di"] > df["minus_di"]) & (df["close"] > df["ema50"])
        d3 = (df["atr_z"] < 1.0) & (df["close"] > df["mid_60d"])

        df["d1"] = d1.astype(int)
        df["d2"] = d2.astype(int)
        df["d3"] = d3.astype(int)
        df["agree_count"] = df["d1"] + df["d2"] + df["d3"]

        # Confirmed agreement: same agree_count >= 3 (full) or >= 2 for N bars
        df["full_signal"] = df["agree_count"] >= 3
        df["half_signal"] = df["agree_count"] >= 2

        # Rolling persistence: signal needs to hold for CONFIRM bars
        full_persist = df["full_signal"].rolling(CONFIRM, min_periods=CONFIRM).sum() >= CONFIRM
        half_persist = df["half_signal"].rolling(CONFIRM, min_periods=CONFIRM).sum() >= CONFIRM

        # Final target
        target = pd.Series(0.0, index=df.index)
        target[full_persist] = FULL_TARGET
        if TWO_OF_THREE_OK:
            target[half_persist & ~full_persist] = HALF_TARGET
        df["target"] = target

        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        ready = df["ema200"].notna() & df["atr_z"].notna()
        enter = ready & (df["target"] >= 0.2)
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = f"triple:{MODE.lower()}"
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        # Exit when target drops below 0.1 (any detector turned bearish)
        df.loc[df["target"] < 0.10, "exit_long"] = 1
        df.loc[df["target"] < 0.10, "exit_tag"] = "triple:lost_consensus"
        return df

    def custom_stake_amount(
        self, pair, current_time, current_rate, proposed_stake, min_stake,
        max_stake, leverage, entry_tag, side, **kwargs,
    ):
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return float(proposed_stake)
        target = float(df.iloc[-1]["target"])
        if max_stake and max_stake > 0:
            return float(max_stake) * max(target, 0.0)
        return float(proposed_stake)

    def adjust_trade_position(
        self, trade, current_time, current_rate, current_profit, min_stake,
        max_stake, current_entry_rate, current_exit_rate, current_entry_profit,
        current_exit_profit, **kwargs,
    ):
        df, _ = self.dp.get_analyzed_dataframe(pair=trade.pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return None
        last = df.iloc[-1]
        target = float(last["target"])
        if target <= 0.10:
            return None
        btc_qty = float(trade.amount or 0)
        btc_value = btc_qty * float(current_rate)
        usdt_free = float(self.wallets.get_free(trade.stake_currency) or 0.0)
        total = btc_value + usdt_free
        if total <= 0:
            return None
        target_btc_value = target * total
        drift = btc_value - target_btc_value
        if drift < -0.05 * total and usdt_free > 1:
            buy = min(-drift, usdt_free * 0.99)
            if max_stake and max_stake > 0:
                buy = min(buy, max_stake)
            if min_stake and buy < min_stake:
                return None
            return float(buy)
        if drift > 0.10 * total:
            sell = min(drift, btc_value * 0.99)
            if min_stake and sell < min_stake:
                return None
            return -float(sell)
        return None


__all__ = ["BtcTripleRegimeStrategy"]
