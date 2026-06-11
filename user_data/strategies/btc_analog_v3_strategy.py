"""BtcAnalogV3Strategy — AnalogV2 with the KNN analog signal replaced by the
LSTM embedding prediction (GPU_HANDOFF task #1).

Identical macro / calendar / cycle / regime machinery to BtcAnalogV2Strategy
so the two are a fair A/B; the ONLY change is the analog tilt source:
  V2: historical_analogs_v2.feather  -> analog_v2_mean   (KNN, corr ~+0.06)
  V3: dl_signals_lstm_{coin}.feather -> lstm_pred_fwd30   (LSTM, WF corr ~+0.3 BTC/ETH)

The LSTM signal is trained with a correlation loss, so it has no anchored
zero (scale/offset invariant). We convert it to a causal rolling z-score
before tilting — no lookahead.

Backtest note: freqtrade does NOT install on the GPU machine (TA-Lib DLL
blocked by Windows Application Control). Run the 9-year backtest on the CPU
machine. A freqtrade-free OOS check lives in GPU_HANDOFF/backtest_signal.py.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import talib.abstract as ta
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
_MACRO = _load_aux("macro_signals.feather")

W_ANALOG          = 0.40
W_MACRO           = 0.20
W_SPY_TREND       = 0.10
MACRO_EXIT_THR    = -0.70
BASE = 0.85
SIGMOID_K = 4.0
N_CONFIRM = 3
LSTM_Z_WINDOW = 90        # causal window for z-scoring the LSTM prediction

PHASE_SHIFTS = {
    "ACCUMULATION":   0.20, "EARLY_BULL":     0.10,
    "PARABOLIC":     -0.15, "DISTRIBUTION":  -0.40,
    "BEAR":          -0.60, "REACCUMULATION": -0.05,
}

CALENDAR_TILTS = {
    "is_october":     0.15,
    "is_july":       -0.05,
    "is_january":     0.10,
    "is_wednesday":   0.05,
    "is_monday":      0.05,
    "is_end_of_month": 0.05,
}
TILT_CLAMP = 0.45


def _sigmoid(x, k=SIGMOID_K, c=0.0):
    return 1.0 / (1.0 + np.exp(-k * (x - c)))


def _load_lstm_signal(coin: str) -> pd.Series:
    """Return a date-indexed Series of lstm_pred_fwd30 for the coin, or empty."""
    sig = _load_aux(f"dl_signals_lstm_{coin}.feather")
    if sig.empty or "lstm_pred_fwd30" not in sig.columns:
        return pd.Series(dtype="float64")
    return sig["lstm_pred_fwd30"]


class BtcAnalogV3Strategy(IStrategy):
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
    startup_candle_count: int = 220

    order_types = {"entry": "limit", "exit": "limit",
                   "stoploss": "limit", "stoploss_on_exchange": False}

    def populate_indicators(self, dataframe, metadata):
        df = dataframe.copy()
        df["ema200"] = ta.EMA(df, timeperiod=200)
        df["adx"] = ta.ADX(df, timeperiod=14)
        df["ret_30d"] = df["close"].pct_change(30)

        bull = (df["close"] > df["ema200"]) & (df["ret_30d"] > 0.05) & (df["adx"] > 20)
        bear = (df["close"] < df["ema200"]) & (df["ret_30d"] < -0.10)
        rcode = pd.Series(0.0, index=df.index)
        rcode[bull] = 1.0; rcode[bear] = -1.0
        rmin = rcode.rolling(N_CONFIRM, min_periods=N_CONFIRM).min()
        rmax = rcode.rolling(N_CONFIRM, min_periods=N_CONFIRM).max()
        stable = rmin == rmax
        df["regime_confirmed_code"] = rcode.where(stable, other=pd.NA).ffill().fillna(0)
        df["regime_confirmed"] = df["regime_confirmed_code"].map({1.0: "BULL", -1.0: "BEAR", 0.0: "NEUTRAL"})

        df["cycle_bias"] = 0.0
        df["cycle_phase"] = "NEUTRAL"
        if not _HALVING.empty:
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            if "cycle_bias" in _HALVING.columns:
                df["cycle_bias"] = d.map(_HALVING["cycle_bias"]).ffill().fillna(0.0)
            df["cycle_phase"] = d.map(_HALVING["phase"]).ffill().fillna("NEUTRAL")

        df["anomaly"] = 0
        if not _ANOMALY.empty:
            coin_anom = _ANOMALY[_ANOMALY["coin"] == "BTC"][["is_anomaly"]] \
                       if "coin" in _ANOMALY.columns else _ANOMALY
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["anomaly"] = d.map(coin_anom["is_anomaly"]).fillna(0).astype(int)

        # === LSTM ANALOG SIGNAL (replaces KNN analog_v2) ===
        coin = metadata["pair"].split("/")[0]
        lstm = _load_lstm_signal(coin)
        df["lstm_pred"] = 0.0
        if not lstm.empty:
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["lstm_pred"] = d.map(lstm).astype(float)
        # Causal z-score (corr-loss signal has arbitrary scale/offset).
        roll_mean = df["lstm_pred"].rolling(LSTM_Z_WINDOW, min_periods=20).mean()
        roll_std = df["lstm_pred"].rolling(LSTM_Z_WINDOW, min_periods=20).std().replace(0, np.nan)
        df["lstm_z"] = ((df["lstm_pred"] - roll_mean) / roll_std).fillna(0.0)
        # tilt from LSTM, bounded like V2's analog tilt
        analog_tilt = (W_ANALOG * np.tanh(df["lstm_z"])).clip(-0.25, 0.25)

        # === MACRO ===
        df["macro_risk_on"] = 0.0
        df["spy_above_ema50"] = 0
        if not _MACRO.empty:
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            if "macro_risk_on" in _MACRO.columns:
                df["macro_risk_on"] = d.map(_MACRO["macro_risk_on"].ffill()).ffill().fillna(0)
            if "spy_above_ema50" in _MACRO.columns:
                df["spy_above_ema50"] = d.map(_MACRO["spy_above_ema50"].ffill()).ffill().fillna(0)
        macro_tilt = W_MACRO * df["macro_risk_on"] + W_SPY_TREND * (df["spy_above_ema50"] * 2 - 1).astype(float)

        # === CALENDAR ===
        d_idx = pd.to_datetime(df["date"], utc=True)
        m = d_idx.dt.month
        dow = d_idx.dt.day_name()
        cal_tilt = (
            (m == 10).astype(float) * CALENDAR_TILTS["is_october"]
          + (m == 7).astype(float) * CALENDAR_TILTS["is_july"]
          + (m == 1).astype(float) * CALENDAR_TILTS["is_january"]
          + (dow == "Wednesday").astype(float) * CALENDAR_TILTS["is_wednesday"]
          + (dow == "Monday").astype(float) * CALENDAR_TILTS["is_monday"]
          + (d_idx.dt.day >= 26).astype(float) * CALENDAR_TILTS["is_end_of_month"]
        )

        total_tilt = (cal_tilt + analog_tilt + macro_tilt).clip(-TILT_CLAMP, TILT_CLAMP)
        df["total_tilt"] = total_tilt.values

        shifts = df["cycle_phase"].map(PHASE_SHIFTS).fillna(0.0).astype(float)
        adjusted_bias = df["cycle_bias"].astype(float) + shifts + df["total_tilt"]
        cycle_mult = _sigmoid(adjusted_bias.values, k=SIGMOID_K, c=0.0)
        df["ai_target"] = (BASE * cycle_mult).clip(0.0, BASE)
        df.loc[df["anomaly"] == 1, "ai_target"] = 0.0
        df.loc[df["regime_confirmed"] == "BEAR", "ai_target"] = 0.0
        df.loc[df["macro_risk_on"] < MACRO_EXIT_THR, "ai_target"] = 0.0

        return df

    def populate_entry_trend(self, dataframe, metadata):
        df = dataframe
        ready = df["ema200"].notna()
        enter = ready & (df["regime_confirmed"] == "BULL") & (df["ai_target"] > 0.15)
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = "analogv3:enter"
        return df

    def populate_exit_trend(self, dataframe, metadata):
        df = dataframe
        exit_cond = (
            (df["regime_confirmed"] == "BEAR")
            | (df["anomaly"] == 1)
            | (df["ai_target"] < 0.20)
            | (df["macro_risk_on"] < MACRO_EXIT_THR)
        )
        df.loc[exit_cond, "exit_long"] = 1
        df.loc[exit_cond, "exit_tag"] = "analogv3:exit"
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
        if df is None or df.empty: return None
        target = float(df.iloc[-1]["ai_target"])
        if target <= 0.10: return None
        qty = float(trade.amount or 0)
        value = qty * float(current_rate)
        usdt_free = float(self.wallets.get_free(trade.stake_currency) or 0.0)
        total = value + usdt_free
        if total <= 0: return None
        target_value = target * total
        drift = value - target_value
        if drift < -0.05 * total and usdt_free > 1:
            buy = min(-drift, usdt_free * 0.99)
            if max_stake and max_stake > 0: buy = min(buy, max_stake)
            if min_stake and buy < min_stake: return None
            return float(buy)
        if drift > 0.10 * total:
            sell = min(drift, value * 0.99)
            if min_stake and sell < min_stake: return None
            return -float(sell)
        return None


__all__ = ["BtcAnalogV3Strategy"]
