"""BtcVolShieldStrategy — Pure Shield + volatility-targeted position sizing.

Same regime detection as the Pure Shield winner (BULL/BEAR/NEUTRAL via
EMA200 + 30d return + ADX). DIFFERENCE: within the BULL state, the
position target shrinks when realized volatility is high.

This is the institutional "volatility targeting" technique. Goal:
keep VAR (value-at-risk) roughly constant regardless of regime.
Empirical research (Moreira & Muir 2017) shows vol-targeting improves
Sharpe by 10-30% on equities. For crypto with much higher vol-of-vol,
the effect can be stronger.

Position size formula:
  current_vol = rolling 30-day std of daily log returns
  target_vol  = 0.04 (4% daily — our "comfortable" baseline)
  vol_scalar  = clamp(target_vol / current_vol, MIN_SCALAR, MAX_SCALAR)
  final_target = base_target * vol_scalar

Examples:
  current_vol = 0.02 (calm)  → scalar 2.0 → can boost (capped at MAX_SCALAR)
  current_vol = 0.04 (avg)   → scalar 1.0 → full size
  current_vol = 0.08 (high)  → scalar 0.5 → half size

Modes (env VS_MODE):
  VS_CLASSIC  — base_target=0.85, target_vol=0.040, scalar [0.3, 1.0]
  VS_LOOSE    — base_target=0.85, target_vol=0.045, scalar [0.4, 1.0]
  VS_AGGR     — base_target=0.85, target_vol=0.035, scalar [0.3, 1.5] (can boost)
  VS_TIGHT    — base_target=0.75, target_vol=0.030, scalar [0.2, 1.0] (less risk)

NOTE: We do NOT use any AI / Chronos here. Walk-forward test showed
naive rolling vol beats Chronos by 6%. Keep it simple.
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


MODE = os.environ.get("VS_MODE", "VS_CLASSIC").upper()

MODE_PARAMS: dict[str, dict] = {
    "VS_CLASSIC":  {"base": 0.85, "target_vol": 0.040, "min_scalar": 0.3, "max_scalar": 1.0,
                    "confirm_bars": 3, "bull_ret_30d": 0.05, "bear_ret_30d": -0.10},
    "VS_LOOSE":    {"base": 0.85, "target_vol": 0.045, "min_scalar": 0.4, "max_scalar": 1.0,
                    "confirm_bars": 3, "bull_ret_30d": 0.05, "bear_ret_30d": -0.10},
    "VS_AGGR":     {"base": 0.85, "target_vol": 0.035, "min_scalar": 0.3, "max_scalar": 1.5,
                    "confirm_bars": 3, "bull_ret_30d": 0.05, "bear_ret_30d": -0.10},
    "VS_TIGHT":    {"base": 0.75, "target_vol": 0.030, "min_scalar": 0.2, "max_scalar": 1.0,
                    "confirm_bars": 3, "bull_ret_30d": 0.05, "bear_ret_30d": -0.10},
}
if MODE not in MODE_PARAMS:
    raise ValueError(f"unknown VS_MODE: {MODE}; valid: {list(MODE_PARAMS)}")
P = MODE_PARAMS[MODE]


class BtcVolShieldStrategy(IStrategy):
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
        df["adx"] = ta.ADX(df, timeperiod=14)
        df["ret_30d"] = df["close"].pct_change(30)

        # Realized 30-day volatility (daily log returns).
        log_ret = np.log(df["close"] / df["close"].shift(1))
        df["vol_30d"] = log_ret.rolling(30, min_periods=10).std()

        # Volatility scalar: clamp(target_vol / current_vol, MIN, MAX).
        v = df["vol_30d"].replace(0, np.nan)
        scalar = (float(P["target_vol"]) / v).clip(lower=float(P["min_scalar"]),
                                                    upper=float(P["max_scalar"]))
        df["vol_scalar"] = scalar.fillna(1.0)

        # Final target = base * scalar.
        df["target_pct"] = float(P["base"]) * df["vol_scalar"]

        # Regime detection (same as Pure Shield).
        bull = (df["close"] > df["ema200"]) & (df["ret_30d"] > float(P["bull_ret_30d"])) & (df["adx"] > 20)
        bear = (df["close"] < df["ema200"]) & (df["ret_30d"] < float(P["bear_ret_30d"]))
        rcode = pd.Series(0.0, index=df.index)
        rcode[bull] = 1.0
        rcode[bear] = -1.0
        df["regime_code"] = rcode

        n = int(P["confirm_bars"])
        rolled_min = rcode.rolling(n, min_periods=n).min()
        rolled_max = rcode.rolling(n, min_periods=n).max()
        stable = rolled_min == rolled_max
        df["regime_confirmed_code"] = rcode.where(stable, other=pd.NA).ffill().fillna(0)
        df["regime_confirmed"] = df["regime_confirmed_code"].map({1.0: "BULL", -1.0: "BEAR", 0.0: "NEUTRAL"})
        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        ready = df["ema200"].notna() & df["vol_30d"].notna()
        enter = ready & (df["regime_confirmed"] == "BULL")
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = f"volshield:{MODE.lower()}"
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        df.loc[df["regime_confirmed"] == "BEAR", "exit_long"] = 1
        df.loc[df["regime_confirmed"] == "BEAR", "exit_tag"] = f"volshield:bear"
        return df

    def custom_stake_amount(
        self, pair: str, current_time: datetime, current_rate: float,
        proposed_stake: float, min_stake: Optional[float], max_stake: float,
        leverage: float, entry_tag: Optional[str], side: str, **kwargs,
    ) -> float:
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return float(proposed_stake)
        target = float(df.iloc[-1]["target_pct"])
        if max_stake and max_stake > 0:
            return float(max_stake) * min(target, 1.0)  # cap at 100% wallet
        return float(proposed_stake)

    def adjust_trade_position(
        self, trade: Trade, current_time: datetime, current_rate: float,
        current_profit: float, min_stake: Optional[float], max_stake: float,
        current_entry_rate: float, current_exit_rate: float,
        current_entry_profit: float, current_exit_profit: float, **kwargs,
    ) -> Optional[float]:
        df, _ = self.dp.get_analyzed_dataframe(pair=trade.pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return None
        last = df.iloc[-1]
        if last["regime_confirmed"] != "BULL":
            return None

        target = min(float(last["target_pct"]), 1.0)
        btc_qty = float(trade.amount or 0)
        btc_value = btc_qty * float(current_rate)
        usdt_free = float(self.wallets.get_free(trade.stake_currency) or 0.0)
        total = btc_value + usdt_free
        if total <= 0:
            return None

        target_btc_value = target * total
        drift = btc_value - target_btc_value

        # Buy if below target by >5%, trim if above by >10%.
        if drift < -0.05 * total and usdt_free > 1:
            buy = min(-drift, usdt_free * 0.99)
            if max_stake and max_stake > 0:
                buy = min(buy, max_stake)
            if min_stake and buy < min_stake:
                return None
            return float(buy) if buy > 0 else None
        if drift > 0.10 * total:
            sell = min(drift, btc_value * 0.99)
            if min_stake and sell < min_stake:
                return None
            return -float(sell) if sell > 0 else None
        return None


__all__ = ["BtcVolShieldStrategy"]
