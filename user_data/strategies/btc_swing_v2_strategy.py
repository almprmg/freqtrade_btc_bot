"""BtcSwingV2Strategy — swing بإشارات هيكلية + macro filter.

الفرق عن V1 (golden cross):
  - بدل golden cross المتأخّر → نكتشف Higher-High + Higher-Low pattern
  - يدخل فقط لما macro_risk_on > 0.3 (risk-on bias)
  - يدخل فقط لما cycle_phase = EARLY_BULL أو PARABOLIC (تجنّب late distribution)
  - تعزيز عند pullbacks مع MACD bullish cross
  - خروج عند Lower-High pattern (هيكل ينكسر) أو cycle_phase = DISTRIBUTION

الفكرة: ندخل عند بداية الترند الواضح هيكليًا، نعزّز في pullbacks، نخرج عند انكسار الهيكل.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


def _load_aux(name: str):
    candidates = [
        Path("/freqtrade/user_data/data") / name,
        Path(__file__).resolve().parents[1] / "data" / name,
        Path(__file__).resolve().parents[2] / "user_data" / "data" / name,
    ]
    for p in candidates:
        if p.exists():
            try:
                df = pd.read_feather(p)
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"], utc=True)
                    df = df.set_index("date").sort_index()
                return df
            except Exception:
                continue
    return pd.DataFrame()


_HALVING = _load_aux("halving_cycle.feather")
_MACRO = _load_aux("macro_signals.feather")

DCA_LEGS_MAX     = 3
DCA_LEG_PCT      = 0.20
PARTIAL_TAKE_PCT = 0.30
PARTIAL_TAKE_AT  = 0.30


class BtcSwingV2Strategy(IStrategy):
    INTERFACE_VERSION: int = 3
    timeframe: str = "1d"
    can_short: bool = False
    process_only_new_candles: bool = True
    minimal_roi: dict = {"0": 10.0}
    stoploss: float = -0.20
    use_custom_stoploss: bool = True
    position_adjustment_enable: bool = True
    max_entry_position_adjustment: int = DCA_LEGS_MAX
    use_exit_signal: bool = True
    startup_candle_count: int = 220

    def populate_indicators(self, dataframe, metadata):
        df = dataframe.copy()
        df["ema20"]  = ta.EMA(df, timeperiod=20)
        df["ema50"]  = ta.EMA(df, timeperiod=50)
        df["ema200"] = ta.EMA(df, timeperiod=200)
        df["rsi"]    = ta.RSI(df, timeperiod=14)
        df["adx"]    = ta.ADX(df, timeperiod=14)

        macd = ta.MACD(df, fastperiod=12, slowperiod=26, signalperiod=9)
        df["macd_hist"] = macd["macdhist"]

        # HH/HL pattern: detect higher-high + higher-low over 30-day windows
        df["high_30"] = df["high"].rolling(30, min_periods=15).max()
        df["low_30"]  = df["low"].rolling(30, min_periods=15).min()
        df["high_30_prev"] = df["high_30"].shift(30)
        df["low_30_prev"]  = df["low_30"].shift(30)

        df["hh"] = (df["high_30"] > df["high_30_prev"]).astype(int)
        df["hl"] = (df["low_30"]  > df["low_30_prev"]).astype(int)
        df["hh_hl_confirmed"] = (df["hh"] & df["hl"]).astype(int)

        # Lower-High pattern (structure breaking down)
        df["lh"] = (df["high_30"] < df["high_30_prev"]).astype(int)
        df["ll"] = (df["low_30"]  < df["low_30_prev"]).astype(int)
        df["lh_ll_breakdown"] = (df["lh"] & df["ll"]).astype(int)

        # Macro filter
        df["macro_risk_on"] = 0.0
        if not _MACRO.empty and "macro_risk_on" in _MACRO.columns:
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["macro_risk_on"] = d.map(_MACRO["macro_risk_on"].ffill()).ffill().fillna(0.0)

        # Cycle phase
        df["cycle_phase"] = "NEUTRAL"
        if not _HALVING.empty:
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["cycle_phase"] = d.map(_HALVING["phase"]).ffill().fillna("NEUTRAL")
        df["good_cycle"] = df["cycle_phase"].isin(["ACCUMULATION", "EARLY_BULL", "PARABOLIC"]).astype(int)

        # Pullback signal: price retraces to EMA50 + RSI bounces from <50
        df["near_ema50"] = ((df["close"] >= df["ema50"] * 0.96) & (df["close"] <= df["ema50"] * 1.04)).astype(int)
        df["rsi_recover"] = ((df["rsi"].shift(2) < 50) & (df["rsi"] > 50)).astype(int)
        df["pullback_buy"] = (df["near_ema50"] & df["rsi_recover"] & (df["macd_hist"] > 0)).astype(int)

        return df

    def populate_entry_trend(self, dataframe, metadata):
        df = dataframe
        # Entry: HH/HL confirmed + macro risk-on + good cycle phase + trend
        enter = (
            (df["hh_hl_confirmed"] == 1)
            & (df["macro_risk_on"] > 0.3)
            & (df["good_cycle"] == 1)
            & (df["close"] > df["ema200"])
            & (df["adx"] > 20)
        )
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = "swingv2:initial"
        return df

    def populate_exit_trend(self, dataframe, metadata):
        df = dataframe
        # Exit on: structure breakdown OR distribution phase OR macro risk-off
        exit_cond = (
            (df["lh_ll_breakdown"] == 1)
            | (df["cycle_phase"] == "DISTRIBUTION")
            | (df["cycle_phase"] == "BEAR")
            | (df["macro_risk_on"] < -0.3)
        )
        df.loc[exit_cond, "exit_long"] = 1
        df.loc[exit_cond, "exit_tag"] = "swingv2:exit"
        return df

    def adjust_trade_position(self, trade, current_time, current_rate, current_profit,
                              min_stake, max_stake, current_entry_rate, current_exit_rate,
                              current_entry_profit, current_exit_profit, **kwargs):
        df, _ = self.dp.get_analyzed_dataframe(pair=trade.pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return None
        last = df.iloc[-1]

        # Partial take-profit
        if current_profit >= PARTIAL_TAKE_AT and trade.nr_of_successful_exits == 0:
            current_value = trade.amount * float(current_rate)
            sell_amount = current_value * PARTIAL_TAKE_PCT
            if sell_amount >= (min_stake or 0):
                return -float(sell_amount)

        # DCA on pullback signal
        if trade.nr_of_successful_entries < (DCA_LEGS_MAX + 1):
            if last["pullback_buy"] == 1:
                if trade.stake_amount and trade.stake_amount > 0:
                    leg = trade.stake_amount * DCA_LEG_PCT
                    if max_stake and max_stake > 0: leg = min(leg, max_stake)
                    if min_stake and leg < min_stake: return None
                    return float(leg)
        return None

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        if current_profit < 0.15:
            return -0.99
        return -0.10  # trail at -10% from peak after +15%


__all__ = ["BtcSwingV2Strategy"]
