"""CalendarFuturesStrategy — Calendar Shield with FUTURES short capability.

Adapted from BtcCalendarShieldStrategy (the strongest deployed pattern).

KEY CHANGES vs spot version:
  1. can_short = True (enables short positions)
  2. trading_mode = "futures" + margin_mode = "isolated"
  3. populate_entry_trend: ALSO fills enter_short when BEAR + cycle_bias very negative
  4. populate_exit_trend: ALSO fills exit_short when regime flips back
  5. Symmetric sizing: BASE_LONG=0.85, BASE_SHORT=0.50 (shorts more conservative
     because unlimited upside risk on the underlying)
  6. Anomaly circuit breaker exits BOTH directions

LEVERAGE: 1x (no leverage). User gains short capability but no liquidation risk
beyond underlying drawdown.

HYPOTHESIS:
  In bear/sideways windows where the spot version returns 0% (sits in cash),
  the futures version can SHORT and convert those zero windows into positive
  PnL. Example: BTC dropped ~65% in 2022. A 1x short during BEAR-confirmed
  periods could capture a meaningful portion of that decline.

COIN: this is a generic template — the COIN constant filters anomaly_flags
and should be set per-deployment (BTC, ETH, BNB, etc.)
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

# Per-deployment customization (set via env var or subclass)
import os
COIN = os.environ.get("CAL_FUT_COIN", "BTC")

N_CONFIRM = 3
BASE_LONG = 0.85       # Same as spot Calendar Shield
BASE_SHORT = 0.50      # More conservative — shorts have unlimited risk
SIGMOID_K = 4.0
SHORT_THRESHOLD = -0.30  # cycle_bias must be < this to enable shorts

PHASE_SHIFTS = {
    "ACCUMULATION":  0.20,
    "EARLY_BULL":    0.10,
    "PARABOLIC":    -0.15,
    "DISTRIBUTION": -0.40,
    "BEAR":         -0.60,
    "REACCUMULATION": -0.05,
}
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


class CalendarFuturesStrategy(IStrategy):
    INTERFACE_VERSION: int = 3
    timeframe: str = "1d"
    can_short: bool = True
    process_only_new_candles: bool = True

    minimal_roi: dict = {"0": 10.0}
    stoploss: float = -0.99
    use_custom_stoploss: bool = False
    position_adjustment_enable: bool = True
    max_entry_position_adjustment: int = 5000
    use_exit_signal: bool = True
    exit_profit_only: bool = False
    startup_candle_count: int = 220

    # Futures-specific
    trading_mode = "futures"
    margin_mode = "isolated"

    order_types = {"entry": "limit", "exit": "limit",
                   "stoploss": "limit", "stoploss_on_exchange": False}

    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, entry_tag, side, **kwargs):
        """Always 1x — no actual leverage, just short capability."""
        return 1.0

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe.copy()
        df["ema200"] = ta.EMA(df, timeperiod=200)
        df["adx"] = ta.ADX(df, timeperiod=14)
        df["ret_30d"] = df["close"].pct_change(30)

        # Regime detection (same as spot)
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

        # Halving cycle (BTC) or zero baseline (other coins)
        df["cycle_bias"] = 0.0
        df["cycle_phase"] = "NEUTRAL"
        if not _HALVING.empty:
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["cycle_bias"] = d.map(_HALVING["cycle_bias"]).ffill().fillna(0.0)
            df["cycle_phase"] = d.map(_HALVING["phase"]).ffill().fillna("NEUTRAL")

        # Anomaly per-coin
        df["anomaly"] = 0
        if not _ANOMALY.empty:
            coin_anom = _ANOMALY[_ANOMALY["coin"] == COIN][["is_anomaly"]] \
                       if "coin" in _ANOMALY.columns else _ANOMALY
            d = pd.to_datetime(df["date"], utc=True).dt.normalize()
            df["anomaly"] = d.map(coin_anom["is_anomaly"]).fillna(0).astype(int)

        # Calendar tilts (same as spot)
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

        # LONG sizing
        shifts = df["cycle_phase"].map(PHASE_SHIFTS).fillna(0.0).astype(float)
        adjusted_bias_long = df["cycle_bias"].astype(float) + shifts + df["calendar_tilt"]
        long_mult = _sigmoid(adjusted_bias_long.values, k=SIGMOID_K, c=0.0)
        df["ai_target_long"] = (BASE_LONG * long_mult).clip(0.0, BASE_LONG)
        df.loc[df["anomaly"] == 1, "ai_target_long"] = 0.0
        df.loc[df["regime_confirmed"] == "BEAR", "ai_target_long"] = 0.0

        # SHORT sizing — symmetric but inverted, only when cycle_bias very negative
        adjusted_bias_short = -df["cycle_bias"].astype(float) - shifts - df["calendar_tilt"]
        short_mult = _sigmoid(adjusted_bias_short.values, k=SIGMOID_K, c=0.0)
        df["ai_target_short"] = (BASE_SHORT * short_mult).clip(0.0, BASE_SHORT)
        df.loc[df["anomaly"] == 1, "ai_target_short"] = 0.0
        df.loc[df["regime_confirmed"] == "BULL", "ai_target_short"] = 0.0
        # Only enable shorts when cycle_bias is meaningfully negative
        df.loc[df["cycle_bias"] > SHORT_THRESHOLD, "ai_target_short"] = 0.0

        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        ready = df["ema200"].notna()

        # LONG entry: BULL regime + ai_target_long meaningful
        enter_long = ready & (df["regime_confirmed"] == "BULL") & (df["ai_target_long"] > 0.15)
        df.loc[enter_long, "enter_long"] = 1
        df.loc[enter_long, "enter_tag"] = "calendar_fut:long"

        # SHORT entry: BEAR regime + cycle_bias very negative + ai_target_short meaningful
        enter_short = ready & (df["regime_confirmed"] == "BEAR") & (df["ai_target_short"] > 0.15)
        df.loc[enter_short, "enter_short"] = 1
        df.loc[enter_short, "enter_tag"] = "calendar_fut:short"

        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe

        # Exit LONG: regime no longer BULL, anomaly, or target collapsed
        exit_long = (
            (df["regime_confirmed"] != "BULL")
            | (df["anomaly"] == 1)
            | (df["ai_target_long"] < 0.20)
        )
        df.loc[exit_long, "exit_long"] = 1
        df.loc[exit_long, "exit_tag"] = "calendar_fut:long_exit"

        # Exit SHORT: regime no longer BEAR, anomaly, or target collapsed
        exit_short = (
            (df["regime_confirmed"] != "BEAR")
            | (df["anomaly"] == 1)
            | (df["ai_target_short"] < 0.10)
        )
        df.loc[exit_short, "exit_short"] = 1
        df.loc[exit_short, "exit_tag"] = "calendar_fut:short_exit"

        return df

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return float(proposed_stake)
        last = df.iloc[-1]
        if side == "long":
            target = float(last["ai_target_long"])
        else:
            target = float(last["ai_target_short"])
        if max_stake and max_stake > 0:
            return float(max_stake) * max(target, 0.0)
        return float(proposed_stake)

    def adjust_trade_position(self, trade, current_time, current_rate, current_profit,
                              min_stake, max_stake, current_entry_rate, current_exit_rate,
                              current_entry_profit, current_exit_profit, **kwargs):
        """Rebalance position toward ai_target as cycle_bias evolves.

        Same drift-based logic as spot Calendar Shield: buy more if undersized,
        sell some if oversized. Works for both long and short.
        """
        df, _ = self.dp.get_analyzed_dataframe(pair=trade.pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return None
        last = df.iloc[-1]
        if trade.is_short:
            target = float(last["ai_target_short"])
        else:
            target = float(last["ai_target_long"])
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

        # Undersized: add to position
        if drift < -0.05 * total and usdt_free > 1:
            buy = min(-drift, usdt_free * 0.99)
            if max_stake and max_stake > 0:
                buy = min(buy, max_stake)
            if min_stake and buy < min_stake:
                return None
            return float(buy)
        # Oversized: reduce
        if drift > 0.10 * total:
            sell = min(drift, value * 0.99)
            if min_stake and sell < min_stake:
                return None
            return -float(sell)
        return None


__all__ = ["CalendarFuturesStrategy"]
