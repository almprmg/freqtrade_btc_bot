"""BtcAdaptiveStrategy — regime-aware adaptive system with stop rules.

The "pro" version that combines four layers:

  1. REGIME DETECTION (every bar)
     - TRENDING: ADX > 25, price clearly above/below EMA50
     - RANGING:  ADX < 20, BB width below median
     - VOLATILE: ATR > 2× rolling avg
     - The current regime drives target_btc_pct.

  2. CORE / GRID / CASH ALLOCATION (regime-driven)
     - TRENDING UP:  core 75%, grid 15%, cash 10%
     - TRENDING DN:  core 30%, grid 0,  cash 70%
     - RANGING:      core 50%, grid 40%, cash 10%  ← grid is most active here
     - VOLATILE:     core 50%, grid 0,  cash 50%

  3. STOP RULES (override allocation when fired)
     - STOP_GRID:  daily price -X% over 2 days → freeze grid entries
     - TRIM_RALLY: price +Y% without an X% pullback → trim 20% of BTC to cash
     - VOL_PUSH:   ATR z-score > 2 → move 10pp of allocation to cash

  4. EXECUTION (one trade, position_adjustment)
     Single trade that DCAs up/down toward the dynamic target. Grid layer
     is simulated by lowering the threshold around target when RANGING
     (more frequent buys/sells, smaller per-action size).

Mode is selected via ENV `AD_MODE`. The sweep tunes:
  - Allocation profile (aggressive / balanced / defensive)
  - Stop sensitivity (tight / baseline / loose)
  - Profit-trim threshold
  - Grid step inside ranging regime
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy

try:
    from _regime_shield import shield_indicators, apply_shield, regime_allows_add
except ImportError:  # pragma: no cover
    from user_data.strategies._regime_shield import shield_indicators, apply_shield, regime_allows_add

WITH_SHIELD = os.environ.get("WITH_SHIELD", "false").lower() in ("true", "1", "yes")


MODE = os.environ.get("AD_MODE", "ADAPT_AGGR_NOSTOP").upper()  # winner of 12-variant sweep


def _build_modes() -> dict[str, dict]:
    base = {
        # Regime targets (BTC % of portfolio):
        "target_trend_up": 0.75,
        "target_trend_dn": 0.30,
        "target_range": 0.50,
        "target_volatile": 0.50,

        # Grid only fires in RANGING regime — smaller threshold for finer rebalancing.
        "range_drift_threshold": 0.03,    # rebalance if drift > 3% (active grid)
        "trend_drift_threshold": 0.08,    # rebalance only on larger drift (no grid)

        # Stop rules:
        "stop_grid_drop_pct": 0.15,       # halt grid if 2d drop ≥ 15%
        "stop_grid_window_days": 2,
        "trim_rally_pct": 0.30,           # trim if up 30% from rolling low
        "trim_rally_amount": 0.20,        # trim 20% of BTC value
        "vol_zscore_threshold": 2.0,      # ATR z-score for vol push
        "vol_push_pct": 0.10,             # move 10pp to cash on vol push

        # Trim rule: after rally without pullback of X%
        "rally_pullback_filter_pct": 0.05,

        # Indicator periods
        "adx_period": 14,
        "atr_period": 14,
        "atr_avg_period": 50,
        "ema_short": 50,
        "ema_long": 200,
        "bb_period": 20,
    }
    profiles = {
        "AGGR": {"target_trend_up": 0.85, "target_trend_dn": 0.40, "target_range": 0.60},
        "BAL":  {"target_trend_up": 0.75, "target_trend_dn": 0.30, "target_range": 0.50},
        "DEF":  {"target_trend_up": 0.65, "target_trend_dn": 0.20, "target_range": 0.40},
    }
    modes = {}
    # 3 baselines × 4 variants = 12 modes
    for pname, ptweaks in profiles.items():
        baseline = {**base, **ptweaks}
        modes[f"ADAPT_{pname}_BASELINE"] = baseline
        modes[f"ADAPT_{pname}_TIGHT"] = {
            **baseline,
            "range_drift_threshold": 0.02,
            "trim_rally_pct": 0.20,
            "stop_grid_drop_pct": 0.10,
        }
        modes[f"ADAPT_{pname}_LOOSE"] = {
            **baseline,
            "range_drift_threshold": 0.05,
            "trim_rally_pct": 0.40,
            "stop_grid_drop_pct": 0.20,
        }
        modes[f"ADAPT_{pname}_NOSTOP"] = {
            **baseline,
            "stop_grid_drop_pct": 1.0,        # effectively disabled
            "trim_rally_pct": 1.0,            # disabled
            "vol_zscore_threshold": 100.0,    # disabled
        }
    return modes


AD_MODES = _build_modes()
if MODE not in AD_MODES:
    raise ValueError(f"unknown AD_MODE: {MODE}; valid: {list(AD_MODES)}")
P = AD_MODES[MODE]


class BtcAdaptiveStrategy(IStrategy):
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

    startup_candle_count: int = max(int(P["ema_long"]) + 20, 220)

    order_types = {"entry": "limit", "exit": "limit", "stoploss": "limit", "stoploss_on_exchange": False}

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        df["adx"] = ta.ADX(df, timeperiod=int(P["adx_period"]))
        df["atr"] = ta.ATR(df, timeperiod=int(P["atr_period"]))
        df["atr_avg"] = df["atr"].rolling(int(P["atr_avg_period"]), min_periods=1).mean()
        df["atr_std"] = df["atr"].rolling(int(P["atr_avg_period"]), min_periods=2).std()
        df["atr_z"] = (df["atr"] - df["atr_avg"]) / df["atr_std"].replace(0, pd.NA)
        df["ema_short"] = ta.EMA(df, timeperiod=int(P["ema_short"]))
        df["ema_long"] = ta.EMA(df, timeperiod=int(P["ema_long"]))
        bb = ta.BBANDS(df, timeperiod=int(P["bb_period"]), nbdevup=2.0, nbdevdn=2.0)
        df["bb_width"] = (bb["upperband"] - bb["lowerband"]) / bb["middleband"]
        df["bb_width_avg"] = df["bb_width"].rolling(50, min_periods=1).mean()
        # 2-day cumulative % change for stop_grid rule:
        df["change_2d_pct"] = df["close"].pct_change(int(P["stop_grid_window_days"]))
        # Rolling low for rally trim trigger
        df["low_90d"] = df["low"].rolling(90, min_periods=1).min()
        df["rally_from_low"] = (df["close"] - df["low_90d"]) / df["low_90d"]
        if WITH_SHIELD:
            df = shield_indicators(df)
        return df

    @staticmethod
    def _regime(last: pd.Series) -> str:
        # Volatile if ATR z-score above threshold.
        if not pd.isna(last.get("atr_z")) and last["atr_z"] > P["vol_zscore_threshold"]:
            return "VOLATILE"
        # Trending: ADX > 25.
        if last["adx"] > 25:
            return "TREND_UP" if last["close"] > last["ema_short"] else "TREND_DN"
        # Ranging: low ADX or BB width below average.
        if last["adx"] < 20 or last["bb_width"] < last["bb_width_avg"]:
            return "RANGE"
        return "TREND_UP" if last["close"] > last["ema_short"] else "TREND_DN"

    def _target_pct(self, regime: str) -> float:
        return {
            "TREND_UP": float(P["target_trend_up"]),
            "TREND_DN": float(P["target_trend_dn"]),
            "RANGE":    float(P["target_range"]),
            "VOLATILE": float(P["target_volatile"]),
        }[regime]

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        ready = df["ema_long"].notna() & df["atr_z"].notna()
        df.loc[ready, "enter_long"] = 1
        df.loc[ready, "enter_tag"] = f"adapt:{MODE.lower()}"
        if WITH_SHIELD:
            df = apply_shield(df, "entry")
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        if WITH_SHIELD:
            dataframe = apply_shield(dataframe, "exit")
        return dataframe

    def custom_stake_amount(
        self, pair: str, current_time: datetime, current_rate: float,
        proposed_stake: float, min_stake: Optional[float], max_stake: float,
        leverage: float, entry_tag: Optional[str], side: str, **kwargs,
    ) -> float:
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return float(proposed_stake)
        last = df.iloc[-1]
        target = self._target_pct(self._regime(last))
        if max_stake and max_stake > 0:
            return float(max_stake) * target
        return float(proposed_stake)

    def adjust_trade_position(
        self, trade: Trade, current_time: datetime, current_rate: float,
        current_profit: float, min_stake: Optional[float], max_stake: float,
        current_entry_rate: float, current_exit_rate: float,
        current_entry_profit: float, current_exit_profit: float, **kwargs,
    ) -> Optional[float]:
        df, _ = self.dp.get_analyzed_dataframe(pair=trade.pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return None
        last = df.iloc[-1]
        regime = self._regime(last)

        btc_qty = float(trade.amount or 0)
        btc_value = btc_qty * float(current_rate)
        usdt_free = float(self.wallets.get_free(trade.stake_currency) or 0.0)
        total = btc_value + usdt_free
        if total <= 0:
            return None

        # --- STOP RULES ----------------------------------------------------
        # STOP_GRID: skip grid actions if recent 2-day drop large.
        stop_grid_active = (last["change_2d_pct"] is not None
                            and last["change_2d_pct"] <= -float(P["stop_grid_drop_pct"]))

        # VOL_PUSH: in volatile regime, push 10pp to cash regardless of target.
        target = self._target_pct(regime)
        if regime == "VOLATILE":
            target = max(0.0, target - float(P["vol_push_pct"]))

        # TRIM_RALLY: if up trim_rally_pct from 90d low and no recent pullback,
        # trim trim_rally_amount of BTC value.
        rally_trim_usdt = 0.0
        if last["rally_from_low"] >= float(P["trim_rally_pct"]):
            rally_trim_usdt = btc_value * float(P["trim_rally_amount"])

        target_btc_value = target * total
        drift_usdt = btc_value - target_btc_value  # >0 → too much BTC

        # Choose drift threshold based on regime — grid is more granular in RANGE.
        if regime == "RANGE" and not stop_grid_active:
            threshold = float(P["range_drift_threshold"])
        else:
            threshold = float(P["trend_drift_threshold"])

        drift_pct = abs(drift_usdt) / total
        # Compose decisions:
        if rally_trim_usdt > 0 and drift_usdt > 0:
            rebalance_usdt = max(drift_usdt, rally_trim_usdt)
        elif rally_trim_usdt > 0 and drift_usdt <= 0:
            rebalance_usdt = rally_trim_usdt  # force a trim even though target says hold/buy
        elif drift_pct < threshold:
            return None
        else:
            rebalance_usdt = drift_usdt

        if rebalance_usdt > 0:
            sell_usdt = min(rebalance_usdt, btc_value * 0.99)
            if min_stake and sell_usdt < min_stake:
                return None
            return -float(sell_usdt) if sell_usdt > 0 else None
        else:
            # In stop_grid_active we don't buy new grid legs even if drift says buy.
            if stop_grid_active:
                return None
            buy_usdt = min(-rebalance_usdt, usdt_free * 0.99)
            if max_stake and max_stake > 0:
                buy_usdt = min(buy_usdt, max_stake)
            if min_stake and buy_usdt < min_stake:
                return None
            return float(buy_usdt) if buy_usdt > 0 else None


__all__ = ["BtcAdaptiveStrategy", "AD_MODES"]
