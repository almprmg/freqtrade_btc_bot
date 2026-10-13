"""Shared partial-exit sizing for strategies that trim via adjust_trade_position.

freqtrade (2026.4: freqtradebot.process_open_trade_positions and
optimize/backtesting._get_adjust_trade_entry_for_candle) converts a NEGATIVE
adjust_trade_position return into a coin amount against the COST BASIS:

    amount = |stake| * trade.amount / trade.stake_amount

Returning the market-value overweight therefore over-sells every position that
is in profit (C14b: 1 coin bought @100, price 200 -> returning -50 sells 0.5
coin = $100, not $50). Every strategy must convert its desired market-value
sell through `exit_stake()` / `partial_exit_stake()`.

Import pattern (same as _regime_shield):
    try:
        from _position_sizing import exit_stake
    except ImportError:  # pragma: no cover
        from user_data.strategies._position_sizing import exit_stake

This module defines no IStrategy, so freqtrade's StrategyResolver ignores it.
"""
from __future__ import annotations

from typing import Any, Optional


def partial_exit_stake(sell_value: float, current_rate: float,
                       trade_amount: float, trade_stake_amount: float) -> float:
    """Stake to return (as a positive number; caller negates) so that freqtrade
    sells `sell_value` worth of coin at `current_rate`.

    We want amount = sell_value / current_rate, hence
    stake = (sell_value / current_rate) / trade.amount * trade.stake_amount.
    Capped at the whole position (fraction 1.0); 0.0 on degenerate inputs.
    """
    if current_rate <= 0 or trade_amount <= 0 or trade_stake_amount <= 0 or sell_value <= 0:
        return 0.0
    fraction = min(float(sell_value) / float(current_rate) / float(trade_amount), 1.0)
    return fraction * float(trade_stake_amount)


def freqtrade_exit_amount(stake: float, trade_amount: float, trade_stake_amount: float) -> float:
    """Mirror of freqtrade 2026.4's negative-stake -> amount conversion (no precision rounding)."""
    return abs(float(stake)) * float(trade_amount) / float(trade_stake_amount)


def exit_stake(trade: Any, sell_value: float, current_rate: float) -> Optional[float]:
    """Negative adjust_trade_position return that sells `sell_value` (market
    value, stake currency) of `trade` at `current_rate`; None if nothing to sell."""
    stake = partial_exit_stake(sell_value, float(current_rate),
                               float(trade.amount or 0.0), float(trade.stake_amount or 0.0))
    return -stake if stake > 0 else None


__all__ = ["partial_exit_stake", "freqtrade_exit_amount", "exit_stake"]
