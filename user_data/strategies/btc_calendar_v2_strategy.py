"""BtcCalendarV2Strategy — parameterized Calendar Shield for A/B testing.

All knobs via env vars so we can test decisions one-by-one:
  CAL_W_JAN   — January tilt (default 0.00, decision 2: try 0.10)
  CAL_W_FEB   — February tilt (default 0.00)
  CAL_W_JUL   — July tilt (default +0.05, decision 1: try -0.05)
  CAL_W_OCT   — October tilt (default 0.15)
  CAL_W_NOV   — November tilt (default 0.00, decision 3: try 0.10)
  CAL_W_DEC   — December tilt (default 0.00)
  CAL_W_MON   — Monday tilt (default 0.05, decision 4: try 0.00)
  CAL_W_WED   — Wednesday tilt (default 0.05)
  CAL_W_EOM   — End-of-month tilt (default 0.05)
  CAL_EXIT_THR — exit threshold (default 0.20, decision 5: try 0.10)
  CAL_COIN     — anomaly coin filter (default BTC)
  CAL_TILT_CLAMP — max total tilt (default 0.30)
"""
from __future__ import annotations

import os
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


def _ef(name, default):
    try: return float(os.environ.get(name, default))
    except (ValueError, TypeError): return default


# Baseline values (current Calendar Shield)
W_JAN  = _ef("CAL_W_JAN", 0.00)
W_FEB  = _ef("CAL_W_FEB", 0.00)
W_JUL  = _ef("CAL_W_JUL", 0.05)
W_OCT  = _ef("CAL_W_OCT", 0.15)
W_NOV  = _ef("CAL_W_NOV", 0.00)
W_DEC  = _ef("CAL_W_DEC", 0.00)
W_MON  = _ef("CAL_W_MON", 0.05)
W_WED  = _ef("CAL_W_WED", 0.05)
W_EOM  = _ef("CAL_W_EOM", 0.05)
EXIT_THR   = _ef("CAL_EXIT_THR", 0.20)
TILT_CLAMP = _ef("CAL_TILT_CLAMP", 0.30)
COIN       = os.environ.get("CAL_COIN", "BTC")
N_CONFIRM  = 3
BASE = 0.85
SIGMOID_K = 4.0

PHASE_SHIFTS = {
    "ACCUMULATION":   0.20, "EARLY_BULL":     0.10,
    "PARABOLIC":     -0.15, "DISTRIBUTION":  -0.40,
    "BEAR":          -0.60, "REACCUMULATION": -0.05,
}


def _sigmoid(x, k=SIGMOID_K, c=0.0):
    return 1.0 / (1.0 + np.exp(-k * (x - c)))


class BtcCalendarV2Strategy(IStrategy):
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
            df["cycle_bias"] = d.map(_HALVING["cycle_bias"]).ffill().fillna(0.0)
            df["cycle_phase"] = d.map(_HALVING["phase"]).ffill().fillna("NEUTRAL")

        df["anomaly"] = 0
        if not _ANOMALY.empty:
            coin_anom = _ANOMALY[_ANOMALY["coin"] == COIN][["is_anomaly"]] \
                       if "coin" in _ANOMALY.columns else _ANOMALY
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["anomaly"] = d.map(coin_anom["is_anomaly"]).fillna(0).astype(int)

        # Calendar tilts (all configurable)
        d_idx = pd.to_datetime(df["date"], utc=True)
        m = d_idx.dt.month
        dow = d_idx.dt.day_name()
        is_jan = (m == 1).astype(float)
        is_feb = (m == 2).astype(float)
        is_jul = (m == 7).astype(float)
        is_oct = (m == 10).astype(float)
        is_nov = (m == 11).astype(float)
        is_dec = (m == 12).astype(float)
        is_mon = (dow == "Monday").astype(float)
        is_wed = (dow == "Wednesday").astype(float)
        is_eom = (d_idx.dt.day >= 26).astype(float)
        tilt = (
            is_jan * W_JAN + is_feb * W_FEB + is_jul * W_JUL + is_oct * W_OCT
            + is_nov * W_NOV + is_dec * W_DEC
            + is_mon * W_MON + is_wed * W_WED + is_eom * W_EOM
        ).clip(-TILT_CLAMP, TILT_CLAMP)
        df["calendar_tilt"] = tilt.values

        shifts = df["cycle_phase"].map(PHASE_SHIFTS).fillna(0.0).astype(float)
        adjusted_bias = df["cycle_bias"].astype(float) + shifts + df["calendar_tilt"]
        cycle_mult = _sigmoid(adjusted_bias.values, k=SIGMOID_K, c=0.0)
        df["ai_target"] = (BASE * cycle_mult).clip(0.0, BASE)
        df.loc[df["anomaly"] == 1, "ai_target"] = 0.0
        df.loc[df["regime_confirmed"] == "BEAR", "ai_target"] = 0.0
        return df

    def populate_entry_trend(self, dataframe, metadata):
        df = dataframe
        ready = df["ema200"].notna()
        enter = ready & (df["regime_confirmed"] == "BULL") & (df["ai_target"] > 0.15)
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = "calv2:enter"
        return df

    def populate_exit_trend(self, dataframe, metadata):
        df = dataframe
        exit_cond = (
            (df["regime_confirmed"] == "BEAR")
            | (df["anomaly"] == 1)
            | (df["ai_target"] < EXIT_THR)
        )
        df.loc[exit_cond, "exit_long"] = 1
        df.loc[exit_cond, "exit_tag"] = "calv2:exit"
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


__all__ = ["BtcCalendarV2Strategy"]
