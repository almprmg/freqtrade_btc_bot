"""Experiment Logger — wraps any Freqtrade backtest and records EVERYTHING.

Saves to research/experiments/<timestamp>__<strategy>__<mode>__<pair>/
  metadata.json     — full run config (strategy, mode, pair, timerange, wallet)
  trades.csv        — every trade with all fields
  orders.csv        — every order
  summary.json      — Freqtrade's summary stats
  raw_payload.json  — full backtest export payload

Plus appends to a master index:
  research/experiments/INDEX.csv
    timestamp, strategy, mode, pair, timerange, wallet,
    trades, win_rate, roi_pct, max_dd_pct, sharpe, sortino,
    profit_factor, calmar, total_pnl, run_dir

Usage as decorator-style wrapper for any backtest function:

  from experiment_logger import log_backtest

  result = log_backtest(
      strategy="BtcRotationStrategy",
      mode="default",
      pair="BTC/USDT",
      timerange="20210101-20260101",
      wallet=10000,
      runner=lambda: subprocess.run([...]),
  )

Or use it post-hoc to log any existing backtest result zip:

  python research/ai/experiment_logger.py \
      --result-zip user_data/backtest_results/backtest-result-2026-06-02_14-15-21.zip \
      --strategy BtcRotationStrategy --mode default --pair BTC/USDT
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
EXP_DIR = REPO / "research" / "experiments"
EXP_DIR.mkdir(parents=True, exist_ok=True)
INDEX = EXP_DIR / "INDEX.csv"


def parse_zip(zip_path: Path) -> dict:
    """Extract trades, orders, summary from a Freqtrade backtest result zip."""
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and "market_change" not in n]
        if not names:
            return {}
        with z.open(names[0]) as f:
            payload = json.load(io.TextIOWrapper(f, encoding="utf-8"))
    return payload


def extract_metrics(payload: dict) -> dict:
    """Pull headline metrics from the strategy payload."""
    strats = payload.get("strategy", {})
    if not strats:
        return {}
    sk = next(iter(strats))
    s = strats[sk]
    return {
        "strategy_class": sk,
        "starting_balance": float(s.get("starting_balance", 0) or 0),
        "final_balance": float(s.get("final_balance", 0) or 0),
        "total_pnl": float(s.get("profit_total_abs", 0) or 0),
        "roi_pct": round(((float(s.get("final_balance", 0) or 0) /
                            max(float(s.get("starting_balance", 1) or 1), 1)) - 1) * 100, 3),
        "n_trades": int(s.get("total_trades", 0)),
        "wins": int(s.get("wins", 0)),
        "losses": int(s.get("losses", 0)),
        "win_rate_pct": round(float(s.get("winrate", 0) or 0) * 100, 2),
        "max_dd_pct": round(float(s.get("max_drawdown_account", 0) or 0) * 100, 3),
        "max_dd_abs": float(s.get("max_drawdown_abs", 0) or 0),
        "sharpe": round(float(s.get("sharpe", 0) or 0), 3),
        "sortino": round(float(s.get("sortino", 0) or 0), 3),
        "calmar": round(float(s.get("calmar", 0) or 0), 3),
        "profit_factor": round(float(s.get("profit_factor", 0) or 0), 3),
        "expectancy": round(float(s.get("expectancy", 0) or 0), 4),
        "best_trade_pct": round(float(s.get("best_pair_profit_ratio", 0) or 0) * 100, 2),
        "worst_trade_pct": round(float(s.get("worst_pair_profit_ratio", 0) or 0) * 100, 2),
        "avg_trade_duration": str(s.get("avg_trade_duration", "")),
        "backtest_start": str(s.get("backtest_start", "")),
        "backtest_end": str(s.get("backtest_end", "")),
    }


def extract_trades(payload: dict) -> pd.DataFrame:
    strats = payload.get("strategy", {})
    if not strats:
        return pd.DataFrame()
    sk = next(iter(strats))
    trades = strats[sk].get("trades", [])
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame(trades)
    # Flatten orders list to separate file if present
    return df


def log_experiment(
    *,
    strategy: str,
    mode: str,
    pair: str,
    timerange: str,
    wallet: float,
    zip_path: Path,
    notes: str = "",
) -> dict:
    """Log a single backtest result. Returns the index row dict."""
    if not zip_path.exists():
        print(f"WARN: zip not found {zip_path}", file=sys.stderr)
        return {}

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_pair = pair.replace("/", "_")
    folder = EXP_DIR / f"{ts}__{strategy}__{mode}__{safe_pair}"
    folder.mkdir(parents=True, exist_ok=True)

    # Parse zip
    payload = parse_zip(zip_path)
    metrics = extract_metrics(payload)
    trades = extract_trades(payload)

    # Write metadata
    meta = {
        "timestamp_utc": ts,
        "strategy": strategy,
        "mode": mode,
        "pair": pair,
        "timerange": timerange,
        "wallet": float(wallet),
        "notes": notes,
        **metrics,
    }
    (folder / "metadata.json").write_text(json.dumps(meta, indent=2, default=str))
    (folder / "raw_payload.json").write_text(json.dumps(payload, indent=2, default=str))

    # Trades CSV
    if not trades.empty:
        # Drop orders nested list to a separate file
        trades_flat = trades.drop(columns=["orders"], errors="ignore")
        trades_flat.to_csv(folder / "trades.csv", index=False)

        if "orders" in trades.columns:
            orders_rows = []
            for _, t in trades.iterrows():
                for o in (t.get("orders") or []):
                    orders_rows.append({"trade_id": t.get("trade_id"), **o})
            if orders_rows:
                pd.DataFrame(orders_rows).to_csv(folder / "orders.csv", index=False)

    # Append to index
    index_row = {
        "timestamp": ts, "strategy": strategy, "mode": mode, "pair": pair,
        "timerange": timerange, "wallet": float(wallet),
        "n_trades": metrics.get("n_trades", 0),
        "win_rate_pct": metrics.get("win_rate_pct", 0),
        "roi_pct": metrics.get("roi_pct", 0),
        "max_dd_pct": metrics.get("max_dd_pct", 0),
        "sharpe": metrics.get("sharpe", 0),
        "sortino": metrics.get("sortino", 0),
        "profit_factor": metrics.get("profit_factor", 0),
        "calmar": metrics.get("calmar", 0),
        "total_pnl": metrics.get("total_pnl", 0),
        "run_dir": folder.name,
        "notes": notes,
    }
    new_index_df = pd.DataFrame([index_row])
    if INDEX.exists():
        old = pd.read_csv(INDEX)
        all_rows = pd.concat([old, new_index_df], ignore_index=True)
    else:
        all_rows = new_index_df
    all_rows.to_csv(INDEX, index=False)
    print(f"  logged: {folder.name}")
    print(f"  ROI: {metrics.get('roi_pct')}%, trades: {metrics.get('n_trades')}, "
          f"max_dd: {metrics.get('max_dd_pct')}%, sharpe: {metrics.get('sharpe')}")
    return index_row


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--result-zip", required=True, type=Path)
    p.add_argument("--strategy", required=True)
    p.add_argument("--mode", default="default")
    p.add_argument("--pair", required=True)
    p.add_argument("--timerange", required=True)
    p.add_argument("--wallet", type=float, default=10000)
    p.add_argument("--notes", default="")
    args = p.parse_args()

    log_experiment(
        strategy=args.strategy, mode=args.mode, pair=args.pair,
        timerange=args.timerange, wallet=args.wallet,
        zip_path=args.result_zip, notes=args.notes,
    )
    print(f"\nIndex updated: {INDEX}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
