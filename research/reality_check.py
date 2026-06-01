"""Reality check — re-run our 4 strategies with REALISTIC execution costs.

Backtest defaults: 0.1% fee, instant fill at close price. Live reality:
  - Binance taker fee: 0.10% per side (already in)
  - Slippage on limit orders that miss: +0.05% per side avg
  - Adverse selection / market impact on bigger orders: another +0.05%
  - Missed entries from network latency / API errors: ~5-10% of signals

We approximate by:
  - Setting fee to 0.20% (double the baseline) — fee_open + fee_close
  - Using market orders instead of limits (price_side="other") so spread eats
  - Compare to 5-year baseline (with the optimistic 0.1% fee)

If "+22% annual on backtest" becomes "+15-17% annual realistically" you
get an honest expectation. If it becomes "+5%" the strategy doesn't survive.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
import io
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO / "user_data" / "backtest_results"

STRATEGIES = [
    ("Rebalance_R5",  "BtcRebalanceStrategy",         "REBALANCE_MODE", "R5_75_BTC"),
    ("DynRebal_P20",  "BtcDynamicRebalanceStrategy",  "DR_MODE",        "DR_PROFIT_20"),
    ("3Layer_AGGR",   "Btc3LayerStrategy",            "L3_MODE",        "L3_AGGR_WIDE_GRID"),
    ("Adaptive_AGGR", "BtcAdaptiveStrategy",          "AD_MODE",        "ADAPT_AGGR_NOSTOP"),
]

CFG_MAP = {
    "BtcRebalanceStrategy":         "config.rebalance.json",
    "BtcDynamicRebalanceStrategy":  "config.dynrebal.json",
    "Btc3LayerStrategy":            "config.3layer.json",
    "BtcAdaptiveStrategy":          "config.adaptive.json",
}


def realistic_config(src: Path) -> Path:
    with src.open() as f:
        cfg = json.load(f)
    # Double the worst-case fee assumption by using market orders (price_side="other"
    # buys above bid, sells below ask).
    cfg["entry_pricing"]["price_side"] = "other"
    cfg["exit_pricing"]["price_side"] = "other"
    # Force market order type (no limit-order skips).
    cfg["order_types"] = {"entry": "market", "exit": "market",
                          "stoploss": "market", "stoploss_on_exchange": False}
    dst = src.parent / f"_realistic_{src.name}"
    with dst.open("w") as f:
        json.dump(cfg, f, indent=2)
    return dst


def run(strategy: str, env_var: str, env_val: str, cfg: Path, wallet: float) -> dict:
    env = os.environ.copy()
    env[env_var] = env_val
    venv_freqtrade = str(REPO / ".venv" / "Scripts" / "freqtrade.exe")
    cmd = [
        venv_freqtrade, "backtesting",
        "--userdir", str(REPO / "user_data"),
        "--config", str(cfg),
        "--strategy", strategy,
        "--timerange", "20210101-20260101",
        "--dry-run-wallet", str(wallet),
        "--fee", "0.002",  # 0.20% (double the default)
        "--cache", "none",
        "--export", "trades",
    ]
    subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=REPO)

    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        return {"final": None}
    with zipfile.ZipFile(zips[-1]) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and "market_change" not in n]
        with z.open(names[0]) as f:
            payload = json.load(io.TextIOWrapper(f, encoding="utf-8"))
    strat_key = next(iter(payload.get("strategy", {})), None)
    if not strat_key:
        return {"final": None}
    s = payload["strategy"][strat_key]
    final = float(s.get("final_balance", 0) or 0)
    return {"final": round(final, 0), "roi_%": round((final - wallet) / wallet * 100, 1)}


def main() -> int:
    WALLET = 10000.0
    BASELINE = {
        "Rebalance_R5":  166.0,
        "DynRebal_P20":  170.4,
        "3Layer_AGGR":   99.6,
        "Adaptive_AGGR": 118.7,
    }
    rows = []
    for label, klass, env_var, env_val in STRATEGIES:
        cfg_src = REPO / CFG_MAP[klass]
        cfg = realistic_config(cfg_src)
        print(f"  - {label} REALISTIC...", end=" ", flush=True)
        stats = run(klass, env_var, env_val, cfg, WALLET)
        cfg.unlink(missing_ok=True)
        baseline_roi = BASELINE[label]
        realistic_roi = stats.get("roi_%", 0) or 0
        degradation = baseline_roi - realistic_roi
        # Annualized
        ann_baseline = (((1 + baseline_roi / 100) ** 0.2 - 1) * 100)
        ann_real = (((1 + realistic_roi / 100) ** 0.2 - 1) * 100) if realistic_roi > -100 else -100
        rows.append({
            "strategy": label,
            "baseline_5y_%": baseline_roi,
            "realistic_5y_%": realistic_roi,
            "degradation_pp": round(degradation, 1),
            "baseline_annual_%": round(ann_baseline, 1),
            "realistic_annual_%": round(ann_real, 1),
        })
        print(f"baseline={baseline_roi}%  realistic={realistic_roi}%  loss={round(degradation,1)}pp")

    df = pd.DataFrame(rows).sort_values("realistic_5y_%", ascending=False).reset_index(drop=True)
    print("\n" + "=" * 95)
    print("REALITY CHECK — backtest (0.1% fees, limit) vs realistic (0.2% fees, market orders)")
    print("=" * 95)
    print(df.to_string(index=False))

    out = REPO / "research" / "reality_check_results.csv"
    df.to_csv(out, index=False)
    print(f"\nSaved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
