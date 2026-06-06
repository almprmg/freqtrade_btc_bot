"""macro_sweep.py — hyperparameter sweep for BtcMacroV2Strategy.

Runs 200+ configurations on the full 9-year BTC backtest and ranks by
compound return + max drawdown.

For each combo:
  1. Set env vars
  2. Run a single 9-year backtest (faster than per-year for sweep)
  3. Collect ROI, max_dd, trades, win_rate
  4. Rank by score = compound * (1 - max_dd_pct/100)

Usage:
  python -m research.ai.macro_sweep        # run sweep (slow ~30 min)
  python -m research.ai.macro_sweep top    # show top 10 from saved results
"""
from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
RESULTS_CSV = REPO / "research" / "macro_sweep_results.csv"
CONFIG_PATH = REPO / "config.macro.json"


def make_config():
    """Create a minimal config for sweep — uses BtcMacroV2Strategy."""
    cfg_path = REPO / "config.macrov2.json"
    cfg = {
        "max_open_trades": 1, "stake_currency": "USDT", "stake_amount": "unlimited",
        "tradable_balance_ratio": 1.0, "fiat_display_currency": "USD",
        "timeframe": "1d", "dry_run": True, "dry_run_wallet": 10000,
        "cancel_open_orders_on_exit": False, "trading_mode": "spot", "margin_mode": "",
        "unfilledtimeout": {"entry": 10, "exit": 10, "exit_timeout_count": 0, "unit": "minutes"},
        "entry_pricing": {"price_side": "same", "use_order_book": False, "order_book_top": 1, "price_last_balance": 0.0, "check_depth_of_market": {"enabled": False}},
        "exit_pricing": {"price_side": "same", "use_order_book": False, "order_book_top": 1},
        "exchange": {"name": "binance", "key": "", "secret": "", "ccxt_config": {}, "ccxt_async_config": {}, "pair_whitelist": ["BTC/USDT"], "pair_blacklist": []},
        "pairlists": [{"method": "StaticPairList"}],
        "strategy": "BtcMacroV2Strategy", "strategy_path": "user_data/strategies/",
        "db_url": "sqlite:///user_data/tradesv3_macrov2.sqlite",
        "logfile": "user_data/logs/freqtrade_macrov2.log", "user_data_dir": "user_data",
        "bot_name": "macrov2", "initial_state": "running"
    }
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg_path


def generate_grid():
    """Smart parameter grid (~200 combos)."""
    combos = []
    # Phase 1: tilt mode — vary macro weights
    for w_macro in [0.0, 0.05, 0.10, 0.15, 0.20]:
        for w_vix in [0.0, 0.05, 0.10]:
            for w_spy in [0.0, 0.05, 0.10]:
                for w_qqq in [0.0, 0.05]:
                    for exit_thr in [-0.7, -0.5, -0.3]:
                        combos.append({
                            "MV_W_MACRO": w_macro, "MV_W_VIX": w_vix,
                            "MV_W_SPY": w_spy, "MV_W_QQQ": w_qqq,
                            "MV_W_DXY": 0.0, "MV_W_RATES": 0.0,
                            "MV_EXIT_THR": exit_thr, "MV_MODE": "tilt",
                        })
    # Phase 2: exit-only mode (no tilt, only forced exit on macro risk-off)
    for exit_thr in [-0.7, -0.5, -0.3, -0.1]:
        combos.append({
            "MV_W_MACRO": 0.0, "MV_W_VIX": 0.0, "MV_W_SPY": 0.0,
            "MV_W_QQQ": 0.0, "MV_W_DXY": 0.0, "MV_W_RATES": 0.0,
            "MV_EXIT_THR": exit_thr, "MV_MODE": "exit_only",
        })
    # Phase 3: filter mode (don't enter if macro risk-off)
    for exit_thr in [-0.5, -0.3, -0.1, 0.0]:
        combos.append({
            "MV_W_MACRO": 0.0, "MV_W_VIX": 0.0, "MV_W_SPY": 0.0,
            "MV_W_QQQ": 0.0, "MV_W_DXY": 0.0, "MV_W_RATES": 0.0,
            "MV_EXIT_THR": exit_thr, "MV_MODE": "filter",
        })
    # Phase 4: DXY/rates-focused variants
    for w_dxy in [0.0, 0.05, 0.10]:
        for w_rates in [0.0, 0.05, 0.10]:
            combos.append({
                "MV_W_MACRO": 0.0, "MV_W_VIX": 0.05, "MV_W_SPY": 0.05,
                "MV_W_QQQ": 0.0, "MV_W_DXY": w_dxy, "MV_W_RATES": w_rates,
                "MV_EXIT_THR": -0.5, "MV_MODE": "tilt",
            })
    return combos


