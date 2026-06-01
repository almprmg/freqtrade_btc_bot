"""BtcDynamicRebalanceStrategy — condition-driven BTC/USDT rebalancing.

Time-based rebalancers fire on a fixed schedule (daily / weekly). This one
fires on MARKET CONDITIONS — RSI extremes, Bollinger touches, profit
milestones, volatility spikes, regime shifts. Idea: only trade when the
market is actually offering an edge.

Trigger families (selected via ENV `DR_MODE`):

  Profit-based — rebalance when portfolio mark hits a milestone:
    DR_PROFIT_10  / DR_PROFIT_20 / DR_PROFIT_30

  RSI-based — RSI extremes call for action:
    DR_RSI_70_30  — trim if RSI>70, add if RSI<30
    DR_RSI_75_25  — tighter bands

  Bollinger Band touches:
    DR_BB

  Volatility (ATR):
    DR_VOL_HIGH   — trim when ATR spikes (regime change), buy when low

  Drawdown buyer:
    DR_DD_20      — only act on -20% from 90d high

  Trend-following:
    DR_EMA50      — trim above EMA50, buy below

  Combined:
    DR_RSI_AND_PROFIT — trigger needs both RSI extreme AND profit milestone
    DR_RSI_OR_BB      — trigger if RSI extreme OR BB touch

  Dynamic target (target_pct itself changes):
    DR_REGIME     — target=0.85 above EMA200, target=0.50 below

In all modes the "rebalance" action means: bring BTC back to TARGET_PCT of
total portfolio (full rebalance). Modes differ only in WHEN they fire.
Target defaults to 0.75 except DR_REGIME.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


MODE = os.environ.get("DR_MODE", "DR_PROFIT_20").upper()  # winner of 12-variant sweep


def _build_modes() -> dict[str, dict]:
    base: dict[str, dict] = {
        "target_pct": 0.75,
        "profit_trigger_pct": 0.20,    # rebalance every +20% portfolio gain since last anchor
        "rsi_high": 70.0,
        "rsi_low": 30.0,
        "bb_period": 20,
        "bb_std": 2.0,
        "atr_period": 14,
        "atr_avg_period": 50,
        "atr_spike_mult": 1.8,
        "dd_threshold": 0.20,
        "ema_short": 50,
        "ema_long": 200,
        "rebalance_fraction": 1.0,
        "trigger_type": "profit_only",  # which condition fires
        "regime_bull_target": 0.75,
        "regime_bear_target": 0.50,
    }
    return {
        "DR_PROFIT_10": {**base, "profit_trigger_pct": 0.10, "trigger_type": "profit_only"},
        "DR_PROFIT_20": {**base, "profit_trigger_pct": 0.20, "trigger_type": "profit_only"},
        "DR_PROFIT_30": {**base, "profit_trigger_pct": 0.30, "trigger_type": "profit_only"},
        "DR_RSI_70_30": {**base, "rsi_high": 70, "rsi_low": 30, "trigger_type": "rsi_only"},
        "DR_RSI_75_25": {**base, "rsi_high": 75, "rsi_low": 25, "trigger_type": "rsi_only"},
        "DR_BB": {**base, "trigger_type": "bb_only"},
        "DR_VOL_HIGH": {**base, "atr_spike_mult": 1.8, "trigger_type": "vol_only"},
        "DR_DD_20": {**base, "dd_threshold": 0.20, "trigger_type": "drawdown_only"},
        "DR_EMA50": {**base, "trigger_type": "ema_trend"},
        "DR_RSI_AND_PROFIT": {**base, "trigger_type": "rsi_and_profit", "profit_trigger_pct": 0.15},
        "DR_RSI_OR_BB": {**base, "trigger_type": "rsi_or_bb"},
        "DR_REGIME": {**base, "trigger_type": "regime_target"},
    }


DR_MODES = _build_modes()
if MODE not in DR_MODES:
    raise ValueError(f"unknown DR_MODE: {MODE}; valid: {list(DR_MODES)}")
P = DR_MODES[MODE]


class BtcDynamicRebalanceStrategy(IStrategy):
    INTERFACE_VERSION: int = 3
    timeframe: str = "1d"
    can_short: bool = False
    process_only_new_candles: bool = True

    minimal_roi: dict = {"0": 10.0}
    stoploss: float = -0.99
    use_custom_stoploss: bool = False

    position_adjustment_enable: bool = True
    max_entry_position_adjustment: int = 5000
    use_exit_signal: bool = False
    exit_profit_only: bool = False

    startup_candle_count: int = max(int(P["ema_long"]) + 20, 220)

    order_types = {
        "entry": "limit", "exit": "limit",
        "stoploss": "limit", "stoploss_on_exchange": False,
    }

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        df["rsi"] = ta.RSI(df, timeperiod=14)

        bb = ta.BBANDS(df, timeperiod=int(P["bb_period"]), nbdevup=P["bb_std"], nbdevdn=P["bb_std"])
        df["bb_upper"] = bb["upperband"]
        df["bb_middle"] = bb["middleband"]
        df["bb_lower"] = bb["lowerband"]

        df["atr"] = ta.ATR(df, timeperiod=int(P["atr_period"]))
        df["atr_avg"] = df["atr"].rolling(int(P["atr_avg_period"]), min_periods=1).mean()

        df["high_90d"] = df["high"].rolling(90, min_periods=1).max()
        df["dd_from_90d_high"] = (df["high_90d"] - df["close"]) / df["high_90d"]

        df["ema_short"] = ta.EMA(df, timeperiod=int(P["ema_short"]))
        df["ema_long"] = ta.EMA(df, timeperiod=int(P["ema_long"]))
        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        ready = df["ema_long"].notna()
        df.loc[ready, "enter_long"] = 1
        df.loc[ready, "enter_tag"] = f"dynrebal:{MODE.lower()}"
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        return dataframe

    def custom_stake_amount(
        self,
        pair: str, current_time: datetime, current_rate: float,
        proposed_stake: float, min_stake: Optional[float], max_stake: float,
        leverage: float, entry_tag: Optional[str], side: str, **kwargs,
    ) -> float:
        target = self._dynamic_target(pair)
        if max_stake and max_stake > 0:
            return float(max_stake) * target
        return float(proposed_stake)

    # ---- Dynamic target (only DR_REGIME uses it; others return base) ----- #

    def _dynamic_target(self, pair: str) -> float:
        if P["trigger_type"] != "regime_target":
            return float(P["target_pct"])
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return float(P["target_pct"])
        last = df.iloc[-1]
        return float(P["regime_bull_target"]) if last["close"] > last["ema_long"] else float(P["regime_bear_target"])

    # ---- The conditional triggers ---------------------------------------- #

    def _trigger_fires(self, last: pd.Series, profit_pct: float) -> bool:
        tt = P["trigger_type"]
        if tt == "profit_only":
            return abs(profit_pct) >= float(P["profit_trigger_pct"])
        if tt == "rsi_only":
            return last["rsi"] >= P["rsi_high"] or last["rsi"] <= P["rsi_low"]
        if tt == "bb_only":
            return last["close"] >= last["bb_upper"] or last["close"] <= last["bb_lower"]
        if tt == "vol_only":
            return last["atr"] >= last["atr_avg"] * float(P["atr_spike_mult"])
        if tt == "drawdown_only":
            return last["dd_from_90d_high"] >= float(P["dd_threshold"])
        if tt == "ema_trend":
            return True  # always rebalance toward target — direction set by relation to ema_short
        if tt == "rsi_and_profit":
            rsi_ext = last["rsi"] >= P["rsi_high"] or last["rsi"] <= P["rsi_low"]
            return rsi_ext and abs(profit_pct) >= float(P["profit_trigger_pct"])
        if tt == "rsi_or_bb":
            rsi_ext = last["rsi"] >= P["rsi_high"] or last["rsi"] <= P["rsi_low"]
            bb_touch = last["close"] >= last["bb_upper"] or last["close"] <= last["bb_lower"]
            return rsi_ext or bb_touch
        if tt == "regime_target":
            return True  # always rebalance toward (regime-dynamic) target
        return False

    # ---- DCA up/down via adjust_trade_position --------------------------- #

    def adjust_trade_position(
        self,
        trade: Trade, current_time: datetime, current_rate: float,
        current_profit: float, min_stake: Optional[float], max_stake: float,
        current_entry_rate: float, current_exit_rate: float,
        current_entry_profit: float, current_exit_profit: float, **kwargs,
    ) -> Optional[float]:
        df, _ = self.dp.get_analyzed_dataframe(pair=trade.pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return None
        last = df.iloc[-1]

        btc_qty = float(trade.amount or 0)
        btc_value = btc_qty * float(current_rate)
        usdt_free = float(self.wallets.get_free(trade.stake_currency) or 0.0)
        total = btc_value + usdt_free
        if total <= 0:
            return None

        # Effective target: regime mode tilts target by regime; otherwise static.
        if P["trigger_type"] == "regime_target":
            target = float(P["regime_bull_target"]) if last["close"] > last["ema_long"] else float(P["regime_bear_target"])
        else:
            target = float(P["target_pct"])
        target_btc_value = target * total
        drift_usdt = btc_value - target_btc_value  # >0 → too much BTC

        # Portfolio profit relative to trade open (simple proxy).
        profit_pct = float(current_profit or 0.0)

        if not self._trigger_fires(last, profit_pct):
            return None

        # ema_trend mode: direction follows regime of price vs ema_short.
        if P["trigger_type"] == "ema_trend":
            if last["close"] > last["ema_short"]:
                # uptrend → trim
                if drift_usdt <= 0:
                    return None
            else:
                if drift_usdt >= 0:
                    return None

        rebalance_usdt = drift_usdt * float(P["rebalance_fraction"])
        if rebalance_usdt > 0:
            sell_usdt = min(rebalance_usdt, btc_value * 0.99)
            if min_stake and sell_usdt < min_stake:
                return None
            return -float(sell_usdt) if sell_usdt > 0 else None
        else:
            buy_usdt = min(-rebalance_usdt, usdt_free * 0.99)
            if max_stake and max_stake > 0:
                buy_usdt = min(buy_usdt, max_stake)
            if min_stake and buy_usdt < min_stake:
                return None
            return float(buy_usdt) if buy_usdt > 0 else None


__all__ = ["BtcDynamicRebalanceStrategy", "DR_MODES"]
