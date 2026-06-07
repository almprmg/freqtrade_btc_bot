"""BtcBounceScalperStrategy — يحدّد مناطق الارتداد ويدخل سريعًا.

الفكرة:
  1. ينتظر السعر يصل لمنطقة oversold (RSI<30) عند دعم قوي
  2. يتأكّد من بداية ارتداد (شمعة خضراء + volume spike + RSI ينعطف)
  3. يدخل سريعًا
  4. هدف ربح محدّد (BB middle أو +8%) → يخرج
  5. وقف خسارة ضيّق (-3.5%)
  6. مدّة قصوى = 7 أيام (لا swing)

أهداف الاستراتيجية:
  - Win rate عالي (>60%) بمكاسب صغيرة متكرّرة
  - DD محدود (<10%)
  - الـEdge من الـmean-reversion في الـoversold zones

ملاحظة: هذه استراتيجية mean-reversion (عكس Calendar Shield التي trend-following).
محتفظ بها للتجربة فقط — غير منشورة.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


# ===== Tunable parameters =====
RSI_OVERSOLD       = 38      # خفّفت من 30 (نادر جدًا على 1d)
RSI_OVERBOUGHT     = 65      # جني أرباح أسرع
BB_PERIOD          = 20
BB_STD             = 2.0
BB_PROXIMITY       = 1.05    # ضمن 5% من BB lower
PROFIT_TARGET_PCT  = 0.08    # +8% take profit
STOP_LOSS_PCT      = -0.06   # -6% (vol BTC اليومي يصل أحيانًا -5%)
MAX_HOLD_DAYS      = 14      # 14 يوم


class BtcBounceScalperStrategy(IStrategy):
    INTERFACE_VERSION: int = 3
    timeframe: str = "1d"
    can_short: bool = False
    process_only_new_candles: bool = True

    # Use freqtrade's built-in ROI/stoploss for the scalper
    minimal_roi: dict = {"0": PROFIT_TARGET_PCT}      # exit immediately when +8%
    stoploss: float = STOP_LOSS_PCT                    # -3.5% hard stop

    use_custom_stoploss: bool = False
    position_adjustment_enable: bool = False           # no DCA (this is scalper)
    use_exit_signal: bool = True
    exit_profit_only: bool = False
    startup_candle_count: int = 50

    order_types = {"entry": "limit", "exit": "limit",
                   "stoploss": "limit", "stoploss_on_exchange": False}

    def populate_indicators(self, dataframe, metadata):
        df = dataframe.copy()

        # RSI for oversold/overbought detection
        df["rsi"] = ta.RSI(df, timeperiod=14)
        df["rsi_prev"] = df["rsi"].shift(1)
        df["rsi_rising"] = (df["rsi"] > df["rsi_prev"]).astype(int)

        # Bollinger Bands for support zone detection
        bb = ta.BBANDS(df, timeperiod=BB_PERIOD, nbdevup=BB_STD, nbdevdn=BB_STD)
        df["bb_upper"] = bb["upperband"]
        df["bb_mid"] = bb["middleband"]
        df["bb_lower"] = bb["lowerband"]
        df["near_bb_lower"] = (df["close"] <= df["bb_lower"] * BB_PROXIMITY).astype(int)

        # Volume confirmation (used as soft signal, optional)
        df["vol_ma20"] = df["volume"].rolling(20, min_periods=10).mean()
        df["vol_spike"] = (df["volume"] > df["vol_ma20"] * 1.1).astype(int)

        # Bounce candle: close > open (green) AND close > previous close
        df["bounce_candle"] = ((df["close"] > df["open"]) & (df["close"] > df["close"].shift(1))).astype(int)

        # Major trend filter — don't catch falling knife in deep bear
        df["ema100"] = ta.EMA(df, timeperiod=100)
        df["above_ema100"] = (df["close"] > df["ema100"] * 0.92).astype(int)  # tolerate -8% below

        return df

    def populate_entry_trend(self, dataframe, metadata):
        df = dataframe
        # ENTRY (loosened): oversold + near BB lower + green candle + not in deep bear
        # Removed volume requirement (too rare on 1d), removed RSI rising (already implicit)
        enter = (
            (df["rsi"] < RSI_OVERSOLD)
            & (df["near_bb_lower"] == 1)
            & (df["bounce_candle"] == 1)
            & (df["above_ema100"] == 1)
        )
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = "bounce:enter"
        return df

    def populate_exit_trend(self, dataframe, metadata):
        df = dataframe
        # EXIT signals:
        # 1. RSI overbought (>70)
        # 2. Price reaches BB middle (target reached)
        # 3. Failed bounce — close back below previous low
        exit_cond = (
            (df["rsi"] > RSI_OVERBOUGHT)
            | (df["close"] >= df["bb_mid"])
            | ((df["close"] < df["low"].shift(1)) & (df["close"] < df["open"]))
        )
        df.loc[exit_cond, "exit_long"] = 1
        df.loc[exit_cond, "exit_tag"] = "bounce:exit"
        return df

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        # Force exit after MAX_HOLD_DAYS regardless
        hold_days = (current_time - trade.open_date_utc).days
        if hold_days >= MAX_HOLD_DAYS:
            return "max_hold_reached"
        return None


__all__ = ["BtcBounceScalperStrategy"]
