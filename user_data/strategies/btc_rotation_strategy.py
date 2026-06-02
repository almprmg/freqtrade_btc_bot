"""BtcRotationStrategy — multi-asset rotation across BTC/ETH/SOL/BNB.

Holds whichever asset has the strongest momentum each day. Falls back to
USDT cash when no asset shows clear strength.

Designed for multi-pair Freqtrade deployment:
  config.exchange.pair_whitelist = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
  max_open_trades = 1     # only ONE asset held at any time
  position_adjustment_enable = False

Pre-computed rotation signal (run research/compute_rotation_signal.py) is
loaded from user_data/data/rotation_signal.feather. Per bar, each pair
asks: "is the signal saying my coin is the winner today?" → enter.
"is the signal saying CASH or different coin?" → exit.

This is the classic momentum / cross-sectional momentum strategy. Asness
(2013), Moskowitz et al. (2012) showed momentum works across asset
classes. For crypto with massive dispersion between coins, the edge can
be substantial.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


# Map full pair names (BTC/USDT) → coin keys in signal (BTC).
def _pair_to_coin(pair: str) -> str:
    return pair.split("/")[0]


# Load rotation signal at module import.
_CANDIDATE_PATHS = [
    Path("/freqtrade/user_data/data/rotation_signal.feather"),
    Path(__file__).resolve().parents[1] / "data" / "rotation_signal.feather",
    Path(__file__).resolve().parents[2] / "user_data" / "data" / "rotation_signal.feather",
]
SIG_PATH = next((p for p in _CANDIDATE_PATHS if p.exists()), _CANDIDATE_PATHS[0])
try:
    _SIG_DF = pd.read_feather(SIG_PATH)
    _SIG_DF["date"] = pd.to_datetime(_SIG_DF["date"], utc=True)
    _SIG_DF = _SIG_DF.set_index("date").sort_index()
    _SIG_LOADED = True
except FileNotFoundError:
    _SIG_DF = pd.DataFrame()
    _SIG_LOADED = False


class BtcRotationStrategy(IStrategy):
    INTERFACE_VERSION: int = 3
    timeframe: str = "1d"
    can_short: bool = False
    process_only_new_candles: bool = True

    # Position sizing: 95% of wallet per trade (single asset at a time).
    minimal_roi: dict = {"0": 10.0}
    stoploss: float = -0.99
    use_custom_stoploss: bool = False

    position_adjustment_enable: bool = False

    use_exit_signal: bool = True
    exit_profit_only: bool = False

    startup_candle_count: int = 220

    order_types = {"entry": "limit", "exit": "limit",
                   "stoploss": "limit", "stoploss_on_exchange": False}

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe.copy()
        my_coin = _pair_to_coin(metadata["pair"])
        df["ema200"] = ta.EMA(df, timeperiod=200)

        # Map each row's date to the rotation winner.
        if _SIG_LOADED:
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["winner"] = d.map(_SIG_DF["winner_pair"])
            df["winner"] = df["winner"].ffill().fillna("CASH")
        else:
            df["winner"] = "CASH"

        df["is_my_turn"] = df["winner"] == my_coin
        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        ready = df["ema200"].notna()
        enter = ready & df["is_my_turn"]
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = f"rotation:{_pair_to_coin(metadata['pair']).lower()}"
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        # Exit when this coin is no longer the winner.
        df.loc[~df["is_my_turn"], "exit_long"] = 1
        df.loc[~df["is_my_turn"], "exit_tag"] = "rotation:rotated_out"
        return df

    def custom_stake_amount(
        self, pair: str, current_time: datetime, current_rate: float,
        proposed_stake: float, min_stake: Optional[float], max_stake: float,
        leverage: float, entry_tag: Optional[str], side: str, **kwargs,
    ) -> float:
        # Use ~95% of wallet (small buffer for fees).
        if max_stake and max_stake > 0:
            return float(max_stake) * 0.95
        return float(proposed_stake)


__all__ = ["BtcRotationStrategy"]
