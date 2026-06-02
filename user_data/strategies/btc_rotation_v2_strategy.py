"""BtcRotationV2Strategy — same as V1 but reads signal_v2 (BTC-gated)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


def _pair_to_coin(pair: str) -> str:
    return pair.split("/")[0]


_CANDIDATE_PATHS = [
    Path("/freqtrade/user_data/data/rotation_signal_v2.feather"),
    Path(__file__).resolve().parents[1] / "data" / "rotation_signal_v2.feather",
    Path(__file__).resolve().parents[2] / "user_data" / "data" / "rotation_signal_v2.feather",
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


class BtcRotationV2Strategy(IStrategy):
    INTERFACE_VERSION: int = 3
    timeframe: str = "1d"
    can_short: bool = False
    process_only_new_candles: bool = True

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
        df.loc[enter, "enter_tag"] = f"rotv2:{_pair_to_coin(metadata['pair']).lower()}"
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        df.loc[~df["is_my_turn"], "exit_long"] = 1
        df.loc[~df["is_my_turn"], "exit_tag"] = "rotv2:rotated"
        return df

    def custom_stake_amount(
        self, pair: str, current_time: datetime, current_rate: float,
        proposed_stake: float, min_stake: Optional[float], max_stake: float,
        leverage: float, entry_tag: Optional[str], side: str, **kwargs,
    ) -> float:
        if max_stake and max_stake > 0:
            return float(max_stake) * 0.95
        return float(proposed_stake)


__all__ = ["BtcRotationV2Strategy"]
