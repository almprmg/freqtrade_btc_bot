"""
BtcDcaHoldStrategy — End-of-day DCA accumulation for BTC/USDT.

Strategy: each daily close, add $100 worth of BTC to a single open position
(DCA via Freqtrade's position-adjustment hook). HODL by default; TP modes
take profit at +100% and start a fresh position the next bar. Up to $500
can be deployed on a single calendar day (only relevant for tiered modes —
single-entry modes always stay at $100/day).

Freqtrade can't open many concurrent trades on the same pair, so this is
modeled as a single growing trade that DCAs in over time. The accumulated
quantity and avg cost basis are equivalent to opening many small trades.

Operating modes (selected via ENV `DCA_MODE`, defaults to V1):
  V1_BLIND       — add $100 every daily close, never sell
  V2_BLIND_TP    — V1 + take profit at +100% then start a new HODL position
  V3_RSI         — add $100 only when RSI(14) < 50
  V4_BELOW_EMA   — add $100 only when close < EMA(200)
  V5_TIERED      — $100 always; +$100 if RSI<30; +$100 if dd>30% from 90d high
  V6_TIERED_TP   — V5 + take profit at +100%

To get a true year-by-year report, run `dca_sweep.sh` then `yearly_report.py`.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


MODE = os.environ.get("DCA_MODE", "V5_TIERED").upper()
PER_BUY_USD = 100.0
DAILY_CAP_USD = 500.0
TIER_EXTRA_USD = 100.0
TP_MODES = {"V2_BLIND_TP", "V6_TIERED_TP"}


class BtcDcaHoldStrategy(IStrategy):
    INTERFACE_VERSION: int = 3

    timeframe: str = "1d"
    can_short: bool = False
    process_only_new_candles: bool = True

    minimal_roi: dict = {"0": 1.0} if MODE in TP_MODES else {"0": 10.0}
    stoploss: float = -0.99
    use_custom_stoploss: bool = False

    position_adjustment_enable: bool = True
    max_entry_position_adjustment: int = 5000  # ~ unlimited for a 5-year DCA

    use_exit_signal: bool = False
    exit_profit_only: bool = False

    # EMA(200) needs 200 days warmup; 220 for safety.
    startup_candle_count: int = 220

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "limit",
        "stoploss_on_exchange": False,
    }

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["high_90d"] = dataframe["high"].rolling(90, min_periods=1).max()
        dataframe["dd_from_90d_high"] = (
            (dataframe["high_90d"] - dataframe["close"]) / dataframe["high_90d"]
        )
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        # First entry: as soon as we have indicators ready and the per-mode
        # condition is met. Subsequent DCAs go through adjust_trade_position.
        df = dataframe
        ready = df["ema200"].notna()
        if MODE in ("V1_BLIND", "V2_BLIND_TP", "V5_TIERED", "V6_TIERED_TP"):
            cond = ready
        elif MODE == "V3_RSI":
            cond = ready & (df["rsi"] < 50)
        elif MODE == "V4_BELOW_EMA":
            cond = ready & (df["close"] < df["ema200"])
        else:
            raise ValueError(f"unknown DCA_MODE: {MODE}")

        df.loc[cond, "enter_long"] = 1
        df.loc[cond, "enter_tag"] = f"dca:{MODE.lower()}"
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        # All exits via minimal_roi (TP modes) or never (HODL modes).
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
        # Initial entry size — always one $100 unit; tier bonuses are added
        # via adjust_trade_position on subsequent days.
        return PER_BUY_USD

    def _tier_amount_for_bar(self, last_row: pd.Series) -> float:
        amount = PER_BUY_USD
        if last_row["rsi"] < 30:
            amount += TIER_EXTRA_USD
        if last_row["dd_from_90d_high"] > 0.30:
            amount += TIER_EXTRA_USD
        return min(amount, DAILY_CAP_USD)

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
        # Run only on a new daily bar (one DCA per day).
        df, _ = self.dp.get_analyzed_dataframe(pair=trade.pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return None
        last = df.iloc[-1]

        # Mode-specific eligibility for today's DCA.
        if MODE in ("V1_BLIND", "V2_BLIND_TP"):
            add = PER_BUY_USD
        elif MODE == "V3_RSI":
            add = PER_BUY_USD if last["rsi"] < 50 else 0.0
        elif MODE == "V4_BELOW_EMA":
            add = PER_BUY_USD if last["close"] < last["ema200"] else 0.0
        elif MODE in ("V5_TIERED", "V6_TIERED_TP"):
            add = self._tier_amount_for_bar(last)
        else:
            return None

        if add <= 0:
            return None

        # Sanity: don't blow past the wallet's remaining buying power. Freqtrade
        # passes max_stake which is the residual headroom; respect it.
        if max_stake is not None and max_stake > 0:
            add = min(add, max_stake)

        return float(add) if add > 0 else None
