"""BtcBreakoutBossStrategy — استراتيجية breakout على المقاومة.

الفكرة الأساسية:
  1. نراقب أعلى سعر في آخر 60 يوم (Donchian high)
  2. لما السعر يكسر هذه المقاومة بـvolume مرتفع → دخول
  3. SL تحت أحدث swing low
  4. خروج عند فشل التذبذب أو ATR-trailing stop

هذا breakout strategy:
  - يدخل عند momentum واضح (مش mean-reversion)
  - وسط الترند الصاعد (مش بدايته)
  - يستهدف "explosive moves" بعد فترات تماسك

تختلف عن Calendar Shield بأنها reactive (تنتظر signal) بدل proactive (تيلت dates).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


DONCHIAN_PERIOD   = 60
VOLUME_MULT       = 1.5      # volume > 1.5x of 20-day MA
ATR_TRAIL_MULT    = 3.0      # trailing stop = 3 × ATR below peak
MAX_HOLD_DAYS     = 60       # تخرج إجباريًا بعد 60 يوم


class BtcBreakoutBossStrategy(IStrategy):
    INTERFACE_VERSION: int = 3
    timeframe: str = "1d"
    can_short: bool = False
    process_only_new_candles: bool = True
    minimal_roi: dict = {"0": 10.0}
    stoploss: float = -0.15
    use_custom_stoploss: bool = True
    position_adjustment_enable: bool = False
    use_exit_signal: bool = True
    startup_candle_count: int = 100

    def populate_indicators(self, dataframe, metadata):
        df = dataframe.copy()
        # Donchian channel
        df["dc_high"] = df["high"].rolling(DONCHIAN_PERIOD, min_periods=20).max()
        df["dc_low"] = df["low"].rolling(DONCHIAN_PERIOD, min_periods=20).min()
        df["dc_high_prev"] = df["dc_high"].shift(1)  # yesterday's 60d high

        # Volume confirmation
        df["vol_ma20"] = df["volume"].rolling(20, min_periods=10).mean()
        df["vol_spike"] = (df["volume"] > df["vol_ma20"] * VOLUME_MULT).astype(int)

        # ATR for stops
        df["atr"] = ta.ATR(df, timeperiod=14)

        # Breakout: today's high breaks above yesterday's 60d high
        df["breakout"] = (df["close"] > df["dc_high_prev"]).astype(int)

        # Trend filter — must be uptrend (above EMA100)
        df["ema100"] = ta.EMA(df, timeperiod=100)
        df["uptrend"] = (df["close"] > df["ema100"]).astype(int)

        # ADX for trend quality
        df["adx"] = ta.ADX(df, timeperiod=14)

        # MACD must be positive
        macd = ta.MACD(df, fastperiod=12, slowperiod=26, signalperiod=9)
        df["macd_positive"] = (macd["macd"] > 0).astype(int)

        return df

    def populate_entry_trend(self, dataframe, metadata):
        df = dataframe
        # Entry: breakout + volume + uptrend + ADX > 20 + MACD positive
        enter = (
            (df["breakout"] == 1)
            & (df["vol_spike"] == 1)
            & (df["uptrend"] == 1)
            & (df["adx"] > 20)
            & (df["macd_positive"] == 1)
        )
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = "breakout:enter"
        return df

    def populate_exit_trend(self, dataframe, metadata):
        df = dataframe
        # Exit on: close below previous low (failed breakout) OR uptrend broken
        exit_cond = (
            (df["close"] < df["low"].shift(1) * 0.97)
            | (df["uptrend"] == 0)
        )
        df.loc[exit_cond, "exit_long"] = 1
        df.loc[exit_cond, "exit_tag"] = "breakout:exit"
        return df

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        # ATR-based trailing stop
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return -0.15
        atr_val = float(df.iloc[-1]["atr"])
        # Trail at ATR × 3 below current price
        trail_pct = (ATR_TRAIL_MULT * atr_val) / float(current_rate)
        # Only activate trailing after +10% profit
        if current_profit < 0.10:
            return -0.15
        return -min(trail_pct, 0.20)

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        hold_days = (current_time - trade.open_date_utc).days
        if hold_days >= MAX_HOLD_DAYS:
            return "max_hold"
        return None


__all__ = ["BtcBreakoutBossStrategy"]
