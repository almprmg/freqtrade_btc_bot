"""BtcPairComboStrategy — blend two low-correlation strategies into one.

Based on meta-analyzer finding: Shield variants vs Meta-Adaptive variants
have correlation = -0.78 on yearly returns. Running both should smooth
the equity curve substantially.

Internal blend:
  target_shield = 0.85 if Shield says BULL else 0.0  (Pure Shield AGGR logic)
  target_meta   = computed by Meta-Adaptive state machine (CASH/DEF/BAL/AGGR)
  final_target  = 0.5 * target_shield + 0.5 * target_meta

This makes the position size = average of two independent signals.
  - Both agree BULL → fully invested
  - One agrees → half allocation
  - Both disagree / bear → cash
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


# Sub-strategy parameters (mirrors winning configs).
SHIELD_TARGET = 0.85
SHIELD_CONFIRM = 3
SHIELD_BULL_RET = 0.05
SHIELD_BEAR_RET = -0.10

META_CASH_DD = 0.15
META_COOLDOWN = 14
META_AGGR_T = 0.85
META_BAL_T = 0.60
META_DEF_T = 0.30

BLEND_W_SHIELD = 0.5   # 50/50 default
BLEND_W_META = 0.5


def _compute_shield(df: pd.DataFrame) -> pd.Series:
    bull = (df["close"] > df["ema200"]) & (df["ret_30d"] > SHIELD_BULL_RET) & (df["adx"] > 20)
    bear = (df["close"] < df["ema200"]) & (df["ret_30d"] < SHIELD_BEAR_RET)
    rcode = pd.Series(0.0, index=df.index)
    rcode[bull] = 1.0
    rcode[bear] = -1.0
    n = SHIELD_CONFIRM
    rmin = rcode.rolling(n, min_periods=n).min()
    rmax = rcode.rolling(n, min_periods=n).max()
    stable = rmin == rmax
    rc = rcode.where(stable, other=pd.NA).ffill().fillna(0)
    target = pd.Series(0.0, index=df.index)
    target[rc == 1.0] = SHIELD_TARGET
    return target


def _compute_meta(df: pd.DataFrame) -> pd.Series:
    """Vectorized state machine — produces target per row."""
    states = []
    cash_until = -1
    state = "DEF"
    for i in range(len(df)):
        row = df.iloc[i]
        if pd.isna(row["ema200"]):
            states.append(state)
            continue
        if row["dd_from_peak"] >= META_CASH_DD:
            if state != "CASH":
                cash_until = i + META_COOLDOWN
            state = "CASH"
            states.append(state)
            continue
        if state == "CASH":
            if i < cash_until:
                states.append(state); continue
            if (row["close"] > row["ema200"] and row["ret_30d"] > 0.05
                    and row["dd_from_peak"] < 0.05):
                state = "DEF"
            states.append(state); continue
        if (state == "DEF" and row["close"] > row["ema200"]
                and row["ret_30d"] > 0.10 and row["adx"] > 25):
            state = "BAL"
        elif (state == "BAL" and row["ret_60d"] > 0.20 and row["adx"] > 30
                and row["close"] > row["ema50"]):
            state = "AGGR"
        elif (state == "AGGR" and (row["ret_30d"] < 0 or row["close"] < row["ema50"])):
            state = "BAL"
        elif (state == "BAL" and (row["close"] < row["ema200"] or row["ret_30d"] < -0.05)):
            state = "DEF"
        states.append(state)

    targets = {"CASH": 0.0, "DEF": META_DEF_T, "BAL": META_BAL_T, "AGGR": META_AGGR_T}
    return pd.Series([targets.get(s, 0.0) for s in states], index=df.index)


class BtcPairComboStrategy(IStrategy):
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
        df["ema200"] = ta.EMA(df, timeperiod=200)
        df["ema50"] = ta.EMA(df, timeperiod=50)
        df["adx"] = ta.ADX(df, timeperiod=14)
        df["ret_30d"] = df["close"].pct_change(30)
        df["ret_60d"] = df["close"].pct_change(60)
        df["peak_60d"] = df["high"].rolling(60, min_periods=1).max()
        df["dd_from_peak"] = (df["peak_60d"] - df["close"]) / df["peak_60d"]

        # Sub-strategy targets
        df["target_shield"] = _compute_shield(df)
        df["target_meta"] = _compute_meta(df)

        # Blended final target
        df["final_target"] = (
            BLEND_W_SHIELD * df["target_shield"] +
            BLEND_W_META * df["target_meta"]
        ).clip(0.0, 1.0)
        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        ready = df["ema200"].notna()
        enter = ready & (df["final_target"] >= 0.20)
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = "combo:meta+shield"
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        df.loc[df["final_target"] < 0.10, "exit_long"] = 1
        df.loc[df["final_target"] < 0.10, "exit_tag"] = "combo:both_bear"
        return df

    def custom_stake_amount(
        self, pair, current_time, current_rate, proposed_stake, min_stake,
        max_stake, leverage, entry_tag, side, **kwargs,
    ):
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return float(proposed_stake)
        target = float(df.iloc[-1]["final_target"])
        if max_stake and max_stake > 0:
            return float(max_stake) * target
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
        target = float(last["final_target"])
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


__all__ = ["BtcPairComboStrategy"]