def run_one_backtest(env_overrides: dict) -> dict | None:
    """Run a single 9-year backtest with given env overrides. Returns metrics."""
    env = os.environ.copy()
    env.update({k: str(v) for k, v in env_overrides.items()})
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [
        sys.executable, "-m", "research.ai.logged_backtest",
        "--config", "config.macrov2.json",
        "--strategy", "BtcMacroV2Strategy",
        "--timerange", "20180101-20260601",
        "--mode", "SWEEP",
        "--notes", f"sweep {env_overrides}",
    ]
    try:
        p = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return None
    if p.returncode != 0:
        return None
    # Parse from stdout
    metrics = {}
    for line in p.stdout.splitlines()[-25:]:
        if "ROI:" in line and "trades:" in line:
            try:
                roi = float(line.split("ROI:")[1].split("%")[0].strip())
                trades_str = line.split("trades:")[1].split(",")[0].strip()
                trades = int(trades_str)
                dd_str = line.split("max_dd:")[1].split("%")[0].strip()
                dd = float(dd_str)
                sharpe_str = line.split("sharpe:")[1].strip()
                sharpe = float(sharpe_str)
                metrics = {"roi_pct": roi, "n_trades": trades,
                          "max_dd_pct": dd, "sharpe": sharpe}
            except Exception:
                pass
    return metrics if metrics else None


def sweep():
    combos = generate_grid()
    print(f"Total combinations to test: {len(combos)}")
    make_config()
    print(f"Config created: config.macrov2.json")
    print()

    results = []
    for i, combo in enumerate(combos, 1):
        m = run_one_backtest(combo)
        if m is None:
            status = "FAIL"
            row = {**combo, "roi_pct": None, "n_trades": None, "max_dd_pct": None, "status": status}
        else:
            row = {**combo, **m, "status": "OK"}
            status = f"ROI={m['roi_pct']:.1f}%  DD={m['max_dd_pct']:.1f}%  n={m['n_trades']}"
        print(f"  [{i:>3}/{len(combos)}]  {combo}  ->  {status}")
        results.append(row)
        # Save progress every 20 runs
        if i % 20 == 0:
            pd.DataFrame(results).to_csv(RESULTS_CSV, index=False)

    df = pd.DataFrame(results)
    df.to_csv(RESULTS_CSV, index=False)
    print(f"\nSaved: {RESULTS_CSV}")
    show_top(df)


def show_top(df=None):
    if df is None:
        df = pd.read_csv(RESULTS_CSV)
    df = df[df["status"] == "OK"].copy()
    # Score = ROI - 2*DD
    df["score"] = df["roi_pct"] - 2 * df["max_dd_pct"]
    df = df.sort_values("score", ascending=False)
    print("\n=== TOP 15 by score (ROI - 2*MaxDD) ===\n")
    cols = ["MV_MODE", "MV_W_MACRO", "MV_W_VIX", "MV_W_SPY", "MV_W_QQQ",
            "MV_W_DXY", "MV_W_RATES", "MV_EXIT_THR",
            "roi_pct", "max_dd_pct", "n_trades", "sharpe", "score"]
    cols = [c for c in cols if c in df.columns]
    print(df[cols].head(15).to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    # Print best as suggested env
    if not df.empty:
        best = df.iloc[0]
        print("\n=== BEST COMBO (use as deployment env) ===")
        for k in ["MV_MODE", "MV_W_MACRO", "MV_W_VIX", "MV_W_SPY", "MV_W_QQQ",
                  "MV_W_DXY", "MV_W_RATES", "MV_EXIT_THR"]:
            if k in best.index:
                print(f"  export {k}={best[k]}")
        print(f"\n  ROI: {best['roi_pct']:.1f}%")
        print(f"  Max DD: {best['max_dd_pct']:.1f}%")
        print(f"  Trades: {best['n_trades']}")
        print(f"  Sharpe: {best['sharpe']:.3f}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sweep"
    if cmd == "top":
        show_top()
    else:
        sweep()
