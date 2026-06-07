"""⭐⭐⭐ BtcAnalogV2Strategy — STAR STRATEGY (Best CAGR in fleet)

🏆 9-year ETH backtest: $10K -> $237,431 (+42.2%/yr)
   Win rate: 77.8% (21W/6L over 27 trades)
   vs ETH Calendar Shield: +$41,305 improvement
   Adversarial: PASS

Architecture: Multi-coin KNN analogs (BTC+ETH+BNB pool, 8,873 days)
  + macro context (DXY/VIX/SPY) + calendar tilts + cycle phases

Status: SAVED, ready to deploy as sub #109 (pending user approval)
See: research/reports/STAR_STRATEGIES.md
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
_ANALOG_V2 = _load_aux("historical_analogs_v2.feather")
_MACRO = _load_aux("macro_signals.feather")

W_ANALOG          = 0.40    # weight for analog tilt (stronger than V1's 0.30)
W_MACRO           = 0.20    # macro tilt
W_SPY_TREND       = 0.10
MACRO_EXIT_THR    = -0.70
BASE = 0.85
SIGMOID_K = 4.0
N_CONFIRM = 3

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


class BtcAnalogV2Strategy(IStrategy):
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
            df["cycle_bias"] = d.map(_HALVING["cycle_bias"]).ffill().fillna(0.0)
            df["cycle_phase"] = d.map(_HALVING["phase"]).ffill().fillna("NEUTRAL")

        df["anomaly"] = 0
        if not _ANOMALY.empty:
            coin_anom = _ANOMALY[_ANOMALY["coin"] == "BTC"][["is_anomaly"]] \
                       if "coin" in _ANOMALY.columns else _ANOMALY
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["anomaly"] = d.map(coin_anom["is_anomaly"]).fillna(0).astype(int)

        # === ANALOG V2 SIGNALS ===
        df["analog_v2"] = 0.0
        if not _ANALOG_V2.empty:
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["analog_v2"] = d.map(_ANALOG_V2["analog_v2_mean"]).fillna(0.0)
        # tilt from analog (centered at 0)
        analog_tilt = (W_ANALOG * df["analog_v2"]).clip(-0.25, 0.25)

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

        # Total tilt
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
        df.loc[enter, "enter_tag"] = "analogv2:enter"
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
        df.loc[exit_cond, "exit_tag"] = "analogv2:exit"
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


__all__ = ["BtcAnalogV2Strategy"]
