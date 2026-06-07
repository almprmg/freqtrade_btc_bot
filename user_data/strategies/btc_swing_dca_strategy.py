"""BtcSwingDcaStrategy — swing طويل المدى مع تعزيز (DCA).

الفكرة:
  1. الدخول الأولي عند تأكيد بداية ترند صاعد طويل المدى
     - EMA20 cross above EMA50 (golden cross)
     - RSI > 50 (momentum positive)
     - ADX > 20 (قوة الترند)

  2. التعزيز (DCA) — مضاعفة الموقف عند:
     - السعر يرتدّ من EMA50 (دعم ديناميكي)
     - أو RSI ينزل تحت 50 ثم يعود فوقها (pullback ended)
     - حد أقصى 4 تعزيزات

  3. الخروج التدريجي:
     - أول خروج 30% عند ROI > 25%
     - الباقي يستمر مع trailing stop عند EMA50
     - الخروج الكامل عند death cross (EMA20 < EMA50)

أهداف الاستراتيجية:
  - Hold فترات طويلة (60-180 يوم avg)
  - Win rate أقل لكن avg win كبير (نمط swing)
  - DD متوسط 15-25% (نتحمّل drawdowns مقابل ride الـtrend)

محتفظ بها للتجربة فقط — غير منشورة.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


# ===== Tunable parameters =====
RSI_ENTRY_MIN      = 50       # دخول فقط لما RSI > 50
ADX_ENTRY_MIN      = 20       # قوة الترند الأدنى
DCA_MAX_LEGS       = 4        # حد أقصى للتعزيزات
DCA_LEG_PCT        = 0.20     # كل تعزيز = 20% من الموقف الأصلي
PARTIAL_TAKE_AT    = 0.25     # أول جني أرباح عند +25%
PARTIAL_TAKE_PCT   = 0.30     # خذ 30% من الموقف
TRAIL_DROP_PCT     = 0.07     # trailing stop عند -7% من القمّة


class BtcSwingDcaStrategy(IStrategy):
    INTERFACE_VERSION: int = 3
    timeframe: str = "1d"
    can_short: bool = False
    process_only_new_candles: bool = True

    minimal_roi: dict = {"0": 10.0}   # لا ROI تلقائي
    stoploss: float = -0.25            # 25% hard stop (catastrophic protection)
    use_custom_stoploss: bool = True
    position_adjustment_enable: bool = True
    max_entry_position_adjustment: int = DCA_MAX_LEGS  # تعزيزات
    use_exit_signal: bool = True
    exit_profit_only: bool = False
    startup_candle_count: int = 220

    order_types = {"entry": "limit", "exit": "limit",
                   "stoploss": "limit", "stoploss_on_exchange": False}

    def populate_indicators(self, dataframe, metadata):
        df = dataframe.copy()
        df["ema20"]  = ta.EMA(df, timeperiod=20)
        df["ema50"]  = ta.EMA(df, timeperiod=50)
        df["ema200"] = ta.EMA(df, timeperiod=200)
        df["rsi"]    = ta.RSI(df, timeperiod=14)
        df["adx"]    = ta.ADX(df, timeperiod=14)
        df["atr"]    = ta.ATR(df, timeperiod=14)

        # Golden/death crosses
        df["ema20_above_50"] = (df["ema20"] > df["ema50"]).astype(int)
        df["golden_cross"] = ((df["ema20_above_50"] == 1) & (df["ema20_above_50"].shift(1) == 0)).astype(int)
        df["death_cross"]  = ((df["ema20_above_50"] == 0) & (df["ema20_above_50"].shift(1) == 1)).astype(int)

        # Pullback to EMA50 (within 3%)
        df["near_ema50"] = (
            (df["close"] >= df["ema50"] * 0.97) & (df["close"] <= df["ema50"] * 1.03)
        ).astype(int)

        # RSI bounce from <50
        df["rsi_was_low"] = (df["rsi"].shift(2) < 50).astype(int)
        df["rsi_recover"] = (df["rsi"] > 50).astype(int)
        df["rsi_bounced"] = (df["rsi_was_low"] & df["rsi_recover"]).astype(int)

        # Long-term trend filter
        df["uptrend"] = ((df["close"] > df["ema200"]) & (df["ema50"] > df["ema200"])).astype(int)

        return df

    def populate_entry_trend(self, dataframe, metadata):
        df = dataframe
        # Initial ENTRY: golden cross + RSI>50 + ADX>20 + close > EMA200
        enter = (
            (df["golden_cross"] == 1)
            & (df["rsi"] > RSI_ENTRY_MIN)
            & (df["adx"] > ADX_ENTRY_MIN)
            & (df["uptrend"] == 1)
        )
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = "swing:initial"
        return df

    def populate_exit_trend(self, dataframe, metadata):
        df = dataframe
        # Full exit on death cross or trend break
        exit_cond = (
            (df["death_cross"] == 1)
            | (df["uptrend"] == 0)  # lost long-term trend
        )
        df.loc[exit_cond, "exit_long"] = 1
        df.loc[exit_cond, "exit_tag"] = "swing:trend_end"
        return df

    def adjust_trade_position(self, trade, current_time, current_rate, current_profit,
                              min_stake, max_stake, current_entry_rate, current_exit_rate,
                              current_entry_profit, current_exit_profit, **kwargs):
        """DCA: add to position on pullbacks; partial take-profit on big wins."""
        df, _ = self.dp.get_analyzed_dataframe(pair=trade.pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return None
        last = df.iloc[-1]

        # Partial take-profit: +25% → sell 30%
        if current_profit >= PARTIAL_TAKE_AT and trade.nr_of_successful_exits == 0:
            current_value = trade.amount * float(current_rate)
            sell_amount = current_value * PARTIAL_TAKE_PCT
            if sell_amount >= (min_stake or 0):
                return -float(sell_amount)

        # DCA on pullback to EMA50 + RSI bounce
        if trade.nr_of_successful_entries < (DCA_MAX_LEGS + 1):
            pullback = last["near_ema50"] == 1 and last["rsi_bounced"] == 1
            if pullback:
                # Add a leg = 20% of original stake
                if trade.stake_amount and trade.stake_amount > 0:
                    leg = trade.stake_amount * DCA_LEG_PCT
                    if max_stake and max_stake > 0:
                        leg = min(leg, max_stake)
                    if min_stake and leg < min_stake:
                        return None
                    return float(leg)

        return None

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        """Trailing stop after first profit milestone."""
        if current_profit < 0.15:
            return -0.99  # disabled until +15% reached
        # Once +15% reached, trail at -7% from peak
        return -TRAIL_DROP_PCT


__all__ = ["BtcSwingDcaStrategy"]
