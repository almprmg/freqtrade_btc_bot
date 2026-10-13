"""Per-coin selection of the Isolation-Forest anomaly flags.

The flags feathers (anomaly_flags.feather / anomaly_flags_wf.feather) hold one
row per (date, coin). A strategy must use the flags of the coin it trades,
derived from metadata["pair"] (base asset), not a hard-coded "BTC".

Coins without their own flags in the file (e.g. XRP today) fall back to BTC's
flags as a market-wide proxy — the behaviour those bots were validated with —
and a warning is logged once per coin so the gap is visible.

Import pattern (same as _regime_shield):
    try:
        from _anomaly_flags import coin_anomaly_flags
    except ImportError:  # pragma: no cover
        from user_data.strategies._anomaly_flags import coin_anomaly_flags
"""
from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

FALLBACK_COIN = "BTC"
_warned: set[str] = set()


def base_coin(pair: str) -> str:
    """'ETH/USDT' -> 'ETH', 'ETH/USDT:USDT' -> 'ETH'."""
    return str(pair).split("/")[0].split(":")[0].upper()


def coin_anomaly_flags(anomaly: pd.DataFrame, pair: str) -> pd.Series:
    """Date-indexed is_anomaly series for the pair's base coin (see module doc)."""
    if anomaly is None or anomaly.empty or "is_anomaly" not in anomaly.columns:
        return pd.Series(dtype=float)
    if "coin" not in anomaly.columns:
        return anomaly["is_anomaly"]
    coin = base_coin(pair)
    sel = anomaly[anomaly["coin"] == coin]
    if sel.empty and coin != FALLBACK_COIN:
        if coin not in _warned:
            _warned.add(coin)
            logger.warning("No anomaly flags for %s; using %s flags as a market proxy.",
                           coin, FALLBACK_COIN)
        sel = anomaly[anomaly["coin"] == FALLBACK_COIN]
    return sel["is_anomaly"]


__all__ = ["base_coin", "coin_anomaly_flags", "FALLBACK_COIN"]
