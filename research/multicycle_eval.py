"""Test MultiCycleShieldStrategy on 7 coins year-by-year, compare with current winners."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "ai"))
import json, os, subprocess, zipfile, io
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO / "user_data" / "backtest_results"

COINS = ["BTC", "ETH", "SOL", "BNB", "AVAX", "DOGE", "ADA"]
YEARS = {
    "2021": "20210101-20220101", "2022": "20220101-20230101",
    "2023": "20230101-20240101", "2024": "20240101-20250101",
    "2025": "20250101-20260101", "2026Q12": "20260101-20260601",
}


def make_config(coin: str) -> Path:
    cfg = {
        "max_open_trades": 1, "stake_currency": "USDT", "stake_amount": "unlimited",
        "tradable_balance_ratio": 1.0, "fiat_display_currency": "USD",
        "timeframe": "1d", "dry_run": True, "dry_run_wallet": 10000,
        "cancel_open_orders_on_exit": False, "trading_mode": "spot", "margin_mode": "",
        "unfilledtimeout": {"entry": 10, "exit": 10, "exit_timeout_count": 0, "unit": "minutes"},
        "entry_pricing": {"price_side": "same", "use_order_book": False, "order_book_top": 1,
                          "price_last_balance": 0.0, "check_depth_of_market": {"enabled": False}},
        "exit_pricing": {"price_side": "same", "use_order_book": False, "order_book_top": 1},
        "exchange": {"name": "binance", "key": "", "secret": "", "ccxt_config": {}, "ccxt_async_config": {},
                     "pair_whitelist": [f"{coin}/USDT"], "pair_blacklist": []},
        "pairlists": [{"method": "StaticPairList"}],
        "telegram": {"enabled": False, "token": "", "chat_id": ""},
        "api_server": {"enabled": False, "listen_ip_address": "127.0.0.1", "listen_port": 8080, "username": "", "password": ""},
        "bot_name": f"multicycle_{coin.lower()}", "initial_state": "running", "force_entry_enable": False,
        "internals": {"process_throttle_secs": 30, "heartbeat_interval": 60},
        "strategy_path": "user_data/strategies/",
        "db_url": f"sqlite:///user_data/tradesv3_mc_{coin.lower()}.sqlite",
        "logfile": f"user_data/logs/freqtrade_mc_{coin.lower()}.log", "user_data_dir": "user_data",
    }
    p = REPO / f"config.mc-{coin}.json"
    with p.open("w") as f:
        json.dump(cfg, f, indent=2)
    return p


def run(strategy: str, cfg: Path, tr: str, wallet=10000):
    venv = str(REPO / ".venv" / "Scripts" / "freqtrade.exe")
    subprocess.run([
        venv, "backtesting", "--userdir", str(REPO / "user_data"),
        "--config", str(cfg), "--strategy", strategy,
        "--timerange", tr, "--dry-run-wallet", str(wallet), "--cache", "none",
    ], capture_output=True, text=True, cwd=REPO)
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips: return None, None
    try:
        with zipfile.ZipFile(zips[-1]) as z:
            names = [n for n in z.namelist() if n.endswith(".json") and "market_change" not in n]
            with z.open(names[0]) as f: payload = json.load(io.TextIOWrapper(f, encoding="utf-8"))
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
    print(f"Testing MultiCycleShield on {len(COINS)} coins x {len(YEARS)} years...")
    rows = []
    for coin in COINS:
        cfg = make_config(coin)
        for year, tr in YEARS.items():
            print(f"  {coin} on {year}...", end=" ", flush=True)
            roi, dd = run("MultiCycleShieldStrategy", cfg, tr)
            print(f"ROI={roi}% DD={dd}%")
            rows.append({"coin": coin, "year": year, "roi_%": roi, "max_dd_%": dd})

    df = pd.DataFrame(rows)
    piv = df.pivot(index="coin", columns="year", values="roi_%")
    print("\n=== ROI year-by-year ===")
    print(piv.to_string())
    piv_dd = df.pivot(index="coin", columns="year", values="max_dd_%")
    print("\n=== Max DD year-by-year ===")
    print(piv_dd.to_string())

    stats = []
    for c in piv.index:
        row = piv.loc[c].dropna()
        dds = piv_dd.loc[c].dropna()
        compound = 1.0
        for r in row: compound *= (1 + r / 100)
        annual = (compound ** (1 / max(len(row), 1)) - 1) * 100
        stats.append({"coin": c,
                      "compound_$10k": round(compound * 10000, 0),
                      "annual_%": round(annual, 1),
                      "best_yr_%": round(row.max(), 1),
                      "worst_yr_%": round(row.min(), 1),
                      "max_DD_%": round(dds.max(), 1),
                      "positive_yrs": int((row > 0).sum())})
    print("\n=== Summary ===")
    print(pd.DataFrame(stats).sort_values("annual_%", ascending=False).to_string(index=False))
    df.to_csv(REPO / "research" / "multicycle_results.csv", index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
