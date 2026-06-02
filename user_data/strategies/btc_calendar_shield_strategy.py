"""BtcCalendarShieldStrategy — AI Shield V2 with calendar-effect tilts.

From calendar_analyzer.py we found 8 statistically significant daily
patterns in BTC 2020-2026 returns. After Bonferroni correction (~31
tests), only October survives at strong significance; others are
borderline but consistent.

This strategy adds a small calendar_tilt to the cycle_bias:
  October                    +0.15  (strongest evidence)
  July                       +0.05
  Wednesday                  +0.05
  Monday                     +0.05
  End-of-month (26-31)       +0.05

Combined tilt clipped to ±0.30 to avoid overwhelming the cycle bias.

Tilts are MULTIPLICATIVE on top of V2 — they don't override anything,
just nudge entries earlier and exits later during historically-strong
days.

Anti-overfit guardrails:
  - Tilts are small (max +0.30 cumulative)
  - Shield BEAR still forces exit
  - Anomaly still forces exit
  - Adversarial Validator must PASS before deployment
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

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


_HALVING = _load_aux("halving_cycle.feather")
_ANOMALY = _load_aux("anomaly_flags.feather")


PHASE_SHIFTS = {
    "ACCUMULATION":  0.20,
    "EARLY_BULL":    0.10,
    "PARABOLIC":    -0.15,
    "DISTRIBUTION": -0.40,
    "BEAR":         -0.60,
    "REACCUMULATION": -0.05,
}
SIGMOID_K = 4.0

# Calendar tilts (from research/calendar_findings.md)
CALENDAR_TILTS = {
    "is_october":     0.15,
    "is_july":        0.05,
    "is_wednesday":   0.05,
    "is_monday":      0.05,
    "is_end_of_month": 0.05,
}
TILT_CLAMP = 0.30


def _sigmoid(x, k=SIGMOID_K, c=0.0):
    return 1.0 / (1.0 + np.exp(-k * (x - c)))


class BtcCalendarShieldStrategy(IStrategy):
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
        bull = (df["close"] > df["ema200"]) & (df["ret_30d"] > 0.05) & (df["adx"] > 20)
        bear = (df["close"] < df["ema200"]) & (df["ret_30d"] < -0.10)
        rcode = pd.Series(0.0, index=df.index)
        rcode[bull] = 1.0
        rcode[bear] = -1.0
        n = 3
        rmin = rcode.rolling(n, min_periods=n).min()
        rmax = rcode.rolling(n, min_periods=n).max()
        stable = rmin == rmax
        df["regime_confirmed_code"] = rcode.where(stable, other=pd.NA).ffill().fillna(0)
        df["regime_confirmed"] = df["regime_confirmed_code"].map({1.0: "BULL", -1.0: "BEAR", 0.0: "NEUTRAL"})

        # Halving cycle
        df["cycle_bias"] = 0.0
        df["cycle_phase"] = "NEUTRAL"
        if not _HALVING.empty:
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["cycle_bias"] = d.map(_HALVING["cycle_bias"]).ffill().fillna(0.0)
            df["cycle_phase"] = d.map(_HALVING["phase"]).ffill().fillna("NEUTRAL")

        # Anomaly
        df["anomaly"] = 0
        if not _ANOMALY.empty:
            btc_anom = _ANOMALY[_ANOMALY["coin"] == "BTC"][["is_anomaly"]] \
                       if "coin" in _ANOMALY.columns else _ANOMALY
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["anomaly"] = d.map(btc_anom["is_anomaly"]).fillna(0).astype(int)

        # Calendar tilts
        d_idx = pd.to_datetime(df["date"], utc=True)
        is_oct = (d_idx.dt.month == 10).astype(float)
        is_jul = (d_idx.dt.month == 7).astype(float)
        is_wed = (d_idx.dt.day_name() == "Wednesday").astype(float)
        is_mon = (d_idx.dt.day_name() == "Monday").astype(float)
        is_eom = (d_idx.dt.day >= 26).astype(float)
        tilt = (
            is_oct * CALENDAR_TILTS["is_october"]
            + is_jul * CALENDAR_TILTS["is_july"]
            + is_wed * CALENDAR_TILTS["is_wednesday"]
            + is_mon * CALENDAR_TILTS["is_monday"]
            + is_eom * CALENDAR_TILTS["is_end_of_month"]
        ).clip(-TILT_CLAMP, TILT_CLAMP)
        df["calendar_tilt"] = tilt.values

        # Sigmoid sizing with tilt added to bias
        BASE = 0.85
        shifts = df["cycle_phase"].map(PHASE_SHIFTS).fillna(0.0).astype(float)
        adjusted_bias = df["cycle_bias"].astype(float) + shifts + df["calendar_tilt"]
        cycle_mult = _sigmoid(adjusted_bias.values, k=SIGMOID_K, c=0.0)
        df["ai_target"] = (BASE * cycle_mult).clip(0.0, BASE)
        df.loc[df["anomaly"] == 1, "ai_target"] = 0.0
        df.loc[df["regime_confirmed"] == "BEAR", "ai_target"] = 0.0
        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        ready = df["ema200"].notna()
        enter = ready & (df["regime_confirmed"] == "BULL") & (df["ai_target"] > 0.15)
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = "calendar_shield"
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        exit_cond = ((df["regime_confirmed"] == "BEAR") | (df["anomaly"] == 1) | (df["ai_target"] < 0.20))
        df.loc[exit_cond, "exit_long"] = 1
        df.loc[exit_cond, "exit_tag"] = "calendar_shield:exit"
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
        self, trade, current_time, current_rate, current_profit, min_stake,
        max_stake, current_entry_rate, current_exit_rate, current_entry_profit,
        current_exit_profit, **kwargs,
    ):
        df, _ = self.dp.get_analyzed_dataframe(pair=trade.pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return None
        last = df.iloc[-1]
        target = float(last["ai_target"])
        if target <= 0.10:
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


__all__ = ["BtcCalendarShieldStrategy"]
