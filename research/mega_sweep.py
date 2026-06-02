"""Mega sweep: 4 coins x 26 strategy modes x 6 years = ~624 backtests.

Coins: AVAX, BNB, DOGE, ADA (4 new ones; BTC/ETH/SOL already covered).
Strategies (top modes per family):
  Rebalance:    R1_DAILY_FULL, R5_75_BTC, R6_HALFWAY                  (3)
  DynRebal:     DR_PROFIT_10, DR_PROFIT_20, DR_PROFIT_30, DR_REGIME   (4)
  3Layer:       L3_AGGR_BASELINE, L3_AGGR_WIDE_GRID,
                L3_AGGR_TIGHT_GRID, L3_BAL_WIDE_GRID                  (4)
  Adaptive:     ADAPT_AGGR_NOSTOP, ADAPT_BAL_NOSTOP,
                ADAPT_DEF_NOSTOP, ADAPT_AGGR_LOOSE                    (4)
  Shield:       RS_FAST, RS_MED, RS_SLOW, RS_AGGR, RS_DEFENSIVE       (5)
  DCA:          V1_BLIND, V5_TIERED                                   (2)
  Meta:         MA_STRICT, MA_BAL, MA_RELAX, MA_VSTRICT               (4)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
import io
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO / "user_data" / "backtest_results"

COINS = ["AVAX", "BNB", "DOGE", "ADA"]
WALLET = 10000

# (label, strategy_class, env_var, env_val, family)
MODES = [
    ("Rebal_R1",   "BtcRebalanceStrategy",        "REBALANCE_MODE", "R1_DAILY_FULL",     "Rebalance"),
    ("Rebal_R5",   "BtcRebalanceStrategy",        "REBALANCE_MODE", "R5_75_BTC",         "Rebalance"),
    ("Rebal_R6",   "BtcRebalanceStrategy",        "REBALANCE_MODE", "R6_HALFWAY",        "Rebalance"),
    ("Dyn_P10",    "BtcDynamicRebalanceStrategy", "DR_MODE",        "DR_PROFIT_10",      "DynRebal"),
    ("Dyn_P20",    "BtcDynamicRebalanceStrategy", "DR_MODE",        "DR_PROFIT_20",      "DynRebal"),
    ("Dyn_P30",    "BtcDynamicRebalanceStrategy", "DR_MODE",        "DR_PROFIT_30",      "DynRebal"),
    ("Dyn_REG",    "BtcDynamicRebalanceStrategy", "DR_MODE",        "DR_REGIME",         "DynRebal"),
    ("L3_AGGR_BL", "Btc3LayerStrategy",           "L3_MODE",        "L3_AGGR_BASELINE",  "3Layer"),
    ("L3_AGGR_WG", "Btc3LayerStrategy",           "L3_MODE",        "L3_AGGR_WIDE_GRID", "3Layer"),
    ("L3_AGGR_TG", "Btc3LayerStrategy",           "L3_MODE",        "L3_AGGR_TIGHT_GRID","3Layer"),
    ("L3_BAL_WG",  "Btc3LayerStrategy",           "L3_MODE",        "L3_BAL_WIDE_GRID",  "3Layer"),
    ("Ad_AGGR",    "BtcAdaptiveStrategy",         "AD_MODE",        "ADAPT_AGGR_NOSTOP", "Adaptive"),
    ("Ad_BAL",     "BtcAdaptiveStrategy",         "AD_MODE",        "ADAPT_BAL_NOSTOP",  "Adaptive"),
    ("Ad_DEF",     "BtcAdaptiveStrategy",         "AD_MODE",        "ADAPT_DEF_NOSTOP",  "Adaptive"),
    ("Ad_AGGR_LO", "BtcAdaptiveStrategy",         "AD_MODE",        "ADAPT_AGGR_LOOSE",  "Adaptive"),
    ("Sh_FAST",    "BtcRegimeShieldStrategy",     "RS_MODE",        "RS_FAST",           "Shield"),
    ("Sh_MED",     "BtcRegimeShieldStrategy",     "RS_MODE",        "RS_MED",            "Shield"),
    ("Sh_SLOW",    "BtcRegimeShieldStrategy",     "RS_MODE",        "RS_SLOW",           "Shield"),
    ("Sh_AGGR",    "BtcRegimeShieldStrategy",     "RS_MODE",        "RS_AGGR",           "Shield"),
    ("Sh_DEF",     "BtcRegimeShieldStrategy",     "RS_MODE",        "RS_DEFENSIVE",      "Shield"),
    ("DCA_V1",     "BtcDcaHoldStrategy",          "DCA_MODE",       "V1_BLIND",          "DCA"),
    ("DCA_V5",     "BtcDcaHoldStrategy",          "DCA_MODE",       "V5_TIERED",         "DCA"),
    ("Meta_STR",   "BtcMetaAdaptiveStrategy",     "MA_MODE",        "MA_STRICT",         "Meta"),
    ("Meta_BAL",   "BtcMetaAdaptiveStrategy",     "MA_MODE",        "MA_BAL",            "Meta"),
    ("Meta_REL",   "BtcMetaAdaptiveStrategy",     "MA_MODE",        "MA_RELAX",          "Meta"),
    ("Meta_VST",   "BtcMetaAdaptiveStrategy",     "MA_MODE",        "MA_VSTRICT",        "Meta"),
]

YEARS = {
    "2021": "20210101-20220101", "2022": "20220101-20230101",
    "2023": "20230101-20240101", "2024": "20240101-20250101",
    "2025": "20250101-20260101", "2026Q12": "20260101-20260601",
}


def make_config(coin: str) -> Path:
    pair = f"{coin}/USDT"
    cfg = {
        "max_open_trades": 1, "stake_currency": "USDT", "stake_amount": "unlimited",
        "tradable_balance_ratio": 1.0, "fiat_display_currency": "USD",
        "timeframe": "1d", "dry_run": True, "dry_run_wallet": WALLET,
        "cancel_open_orders_on_exit": False, "trading_mode": "spot", "margin_mode": "",
        "unfilledtimeout": {"entry": 10, "exit": 10, "exit_timeout_count": 0, "unit": "minutes"},
        "entry_pricing": {"price_side": "same", "use_order_book": False, "order_book_top": 1,
                          "price_last_balance": 0.0, "check_depth_of_market": {"enabled": False}},
        "exit_pricing": {"price_side": "same", "use_order_book": False, "order_book_top": 1},
        "exchange": {"name": "binance", "key": "", "secret": "",
                     "ccxt_config": {}, "ccxt_async_config": {},
                     "pair_whitelist": [pair], "pair_blacklist": []},
        "pairlists": [{"method": "StaticPairList"}],
        "telegram": {"enabled": False, "token": "", "chat_id": ""},
        "api_server": {"enabled": False, "listen_ip_address": "127.0.0.1", "listen_port": 8080,
                       "username": "", "password": ""},
        "bot_name": f"{coin.lower()}_sweep", "initial_state": "running", "force_entry_enable": False,
        "internals": {"process_throttle_secs": 30, "heartbeat_interval": 60},
        "strategy_path": "user_data/strategies/",
        "db_url": f"sqlite:///user_data/tradesv3_{coin.lower()}_sweep.sqlite",
        "logfile": f"user_data/logs/freqtrade_{coin.lower()}_sweep.log",
        "user_data_dir": "user_data",
    }
    p = REPO / f"config.mega-{coin}.json"
    with p.open("w") as f:
        json.dump(cfg, f, indent=2)
    return p


def run(strategy: str, env_var: str, env_val: str, cfg: Path, tr: str, wallet: float = WALLET):
    env = os.environ.copy()
    env[env_var] = env_val
    venv = str(REPO / ".venv" / "Scripts" / "freqtrade.exe")
    subprocess.run([
        venv, "backtesting", "--userdir", str(REPO / "user_data"),
        "--config", str(cfg), "--strategy", strategy,
        "--timerange", tr, "--dry-run-wallet", str(wallet), "--cache", "none",
    ], env=env, capture_output=True, text=True, cwd=REPO)
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips: return None, None
    try:
        with zipfile.ZipFile(zips[-1]) as z:
            names = [n for n in z.namelist() if n.endswith(".json") and "market_change" not in n]
            with z.open(names[0]) as f:
                payload = json.load(io.TextIOWrapper(f, encoding="utf-8"))
        sk = next(iter(payload.get("strategy", {})), None)
        if not sk: return None, None
        s = payload["strategy"][sk]
        final = float(s.get("final_balance", 0) or 0)
        roi = (final - wallet) / wallet * 100
        dd = float(s.get("max_drawdown_account", 0) or 0) * 100
        return round(roi, 1), round(dd, 1)
    except Exception:
        return None, None


def main():
    total = len(COINS) * len(MODES) * len(YEARS)
    n = 0
    rows = []
    for coin in COINS:
        print(f"\n>>> COIN: {coin}")
        cfg_path = make_config(coin)
        for label, klass, env_var, env_val, family in MODES:
            for year, tr in YEARS.items():
                n += 1
                print(f"  [{n}/{total}] {coin} {label} {year}...", end=" ", flush=True)
                roi, dd = run(klass, env_var, env_val, cfg_path, tr)
                print(f"ROI={roi}% DD={dd}%")
                rows.append({"coin": coin, "family": family, "variant": label, "year": year,
                             "roi_%": roi, "max_dd_%": dd})

    df = pd.DataFrame(rows)
    df.to_csv(REPO / "research" / "mega_sweep_raw.csv", index=False)

    # Per-coin summary
    print("\n" + "=" * 110)
    print("PER-COIN SUMMARY (top 10 modes by annual compound)")
    print("=" * 110)
    all_stats = []
    for coin in COINS:
        sub = df[df["coin"] == coin]
        piv = sub.pivot(index="variant", columns="year", values="roi_%")
        piv_dd = sub.pivot(index="variant", columns="year", values="max_dd_%")
        stats = []
        for v in piv.index:
            row = piv.loc[v].dropna()
            dds = piv_dd.loc[v].dropna()
            compound = 1.0
            for r in row: compound *= (1 + r / 100)
            annual = (compound ** (1 / max(len(row), 1)) - 1) * 100
            stats.append({
                "coin": coin,
                "variant": v,
                "family": sub[sub["variant"] == v]["family"].iloc[0],
                "compound_$10k": round(compound * 10000, 0),
                "annual_%": round(annual, 1),
                "best_yr_%": round(row.max(), 1),
                "worst_yr_%": round(row.min(), 1),
                "max_yearly_dd_%": round(dds.max(), 1),
                "positive_yrs": int((row > 0).sum()),
            })
        coin_df = pd.DataFrame(stats).sort_values("annual_%", ascending=False)
        all_stats.append(coin_df)
        print(f"\n=== {coin} ===")
        print(coin_df.head(10).to_string(index=False))

    all_stats_df = pd.concat(all_stats, ignore_index=True)
    all_stats_df.to_csv(REPO / "research" / "mega_sweep_summary.csv", index=False)

    # Best per coin
    print("\n=== BEST MODE PER COIN ===")
    best = all_stats_df.loc[all_stats_df.groupby("coin")["annual_%"].idxmax()]
    print(best[["coin", "variant", "family", "annual_%", "best_yr_%", "worst_yr_%",
                "max_yearly_dd_%", "positive_yrs"]].to_string(index=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
