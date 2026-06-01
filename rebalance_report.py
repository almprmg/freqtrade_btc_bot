"""
Reads each rebalance mode's last backtest result zip and prints a
year-by-year breakdown (final portfolio value, ROI, BTC qty at year-end).
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

MODES = ["R1_DAILY_FULL", "R2_DAILY_5PCT", "R3_DAILY_10PCT", "R4_25_BTC", "R5_75_BTC", "R6_HALFWAY"]
RESULTS_DIR = Path("user_data/backtest_results")
BTC_DATA = Path("user_data/data/binance/BTC_USDT-1d.feather")


def load_btc_close() -> pd.Series:
    df = pd.read_feather(BTC_DATA)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df.set_index("date")["close"]


def latest_n_zips(n: int) -> list[Path]:
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    return zips[-n:]


def trades_from_zip(p: Path) -> tuple[pd.DataFrame, dict]:
    with zipfile.ZipFile(p) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and "market_change" not in n]
        if not names:
            return pd.DataFrame(), {}
        with z.open(names[0]) as f:
            payload = json.load(io.TextIOWrapper(f, encoding="utf-8"))
    strat_key = next(iter(payload.get("strategy", {})), None)
    if strat_key is None:
        return pd.DataFrame(), {}
    strat = payload["strategy"][strat_key]
    trades = strat.get("trades", [])
    if not trades:
        return pd.DataFrame(), strat
    df = pd.DataFrame(trades)
    df["open_date"] = pd.to_datetime(df["open_date"], utc=True)
    df["close_date"] = pd.to_datetime(df["close_date"], utc=True, errors="coerce")
    return df, strat


def yearly_from_orders(df: pd.DataFrame, starting_wallet: float, close: pd.Series) -> pd.DataFrame:
    """Walk every order in chronological order and recompute portfolio state per year-end."""
    events = []
    for _, t in df.iterrows():
        if "orders" not in df.columns or t["orders"] is None:
            continue
        for o in t["orders"]:
            ts_ms = o.get("order_filled_timestamp")
            ts = pd.to_datetime(ts_ms, utc=True, unit="ms", errors="coerce") if ts_ms else pd.NaT
            if pd.isna(ts):
                ts = pd.to_datetime(o.get("order_date_utc") or o.get("order_date"), utc=True, errors="coerce")
            if pd.isna(ts):
                continue
            side = o.get("ft_order_side") or o.get("side")
            cost = float(o.get("cost") or 0.0)
            amt = float(o.get("amount") or 0.0)
            events.append({"date": ts, "side": side, "cost": cost, "amt": amt})

    if not events:
        return pd.DataFrame()

    ev = pd.DataFrame(events).sort_values("date").reset_index(drop=True)
    # Track cumulative state.
    cash = starting_wallet
    btc = 0.0
    invested_total = starting_wallet  # capital deployed once at start

    ev["year"] = ev["date"].dt.year
    rows = []

    for year in sorted(ev["year"].unique()):
        sub = ev[ev["year"] == year]
        buys_count = int((sub["side"] == "buy").sum())
        sells_count = int((sub["side"] == "sell").sum())
        for _, e in sub.iterrows():
            if e["side"] == "buy":
                cash -= e["cost"]
                btc += e["amt"]
            else:
                cash += e["cost"]
                btc -= e["amt"]

        year_end = pd.Timestamp(f"{year}-12-31 23:59", tz="UTC")
        px = close.loc[:year_end].iloc[-1] if len(close.loc[:year_end]) else float("nan")
        portfolio = cash + btc * px
        roi = (portfolio - starting_wallet) / starting_wallet * 100.0

        rows.append({
            "year": year,
            "buys": buys_count,
            "sells": sells_count,
            "cash_$": round(cash, 0),
            "btc_qty": round(btc, 5),
            "btc_val_$": round(btc * px, 0),
            "px_y_end": round(float(px), 0),
            "portfolio_$": round(portfolio, 0),
            "roi_%": round(roi, 1),
        })
    return pd.DataFrame(rows)


def main() -> int:
    close = load_btc_close()
    # 6 modes at $500 + sweep's default-winner R1 at $100 + manual R5 at $100.
    zips = latest_n_zips(8)
    labels = list(MODES) + ["R1_DAILY_FULL_at_100", "R5_75_BTC_at_100"]
    wallets = [500.0] * 6 + [100.0, 100.0]

    final_summary = []
    print("\n" + "=" * 110)
    print("YEAR-BY-YEAR BY MODE  ($500 portfolio)")
    print("=" * 110)
    for label, zpath, w in zip(labels, zips, wallets):
        df, strat = trades_from_zip(zpath)
        if df.empty:
            print(f"\n--- {label}  ({zpath.name})  — no trades")
            continue
        yr = yearly_from_orders(df, w, close)
        if yr.empty:
            continue
        print(f"\n--- {label}  (wallet ${int(w)}, {zpath.name}) ---")
        print(yr.to_string(index=False))
        last = yr.iloc[-1].copy()
        last["mode"] = label
        last["wallet_$"] = int(w)
        final_summary.append(last)

    if final_summary:
        fdf = pd.DataFrame(final_summary)
        fdf = fdf[["mode", "wallet_$", "year", "buys", "sells", "btc_qty", "portfolio_$", "roi_%"]]
        print("\n" + "=" * 110)
        print("FINAL — last row per run (whole 5-year period):")
        print(fdf.to_string(index=False))
        Path("rebalance_results").mkdir(exist_ok=True)
        fdf.to_csv("rebalance_results/final_summary.csv", index=False)
        print("\nSaved: rebalance_results/final_summary.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
