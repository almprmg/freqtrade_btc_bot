"""BTC/USDT 4h regime-aware bot for Freqtrade (Binance Spot only).

How it works
============
1. On every closed 4h candle, `RegimeDetector` classifies the market as one
   of TRENDING / RANGING / NEUTRAL using ADX + ATR (with a 3-bar whipsaw
   guard). The strategy then picks the matching playbook:

       TRENDING → Trend Pullback     (entry inside a healthy retracement)
       RANGING  → Mean Reversion     (oversold bounce off the lower band)
       NEUTRAL  → no new entries (existing positions still exit on their rules)

2. Multi-timeframe context: 1h (RSI confirmation) and 1d (EMA200 trend filter)
   are merged into the 4h dataframe via Freqtrade's `merge_informative_pair`.

3. Cost discipline: every entry is gated on the expected move (live ATR%)
   clearing the 0.20% round-trip cost (commission + slippage) plus 0.05%
   margin. All orders are LIMIT (Maker rebate). `custom_entry_price` /
   `custom_exit_price` shave a small offset from `proposed_rate` so the
   LIMIT sits inside the book (postOnly-style; Binance Spot has no GTX so
   we approximate by pricing below the ask on entry, above the bid on exit).

4. Position sizing per-tag:
       mean_reversion  → 15% of total wallet (smaller, more frequent)
       trend_pullback  → 20% of total wallet (larger, less frequent)

5. Custom exits per strategy + custom_stoploss for trend-pullback's trailing
   stop (initial -4%, tightens to entry+1% after +3% in profit).

6. Risk caps via Freqtrade protections:
       MaxDrawdown 5%  / lookback 1 day   → daily kill-switch
       MaxDrawdown 15% / lookback 30 days → monthly kill-switch
   plus a per-pair cooldown after losing trades.

Why a single strategy class instead of two:
    Freqtrade routes by `strategy` config, not per-tag. Keeping both
    playbooks in one class lets the regime decide AT signal time and
    Freqtrade's per-trade `enter_tag` carries it through to exits and
    custom_stake_amount. The tag is the source of truth — neither side
    needs to know about the other once a trade is open.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import (
    DecimalParameter,
    IStrategy,
    IntParameter,
    merge_informative_pair,
)

# Freqtrade loads strategy files by file path (not as a package), so relative
# imports like `from .regime_detector` raise
# "attempted relative import with no known parent package". The bare import
# below works in that context (Freqtrade puts user_data/strategies/ on
# sys.path). pytest doesn't, so we fall back to the package path — both
# branches MUST resolve to the SAME module so `isinstance` checks hold.
try:
    from regime_detector import RegimeDetector  # noqa: I001
except ImportError:  # pragma: no cover — exercised under pytest
    from user_data.strategies.regime_detector import RegimeDetector

logger = logging.getLogger(__name__)


class BtcRegimeStrategy(IStrategy):
    """Regime-aware BTC/USDT 4h bot (Spot, long-only)."""

    # ------------------------------------------------------------------ #
    # Freqtrade contract                                                 #
    # ------------------------------------------------------------------ #
    INTERFACE_VERSION: int = 3

    # 1h primary (was 4h — reduced to get more signal opportunities; the
    # spec's combined-filter requirements yielded only 8 trades over 3.5y on
    # 4h). 1d EMA200 still merged as macro filter; the 1h "informative" is
    # now degenerate with the primary so we skip it.
    timeframe: str = "1h"

    # Long-only spot bot.
    can_short: bool = False

    # ROI table disabled — exits are signal/stoploss-driven, not time-based.
    # An effectively-infinite ROI keeps the framework from short-circuiting
    # our custom exits. Setting a single 1000% entry is the idiomatic
    # "disable ROI" pattern in Freqtrade.
    minimal_roi: dict[str, float] = {"0": 10.0}

    # Per-trade absolute floor. The real stops are per-strategy via
    # `custom_stoploss` (MR: -3% fixed; Trend: trailing). This value is the
    # outer safety net Freqtrade enforces unconditionally.
    stoploss: float = -0.08

    # CRITICAL: enable custom_stoploss(). Without this Freqtrade ignores
    # the per-strategy MR -3% and Trend trailing rules and only honours
    # the `stoploss` float above.
    use_custom_stoploss: bool = True

    # We compute on closed candles only — no intra-bar signal flapping.
    process_only_new_candles: bool = True
    use_exit_signal: bool = True
    exit_profit_only: bool = False
    ignore_roi_if_entry_signal: bool = False

    # Order plumbing. All entries/exits as LIMIT — Maker rebate. Emergency
    # exits stay MARKET so we can bail through any book quickly.
    order_types: dict[str, str | bool] = {
        "entry": "limit",
        "exit": "limit",
        "emergency_exit": "market",
        "force_entry": "market",
        "force_exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force: dict[str, str] = {"entry": "GTC", "exit": "GTC"}

    # Startup history: 200 daily candles for EMA200_1d → 200 × 24 = 4800
    # hourly candles. Capped at 4900 (just under Freqtrade's 5×999 limit on
    # Binance 1h). 4h EMAs (~ 200 × 4 = 800 hours) easily fit inside.
    startup_candle_count: int = 4900

    # ------------------------------------------------------------------ #
    # Cost / size constants (mirror the spec)                            #
    # ------------------------------------------------------------------ #
    # 0.075% per side (BNB-discounted Spot) × 2 + 0.05% slippage = 0.20%.
    ROUND_TRIP_COST_PCT: float = 0.20
    MIN_EXPECTED_MOVE_PCT: float = 0.25  # 0.20% costs + 0.05% margin.
    MIN_STAKE_USDT: float = 10.0          # stricter than Binance's 5 USDT.

    # Per-strategy wallet share (computed in `custom_stake_amount`).
    MEAN_REVERSION_STAKE_RATIO: float = 0.15
    TREND_PULLBACK_STAKE_RATIO: float = 0.20

    # Maker offset for LIMIT pricing (0.05% inside the book).
    MAKER_OFFSET_PCT: float = 0.0005

    # ------------------------------------------------------------------ #
    # Hyperopt parameters (kept conservative — overridable for tuning)   #
    # ------------------------------------------------------------------ #
    mr_rsi_oversold = IntParameter(20, 35, default=30, space="buy", optimize=False)
    mr_stoch_oversold = IntParameter(15, 30, default=25, space="buy", optimize=False)
    mr_rsi_overbought = IntParameter(60, 75, default=65, space="sell", optimize=False)
    trend_rsi_min = IntParameter(30, 40, default=35, space="buy", optimize=False)
    trend_rsi_max = IntParameter(50, 60, default=55, space="buy", optimize=False)
    mr_bb_band_tolerance_pct = DecimalParameter(0.0, 1.0, default=0.5, space="buy", optimize=False)
    mr_stoploss = DecimalParameter(-0.05, -0.02, default=-0.03, space="sell", optimize=False)

    # ------------------------------------------------------------------ #
    # Construct regime detector once (Freqtrade instantiates strategy   #
    # once per process, so this is fine).                                #
    # ------------------------------------------------------------------ #
    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.regime = RegimeDetector(
            adx_period=14,
            atr_period=14,
            atr_avg_period=20,
            adx_trending_threshold=25.0,
            adx_ranging_threshold=20.0,
            atr_range_multiplier=1.1,
            confirm_bars=3,
        )
        # Cache the last logged regime per pair so we only emit a Telegram
        # notification on actual flips (Freqtrade dispatches Telegram from
        # populate_indicators logging via custom_info → see send_msg).
        self._last_regime_logged: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # MTF declaration                                                    #
    # ------------------------------------------------------------------ #
    def informative_pairs(self) -> list[tuple[str, str]]:
        """Add the 1d feed for every pair we trade (macro trend filter).
        Primary is now 1h; the spec's 1h RSI confirmation degenerates to the
        primary-frame RSI, so we skip the 1h informative."""
        pairs = self.dp.current_whitelist()
        return [(p, "1d") for p in pairs]

    # ------------------------------------------------------------------ #
    # Indicators                                                         #
    # ------------------------------------------------------------------ #
    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """Compute everything both strategies need on the 4h dataframe."""
        pair: str = metadata["pair"]

        # ---- 4h indicators (this dataframe) ---------------------------- #
        # Bollinger Bands for mean-reversion.
        bb_period = 20
        bb_std = 2
        sma = dataframe["close"].rolling(bb_period).mean()
        rolling_std = dataframe["close"].rolling(bb_period).std(ddof=0)
        dataframe["bb_middle"] = sma
        dataframe["bb_lower"] = sma - rolling_std * bb_std
        dataframe["bb_upper"] = sma + rolling_std * bb_std

        # Momentum / oscillators.
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        stoch = ta.STOCH(dataframe, fastk_period=14, slowk_period=3, slowd_period=3)
        dataframe["stoch_k"] = stoch["slowk"]

        # EMA stack for trend pullback.
        dataframe["ema21"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)

        # MACD (12/26/9) — used for trend zugzwang / exit.
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd["macd"]
        dataframe["macd_signal"] = macd["macdsignal"]
        dataframe["macd_hist"] = macd["macdhist"]

        # Volume sanity — only enter when liquidity is at least ~80% of normal.
        dataframe["volume_sma"] = dataframe["volume"].rolling(20).mean()
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_sma"]

        # Regime detector (writes adx, atr, atr_avg, regime_raw,
        # regime_confirmed).
        dataframe = self.regime.annotate(dataframe)

        # Expected-move filter: ATR as a percentage of price. Used by both
        # entries to refuse trades where the typical move can't even cover
        # the 0.20% round-trip cost + a 0.05% margin.
        dataframe["expected_move_pct"] = (dataframe["atr"] / dataframe["close"]) * 100.0

        # ---- 1h "informative" RSI — degenerate with primary on 1h tf --- #
        # Primary is 1h now, so the spec's "RSI on 1h timeframe" filter is
        # just the primary-frame RSI under a different name. Alias it.
        dataframe["rsi_1h"] = dataframe["rsi"]

        # ---- 1d informative: EMA200 for the macro trend filter --------- #
        df_1d = self.dp.get_pair_dataframe(pair=pair, timeframe="1d")
        if not df_1d.empty:
            df_1d = df_1d.copy()
            df_1d["ema200"] = ta.EMA(df_1d, timeperiod=200)
            dataframe = merge_informative_pair(
                dataframe, df_1d, self.timeframe, "1d", ffill=True
            )
        else:
            dataframe["ema200_1d"] = np.nan

        # Notify on regime change (Telegram via Freqtrade's send_msg).
        self._maybe_notify_regime_change(pair, dataframe)
        return dataframe

    # ------------------------------------------------------------------ #
    # Entries                                                            #
    # ------------------------------------------------------------------ #
    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """Compute entry signals for both strategies; tag each with which one fired.

        Only one path can fire per bar (TRENDING vs RANGING are mutually
        exclusive after the whipsaw guard), so there's no ambiguity for
        `enter_tag`.
        """
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = ""

        # ---- shared cost + safety filter ------------------------------- #
        cost_ok = dataframe["expected_move_pct"] > self.MIN_EXPECTED_MOVE_PCT
        # Refuse warm-up rows: EMA200_1d / rsi_1h NaN means MTF data missing.
        mtf_ready = dataframe["ema200_1d"].notna() & dataframe["rsi_1h"].notna()
        volume_ok = dataframe["volume_ratio"] >= 0.8  # MR's 80% floor

        # ---- mean-reversion (RANGING regime) --------------------------- #
        # RSI oversold for TWO bars in a row (not a single-bar wick).
        rsi_oversold_now = dataframe["rsi"] < self.mr_rsi_oversold.value
        rsi_oversold_prev = dataframe["rsi"].shift(1) < self.mr_rsi_oversold.value
        # Price at or below the lower band (with a small leniency band).
        tol = self.mr_bb_band_tolerance_pct.value / 100.0
        at_lower_band = dataframe["close"] <= dataframe["bb_lower"] * (1 + tol)
        # Bullish current candle (buyers stepping in).
        bullish_candle = dataframe["close"] > dataframe["open"]
        # Macro filter — don't catch a falling knife.
        above_macro = dataframe["close"] > dataframe["ema200_1d"]

        mean_rev_entry = (
            (dataframe["regime_confirmed"] == RegimeDetector.RANGING)
            & rsi_oversold_now
            & rsi_oversold_prev
            & (dataframe["stoch_k"] < self.mr_stoch_oversold.value)
            & at_lower_band
            & bullish_candle
            & above_macro
            & volume_ok
            & cost_ok
            & mtf_ready
        )
        dataframe.loc[mean_rev_entry, "enter_long"] = 1
        dataframe.loc[mean_rev_entry, "enter_tag"] = "mean_reversion"

        # ---- trend pullback (TRENDING regime) -------------------------- #
        # Macro + meso trend filters.
        macro_uptrend = dataframe["close"] > dataframe["ema200_1d"]
        meso_uptrend = dataframe["ema50"] > dataframe["ema200"]
        # In the pullback zone: above EMA21 by ≤0.5%, below EMA50 by ≤1%.
        # The "above EMA21" band lets the price hold the fast MA as support
        # without being overextended toward EMA50.
        in_pullback = (
            (dataframe["close"] >= dataframe["ema21"] * 0.995)
            & (dataframe["close"] <= dataframe["ema50"] * 1.01)
        )
        # RSI on 4h in the healthy-retracement band (not oversold, not OB).
        rsi_in_band = (
            (dataframe["rsi"] >= self.trend_rsi_min.value)
            & (dataframe["rsi"] <= self.trend_rsi_max.value)
        )
        bullish_candle_t = dataframe["close"] > dataframe["open"]
        # MACD histogram positive AND rising (momentum returning).
        macd_hist_positive = dataframe["macd_hist"] > 0
        macd_hist_rising = dataframe["macd_hist"] > dataframe["macd_hist"].shift(1)
        # 1h RSI > 45 (confirmation from the lower timeframe).
        rsi_1h_ok = dataframe["rsi_1h"] > 45
        # Volume ratio > 1.0 (stricter than MR — trending entries need
        # participation).
        volume_strong = dataframe["volume_ratio"] > 1.0

        trend_entry = (
            (dataframe["regime_confirmed"] == RegimeDetector.TRENDING)
            & macro_uptrend
            & meso_uptrend
            & in_pullback
            & rsi_in_band
            & bullish_candle_t
            & macd_hist_positive
            & macd_hist_rising
            & rsi_1h_ok
            & volume_strong
            & cost_ok
            & mtf_ready
        )
        # Trend path wins if both fire on the same bar (regimes are exclusive
        # after the whipsaw guard, so this is a defence-in-depth — never
        # observed in practice).
        dataframe.loc[trend_entry, "enter_long"] = 1
        dataframe.loc[trend_entry, "enter_tag"] = "trend_pullback"
        return dataframe

    # ------------------------------------------------------------------ #
    # Exits                                                              #
    # ------------------------------------------------------------------ #
    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """Signal-based exits. The `enter_tag` recorded at entry decides
        which exit rule applies — branches are mutually exclusive.

        Hard stop-losses (MR -3%, Trend trailing) live in `custom_stoploss`
        so they have access to the live trade object and can use the entry
        timestamp / fill price.
        """
        dataframe["exit_long"] = 0
        dataframe["exit_tag"] = ""

        # NOTE: populate_exit_trend can't see the trade's enter_tag directly
        # (it's per-bar, not per-trade). We mark BOTH exit conditions on
        # the dataframe; the per-trade decision happens in `custom_exit`,
        # which has the Trade object and can branch on `trade.enter_tag`.
        # Here we just flag generic candidates so the dataframe carries the
        # signals; custom_exit picks the right one.

        # ---- mean-reversion candidate exits ---------------------------- #
        # A: back to BB middle, B: RSI overbought, C: regime flipped.
        mr_bb_middle = dataframe["close"] >= dataframe["bb_middle"]
        mr_rsi_ob = dataframe["rsi"] > self.mr_rsi_overbought.value
        mr_regime_changed = dataframe["regime_confirmed"] != RegimeDetector.RANGING

        # ---- trend-pullback candidate exits ---------------------------- #
        # A: MACD hist negative, B: price < EMA50 * 0.99, C: regime flipped.
        trend_macd_neg = dataframe["macd_hist"] < 0
        trend_below_ema50 = dataframe["close"] < dataframe["ema50"] * 0.99
        trend_regime_changed = dataframe["regime_confirmed"] != RegimeDetector.TRENDING

        # Boolean columns custom_exit will read.
        dataframe["mr_exit_bb"] = mr_bb_middle
        dataframe["mr_exit_rsi"] = mr_rsi_ob
        dataframe["mr_exit_regime"] = mr_regime_changed
        dataframe["trend_exit_macd"] = trend_macd_neg
        dataframe["trend_exit_ema50"] = trend_below_ema50
        dataframe["trend_exit_regime"] = trend_regime_changed
        return dataframe

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> Optional[str]:
        """Per-trade exit decision — branches on `trade.enter_tag` and
        returns a tag string when an exit condition is met (or None to hold).
        """
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        if df is None or df.empty:
            return None
        last = df.iloc[-1]

        if trade.enter_tag == "mean_reversion":
            if bool(last.get("mr_exit_bb")):
                return "mr_bb_middle"
            if bool(last.get("mr_exit_rsi")):
                return "mr_rsi_overbought"
            if bool(last.get("mr_exit_regime")):
                return "mr_regime_change"
            return None

        if trade.enter_tag == "trend_pullback":
            if bool(last.get("trend_exit_macd")):
                return "trend_macd_negative"
            if bool(last.get("trend_exit_ema50")):
                return "trend_below_ema50"
            if bool(last.get("trend_exit_regime")):
                return "trend_regime_change"
            return None
        return None

    # ------------------------------------------------------------------ #
    # Custom stoploss (per-strategy)                                     #
    # ------------------------------------------------------------------ #
    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        """Branch by entry tag.

          * mean_reversion → fixed -3% from entry.
          * trend_pullback → initial -4%; once +3% in profit, ratchet to
            +1% above entry (lock at least +1% — minus fees ≈ +0.8% net).
        """
        if trade.enter_tag == "mean_reversion":
            # Negative float = max loss from entry, in Freqtrade convention.
            return float(self.mr_stoploss.value)  # default -0.03

        if trade.enter_tag == "trend_pullback":
            if current_profit > 0.03:
                # Lock in: stop sits +1% above entry (so current_profit must
                # not drop below +0.01).
                return -(current_profit - 0.01)
            return -0.04

        # Unknown tag — fall back to the framework absolute floor.
        return self.stoploss

    # ------------------------------------------------------------------ #
    # Position sizing                                                    #
    # ------------------------------------------------------------------ #
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
        """Per-strategy wallet share + enforce the 10 USDT floor."""
        total_wallet = self.wallets.get_total_stake_amount() if self.wallets else 0.0
        if total_wallet <= 0:
            # Wallet API unavailable (e.g. early backtest tick) — let
            # Freqtrade fall through to its default sizing.
            return proposed_stake

        if entry_tag == "mean_reversion":
            target = total_wallet * self.MEAN_REVERSION_STAKE_RATIO
        elif entry_tag == "trend_pullback":
            target = total_wallet * self.TREND_PULLBACK_STAKE_RATIO
        else:
            target = proposed_stake

        # Clamp to Freqtrade's reported min/max and the strategy floor.
        target = max(target, self.MIN_STAKE_USDT)
        if min_stake is not None:
            target = max(target, min_stake)
        target = min(target, max_stake)
        return float(target)

    # ------------------------------------------------------------------ #
    # Custom entry / exit pricing (Maker-only LIMIT)                    #
    # ------------------------------------------------------------------ #
    def custom_entry_price(
        self,
        pair: str,
        trade: Optional[Trade],
        current_time: datetime,
        proposed_rate: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> float:
        """Place BUY LIMIT slightly BELOW the proposed rate so it rests
        inside the book (Maker)."""
        return float(proposed_rate * (1.0 - self.MAKER_OFFSET_PCT))

    def custom_exit_price(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        proposed_rate: float,
        current_profit: float,
        exit_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> float:
        """Place SELL LIMIT slightly ABOVE the proposed rate (Maker)."""
        return float(proposed_rate * (1.0 + self.MAKER_OFFSET_PCT))

    # ------------------------------------------------------------------ #
    # Protections (daily / monthly drawdown kill-switches + cooldown)    #
    # ------------------------------------------------------------------ #
    @property
    def protections(self) -> list[dict]:
        return [
            # Daily 5% drawdown kill-switch.
            {
                "method": "MaxDrawdown",
                "lookback_period": 1440,        # minutes (1 day)
                "trade_limit": 1,
                "stop_duration": 1440,          # halt for the rest of the day
                "max_allowed_drawdown": 0.05,
            },
            # Monthly 15% drawdown kill-switch.
            {
                "method": "MaxDrawdown",
                "lookback_period": 43200,       # minutes (30 days)
                "trade_limit": 1,
                "stop_duration": 43200,         # halt for the next 30 days
                "max_allowed_drawdown": 0.15,
            },
            # Cooldown after any losing trade (avoid revenge sizing).
            {
                "method": "CooldownPeriod",
                "stop_duration_candles": 2,     # 2 × 4h = 8h cool-off
            },
        ]

    # ------------------------------------------------------------------ #
    # Telegram-friendly regime-change notice                             #
    # ------------------------------------------------------------------ #
    def _maybe_notify_regime_change(self, pair: str, dataframe: pd.DataFrame) -> None:
        """Emit a Telegram message when `regime_confirmed` flips.

        Freqtrade's `send_msg` routes to all enabled notifiers (Telegram,
        WebHook, etc.). We deduplicate by tracking the last-seen regime per
        pair so re-runs of populate_indicators on the same bar don't spam.
        """
        if dataframe.empty:
            return
        latest = dataframe["regime_confirmed"].iat[-1]
        if not isinstance(latest, str) or not latest:
            return
        prev = self._last_regime_logged.get(pair)
        if latest == prev:
            return
        self._last_regime_logged[pair] = latest
        if prev is None:
            return  # first sighting; not a "flip"
        msg = f"📊 Regime change on {pair}: {prev} → {latest}"
        logger.info(msg)
        # dp.send_msg is the Freqtrade-supported notification hook.
        try:
            self.dp.send_msg(msg)
        except Exception as exc:  # pragma: no cover — best-effort UI hook
            logger.warning("send_msg failed: %s", exc)
