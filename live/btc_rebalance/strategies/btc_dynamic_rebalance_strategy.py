"""BtcDynamicRebalanceStrategy — condition-driven BTC/USDT rebalancing.

Time-based rebalancers fire on a fixed schedule (daily / weekly). This one
fires on MARKET CONDITIONS — RSI extremes, Bollinger touches, profit
milestones, volatility spikes, regime shifts. Idea: only trade when the
market is actually offering an edge.

Trigger families (selected via ENV `DR_MODE`):

  Profit-based — rebalance when portfolio mark hits a milestone:
    DR_PROFIT_10  / DR_PROFIT_20 / DR_PROFIT_30

  RSI-based — RSI extremes call for action:
    DR_RSI_70_30  — trim if RSI>70, add if RSI<30
    DR_RSI_75_25  — tighter bands

  Bollinger Band touches:
    DR_BB

  Volatility (ATR):
    DR_VOL_HIGH   — trim when ATR spikes (regime change), buy when low

  Drawdown buyer:
    DR_DD_20      — only act on -20% from 90d high

  Trend-following:
    DR_EMA50      — trim above EMA50, buy below

  Combined:
    DR_RSI_AND_PROFIT — trigger needs both RSI extreme AND profit milestone
    DR_RSI_OR_BB      — trigger if RSI extreme OR BB touch

  Dynamic target (target_pct itself changes):
    DR_REGIME     — target=0.85 above EMA200, target=0.50 below; rebalances
                    toward it on EVERY loop past min_stake (churns, kept for
                    the archive)
    DR_REGIME_BAND — same 85/50 regime target, but rebalances only when the
                    regime FLIPS or the portfolio moved +-20% since the last
                    fill (2026-10-29: stress-tested on the 2022, 2024 and
                    2025-26 drops; 2020-now +839% / max DD -58% vs 75/25
                    +711% / -65% in the hourly simulation)

In all modes the "rebalance" action means: bring BTC back to TARGET_PCT of
total portfolio (full rebalance). Modes differ only in WHEN they fire.
Target defaults to 0.75 except DR_REGIME.

Profit anchor (fix C14): profit-based triggers (DR_PROFIT_*, and the profit
leg of DR_RSI_AND_PROFIT) measure the move of the PORTFOLIO value
(position value + free stake) against an anchor stored per trade in
`trade.custom_data["dr_anchor_value"]`. The anchor is (re)set to the
portfolio value at the price of the most recent filled order (entry or
rebalance), so a rebalance fires once per ±profit_trigger_pct move and then
re-arms. Previously the trigger used `current_profit` (vs the average entry
rate), which stayed past the threshold forever and re-rebalanced on every
bot loop (live churn: duplicate fills seconds apart).

Cooldown (all modes): no adjustment while the trade has an open order, or
within DR_COOLDOWN_MIN minutes (default 60) of the last filled order.
On 1d backtests this is a no-op (adjust is evaluated once per candle).

Partial-sell sizing (fix C14b): freqtrade converts a NEGATIVE
adjust_trade_position return into a coin amount against the position's COST
BASIS, not its market value:
    amount = |stake| * trade.amount / trade.stake_amount
(freqtrade 2026.4: freqtradebot.py process_open_trade_positions /
optimize/backtesting.py _get_adjust_trade_entry_for_candle). Returning the
market-value overweight (e.g. -drift_usdt) therefore over-sells when the
position is in profit (BTC 2021-02-12 trim left 49% BTC instead of 75%) and
under-sells when it is at a loss. The strategy now computes the coin quantity
it actually wants to sell (overweight_value / current_rate) and returns it as
a fraction of trade.stake_amount — see `partial_exit_stake()`.

ROI (fix C14b): the strategy must never ROI-exit. `minimal_roi = {}` means no
ROI table entry ever matches, so IStrategy.min_roi_reached() returns False for
any profit (an empty dict on the class is kept by StrategyResolver; the old
{"0": 10.0} == +1000% was reachable for SOL 2021 and closed the trade).
Do NOT set `minimal_roi` in the bot configs — config overrides the strategy.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy

try:
    from _regime_shield import shield_indicators, apply_shield, regime_allows_add
except ImportError:  # pragma: no cover
    from user_data.strategies._regime_shield import shield_indicators, apply_shield, regime_allows_add
try:  # shared cost-basis partial-exit sizing (C14b); names re-exported for tests
    from _position_sizing import partial_exit_stake, freqtrade_exit_amount  # noqa: F401
except ImportError:  # pragma: no cover
    from user_data.strategies._position_sizing import partial_exit_stake, freqtrade_exit_amount  # noqa: F401

WITH_SHIELD = os.environ.get("WITH_SHIELD", "false").lower() in ("true", "1", "yes")


MODE = os.environ.get("DR_MODE", "DR_PROFIT_20").upper()  # winner of 12-variant sweep
COOLDOWN_MIN = float(os.environ.get("DR_COOLDOWN_MIN", "60"))

ANCHOR_KEY = "dr_anchor_value"
ANCHOR_NFILLS_KEY = "dr_anchor_nfills"
# DR_REGIME_BAND: the target the position was last rebalanced to, and the
# order we placed to get there (confirmed only once it fills).
APPLIED_TARGET_KEY = "dr_applied_target"
PENDING_TARGET_KEY = "dr_pending_target"
PENDING_NFILLS_KEY = "dr_pending_nfills"
NO_PENDING = -1.0  # freqtrade stores None as the string 'null': never write None


def custom_float(trade, key: str) -> Optional[float]:
    """Numeric custom_data value, or None when unset / cleared / not a number."""
    raw = trade.get_custom_data(key)
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return None if val < 0 else val


# ---- Pure helpers (unit-tested in tests/test_dynrebal_anchor.py) ---------- #

def anchor_value(amount: float, fill_price: float, free_stake: float) -> float:
    """Portfolio value at the last fill: position marked at the fill price + free stake."""
    return float(amount) * float(fill_price) + float(free_stake)


def portfolio_move(anchor: float, total: float) -> float:
    """Relative portfolio move since the anchor (0.2 == +20%)."""
    if not anchor or anchor <= 0:
        return 0.0
    return float(total) / float(anchor) - 1.0


def profit_trigger_fires(anchor: float, total: float, threshold: float) -> bool:
    """True once the portfolio moved >= threshold (either direction) from the anchor."""
    return abs(portfolio_move(anchor, total)) >= float(threshold) - 1e-9  # float tolerance


def in_cooldown(has_open_orders: bool, last_fill: Optional[datetime],
                now: datetime, cooldown_min: float) -> bool:
    """Block adjustments while an order is open or the last fill is too recent."""
    if has_open_orders:
        return True
    if last_fill is None or cooldown_min <= 0:
        return False
    if last_fill.tzinfo is None:
        last_fill = last_fill.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now - last_fill < timedelta(minutes=cooldown_min)


def regime_target(close: float, ema_long: float, bull: float, bear: float) -> float:
    """Bull (close above the long EMA) -> bull target, else bear target."""
    return float(bull) if float(close) > float(ema_long) else float(bear)


def regime_band_fires(applied_target: Optional[float], target: float,
                      move: float, threshold: float) -> bool:
    """Rebalance when the regime target changed or the portfolio left the +-band."""
    if applied_target is not None and abs(float(applied_target) - float(target)) > 1e-9:
        return True
    return abs(float(move)) >= float(threshold) - 1e-9


def _build_modes() -> dict[str, dict]:
    base: dict[str, dict] = {
        "target_pct": 0.75,
        "profit_trigger_pct": 0.20,    # rebalance every +20% portfolio gain since last anchor
        "rsi_high": 70.0,
        "rsi_low": 30.0,
        "bb_period": 20,
        "bb_std": 2.0,
        "atr_period": 14,
        "atr_avg_period": 50,
        "atr_spike_mult": 1.8,
        "dd_threshold": 0.20,
        "ema_short": 50,
        "ema_long": 200,
        "rebalance_fraction": 1.0,
        "trigger_type": "profit_only",  # which condition fires
        "regime_bull_target": 0.75,
        "regime_bear_target": 0.50,
    }
    return {
        "DR_PROFIT_10": {**base, "profit_trigger_pct": 0.10, "trigger_type": "profit_only"},
        "DR_PROFIT_20": {**base, "profit_trigger_pct": 0.20, "trigger_type": "profit_only"},
        "DR_PROFIT_30": {**base, "profit_trigger_pct": 0.30, "trigger_type": "profit_only"},
        "DR_RSI_70_30": {**base, "rsi_high": 70, "rsi_low": 30, "trigger_type": "rsi_only"},
        "DR_RSI_75_25": {**base, "rsi_high": 75, "rsi_low": 25, "trigger_type": "rsi_only"},
        "DR_BB": {**base, "trigger_type": "bb_only"},
        "DR_VOL_HIGH": {**base, "atr_spike_mult": 1.8, "trigger_type": "vol_only"},
        "DR_DD_20": {**base, "dd_threshold": 0.20, "trigger_type": "drawdown_only"},
        "DR_EMA50": {**base, "trigger_type": "ema_trend"},
        "DR_RSI_AND_PROFIT": {**base, "trigger_type": "rsi_and_profit", "profit_trigger_pct": 0.15},
        "DR_RSI_OR_BB": {**base, "trigger_type": "rsi_or_bb"},
        "DR_REGIME": {**base, "trigger_type": "regime_target"},
        "DR_REGIME_BAND": {**base, "trigger_type": "regime_band", "profit_trigger_pct": 0.20,
                           "regime_bull_target": 0.85, "regime_bear_target": 0.50},
    }


DR_MODES = _build_modes()
if MODE not in DR_MODES:
    raise ValueError(f"unknown DR_MODE: {MODE}; valid: {list(DR_MODES)}")
P = DR_MODES[MODE]


class BtcDynamicRebalanceStrategy(IStrategy):
    INTERFACE_VERSION: int = 3
    timeframe: str = "1d"
    can_short: bool = False
    process_only_new_candles: bool = True

    # Never ROI-exit (C14b): empty table -> min_roi_reached() is always False.
    minimal_roi: dict = {}
    stoploss: float = -0.99
    use_custom_stoploss: bool = False

    position_adjustment_enable: bool = True
    max_entry_position_adjustment: int = 5000
    use_exit_signal: bool = True  # shield needs this on so it can force a bear-exit
    exit_profit_only: bool = False

    startup_candle_count: int = max(int(P["ema_long"]) + 20, 220)

    order_types = {
        "entry": "limit", "exit": "limit",
        "stoploss": "limit", "stoploss_on_exchange": False,
    }

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        df["rsi"] = ta.RSI(df, timeperiod=14)

        bb = ta.BBANDS(df, timeperiod=int(P["bb_period"]), nbdevup=P["bb_std"], nbdevdn=P["bb_std"])
        df["bb_upper"] = bb["upperband"]
        df["bb_middle"] = bb["middleband"]
        df["bb_lower"] = bb["lowerband"]

        df["atr"] = ta.ATR(df, timeperiod=int(P["atr_period"]))
        df["atr_avg"] = df["atr"].rolling(int(P["atr_avg_period"]), min_periods=1).mean()

        df["high_90d"] = df["high"].rolling(90, min_periods=1).max()
        df["dd_from_90d_high"] = (df["high_90d"] - df["close"]) / df["high_90d"]

        df["ema_short"] = ta.EMA(df, timeperiod=int(P["ema_short"]))
        df["ema_long"] = ta.EMA(df, timeperiod=int(P["ema_long"]))
        if WITH_SHIELD:
            df = shield_indicators(df)
        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        ready = df["ema_long"].notna()
        df.loc[ready, "enter_long"] = 1
        df.loc[ready, "enter_tag"] = f"dynrebal:{MODE.lower()}"
        if WITH_SHIELD:
            df = apply_shield(df, "entry")
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        if WITH_SHIELD:
            dataframe = apply_shield(dataframe, "exit")
        return dataframe

    def custom_stake_amount(
        self,
        pair: str, current_time: datetime, current_rate: float,
        proposed_stake: float, min_stake: Optional[float], max_stake: float,
        leverage: float, entry_tag: Optional[str], side: str, **kwargs,
    ) -> float:
        target = self._dynamic_target(pair)
        if max_stake and max_stake > 0:
            return float(max_stake) * target
        return float(proposed_stake)

    # ---- Dynamic target (only DR_REGIME uses it; others return base) ----- #

    def _dynamic_target(self, pair: str) -> float:
        if P["trigger_type"] not in ("regime_target", "regime_band"):
            return float(P["target_pct"])
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return float(P["target_pct"])
        last = df.iloc[-1]
        return regime_target(last["close"], last["ema_long"], P["regime_bull_target"], P["regime_bear_target"])

    # ---- The conditional triggers ---------------------------------------- #

    def _trigger_fires(self, last: pd.Series, profit_pct: float) -> bool:
        # profit_pct = portfolio move since the per-trade anchor (see module docstring)
        tt = P["trigger_type"]
        if tt == "profit_only":
            return abs(profit_pct) >= float(P["profit_trigger_pct"])
        if tt == "rsi_only":
            return last["rsi"] >= P["rsi_high"] or last["rsi"] <= P["rsi_low"]
        if tt == "bb_only":
            return last["close"] >= last["bb_upper"] or last["close"] <= last["bb_lower"]
        if tt == "vol_only":
            return last["atr"] >= last["atr_avg"] * float(P["atr_spike_mult"])
        if tt == "drawdown_only":
            return last["dd_from_90d_high"] >= float(P["dd_threshold"])
        if tt == "ema_trend":
            return True  # always rebalance toward target — direction set by relation to ema_short
        if tt == "rsi_and_profit":
            rsi_ext = last["rsi"] >= P["rsi_high"] or last["rsi"] <= P["rsi_low"]
            return rsi_ext and abs(profit_pct) >= float(P["profit_trigger_pct"])
        if tt == "rsi_or_bb":
            rsi_ext = last["rsi"] >= P["rsi_high"] or last["rsi"] <= P["rsi_low"]
            bb_touch = last["close"] >= last["bb_upper"] or last["close"] <= last["bb_lower"]
            return rsi_ext or bb_touch
        if tt == "regime_target":
            return True  # always rebalance toward (regime-dynamic) target
        return False

    # ---- DCA up/down via adjust_trade_position --------------------------- #

    def adjust_trade_position(
        self,
        trade: Trade, current_time: datetime, current_rate: float,
        current_profit: float, min_stake: Optional[float], max_stake: float,
        current_entry_rate: float, current_exit_rate: float,
        current_entry_profit: float, current_exit_profit: float, **kwargs,
    ) -> Optional[float]:
        # Cooldown: never stack a second order on an open one, and wait
        # COOLDOWN_MIN after the last fill (prevents back-to-back duplicates).
        filled = trade.select_filled_orders()
        last_fill = filled[-1] if filled else None
        if in_cooldown(trade.has_open_orders,
                       last_fill.order_filled_utc if last_fill else None,
                       current_time, COOLDOWN_MIN):
            return None

        df, _ = self.dp.get_analyzed_dataframe(pair=trade.pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return None
        last = df.iloc[-1]

        if WITH_SHIELD and not regime_allows_add(last):
            return None  # bear → don't add; exit_signal handles the close

        btc_qty = float(trade.amount or 0)
        btc_value = btc_qty * float(current_rate)
        usdt_free = float(self.wallets.get_free(trade.stake_currency) or 0.0)
        total = btc_value + usdt_free
        if total <= 0:
            return None

        # Effective target: regime mode tilts target by regime; otherwise static.
        if P["trigger_type"] in ("regime_target", "regime_band"):
            target = regime_target(last["close"], last["ema_long"], P["regime_bull_target"], P["regime_bear_target"])
        else:
            target = float(P["target_pct"])
        target_btc_value = target * total
        drift_usdt = btc_value - target_btc_value  # >0 → too much BTC

        # Portfolio move since the anchor. The anchor is re-set whenever a new
        # order has filled since it was taken (entry or rebalance fill), valued
        # at that fill's price — free stake is unchanged since that fill.
        profit_pct = 0.0
        if P["trigger_type"] in ("profit_only", "rsi_and_profit", "regime_band") and last_fill is not None:
            anchor = trade.get_custom_data(ANCHOR_KEY)
            if anchor is None or trade.get_custom_data(ANCHOR_NFILLS_KEY) != len(filled):
                anchor = anchor_value(btc_qty, last_fill.safe_price, usdt_free)
                trade.set_custom_data(ANCHOR_KEY, anchor)
                trade.set_custom_data(ANCHOR_NFILLS_KEY, len(filled))
            profit_pct = portfolio_move(float(anchor), total)

        if P["trigger_type"] == "regime_band":
            # A placed rebalance counts only once it filled (a cancelled order is retried).
            pending = custom_float(trade, PENDING_TARGET_KEY)
            if pending is not None and len(filled) > int(custom_float(trade, PENDING_NFILLS_KEY) or 0):
                trade.set_custom_data(APPLIED_TARGET_KEY, pending)
                trade.set_custom_data(PENDING_TARGET_KEY, NO_PENDING)
            applied = custom_float(trade, APPLIED_TARGET_KEY)
            if applied is None:  # first look at this trade: the entry was sized at the regime target
                applied = target
                trade.set_custom_data(APPLIED_TARGET_KEY, applied)
            if not regime_band_fires(applied, target, profit_pct, float(P["profit_trigger_pct"])):
                return None
            out = self._rebalance_order(trade, drift_usdt, btc_value, btc_qty, usdt_free,
                                        current_rate, min_stake, max_stake)
            if out is None:
                # Already at target within min_stake: the regime change is applied.
                trade.set_custom_data(APPLIED_TARGET_KEY, target)
            else:
                trade.set_custom_data(PENDING_TARGET_KEY, target)
                trade.set_custom_data(PENDING_NFILLS_KEY, len(filled))
            return out

        if not self._trigger_fires(last, profit_pct):
            return None

        # ema_trend mode: direction follows regime of price vs ema_short.
        if P["trigger_type"] == "ema_trend":
            if last["close"] > last["ema_short"]:
                # uptrend → trim
                if drift_usdt <= 0:
                    return None
            else:
                if drift_usdt >= 0:
                    return None

        return self._rebalance_order(trade, drift_usdt, btc_value, btc_qty, usdt_free,
                                     current_rate, min_stake, max_stake)

    def _rebalance_order(self, trade: Trade, drift_usdt: float, btc_value: float, btc_qty: float,
                         usdt_free: float, current_rate: float, min_stake: Optional[float],
                         max_stake: float) -> Optional[float]:
        """adjust_trade_position return that moves the position back to target."""
        rebalance_usdt = drift_usdt * float(P["rebalance_fraction"])
        if rebalance_usdt > 0:
            sell_usdt = min(rebalance_usdt, btc_value * 0.99)
            if min_stake and sell_usdt < min_stake:
                return None
            # sell_usdt is a MARKET value; freqtrade expects a cost-basis stake
            # for partial exits (see partial_exit_stake / module docstring).
            stake = partial_exit_stake(sell_usdt, float(current_rate), btc_qty,
                                       float(trade.stake_amount or 0.0))
            return -stake if stake > 0 else None
        else:
            buy_usdt = min(-rebalance_usdt, usdt_free * 0.99)
            if max_stake and max_stake > 0:
                buy_usdt = min(buy_usdt, max_stake)
            if min_stake and buy_usdt < min_stake:
                return None
            return float(buy_usdt) if buy_usdt > 0 else None


__all__ = ["BtcDynamicRebalanceStrategy", "DR_MODES"]
