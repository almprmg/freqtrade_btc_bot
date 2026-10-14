"""Btc3LayerStrategy — three-layer BTC/USDT capital allocation.

Splits the wallet into three logical buckets:

  1. CORE (core_pct)
     - Long-term BTC accumulation, slow-moving.
     - Rebalanced on a fixed cadence (weekly / monthly / quarterly) toward
       its share of the total portfolio.
     - The bulk of the capital. Captures the macro trend.

  2. GRID (grid_pct)
     - Active layer for harvesting volatility.
     - On every daily close: if price dropped >= grid_step_pct since the
       last grid BUY, deploy one grid slice (= grid_pct / grid_levels).
     - On every daily close: if any grid leg's mark gain >= grid_take_pct,
       close that leg (FIFO of profitable).
     - Caps at grid_levels concurrent grid trades.

  3. CASH HEDGE (cash_pct)
     - Reserve USDT held flat.
     - Deployed only on a "crash" event: portfolio mark-to-market drawdown
       >= crash_threshold_pct from the rolling N-day high.
     - On crash trigger: deploy crash_deploy_fraction of remaining cash
       into BTC at the next close. The added BTC counts toward CORE
       thereafter (its take-profit is the next rebalance to target).
     - Once cash is exhausted, layer 3 is dormant until a closed trade
       refills it.

Each trade is tagged via enter_tag so the strategy (grid cap, grid anchor,
grid-only ROI) and the post-backtest analyzer can tell the layers apart:
  enter_tag = "core:initial" | "core:rebalance_up"
            | "grid:buy_N" (N = grid level index)
            | "hedge:crash_deploy"
The entry signal itself can only carry a generic "layer:auto" tag (the
layer is decided later, in custom_stake_amount), so the decision is stashed
per pair and written onto the trade's enter_tag in order_filled(). Trades
still carrying "layer:auto" (opened before this fix) are classified by
position: the oldest open trade on the pair is CORE, later ones are GRID.

NOTE: live freqtrade opens at most ONE trade per pair (enter_positions drops
pairs that already have an open trade; backtesting does the same unless
--enable-position-stacking). Grid/hedge legs therefore only materialise in
stacked backtests; in the live bot the single trade is the CORE.

Mode is selected via ENV `L3_MODE` (default L3_BALANCED). See L3_MODES
for the parameter combinations the sweep covers.
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
    from _regime_shield import shield_indicators, apply_shield
except ImportError:  # pragma: no cover
    from user_data.strategies._regime_shield import shield_indicators, apply_shield

WITH_SHIELD = os.environ.get("WITH_SHIELD", "false").lower() in ("true", "1", "yes")


MODE = os.environ.get("L3_MODE", "L3_AGGR_WIDE_GRID").upper()


def _build_modes() -> dict[str, dict]:
    """Hand-picked parameter combinations covering the strategy space.

    Naming: L3_<profile>_<variant>
      profile = AGGR (70/25/5) | BAL (60/30/10) | DEF (50/30/20)
      variant = baseline tweaks: rebalance cadence, grid step, crash threshold
    """
    # Common defaults.
    base: dict[str, dict] = {
        "rebal_days": 30,           # monthly core rebalance
        "rebal_threshold": 0.05,    # only rebalance if drift > 5% of portfolio
        "grid_levels": 5,           # 5 concurrent grid legs
        "grid_step_pct": 0.04,      # buy on -4% dip from last grid buy
        "grid_take_pct": 0.06,      # close grid leg at +6% gain
        "crash_threshold_pct": 0.30,
        "crash_lookback_days": 90,
        "crash_deploy_fraction": 1.0,
    }

    modes = {
        # === Aggressive (70 core / 25 grid / 5 cash) ===
        "L3_AGGR_BASELINE": {**base, "core_pct": 0.70, "grid_pct": 0.25, "cash_pct": 0.05},
        "L3_AGGR_TIGHT_GRID": {**base, "core_pct": 0.70, "grid_pct": 0.25, "cash_pct": 0.05,
                                "grid_step_pct": 0.02, "grid_take_pct": 0.03, "grid_levels": 8},
        "L3_AGGR_WIDE_GRID": {**base, "core_pct": 0.70, "grid_pct": 0.25, "cash_pct": 0.05,
                                "grid_step_pct": 0.06, "grid_take_pct": 0.10, "grid_levels": 3},
        "L3_AGGR_WEEKLY": {**base, "core_pct": 0.70, "grid_pct": 0.25, "cash_pct": 0.05, "rebal_days": 7},

        # === Balanced (60 core / 30 grid / 10 cash) ===
        "L3_BAL_BASELINE": {**base, "core_pct": 0.60, "grid_pct": 0.30, "cash_pct": 0.10},
        "L3_BAL_TIGHT_GRID": {**base, "core_pct": 0.60, "grid_pct": 0.30, "cash_pct": 0.10,
                               "grid_step_pct": 0.02, "grid_take_pct": 0.03, "grid_levels": 8},
        "L3_BAL_WIDE_GRID": {**base, "core_pct": 0.60, "grid_pct": 0.30, "cash_pct": 0.10,
                               "grid_step_pct": 0.06, "grid_take_pct": 0.10, "grid_levels": 3},
        "L3_BAL_WEEKLY": {**base, "core_pct": 0.60, "grid_pct": 0.30, "cash_pct": 0.10, "rebal_days": 7},
        "L3_BAL_QUARTERLY": {**base, "core_pct": 0.60, "grid_pct": 0.30, "cash_pct": 0.10, "rebal_days": 90},
        "L3_BAL_CRASH_SOFT": {**base, "core_pct": 0.60, "grid_pct": 0.30, "cash_pct": 0.10,
                                "crash_threshold_pct": 0.20},
        "L3_BAL_CRASH_HARD": {**base, "core_pct": 0.60, "grid_pct": 0.30, "cash_pct": 0.10,
                                "crash_threshold_pct": 0.40},

        # === Defensive (50 core / 30 grid / 20 cash) ===
        "L3_DEF_BASELINE": {**base, "core_pct": 0.50, "grid_pct": 0.30, "cash_pct": 0.20},
        "L3_DEF_TIGHT_GRID": {**base, "core_pct": 0.50, "grid_pct": 0.30, "cash_pct": 0.20,
                                "grid_step_pct": 0.02, "grid_take_pct": 0.03, "grid_levels": 8},
        "L3_DEF_WIDE_GRID": {**base, "core_pct": 0.50, "grid_pct": 0.30, "cash_pct": 0.20,
                                "grid_step_pct": 0.06, "grid_take_pct": 0.10, "grid_levels": 3},
        "L3_DEF_CRASH_SOFT": {**base, "core_pct": 0.50, "grid_pct": 0.30, "cash_pct": 0.20,
                                "crash_threshold_pct": 0.20},
        "L3_DEF_PARTIAL_DEPLOY": {**base, "core_pct": 0.50, "grid_pct": 0.30, "cash_pct": 0.20,
                                   "crash_deploy_fraction": 0.5},
    }
    return modes


L3_MODES = _build_modes()

if MODE not in L3_MODES:
    raise ValueError(f"unknown L3_MODE: {MODE}; valid: {list(L3_MODES)}")

P = L3_MODES[MODE]
CORE_PCT = float(P["core_pct"])
GRID_PCT = float(P["grid_pct"])
CASH_PCT = float(P["cash_pct"])
REBAL_DAYS = int(P["rebal_days"])
REBAL_THRESHOLD = float(P["rebal_threshold"])
GRID_LEVELS = int(P["grid_levels"])
GRID_STEP = float(P["grid_step_pct"])
GRID_TAKE = float(P["grid_take_pct"])
CRASH_THRESHOLD = float(P["crash_threshold_pct"])
CRASH_LOOKBACK = int(P["crash_lookback_days"])
CRASH_DEPLOY_FRACTION = float(P["crash_deploy_fraction"])


class Btc3LayerStrategy(IStrategy):
    INTERFACE_VERSION: int = 3

    timeframe: str = "1d"
    can_short: bool = False
    process_only_new_candles: bool = True

    # ROI is the take-profit of GRID legs only. A table-wide {"0": GRID_TAKE}
    # also ROI-closed the 70% CORE trade at +10%, contradicting the design
    # (core is long-term accumulation). The table is therefore empty and
    # custom_roi() returns GRID_TAKE for grid legs and None (= never) for
    # core/hedge trades. Do NOT set minimal_roi in the bot configs.
    minimal_roi: dict = {}
    use_custom_roi: bool = True
    stoploss: float = -0.99
    use_custom_stoploss: bool = False

    # Grid + core + crash deploys all share the same pair → many concurrent
    # trades. Freqtrade's max_open_trades is set to -1 (unlimited) in config.
    position_adjustment_enable: bool = False  # we open distinct trades

    use_exit_signal: bool = True
    exit_profit_only: bool = False

    startup_candle_count: int = max(CRASH_LOOKBACK + 5, 220)

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "limit",
        "stoploss_on_exchange": False,
    }

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rolling_high"] = dataframe["high"].rolling(CRASH_LOOKBACK, min_periods=1).max()
        dataframe["dd_from_high"] = (
            dataframe["rolling_high"] - dataframe["close"]
        ) / dataframe["rolling_high"]
        if WITH_SHIELD:
            dataframe = shield_indicators(dataframe)
        return dataframe

    # ---- Helpers --------------------------------------------------------- #

    @staticmethod
    def _explicit_layer(trade: Trade) -> Optional[str]:
        """Layer encoded in the enter_tag ("core:"/"grid:"/"hedge:"), else None."""
        tag = (trade.enter_tag or "").lower()
        for layer in ("grid", "hedge", "core"):
            if tag.startswith(layer + ":"):
                return layer
        return None

    @classmethod
    def _classify(cls, trades: list) -> dict:
        """Split one pair's open trades into layers (oldest first). Untagged
        trades: the first position on the pair is CORE, later ones GRID."""
        ordered = sorted(trades, key=lambda t: (t.open_date_utc, getattr(t, "id", None) or 0))
        layers: dict = {"core": [], "grid": [], "hedge": []}
        for t in ordered:
            layer = cls._explicit_layer(t)
            if layer is None:
                layer = "grid" if (layers["core"] or layers["hedge"]) else "core"
            layers[layer].append(t)
        return layers

    def _layer_of(self, trade: Trade) -> str:
        layer = self._explicit_layer(trade)
        if layer is not None:
            return layer
        try:
            same_pair = [t for t in Trade.get_open_trades() if t.pair == trade.pair]
        except Exception:  # no persistence available (unit tests)
            return "core"
        for name, ts in self._classify(same_pair).items():
            if any(t is trade or (getattr(t, "id", None) is not None
                                  and t.id == getattr(trade, "id", None)) for t in ts):
                return name
        return "core"

    def _stash_layer_tag(self, pair: str, tag: str) -> None:
        if not hasattr(self, "_l3_pending_tag"):
            self._l3_pending_tag = {}
        self._l3_pending_tag[pair] = tag

    def _portfolio_state(self, pair: str, current_rate: float) -> dict:
        open_trades = [t for t in Trade.get_open_trades() if t.pair == pair]
        layers = self._classify(open_trades)

        def qty(ts):
            return sum((float(t.amount) for t in ts), 0.0)

        def cost(ts):
            return sum((float(t.stake_amount) for t in ts), 0.0)

        core_qty = qty(layers["core"]) + qty(layers["hedge"])  # hedge merges into core
        grid_qty = qty(layers["grid"])
        return {
            "core_trades": layers["core"] + layers["hedge"],
            "grid_trades": layers["grid"],
            "core_qty": core_qty,
            "grid_qty": grid_qty,
            "core_cost": cost(layers["core"]) + cost(layers["hedge"]),
            "grid_cost": cost(layers["grid"]),
            "total_btc_value": (core_qty + grid_qty) * current_rate,
        }

    # ---- Entry signals --------------------------------------------------- #

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        ready = df["ema200"].notna()
        # We always allow entry; the actual decision (which layer, how much)
        # is in custom_stake_amount via Freqtrade's open-trade-on-signal flow.
        df.loc[ready, "enter_long"] = 1
        df.loc[ready, "enter_tag"] = "layer:auto"
        if WITH_SHIELD:
            df = apply_shield(df, "entry")
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        if WITH_SHIELD:
            dataframe = apply_shield(dataframe, "exit")
        return dataframe

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: Optional[float],
        max_stake: float,
        leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> float:
        # Total wallet capacity = max_stake passed by Freqtrade (free balance
        # for this entry). Pre-allocate the three buckets the first time we
        # see this pair: take a snapshot of total = current free + invested.
        st = self._portfolio_state(pair, current_rate)
        invested = st["core_cost"] + st["grid_cost"]
        free = float(max_stake or 0.0)
        total = invested + free
        if total <= 0:
            return 0.0

        core_target = total * CORE_PCT
        grid_target_total = total * GRID_PCT
        cash_target = total * CASH_PCT

        # 1) Bootstrap CORE first.
        core_value = st["core_qty"] * current_rate
        core_deficit = core_target - core_value
        if core_deficit > 0:
            stake = min(core_deficit, free)
            if min_stake and stake < min_stake:
                return 0.0
            if stake > 0:
                self._stash_layer_tag(pair, "core:rebalance_up" if st["core_trades"] else "core:initial")
            return float(stake) if stake > 0 else 0.0

        # 2) GRID layer: only open a new leg if the latest closed candle is
        #    at least grid_step % below the last GRID buy (or the all-time
        #    grid-anchor = first core entry if no grid yet).
        if len(st["grid_trades"]) < GRID_LEVELS:
            if not st["grid_trades"]:
                anchor_price = float(st["core_trades"][0].open_rate) if st["core_trades"] else current_rate
            else:
                # Last grid leg's entry price.
                anchor_price = float(st["grid_trades"][-1].open_rate)
            if current_rate <= anchor_price * (1.0 - GRID_STEP):
                grid_slice = grid_target_total / GRID_LEVELS
                stake = min(grid_slice, free)
                if min_stake and stake < min_stake:
                    return 0.0
                if stake > 0:
                    self._stash_layer_tag(pair, f"grid:buy_{len(st['grid_trades']) + 1}")
                return float(stake) if stake > 0 else 0.0

        # 3) HEDGE / Crash deploy: if drawdown from rolling high exceeds
        #    crash threshold, deploy a fraction of remaining cash into BTC
        #    (joins the CORE bucket via enter_tag).
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        if df is not None and not df.empty:
            dd = float(df.iloc[-1]["dd_from_high"])
            if dd >= CRASH_THRESHOLD:
                cash_reserve_now = max(0.0, free - 0.0)  # free is the available cash
                deploy = min(cash_reserve_now * CRASH_DEPLOY_FRACTION, free)
                if min_stake and deploy < min_stake:
                    return 0.0
                if deploy > 0:
                    self._stash_layer_tag(pair, "hedge:crash_deploy")
                    return float(deploy)

        return 0.0  # nothing to do this bar

    def custom_roi(self, pair: str, trade: Trade, current_time: datetime,
                   trade_duration: int, entry_tag: Optional[str], side: str,
                   **kwargs) -> Optional[float]:
        """Per-trade ROI: grid legs take profit at GRID_TAKE; core/hedge never."""
        return GRID_TAKE if self._layer_of(trade) == "grid" else None

    # ---- Override enter_tag based on layer decision --------------------- #

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> bool:
        # The layer is written onto the trade in order_filled() (the Trade
        # row does not exist yet here).
        return True

    def order_filled(self, pair: str, trade: Trade, order, current_time: datetime,
                     **kwargs) -> None:
        """Retag the trade with the layer custom_stake_amount decided for it."""
        if getattr(order, "ft_order_side", None) != trade.entry_side:
            return
        tag = getattr(self, "_l3_pending_tag", {}).pop(pair, None)
        if tag and self._explicit_layer(trade) is None:
            trade.enter_tag = tag


# Expose modes for the sweep harness to enumerate.
__all__ = ["Btc3LayerStrategy", "L3_MODES"]
