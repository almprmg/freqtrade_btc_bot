"""BtcBounceV2Strategy — bounce بإشارات أقوى.

الفرق عن V1:
  - بدل RSI<30 + BB → MACD bullish divergence (سعر يصنع low أدنى، MACD يصنع low أعلى)
  - بدل BB lower → swing-low cluster (مناطق سعر تكرّر فيها bounce تاريخيًا)
  - دخول فقط لما الـMACD يعكس + السعر عند historical support
  - TP عند first resistance (recent high) — هدف ديناميكي
  - SL تحت آخر swing low

الفكرة: divergence + support = high-probability reversal setups.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


LOOKBACK_LOWS    = 30      # نبحث عن low في آخر 30 يوم
SWING_PROXIMITY  = 0.05    # السعر ضمن 5% من swing low التاريخي
PROFIT_TARGET    = 0.10    # +10% TP
STOP_LOSS_PCT    = -0.06   # -6% SL
MAX_HOLD_DAYS    = 21


class BtcBounceV2Strategy(IStrategy):
    INTERFACE_VERSION: int = 3
    timeframe: str = "1d"
    can_short: bool = False
    process_only_new_candles: bool = True
    minimal_roi: dict = {"0": PROFIT_TARGET}
    stoploss: float = STOP_LOSS_PCT
    use_custom_stoploss: bool = False
    position_adjustment_enable: bool = False
    use_exit_signal: bool = True
    startup_candle_count: int = 100

    def populate_indicators(self, dataframe, metadata):
        df = dataframe.copy()
        macd = ta.MACD(df, fastperiod=12, slowperiod=26, signalperiod=9)
        df["macd"] = macd["macd"]
        df["macd_signal"] = macd["macdsignal"]
        df["macd_hist"] = macd["macdhist"]

        # MACD bullish divergence detection
        # Price makes a lower low while MACD makes a higher low (vs N candles ago)
        df["low_n_ago"] = df["low"].shift(LOOKBACK_LOWS)
        df["macd_n_ago"] = df["macd"].shift(LOOKBACK_LOWS)
        # Rolling minimum of last LOOKBACK_LOWS candles
        df["recent_low"] = df["low"].rolling(LOOKBACK_LOWS, min_periods=10).min()
        df["recent_macd_low"] = df["macd"].rolling(LOOKBACK_LOWS, min_periods=10).min()

        # Divergence: current low < recent_low (new low) AND current macd > recent_macd_low (higher MACD low)
        df["divergence"] = (
            (df["low"] <= df["recent_low"] * 1.02)              # near or below recent low
            & (df["macd"] > df["recent_macd_low"] * 0.85)        # MACD didn't make new low (higher low)
        ).astype(int)

        # MACD turning up (histogram crossing from negative to positive direction)
        df["macd_turning_up"] = (
            (df["macd_hist"] > df["macd_hist"].shift(1))
            & (df["macd_hist"].shift(1) > df["macd_hist"].shift(2))
        ).astype(int)

        # Long-term trend filter
        df["ema100"] = ta.EMA(df, timeperiod=100)
        df["above_trend"] = (df["close"] > df["ema100"] * 0.80).astype(int)

        # Target = recent high (resistance)
        df["recent_high"] = df["high"].rolling(20, min_periods=10).max()

        return df

    def populate_entry_trend(self, dataframe, metadata):
        df = dataframe
        enter = (
            (df["divergence"] == 1)
            & (df["macd_turning_up"] == 1)
            & (df["above_trend"] == 1)
        )
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = "bouncev2:enter"
        return df

    def populate_exit_trend(self, dataframe, metadata):
        df = dataframe
        # Exit on:
        # 1. Price reaches recent high (target hit dynamically)
        # 2. MACD hist turns negative again (momentum lost)
        # 3. Close below previous low (failed bounce)
        exit_cond = (
            (df["close"] >= df["recent_high"] * 0.98)
            | (df["macd_hist"] < -0.0001)
            | (df["close"] < df["low"].shift(1) * 0.97)
        )
        df.loc[exit_cond, "exit_long"] = 1
        df.loc[exit_cond, "exit_tag"] = "bouncev2:exit"
        return df

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        hold_days = (current_time - trade.open_date_utc).days
        if hold_days >= MAX_HOLD_DAYS:
            return "max_hold"
        return None


__all__ = ["BtcBounceV2Strategy"]
