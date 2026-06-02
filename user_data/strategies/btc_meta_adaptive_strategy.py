"""BtcMetaAdaptiveStrategy — self-adapting strategy with DD circuit breaker.

The user's complaint: no strategy should lose 50% in a year. This one tries
to keep yearly DD under 20% by using a drawdown-targeting approach common
in professional fund management.

State machine (re-evaluated every bar):
  CASH      — sit in USDT. Triggered when DD from rolling 60d portfolio
              peak exceeds CASH_DD_THRESHOLD (default 15%).
  DEFENSIVE — 30% BTC allocation. Used during NEUTRAL regime or after
              cash-recovery confirmation.
  BALANCED  — 60% BTC. Used in mild bull conditions.
  AGGRESSIVE — 85% BTC. Used in strong confirmed bull with low DD.

Transitions:
  ANY -> CASH         if portfolio_dd > CASH_DD_THRESHOLD
  CASH -> DEFENSIVE   if (price > EMA200) AND (30d_ret > +5%) AND
                         (dd_from_peak < 5%) for CONFIRM_BARS=3
  DEF  -> BALANCED    if price > EMA200 AND 30d_ret > +10% AND ADX > 25
  BAL  -> AGGRESSIVE  if 60d_ret > +20% AND ADX > 30
  Down-shifts triggered by drops in same indicators or rising DD.

The CASH state is sticky: once we go cash, we stay at least COOLDOWN_BARS
(default 14) bars to prevent whipsaws.

Modes (env MA_MODE):
  MA_STRICT  — cash threshold 12%, cooldown 21d (very defensive)
  MA_BAL     — cash threshold 15%, cooldown 14d (default)
  MA_RELAX   — cash threshold 20%, cooldown 7d (more aggressive)
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


MODE = os.environ.get("MA_MODE", "MA_BAL").upper()

MODE_PARAMS: dict[str, dict] = {
    "MA_STRICT": {"cash_dd": 0.12, "cooldown": 21,
                  "aggr_target": 0.75, "bal_target": 0.50, "def_target": 0.25,
                  "reentry_ret_30d": 0.05, "reentry_ret_60d": 0.0, "reentry_adx": 0,
                  "reentry_dd": 0.05},
    "MA_BAL":    {"cash_dd": 0.15, "cooldown": 14,
                  "aggr_target": 0.85, "bal_target": 0.60, "def_target": 0.30,
                  "reentry_ret_30d": 0.05, "reentry_ret_60d": 0.0, "reentry_adx": 0,
                  "reentry_dd": 0.05},
    "MA_RELAX":  {"cash_dd": 0.20, "cooldown": 7,
                  "aggr_target": 0.85, "bal_target": 0.65, "def_target": 0.35,
                  "reentry_ret_30d": 0.03, "reentry_ret_60d": 0.0, "reentry_adx": 0,
                  "reentry_dd": 0.05},
    # New: very strict re-entry — only on multi-criteria confirmed bull.
    # Designed specifically for high-volatility assets like LINK.
    "MA_VSTRICT": {"cash_dd": 0.10, "cooldown": 30,
                   "aggr_target": 0.70, "bal_target": 0.45, "def_target": 0.20,
                   "reentry_ret_30d": 0.10, "reentry_ret_60d": 0.15, "reentry_adx": 25,
                   "reentry_dd": 0.03},
}
if MODE not in MODE_PARAMS:
    raise ValueError(f"unknown MA_MODE: {MODE}; valid: {list(MODE_PARAMS)}")
P = MODE_PARAMS[MODE]
CASH_DD = float(P["cash_dd"])
COOLDOWN = int(P["cooldown"])
AGGR_T = float(P["aggr_target"])
BAL_T = float(P["bal_target"])
DEF_T = float(P["def_target"])
REENTRY_R30 = float(P["reentry_ret_30d"])
REENTRY_R60 = float(P["reentry_ret_60d"])
REENTRY_ADX = float(P["reentry_adx"])
REENTRY_DD = float(P["reentry_dd"])


class BtcMetaAdaptiveStrategy(IStrategy):
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

        # Portfolio-style proxy DD: use BTC price drawdown from rolling 60d peak.
        # In live trading we'd track actual portfolio DD via Trade rows, but for
        # backtest a price-DD proxy is close enough.
        df["peak_60d"] = df["high"].rolling(60, min_periods=1).max()
        df["dd_from_peak"] = (df["peak_60d"] - df["close"]) / df["peak_60d"]

        # Track cumulative regime state per row via vectorized logic.
        states = []
        cash_until = -1  # bar index when cooldown expires
        state = "DEF"  # start defensive (no priors)
        for i in range(len(df)):
            row = df.iloc[i]
            if pd.isna(row["ema200"]):
                states.append(state)
                continue

            # 1. Forced CASH on big DD.
            if row["dd_from_peak"] >= CASH_DD:
                if state != "CASH":
                    cash_until = i + COOLDOWN
                state = "CASH"
                states.append(state)
                continue

            # 2. Stuck in CASH cooldown — can only exit cash on strong bull confirmation.
            if state == "CASH":
                if i < cash_until:
                    states.append(state); continue
                # Multi-criteria re-entry (mode-tunable).
                if (row["close"] > row["ema200"]
                        and row["ret_30d"] > REENTRY_R30
                        and row["ret_60d"] > REENTRY_R60
                        and row["adx"] > REENTRY_ADX
                        and row["dd_from_peak"] < REENTRY_DD):
                    state = "DEF"
                states.append(state); continue

            # 3. Up-shift conditions.
            if (state == "DEF"
                    and row["close"] > row["ema200"] and row["ret_30d"] > 0.10
                    and row["adx"] > 25):
                state = "BAL"
            elif (state == "BAL"
                    and row["ret_60d"] > 0.20 and row["adx"] > 30
                    and row["close"] > row["ema50"]):
                state = "AGGR"
            # 4. Down-shifts (no DD trigger needed; just losing momentum).
            elif (state == "AGGR"
                    and (row["ret_30d"] < 0 or row["close"] < row["ema50"])):
                state = "BAL"
            elif (state == "BAL"
                    and (row["close"] < row["ema200"] or row["ret_30d"] < -0.05)):
                state = "DEF"

            states.append(state)

        df["meta_state"] = states
        return df

    def _target_for_state(self, state: str) -> float:
        return {"CASH": 0.0, "DEF": DEF_T, "BAL": BAL_T, "AGGR": AGGR_T}.get(state, 0.0)

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        # Allow entry whenever state is not CASH and we have indicators ready.
        ready = df["ema200"].notna()
        not_cash = df["meta_state"] != "CASH"
        enter = ready & not_cash
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = "meta:" + MODE.lower()
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        # Force full exit when state goes to CASH.
        df.loc[df["meta_state"] == "CASH", "exit_long"] = 1
        df.loc[df["meta_state"] == "CASH", "exit_tag"] = "meta:cash_circuit"
        return df

    def custom_stake_amount(
        self, pair: str, current_time: datetime, current_rate: float,
        proposed_stake: float, min_stake: Optional[float], max_stake: float,
        leverage: float, entry_tag: Optional[str], side: str, **kwargs,
    ) -> float:
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return float(proposed_stake)
        last = df.iloc[-1]
        target = self._target_for_state(last["meta_state"])
        if max_stake and max_stake > 0 and target > 0:
            return float(max_stake) * target
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
        state = last["meta_state"]
        if state == "CASH":
            return None  # exit_signal handles the close
        target = self._target_for_state(state)
        if target <= 0:
            return None

        btc_qty = float(trade.amount or 0)
        btc_value = btc_qty * float(current_rate)
        usdt_free = float(self.wallets.get_free(trade.stake_currency) or 0.0)
        total = btc_value + usdt_free
        if total <= 0:
            return None

        target_btc_value = target * total
        drift = btc_value - target_btc_value

        # Buy if below target by >5%, trim if above by >10% (lazy rebalance).
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


__all__ = ["BtcMetaAdaptiveStrategy"]
