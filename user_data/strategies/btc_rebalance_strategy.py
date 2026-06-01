"""
BtcRebalanceStrategy — daily BTC/USDT rebalancing toward a fixed allocation.

The portfolio holds X% in BTC and (100-X)% in USDT cash. On each daily close
we compute the actual allocation and, if it has drifted past a threshold,
buy or sell BTC to push it back toward target. The idea is to monetise
volatility: BTC up → trim profits into USDT; BTC down → accumulate cheaper.

Modes (selected via ENV `REBALANCE_MODE`, default R1):
  R1_DAILY_FULL   — 50/50, rebalance fully every day
  R2_DAILY_5PCT   — 50/50, rebalance only when |drift| > 5% of portfolio
  R3_DAILY_10PCT  — 50/50, rebalance only when |drift| > 10%
  R4_25_BTC       — 25/75 BTC/USDT, full daily
  R5_75_BTC       — 75/25 BTC/USDT, full daily
  R6_HALFWAY      — 50/50, halve the drift each day (smoother)

Implementation note: Freqtrade represents one growing/shrinking BTC trade
that we DCA into (`positive` return from adjust_trade_position) and trim out
of (`negative` return). On the first bar we open with target_pct × wallet.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


MODE = os.environ.get("REBALANCE_MODE", "R5_75_BTC").upper()

MODE_PARAMS: dict[str, dict] = {
    "R1_DAILY_FULL":  {"target_pct": 0.50, "threshold_pct": 0.0,  "rebalance_fraction": 1.0},
    "R2_DAILY_5PCT":  {"target_pct": 0.50, "threshold_pct": 0.05, "rebalance_fraction": 1.0},
    "R3_DAILY_10PCT": {"target_pct": 0.50, "threshold_pct": 0.10, "rebalance_fraction": 1.0},
    "R4_25_BTC":      {"target_pct": 0.25, "threshold_pct": 0.0,  "rebalance_fraction": 1.0},
    "R5_75_BTC":      {"target_pct": 0.75, "threshold_pct": 0.0,  "rebalance_fraction": 1.0},
    "R6_HALFWAY":     {"target_pct": 0.50, "threshold_pct": 0.0,  "rebalance_fraction": 0.5},
}

if MODE not in MODE_PARAMS:
    raise ValueError(f"unknown REBALANCE_MODE: {MODE}; valid: {list(MODE_PARAMS)}")

PARAMS = MODE_PARAMS[MODE]
TARGET_PCT = PARAMS["target_pct"]
THRESHOLD_PCT = PARAMS["threshold_pct"]
REBALANCE_FRACTION = PARAMS["rebalance_fraction"]


class BtcRebalanceStrategy(IStrategy):
    INTERFACE_VERSION: int = 3

    timeframe: str = "1d"
    can_short: bool = False
    process_only_new_candles: bool = True

    # Rebalancing never wants Freqtrade's auto-exit to trigger — it controls
    # all increase/decrease via adjust_trade_position.
    minimal_roi: dict = {"0": 10.0}
    stoploss: float = -0.99
    use_custom_stoploss: bool = False

    position_adjustment_enable: bool = True
    max_entry_position_adjustment: int = 5000

    use_exit_signal: bool = False
    exit_profit_only: bool = False

    startup_candle_count: int = 220  # for EMA(200) readiness

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "limit",
        "stoploss_on_exchange": False,
    }

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        ready = df["ema200"].notna()
        df.loc[ready, "enter_long"] = 1
        df.loc[ready, "enter_tag"] = f"rebalance:{MODE.lower()}"
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        return dataframe

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: Optional[float],
        max_stake: float,
        leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> float:
        # Open the initial BTC leg at the target % of total available wallet.
        # max_stake here is what Freqtrade thinks the wallet can afford right now.
        if max_stake and max_stake > 0:
            initial = float(max_stake) * TARGET_PCT
            return max(initial, proposed_stake)  # ensure at least min entry size
        return float(proposed_stake)

    def _portfolio_state(self, trade: Trade, current_rate: float) -> tuple[float, float, float]:
        """Returns (btc_value_usdt, usdt_free, total_value)."""
        btc_qty = float(trade.amount or 0.0)
        btc_value = btc_qty * float(current_rate)
        usdt_free = float(self.wallets.get_free(trade.stake_currency) or 0.0)
        total = btc_value + usdt_free
        return btc_value, usdt_free, total

    def adjust_trade_position(
        self,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        min_stake: Optional[float],
        max_stake: float,
        current_entry_rate: float,
        current_exit_rate: float,
        current_entry_profit: float,
        current_exit_profit: float,
        **kwargs,
    ) -> Optional[float]:
        btc_value, usdt_free, total = self._portfolio_state(trade, current_rate)
        if total <= 0:
            return None

        target_btc_value = TARGET_PCT * total
        drift_usdt = btc_value - target_btc_value  # positive => too much BTC
        drift_pct = abs(drift_usdt) / total

        # Below threshold → do nothing.
        if drift_pct < THRESHOLD_PCT:
            return None

        # Apply the rebalance fraction (1.0 = full re-target, 0.5 = halfway).
        rebalance_usdt = drift_usdt * REBALANCE_FRACTION

        # `adjust_trade_position` convention: + adds USDT to position (buy more BTC);
        # − removes USDT from position (sell some BTC).
        if rebalance_usdt > 0:
            # Too much BTC → sell some. Cap by what we currently hold.
            sell_usdt = min(rebalance_usdt, btc_value * 0.99)
            if min_stake is not None and sell_usdt < min_stake:
                return None
            return -float(sell_usdt)
        else:
            # Too little BTC → buy more. Cap by free USDT.
            buy_usdt = min(-rebalance_usdt, usdt_free * 0.99)
            if max_stake is not None and max_stake > 0:
                buy_usdt = min(buy_usdt, max_stake)
            if min_stake is not None and buy_usdt < min_stake:
                return None
            return float(buy_usdt) if buy_usdt > 0 else None
