"""BtcOnChainStrategy — combine on-chain BTC fundamentals with price-based Shield.

The pure Shield uses price + EMA200 + 30d return + ADX to decide BULL/BEAR.
That's fast (responds in days) but reactive — it only knows what already
happened to the price.

On-chain data tells you what's happening on the network BEFORE it shows
up in the price:
  - Miners committing more hashpower? They're long-term bullish.
  - Transaction volume collapsing? Demand drying up.
  - Active addresses falling? User base shrinking.
  - Miner revenue depressed? Capitulation — usually a bottom.

We pre-compute a composite 0-100 on-chain score in research/onchain_indicators.py
and the strategy loads it on startup. Then on each daily bar:
  - If shield_regime == BEAR → exit (Shield is non-negotiable)
  - Else if onchain_score >= ENTER_THRESHOLD → hold target % BTC
  - Else if onchain_score <= EXIT_THRESHOLD → exit to cash
  - Otherwise hold current state (no whipsaw)

Modes (env OC_MODE):
  OC_BAL    — threshold 65 / 35, target 75% (default — best risk/reward)
  OC_AGGR   — threshold 60 / 30, target 85% (more aggressive)
  OC_TIGHT  — threshold 70 / 40, target 75% (fewer entries, higher quality)
  OC_NOSHIELD — uses ONLY on-chain (no price Shield) — for comparison
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

try:
    from _regime_shield import shield_indicators
except ImportError:  # pragma: no cover
    from user_data.strategies._regime_shield import shield_indicators


MODE = os.environ.get("OC_MODE", "OC_AGGR").upper()  # OC_AGGR won the +122% 2023 year

MODE_PARAMS: dict[str, dict] = {
    "OC_BAL":      {"target": 0.75, "enter_th": 65.0, "exit_th": 35.0, "use_shield": True},
    "OC_AGGR":     {"target": 0.85, "enter_th": 60.0, "exit_th": 30.0, "use_shield": True},
    "OC_TIGHT":    {"target": 0.75, "enter_th": 70.0, "exit_th": 40.0, "use_shield": True},
    "OC_NOSHIELD": {"target": 0.75, "enter_th": 65.0, "exit_th": 35.0, "use_shield": False},
}
if MODE not in MODE_PARAMS:
    raise ValueError(f"unknown OC_MODE: {MODE}; valid: {list(MODE_PARAMS)}")
P = MODE_PARAMS[MODE]
TARGET = float(P["target"])
ENTER_TH = float(P["enter_th"])
EXIT_TH = float(P["exit_th"])
USE_SHIELD = bool(P["use_shield"])

# Resolve the on-chain features path. We try a few common locations because
# Freqtrade's strategy_path may differ between local and docker.
_CANDIDATE_PATHS = [
    Path("/freqtrade/user_data/data/onchain_features.feather"),
    Path(__file__).resolve().parents[1] / "data" / "onchain_features.feather",
    Path(__file__).resolve().parents[2] / "user_data" / "data" / "onchain_features.feather",
]
ONCHAIN_PATH = next((p for p in _CANDIDATE_PATHS if p.exists()), _CANDIDATE_PATHS[0])

# Load on-chain features ONCE at import time (small file, ~6k rows).
try:
    _OC_DF = pd.read_feather(ONCHAIN_PATH)
    _OC_DF["date"] = pd.to_datetime(_OC_DF["date"], utc=True)
    _OC_DF = _OC_DF.set_index("date").sort_index()
    _OC_LOADED = True
except FileNotFoundError:
    _OC_DF = pd.DataFrame()
    _OC_LOADED = False


class BtcOnChainStrategy(IStrategy):
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
        if USE_SHIELD:
            df = shield_indicators(df)

        # Merge on-chain features by date (normalize to midnight UTC).
        if _OC_LOADED:
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["onchain_score"] = d.map(_OC_DF["onchain_score"])
            df["onchain_score"] = df["onchain_score"].ffill().fillna(50.0)
        else:
            df["onchain_score"] = 50.0  # neutral if data missing

        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        ready = df["ema200"].notna()
        if USE_SHIELD:
            allowed_regime = df["regime_confirmed"].isin(["BULL", "NEUTRAL"])
        else:
            allowed_regime = pd.Series(True, index=df.index)
        bullish_onchain = df["onchain_score"] >= ENTER_TH
        enter = ready & allowed_regime & bullish_onchain
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = f"onchain:{MODE.lower()}"
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        # Exit when:
        #   * On-chain score collapses below EXIT_TH, OR
        #   * Shield regime turns BEAR (if shield enabled).
        bear_onchain = df["onchain_score"] <= EXIT_TH
        if USE_SHIELD:
            bear_shield = df["regime_confirmed"] == "BEAR"
            exit_signal = bear_onchain | bear_shield
        else:
            exit_signal = bear_onchain
        df.loc[exit_signal, "exit_long"] = 1
        df.loc[exit_signal, "exit_tag"] = f"onchain:{MODE.lower()}_exit"
        return df

    def custom_stake_amount(
        self, pair: str, current_time: datetime, current_rate: float,
        proposed_stake: float, min_stake: Optional[float], max_stake: float,
        leverage: float, entry_tag: Optional[str], side: str, **kwargs,
    ) -> float:
        if max_stake and max_stake > 0:
            return float(max_stake) * TARGET
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
        if USE_SHIELD and last["regime_confirmed"] == "BEAR":
            return None
        if last["onchain_score"] <= EXIT_TH:
            return None

        btc_qty = float(trade.amount or 0)
        btc_value = btc_qty * float(current_rate)
        usdt_free = float(self.wallets.get_free(trade.stake_currency) or 0.0)
        total = btc_value + usdt_free
        if total <= 0:
            return None

        target_btc_value = TARGET * total
        drift = btc_value - target_btc_value
        # Only top up if below target by >5%, only trim if above by >10% (lazy).
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


__all__ = ["BtcOnChainStrategy"]
