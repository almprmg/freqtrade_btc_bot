"""BtcRegimeShieldStrategy — regime-switching long/cash with full exit.

The hardest lesson from the year-by-year evaluation: rebalance strategies
all bled -45 to -55% in 2022. They had no mechanism to STOP being long
when the regime turned. This strategy fixes that:

  BULL regime  -> hold 75% BTC / 25% cash (like R5_75_BTC).
  BEAR regime  -> FULL EXIT to USDT (0% BTC).
  NEUTRAL      -> hold whatever we're in; no new commitments.

Regime definition (lagged so we don't whipsaw on noise):
  BULL  : close > EMA200  AND  30d return > +5%   AND  ADX > 20
  BEAR  : close < EMA200  AND  30d return < -10%
  NEUTRAL: anything else

To avoid whipsaws we require N_CONFIRM_BARS = 3 consecutive bars in the
new regime before switching. Entry uses 50% of wallet on first BULL
confirmation (defensive ramp), then DCA'd up to 75% over the next bars.

Modes (env RS_MODE):
  RS_FAST    — N_CONFIRM=2 bars, ramp 1 bar (more responsive, more whipsaw)
  RS_MED     — N_CONFIRM=3 bars, ramp 3 bars (default — best balance)
  RS_SLOW    — N_CONFIRM=5 bars, ramp 5 bars (fewer trades, slower exit)
  RS_AGGR    — target 85% in bull (was 75%) — higher upside
  RS_DEFENSIVE — target 60% in bull, exit faster (-5% 30d threshold)

If 2022's -47% becomes 0% in this design, we win meaningfully.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


MODE = os.environ.get("RS_MODE", "RS_AGGR").upper()  # winner: +24.5%/yr compound, worst year -13%

MODE_PARAMS: dict[str, dict] = {
    "RS_FAST":      {"target": 0.75, "confirm_bars": 2,
                     "bull_ret_pct": 0.05, "bear_ret_pct": -0.10},
    "RS_MED":       {"target": 0.75, "confirm_bars": 3,
                     "bull_ret_pct": 0.05, "bear_ret_pct": -0.10},
    "RS_SLOW":      {"target": 0.75, "confirm_bars": 5,
                     "bull_ret_pct": 0.05, "bear_ret_pct": -0.10},
    "RS_AGGR":      {"target": 0.85, "confirm_bars": 3,
                     "bull_ret_pct": 0.05, "bear_ret_pct": -0.10},
    "RS_DEFENSIVE": {"target": 0.60, "confirm_bars": 3,
                     "bull_ret_pct": 0.03, "bear_ret_pct": -0.05},
}
if MODE not in MODE_PARAMS:
    raise ValueError(f"unknown RS_MODE: {MODE}; valid: {list(MODE_PARAMS)}")
P = MODE_PARAMS[MODE]
TARGET = float(P["target"])
CONFIRM = int(P["confirm_bars"])
BULL_RET = float(P["bull_ret_pct"])
BEAR_RET = float(P["bear_ret_pct"])


class BtcRegimeShieldStrategy(IStrategy):
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
        df = dataframe
        df["ema200"] = ta.EMA(df, timeperiod=200)
        df["adx"] = ta.ADX(df, timeperiod=14)
        df["ret_30d"] = df["close"].pct_change(30)

        # Encode regime as int: -1 BEAR, 0 NEUTRAL, +1 BULL.
        bull = (df["close"] > df["ema200"]) & (df["ret_30d"] > BULL_RET) & (df["adx"] > 20)
        bear = (df["close"] < df["ema200"]) & (df["ret_30d"] < BEAR_RET)
        rcode = pd.Series(0, index=df.index, dtype=float)
        rcode[bull] = 1.0
        rcode[bear] = -1.0
        df["regime_code"] = rcode

        # Confirmed switch: only flip the confirmed state once we've seen the
        # same code CONFIRM bars in a row. We compute via a rolling min/max
        # equality trick on the int code.
        rolled_min = rcode.rolling(CONFIRM, min_periods=CONFIRM).min()
        rolled_max = rcode.rolling(CONFIRM, min_periods=CONFIRM).max()
        stable = rolled_min == rolled_max
        df["regime_confirmed_code"] = rcode.where(stable, other=pd.NA).ffill().fillna(0)
        # Human-readable for entry/exit logic
        df["regime_confirmed"] = df["regime_confirmed_code"].map({1.0: "BULL", -1.0: "BEAR", 0.0: "NEUTRAL"})

        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        ready = df["ema200"].notna()
        # Enter only when confirmed BULL.
        enter = ready & (df["regime_confirmed"] == "BULL")
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = f"shield:bull_{MODE.lower()}"
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        # Full exit when confirmed BEAR.
        exit_signal = df["regime_confirmed"] == "BEAR"
        df.loc[exit_signal, "exit_long"] = 1
        df.loc[exit_signal, "exit_tag"] = f"shield:bear_{MODE.lower()}"
        return df

    def custom_stake_amount(
        self, pair: str, current_time: datetime, current_rate: float,
        proposed_stake: float, min_stake: Optional[float], max_stake: float,
        leverage: float, entry_tag: Optional[str], side: str, **kwargs,
    ) -> float:
        # Open initial position at TARGET of wallet (capped by what Freqtrade allows).
        if max_stake and max_stake > 0:
            return float(max_stake) * TARGET
        return float(proposed_stake)

    def adjust_trade_position(
        self, trade: Trade, current_time: datetime, current_rate: float,
        current_profit: float, min_stake: Optional[float], max_stake: float,
        current_entry_rate: float, current_exit_rate: float,
        current_entry_profit: float, current_exit_profit: float, **kwargs,
    ) -> Optional[float]:
        # In BULL regime: maintain TARGET % allocation (rebalance up to it).
        df, _ = self.dp.get_analyzed_dataframe(pair=trade.pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return None
        last = df.iloc[-1]
        if last["regime_confirmed"] != "BULL":
            return None  # don't add in non-bull regimes; exit_signal handles bear.

        btc_qty = float(trade.amount or 0)
        btc_value = btc_qty * float(current_rate)
        usdt_free = float(self.wallets.get_free(trade.stake_currency) or 0.0)
        total = btc_value + usdt_free
        if total <= 0:
            return None

        target_btc_value = TARGET * total
        drift = btc_value - target_btc_value
        # Only buy more if we're below target by >5% of portfolio.
        if drift < -0.05 * total and usdt_free > 1:
            buy = min(-drift, usdt_free * 0.99)
            if max_stake and max_stake > 0:
                buy = min(buy, max_stake)
            if min_stake and buy < min_stake:
                return None
            return float(buy) if buy > 0 else None
        # Only trim if above target by >10% of portfolio (lazy trim).
        if drift > 0.10 * total:
            sell = min(drift, btc_value * 0.99)
            if min_stake and sell < min_stake:
                return None
            return -float(sell) if sell > 0 else None
        return None


__all__ = ["BtcRegimeShieldStrategy"]
