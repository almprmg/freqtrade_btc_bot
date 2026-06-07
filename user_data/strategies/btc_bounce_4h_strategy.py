"""BtcBounce4hStrategy — bounce scalper على 4h timeframe.

نفس فكرة BtcBounceScalperStrategy لكن مع 4h candles بدل 1d.
- شمعة 4h = أسرع → فرص أكثر
- نفس الشروط الـlooser
- TP +5% بدل 8% (scalp 4h أقصر)
- SL -3% (احتكاك أقل)
- max hold = 48 شمعة (8 أيام)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


RSI_OVERSOLD       = 35
RSI_OVERBOUGHT     = 65
BB_PERIOD          = 20
BB_STD             = 2.0
BB_PROXIMITY       = 1.03
PROFIT_TARGET_PCT  = 0.05    # 4h: أهداف أصغر
STOP_LOSS_PCT      = -0.03
MAX_HOLD_CANDLES   = 48      # 48 × 4h = 8 days


class BtcBounce4hStrategy(IStrategy):
    INTERFACE_VERSION: int = 3
    timeframe: str = "4h"
    can_short: bool = False
    process_only_new_candles: bool = True

    minimal_roi: dict = {"0": PROFIT_TARGET_PCT}
    stoploss: float = STOP_LOSS_PCT
    use_custom_stoploss: bool = False
    position_adjustment_enable: bool = False
    use_exit_signal: bool = True
    startup_candle_count: int = 200

    order_types = {"entry": "limit", "exit": "limit",
                   "stoploss": "limit", "stoploss_on_exchange": False}

    def populate_indicators(self, dataframe, metadata):
        df = dataframe.copy()
        df["rsi"] = ta.RSI(df, timeperiod=14)
        bb = ta.BBANDS(df, timeperiod=BB_PERIOD, nbdevup=BB_STD, nbdevdn=BB_STD)
        df["bb_lower"] = bb["lowerband"]
        df["bb_mid"] = bb["middleband"]
        df["near_bb_lower"] = (df["close"] <= df["bb_lower"] * BB_PROXIMITY).astype(int)
        df["bounce_candle"] = ((df["close"] > df["open"]) & (df["close"] > df["close"].shift(1))).astype(int)
        # ema200 on 4h = ~33 days — long-term trend filter
        df["ema200"] = ta.EMA(df, timeperiod=200)
        df["above_trend"] = (df["close"] > df["ema200"] * 0.85).astype(int)
        return df

    def populate_entry_trend(self, dataframe, metadata):
        df = dataframe
        enter = (
            (df["rsi"] < RSI_OVERSOLD)
            & (df["near_bb_lower"] == 1)
            & (df["bounce_candle"] == 1)
            & (df["above_trend"] == 1)
        )
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = "bounce4h:enter"
        return df

    def populate_exit_trend(self, dataframe, metadata):
        df = dataframe
        exit_cond = (
            (df["rsi"] > RSI_OVERBOUGHT)
            | (df["close"] >= df["bb_mid"])
        )
        df.loc[exit_cond, "exit_long"] = 1
        df.loc[exit_cond, "exit_tag"] = "bounce4h:exit"
        return df

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        hold_hours = (current_time - trade.open_date_utc).total_seconds() / 3600
        if hold_hours >= MAX_HOLD_CANDLES * 4:
            return "max_hold"
        return None


__all__ = ["BtcBounce4hStrategy"]
