"""BtcMacroV2Strategy — fully parameterized version for hyperparameter sweep.

All knobs are env-var controlled so we can test 200+ configurations without
recompiling.

ENV vars:
  MV_W_MACRO       — macro_risk_on weight in adjusted_bias (default 0.0)
  MV_W_DXY         — DXY z-score weight (negative dollar = bullish crypto; default 0.0)
  MV_W_VIX         — VIX panic penalty weight (default 0.0)
  MV_W_SPY         — SPY trend weight (above EMA50 = bull; default 0.0)
  MV_W_QQQ         — QQQ trend weight (default 0.0)
  MV_W_RATES       — rates_rising penalty weight (default 0.0)
  MV_W_CALENDAR    — calendar tilt scaler (default 1.0; set 0 to disable)
  MV_W_CYCLE       — cycle bias scaler (default 1.0)
  MV_TILT_CLAMP    — max total tilt (default 0.30)
  MV_EXIT_THR      — macro_risk_on exit threshold (default -0.5)
  MV_MODE          — "tilt" | "exit_only" | "filter" | "multiplier" (default "tilt")
  MV_COIN          — anomaly coin filter (default "BTC")
  MV_N_CONFIRM     — regime confirmation days (default 3)
  MV_BASE          — base position size (default 0.85)
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
_MACRO = _load_aux("macro_signals.feather")


def _env_float(name, default):
    try: return float(os.environ.get(name, default))
    except (ValueError, TypeError): return default


W_MACRO    = _env_float("MV_W_MACRO", 0.0)
W_DXY      = _env_float("MV_W_DXY", 0.0)
W_VIX      = _env_float("MV_W_VIX", 0.0)
W_SPY      = _env_float("MV_W_SPY", 0.0)
W_QQQ      = _env_float("MV_W_QQQ", 0.0)
W_RATES    = _env_float("MV_W_RATES", 0.0)
W_CALENDAR = _env_float("MV_W_CALENDAR", 1.0)
W_CYCLE    = _env_float("MV_W_CYCLE", 1.0)
TILT_CLAMP = _env_float("MV_TILT_CLAMP", 0.30)
EXIT_THR   = _env_float("MV_EXIT_THR", -0.5)
N_CONFIRM  = int(_env_float("MV_N_CONFIRM", 3))
BASE       = _env_float("MV_BASE", 0.85)
COIN       = os.environ.get("MV_COIN", "BTC")
MODE       = os.environ.get("MV_MODE", "tilt")

SIGMOID_K = 4.0

PHASE_SHIFTS = {
    "ACCUMULATION":   0.20,
    "EARLY_BULL":     0.10,
    "PARABOLIC":     -0.15,
    "DISTRIBUTION":  -0.40,
    "BEAR":          -0.60,
    "REACCUMULATION": -0.05,
}

CALENDAR_TILTS = {
    "is_october":     0.15,
    "is_july":        0.05,
    "is_wednesday":   0.05,
    "is_monday":      0.05,
    "is_end_of_month": 0.05,
}


def _sigmoid(x, k=SIGMOID_K, c=0.0):
    return 1.0 / (1.0 + np.exp(-k * (x - c)))


class BtcMacroV2Strategy(IStrategy):
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

        bull = (df["close"] > df["ema200"]) & (df["ret_30d"] > 0.05) & (df["adx"] > 20)
        bear = (df["close"] < df["ema200"]) & (df["ret_30d"] < -0.10)
        rcode = pd.Series(0.0, index=df.index)
        rcode[bull] = 1.0
        rcode[bear] = -1.0
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

        d_idx = pd.to_datetime(df["date"], utc=True)
        is_oct = (d_idx.dt.month == 10).astype(float)
        is_jul = (d_idx.dt.month == 7).astype(float)
        is_wed = (d_idx.dt.day_name() == "Wednesday").astype(float)
        is_mon = (d_idx.dt.day_name() == "Monday").astype(float)
        is_eom = (d_idx.dt.day >= 26).astype(float)
        cal_tilt = (
            is_oct * CALENDAR_TILTS["is_october"]
            + is_jul * CALENDAR_TILTS["is_july"]
            + is_wed * CALENDAR_TILTS["is_wednesday"]
            + is_mon * CALENDAR_TILTS["is_monday"]
            + is_eom * CALENDAR_TILTS["is_end_of_month"]
        )
        df["calendar_tilt"] = (W_CALENDAR * cal_tilt).values

        # Macro
        df["macro_risk_on"] = 0.0
        df["macro_dxy_z"] = 0.0
        df["macro_vix_panic"] = 0
        df["macro_spy_up"] = 0
        df["macro_qqq_up"] = 0
        df["macro_rates_rising"] = 0
        if not _MACRO.empty:
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            for col_out, col_in in [
                ("macro_risk_on",     "macro_risk_on"),
                ("macro_dxy_z",       "dxy_zscore"),
                ("macro_vix_panic",   "vix_is_panic"),
                ("macro_spy_up",      "spy_above_ema50"),
                ("macro_qqq_up",      "qqq_above_ema50"),
                ("macro_rates_rising","rates_rising"),
            ]:
                if col_in in _MACRO.columns:
                    df[col_out] = d.map(_MACRO[col_in].ffill()).ffill().fillna(0)

        # Macro tilt (additive contribution)
        macro_tilt = (
            W_MACRO   * df["macro_risk_on"]
          - W_DXY     * df["macro_dxy_z"].clip(-2, 2) / 2  # high z = strong $ = bearish
          - W_VIX     * df["macro_vix_panic"].astype(float)
          + W_SPY     * (df["macro_spy_up"].astype(float) * 2 - 1)
          + W_QQQ     * (df["macro_qqq_up"].astype(float) * 2 - 1)
          - W_RATES   * df["macro_rates_rising"].astype(float)
        )
        df["macro_tilt"] = macro_tilt.values

        # Total tilt clamped
        df["total_tilt"] = (df["calendar_tilt"] + df["macro_tilt"]).clip(-TILT_CLAMP, TILT_CLAMP)

        shifts = df["cycle_phase"].map(PHASE_SHIFTS).fillna(0.0).astype(float)
        if MODE == "multiplier":
            base_bias = W_CYCLE * df["cycle_bias"].astype(float) + shifts
            cycle_mult = _sigmoid(base_bias.values, k=SIGMOID_K, c=0.0)
            macro_mult = _sigmoid(df["macro_risk_on"].values, k=3.0, c=0.0)
            df["ai_target"] = (BASE * cycle_mult * macro_mult).clip(0.0, BASE)
        else:
            adjusted_bias = W_CYCLE * df["cycle_bias"].astype(float) + shifts + df["total_tilt"]
            cycle_mult = _sigmoid(adjusted_bias.values, k=SIGMOID_K, c=0.0)
            df["ai_target"] = (BASE * cycle_mult).clip(0.0, BASE)

        df.loc[df["anomaly"] == 1, "ai_target"] = 0.0
        df.loc[df["regime_confirmed"] == "BEAR", "ai_target"] = 0.0

        if MODE in ("exit_only", "filter", "tilt", "multiplier"):
            df.loc[df["macro_risk_on"] < EXIT_THR, "ai_target"] = 0.0

        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        ready = df["ema200"].notna()
        enter = ready & (df["regime_confirmed"] == "BULL") & (df["ai_target"] > 0.15)
        if MODE == "filter":
            enter = enter & (df["macro_risk_on"] > -0.2)
        df.loc[enter, "enter_long"] = 1
        df.loc[enter, "enter_tag"] = "mv2:enter"
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        exit_cond = (
            (df["regime_confirmed"] == "BEAR")
            | (df["anomaly"] == 1)
            | (df["ai_target"] < 0.20)
            | (df["macro_risk_on"] < EXIT_THR)
        )
        df.loc[exit_cond, "exit_long"] = 1
        df.loc[exit_cond, "exit_tag"] = "mv2:exit"
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
        target = float(df.iloc[-1]["ai_target"])
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


__all__ = ["BtcMacroV2Strategy"]
