"""BtcAiShieldStrategy — Pure Shield + ALL the AI signals we've built.

Combines:
  1. Pure Shield regime (BULL/BEAR/NEUTRAL via price + EMA200 + ADX + 30d)
  2. Halving Cycle bias (-1 to +1) — sizes position by cycle phase
  3. Anomaly flag — exits if abnormal market state detected
  4. (future) XGBoost target — currently unused (didn't beat naive)
  5. (future) Sentiment — slot reserved for when FinBERT pipeline lands

Position sizing:
  base_target = 0.85 (Shield AGGR baseline)
  cycle_multiplier = 0.5 + cycle_bias / 2  (range 0 to 1, neutral=0.5)
  final_target = base_target * cycle_multiplier
  if anomaly_flag: final_target = 0 (force exit)
  if Shield says BEAR: final_target = 0
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


def _load_aux(name: str):
    candidates = [
        Path("/freqtrade/user_data/data") / name,
        Path(__file__).resolve().parents[1] / "data" / name,
        Path(__file__).resolve().parents[2] / "user_data" / "data" / name,
    ]
    for p in candidates:
        if p.exists():
            try:
                df = pd.read_feather(p)
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"], utc=True)
                    df = df.set_index("date").sort_index()
                return df
            except Exception:
                continue
    return pd.DataFrame()


_HALVING = _load_aux("halving_cycle.feather")
_ANOMALY = _load_aux("anomaly_flags.feather")


class BtcAiShieldStrategy(IStrategy):
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

        # Shield regime
        import pandas as _pd
        bull = (df["close"] > df["ema200"]) & (df["ret_30d"] > 0.05) & (df["adx"] > 20)
        bear = (df["close"] < df["ema200"]) & (df["ret_30d"] < -0.10)
        rcode = _pd.Series(0.0, index=df.index)
        rcode[bull] = 1.0
        rcode[bear] = -1.0
        n = 3
        rmin = rcode.rolling(n, min_periods=n).min()
        rmax = rcode.rolling(n, min_periods=n).max()
        stable = rmin == rmax
        df["regime_confirmed_code"] = rcode.where(stable, other=_pd.NA).ffill().fillna(0)
        df["regime_confirmed"] = df["regime_confirmed_code"].map({1.0: "BULL", -1.0: "BEAR", 0.0: "NEUTRAL"})

        # Halving cycle bias
        if not _HALVING.empty:
            d = _pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["cycle_bias"] = d.map(_HALVING["cycle_bias"]).ffill().fillna(0.0)
        else:
            df["cycle_bias"] = 0.0

        # Anomaly flag (BTC-specific)
        df["anomaly"] = 0
        if not _ANOMALY.empty:
            btc_anom = _ANOMALY[_ANOMALY["coin"] == "BTC"][["is_anomaly"]] if "coin" in _ANOMALY.columns else _ANOMALY
            d = _pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["anomaly"] = d.map(btc_anom["is_anomaly"]).fillna(0).astype(int)

        # Final composite target
        BASE = 0.85
        cycle_mult = (0.5 + df["cycle_bias"] / 2).clip(0.0, 1.0)
        df["ai_target"] = BASE * cycle_mult
        # Force 0 on anomaly or bear
        df.loc[df["anomaly"] == 1, "ai_target"] = 0.0
        df.loc[df["regime_confirmed"] == "BEAR", "ai_target"] = 0.0
        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        ready = df["ema200"].notna()
        enter = ready & (df["regime_confirmed"] == "BULL") & (df["ai_target"] > 0.1)
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = "ai_shield"
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        # Exit on bear, anomaly, or low ai_target
        exit_cond = (df["regime_confirmed"] == "BEAR") | (df["anomaly"] == 1) | (df["ai_target"] < 0.3)
        df.loc[exit_cond, "exit_long"] = 1
        df.loc[exit_cond, "exit_tag"] = "ai_shield:bearish"
        return df

    def custom_stake_amount(
        self, pair, current_time, current_rate, proposed_stake, min_stake,
        max_stake, leverage, entry_tag, side, **kwargs,
    ):
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return float(proposed_stake)
        target = float(df.iloc[-1]["ai_target"])
        if max_stake and max_stake > 0:
            return float(max_stake) * max(target, 0.0)
        return float(proposed_stake)

    def adjust_trade_position(
        self, trade, current_time, current_rate, current_profit,
        min_stake, max_stake, current_entry_rate, current_exit_rate,
        current_entry_profit, current_exit_profit, **kwargs,
    ):
        df, _ = self.dp.get_analyzed_dataframe(pair=trade.pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return None
        last = df.iloc[-1]
        target = float(last["ai_target"])
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


__all__ = ["BtcAiShieldStrategy"]
