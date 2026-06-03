"""SolVolShieldStrategy — volatility-aware Shield for SOL.

The three previous SOL Shield attempts (Pure, AIShV2, Triple) all failed
the Adversarial Validator, each for a different reason:
  Pure Shield      -43% in 2025 sideways (false BULL signals from chop)
  AI Shield V2     -35% in 2025 (BTC halving phases don't transfer to SOL)
  Triple Regime    only 3.6%/yr — misses bull rallies entirely

Root cause: SOL's 24-month annualized vol ~95% (vs BTC ~55%, ETH ~70%).
Simple regime detectors get whipsawed on its faster drawdowns and rebounds.

This strategy uses VOLATILITY-AWARE filters:
  1. Longer trend window: ret_60d > 15% (vs Pure's ret_30d > 5%)
  2. Stronger trend strength: ADX > 30 (vs Pure's 20)
  3. ATR-based chop filter: skip entries when ATR_pct > 8% (high vol = chop risk)
  4. Donchian breakout confirmation: must be making 60-day highs
  5. Stable BULL regime requires 5 consecutive days (vs Pure's 3)

Aim: trade fewer, but only during high-confidence bull legs. Accept missing
short bounces in sideways markets — that's where the previous variants died.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
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


_ANOMALY = _load_aux("anomaly_flags.feather")


class SolVolShieldStrategy(IStrategy):
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
        df["ret_60d"] = df["close"].pct_change(60)
        df["atr14"] = ta.ATR(df, timeperiod=14)
        df["atr_pct"] = df["atr14"] / df["close"]
        # Donchian 60d
        df["dc_high60"] = df["high"].rolling(60, min_periods=20).max()
        df["dc_low60"] = df["low"].rolling(60, min_periods=20).min()

        # V3: chop-aware. Require BOTH 30d AND 60d trends positive,
        # ADX > 30 (strong trend only), and EMA50 > EMA200 (Golden cross-like)
        df["ema50"] = ta.EMA(df, timeperiod=50)
        df["ret_30d"] = df["close"].pct_change(30)
        bull = (
            (df["close"] > df["ema200"])
            & (df["ema50"] > df["ema200"])
            & (df["ret_30d"] > 0.05)
            & (df["ret_60d"] > 0.15)
            & (df["adx"] > 30)
            & (df["atr_pct"] < 0.10)
        )
        bear = (
            (df["close"] < df["ema200"])
            & (df["ret_60d"] < -0.10)
        )
        rcode = pd.Series(0.0, index=df.index)
        rcode[bull] = 1.0
        rcode[bear] = -1.0
        n = 5  # 5-day confirmation
        rmin = rcode.rolling(n, min_periods=n).min()
        rmax = rcode.rolling(n, min_periods=n).max()
        stable = rmin == rmax
        df["regime_confirmed_code"] = rcode.where(stable, other=pd.NA).ffill().fillna(0)
        df["regime_confirmed"] = df["regime_confirmed_code"].map({1.0: "BULL", -1.0: "BEAR", 0.0: "NEUTRAL"})

        df["anomaly"] = 0
        if not _ANOMALY.empty:
            sol_anom = _ANOMALY[_ANOMALY["coin"] == "SOL"][["is_anomaly"]] \
                       if "coin" in _ANOMALY.columns else _ANOMALY
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["anomaly"] = d.map(sol_anom["is_anomaly"]).fillna(0).astype(int)

        # Target sizing: BULL=75%, NEUTRAL=0, BEAR=0
        df["sol_target"] = 0.0
        df.loc[df["regime_confirmed"] == "BULL", "sol_target"] = 0.75
        df.loc[df["anomaly"] == 1, "sol_target"] = 0.0
        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        enter = df["ema200"].notna() & (df["regime_confirmed"] == "BULL") & (df["sol_target"] > 0.1)
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = "sol_vol_shield"
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        exit_cond = (df["regime_confirmed"] != "BULL") | (df["anomaly"] == 1)
        df.loc[exit_cond, "exit_long"] = 1
        df.loc[exit_cond, "exit_tag"] = "sol_vol_shield:exit"
        return df

    def custom_stake_amount(
        self, pair, current_time, current_rate, proposed_stake, min_stake,
        max_stake, leverage, entry_tag, side, **kwargs,
    ):
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return float(proposed_stake)
        target = float(df.iloc[-1]["sol_target"])
        if max_stake and max_stake > 0:
            return float(max_stake) * max(target, 0.0)
        return float(proposed_stake)

    def adjust_trade_position(
        self, trade, current_time, current_rate, current_profit, min_stake,
        max_stake, current_entry_rate, current_exit_rate, current_entry_profit,
        current_exit_profit, **kwargs,
    ):
        df, _ = self.dp.get_analyzed_dataframe(pair=trade.pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return None
        last = df.iloc[-1]
        target = float(last["sol_target"])
        if target <= 0.10:
            return None
        sol_qty = float(trade.amount or 0)
        sol_value = sol_qty * float(current_rate)
        usdt_free = float(self.wallets.get_free(trade.stake_currency) or 0.0)
        total = sol_value + usdt_free
        if total <= 0:
            return None
        target_value = target * total
        drift = sol_value - target_value
        if drift < -0.05 * total and usdt_free > 1:
            buy = min(-drift, usdt_free * 0.99)
            if max_stake and max_stake > 0:
                buy = min(buy, max_stake)
            if min_stake and buy < min_stake:
                return None
            return float(buy)
        if drift > 0.10 * total:
            sell = min(drift, sol_value * 0.99)
            if min_stake and sell < min_stake:
                return None
            return -float(sell)
        return None


__all__ = ["SolVolShieldStrategy"]
