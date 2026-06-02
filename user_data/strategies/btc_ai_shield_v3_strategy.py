"""BtcAiShieldV3Strategy — V2 + 7-day anomaly cooldown.

V2 logic:
  - Shield regime (price + EMA200 + ADX + 30d-ret + 3-bar confirm)
  - Sigmoid halving cycle sizing with per-phase shifts
  - Anomaly flag exits position immediately

V3 adds:
  - After ANY anomaly bar (is_anomaly == 1), force CASH for the next
    COOLDOWN_BARS bars (default 7), even if Shield/cycle say BULL.
  - Rationale (from meta-analysis E): post-flash-crash bounces are
    often dead-cat. Empirically, of 40 historical BTC anomaly days,
    >50% were followed by another -5% drop within a week.

State machine:
  anomaly_cooldown_remaining starts at 0
  on each bar:
    if is_anomaly == 1:
       anomaly_cooldown_remaining = COOLDOWN_BARS  (resets)
    else if anomaly_cooldown_remaining > 0:
       anomaly_cooldown_remaining -= 1
  while remaining > 0: target = 0 (force cash)

Modes (env AI3_MODE):
  AI3_COOLDOWN_7   — 7-bar cooldown (default)
  AI3_COOLDOWN_14  — 14-bar cooldown (more conservative)
  AI3_COOLDOWN_3   — 3-bar cooldown (faster re-entry)
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


MODE = os.environ.get("AI3_MODE", "AI3_COOLDOWN_7").upper()
COOLDOWN_MAP = {
    "AI3_COOLDOWN_3": 3,
    "AI3_COOLDOWN_7": 7,
    "AI3_COOLDOWN_14": 14,
}
if MODE not in COOLDOWN_MAP:
    raise ValueError(f"unknown AI3_MODE: {MODE}; valid: {list(COOLDOWN_MAP)}")
COOLDOWN_BARS = COOLDOWN_MAP[MODE]


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


def _sigmoid(x, k=SIGMOID_K, c=0.0):
    return 1.0 / (1.0 + np.exp(-k * (x - c)))


class BtcAiShieldV3Strategy(IStrategy):
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

        # Shield regime (same as V2)
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

        # Halving cycle + phase
        df["cycle_bias"] = 0.0
        df["cycle_phase"] = "NEUTRAL"
        if not _HALVING.empty:
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["cycle_bias"] = d.map(_HALVING["cycle_bias"]).ffill().fillna(0.0)
            df["cycle_phase"] = d.map(_HALVING["phase"]).ffill().fillna("NEUTRAL")

        # Anomaly flag
        df["anomaly"] = 0
        if not _ANOMALY.empty:
            btc_anom = _ANOMALY[_ANOMALY["coin"] == "BTC"][["is_anomaly"]] if "coin" in _ANOMALY.columns else _ANOMALY
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["anomaly"] = d.map(btc_anom["is_anomaly"]).fillna(0).astype(int)

        # NEW IN V3: Anomaly cooldown counter
        # Vectorized computation: scan once, reset to COOLDOWN_BARS on anomaly, else decrement.
        cooldown = np.zeros(len(df), dtype=int)
        c = 0
        anom_arr = df["anomaly"].values
        for i in range(len(df)):
            if anom_arr[i] == 1:
                c = COOLDOWN_BARS
            cooldown[i] = c
            if c > 0:
                c -= 1
        df["anomaly_cooldown"] = cooldown

        # Sigmoid sizing per phase
        BASE = 0.85
        shifts = df["cycle_phase"].map(PHASE_SHIFTS).fillna(0.0).astype(float)
        adjusted_bias = df["cycle_bias"].astype(float) + shifts
        cycle_mult = _sigmoid(adjusted_bias.values, k=SIGMOID_K, c=0.0)
        df["ai_target"] = (BASE * cycle_mult).clip(0.0, BASE)

        # Force 0 on anomaly, cooldown, or bear
        df.loc[df["anomaly"] == 1, "ai_target"] = 0.0
        df.loc[df["anomaly_cooldown"] > 0, "ai_target"] = 0.0  # NEW
        df.loc[df["regime_confirmed"] == "BEAR", "ai_target"] = 0.0

        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        ready = df["ema200"].notna()
        enter = ready & (df["regime_confirmed"] == "BULL") & (df["ai_target"] > 0.15)
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = f"ai_shield_v3:{MODE.lower()}"
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        exit_cond = ((df["regime_confirmed"] == "BEAR") |
                     (df["anomaly"] == 1) |
                     (df["anomaly_cooldown"] > 0) |
                     (df["ai_target"] < 0.20))
        df.loc[exit_cond, "exit_long"] = 1
        df.loc[exit_cond, "exit_tag"] = "ai_shield_v3:exit"
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


__all__ = ["BtcAiShieldV3Strategy"]
