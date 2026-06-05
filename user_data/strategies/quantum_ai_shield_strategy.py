"""QuantumAiShieldStrategy — 6-signal probabilistic ensemble.

Instead of hard BULL/BEAR/NEUTRAL switches, each of 6 independent signals
produces a probability of BULL ∈ [0,1]. Weighted ensemble produces final
P(bull). Position size = sigmoid(P(bull)) × BASE × (1 + calendar_tilt).

Signals (each weighted):
  1. EMA trend       (25%) — close > EMA200 + ret_30d magnitude
  2. ADX strength    (15%) — trend strength quality
  3. Donchian        (20%) — breakout vs 60-day high/low
  4. MACD momentum   (15%) — MACD-signal cross strength
  5. Halving cycle   (20%) — BTC cycle_bias, phase shifts
  6. Vol regime      ( 5%) — atr_pct stability (HIGH vol = LOW prob)

Plus:
  Calendar tilt added multiplicatively (October +15%, Mon/Wed +5%, etc.)
  Anomaly circuit breaker exits everything immediately
  Bear hard exit: if P(bull) < 0.25 → exit

This is meant to capture the FULL signal picture rather than relying on
single binary detectors. Inspired by quantum superposition: position is in
a superposition of bullishness states until observed (executed).

CALIBRATED ON: BTC 2021-2026 (in-sample), validated on 2018-2020 virgin.
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


_HALVING = _load_aux("halving_cycle.feather")
_ANOMALY = _load_aux("anomaly_flags.feather")

import os
COIN = os.environ.get("QUANTUM_COIN", "BTC")

# Signal weights (sum to 1.0)
W_EMA_TREND   = 0.25
W_ADX         = 0.15
W_DONCHIAN    = 0.20
W_MACD        = 0.15
W_CYCLE       = 0.20
W_VOL_REGIME  = 0.05

BASE = 0.85
SIGMOID_K = 5.0
ENTRY_THRESHOLD = 0.55
EXIT_THRESHOLD = 0.25
N_CONFIRM = 3

CALENDAR_TILTS = {
    "is_october":     0.15,
    "is_july":        0.05,
    "is_wednesday":   0.05,
    "is_monday":      0.05,
    "is_end_of_month": 0.05,
}
TILT_CLAMP = 0.30

PHASE_SHIFTS = {
    "ACCUMULATION":   0.20,
    "EARLY_BULL":     0.10,
    "PARABOLIC":     -0.15,
    "DISTRIBUTION":  -0.40,
    "BEAR":          -0.60,
    "REACCUMULATION": -0.05,
}


def _sigmoid(x, k=SIGMOID_K, c=0.5):
    """Sigmoid centered at 0.5 (the neutral point)."""
    return 1.0 / (1.0 + np.exp(-k * (x - c)))


def _logistic_squash(x, low, high):
    """Map x from [low, high] linearly to [0, 1], clipped."""
    return np.clip((x - low) / (high - low), 0.0, 1.0)


class QuantumAiShieldStrategy(IStrategy):
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

        # Base indicators
        df["ema50"] = ta.EMA(df, timeperiod=50)
        df["ema200"] = ta.EMA(df, timeperiod=200)
        df["adx"] = ta.ADX(df, timeperiod=14)
        df["ret_30d"] = df["close"].pct_change(30)
        df["ret_60d"] = df["close"].pct_change(60)
        df["atr14"] = ta.ATR(df, timeperiod=14)
        df["atr_pct"] = df["atr14"] / df["close"]

        # Donchian 60d
        df["dc_high60"] = df["high"].rolling(60, min_periods=20).max()
        df["dc_low60"] = df["low"].rolling(60, min_periods=20).min()
        df["dc_pos"] = (df["close"] - df["dc_low60"]) / (df["dc_high60"] - df["dc_low60"]).replace(0, np.nan)

        # MACD
        macd_out = ta.MACD(df, fastperiod=12, slowperiod=26, signalperiod=9)
        df["macd"] = macd_out["macd"]
        df["macd_signal"] = macd_out["macdsignal"]
        df["macd_diff"] = df["macd"] - df["macd_signal"]

        # === SIGNAL 1: EMA TREND ===
        # P(bull) = how much above EMA200 + magnitude of ret_30d
        above_ema = (df["close"] - df["ema200"]) / df["ema200"]
        p_above = _logistic_squash(above_ema, -0.10, 0.20)  # -10% → 0, +20% → 1
        p_ret = _logistic_squash(df["ret_30d"], -0.10, 0.15)
        df["sig_ema_trend"] = (p_above + p_ret) / 2

        # === SIGNAL 2: ADX STRENGTH ===
        # P(strong_trend) — strong ADX = high prob (regardless of direction)
        df["sig_adx"] = _logistic_squash(df["adx"], 15, 40)

        # === SIGNAL 3: DONCHIAN POSITION ===
        # P(bull) = where in the 60d channel are we? Top = bull
        df["sig_donchian"] = df["dc_pos"].fillna(0.5).clip(0, 1)

        # === SIGNAL 4: MACD MOMENTUM ===
        # P(bull) from MACD diff sign + magnitude relative to price
        macd_norm = df["macd_diff"] / df["close"]
        df["sig_macd"] = _logistic_squash(macd_norm, -0.005, 0.005)

        # === SIGNAL 5: HALVING CYCLE (BTC-anchored) ===
        df["cycle_bias"] = 0.0
        df["cycle_phase"] = "NEUTRAL"
        if not _HALVING.empty:
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["cycle_bias"] = d.map(_HALVING["cycle_bias"]).ffill().fillna(0.0)
            df["cycle_phase"] = d.map(_HALVING["phase"]).ffill().fillna("NEUTRAL")
        # Convert cycle_bias [-1, +1] + phase shifts to P(bull)
        shifts = df["cycle_phase"].map(PHASE_SHIFTS).fillna(0.0).astype(float)
        cycle_signal = (df["cycle_bias"].astype(float) + shifts).clip(-1.5, 1.5)
        df["sig_cycle"] = _logistic_squash(cycle_signal, -0.8, 0.8)

        # === SIGNAL 6: VOL REGIME (inverse — high vol = unsafe) ===
        # P(safe) = low atr_pct
        df["sig_vol_regime"] = 1.0 - _logistic_squash(df["atr_pct"], 0.02, 0.12)

        # === ENSEMBLE: weighted probability ===
        df["p_bull"] = (
            W_EMA_TREND  * df["sig_ema_trend"]
            + W_ADX      * df["sig_adx"]
            + W_DONCHIAN * df["sig_donchian"]
            + W_MACD     * df["sig_macd"]
            + W_CYCLE    * df["sig_cycle"]
            + W_VOL_REGIME * df["sig_vol_regime"]
        )

        # === CALENDAR TILT (additive booster) ===
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

        # === ANOMALY CIRCUIT BREAKER ===
        df["anomaly"] = 0
        if not _ANOMALY.empty:
            coin_anom = _ANOMALY[_ANOMALY["coin"] == COIN][["is_anomaly"]] \
                       if "coin" in _ANOMALY.columns else _ANOMALY
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["anomaly"] = d.map(coin_anom["is_anomaly"]).fillna(0).astype(int)

        # === N-DAY CONFIRMATION of p_bull state ===
        df["p_bull_conf"] = df["p_bull"].rolling(N_CONFIRM, min_periods=N_CONFIRM).min()  # min => requires sustained signal

        # === FINAL TARGET SIZE ===
        # sigmoid of p_bull with calendar tilt added
        adjusted = df["p_bull"] + df["calendar_tilt"]
        size_mult = _sigmoid(adjusted.values, k=SIGMOID_K, c=0.5)
        df["ai_target"] = (BASE * size_mult).clip(0.0, BASE)
        df.loc[df["anomaly"] == 1, "ai_target"] = 0.0
        df.loc[df["p_bull_conf"] < EXIT_THRESHOLD, "ai_target"] = 0.0

        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        ready = df["ema200"].notna() & df["p_bull_conf"].notna()
        enter = ready & (df["p_bull_conf"] > ENTRY_THRESHOLD) & (df["ai_target"] > 0.15) & (df["anomaly"] == 0)
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = "quantum:enter"
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        exit_cond = (
            (df["p_bull_conf"] < EXIT_THRESHOLD)
            | (df["anomaly"] == 1)
            | (df["ai_target"] < 0.15)
        )
        df.loc[exit_cond, "exit_long"] = 1
        df.loc[exit_cond, "exit_tag"] = "quantum:exit"
        return df

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return float(proposed_stake)
        target = float(df.iloc[-1]["ai_target"])
        if max_stake and max_stake > 0:
            return float(max_stake) * max(target, 0.0)
        return float(proposed_stake)

    def adjust_trade_position(self, trade, current_time, current_rate, current_profit,
                              min_stake, max_stake, current_entry_rate, current_exit_rate,
                              current_entry_profit, current_exit_profit, **kwargs):
        df, _ = self.dp.get_analyzed_dataframe(pair=trade.pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return None
        last = df.iloc[-1]
        target = float(last["ai_target"])
        if target <= 0.10:
            return None
        qty = float(trade.amount or 0)
        value = qty * float(current_rate)
        usdt_free = float(self.wallets.get_free(trade.stake_currency) or 0.0)
        total = value + usdt_free
        if total <= 0:
            return None
        target_value = target * total
        drift = value - target_value
        if drift < -0.05 * total and usdt_free > 1:
            buy = min(-drift, usdt_free * 0.99)
            if max_stake and max_stake > 0:
                buy = min(buy, max_stake)
            if min_stake and buy < min_stake:
                return None
            return float(buy)
        if drift > 0.10 * total:
            sell = min(drift, value * 0.99)
            if min_stake and sell < min_stake:
                return None
            return -float(sell)
        return None


__all__ = ["QuantumAiShieldStrategy"]
