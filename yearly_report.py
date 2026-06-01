"""
Reads each DCA mode's exported backtest result and prints a year-by-year
breakdown. Run AFTER `bash dca_sweep.sh` finishes.

Freqtrade exports as timestamped `backtest-result-YYYY-MM-DD_HH-MM-SS.zip`,
so we match the 6 newest zips (one per sweep run) to the 6 modes by
chronological order — V1_BLIND first, V6_TIERED_TP last.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

MODES = ["V1_BLIND", "V2_BLIND_TP", "V3_RSI", "V4_BELOW_EMA", "V5_TIERED", "V6_TIERED_TP"]
RESULTS_DIR = Path("user_data/backtest_results")
BTC_DATA = Path("user_data/data/binance/BTC_USDT-1d.feather")


def load_btc_close() -> pd.Series:
    df = pd.read_feather(BTC_DATA)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df.set_index("date")["close"]


def latest_n_zips(n: int) -> list[Path]:
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    return zips[-n:]


def trades_from_zip(p: Path) -> pd.DataFrame:
    with zipfile.ZipFile(p) as z:
        # The first .json inside is the strategy payload.
        json_names = [n for n in z.namelist() if n.endswith(".json") and "market_change" not in n]
        if not json_names:
            return pd.DataFrame()
        with z.open(json_names[0]) as f:
            payload = json.load(io.TextIOWrapper(f, encoding="utf-8"))
    strat_key = next(iter(payload.get("strategy", {})), None)
    if strat_key is None:
        return pd.DataFrame()
    trades = payload["strategy"][strat_key].get("trades", [])
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame(trades)
    df["open_date"] = pd.to_datetime(df["open_date"], utc=True)
    df["close_date"] = pd.to_datetime(df["close_date"], utc=True, errors="coerce")
    return df


def trades_to_position_events(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten DCA position adjustments into individual (date, usdt_in, btc_qty) events.

    Each Freqtrade trade with `orders` list captures each entry/exit. We use
    those to reconstruct the cumulative cost basis over time.
    """
    rows = []
    if "orders" not in df.columns:
        # Fall back to trade-level — one entry per trade.
        for _, t in df.iterrows():
            rows.append({
                "date": t["open_date"],
                "usdt_in": float(t["stake_amount"]),
                "btc_qty": float(t["amount"]),
                "kind": "buy",
            })
            if pd.notna(t["close_date"]):
                rows.append({
                    "date": t["close_date"],
                    "usdt_in": -float(t["stake_amount"]),
                    "btc_qty": -float(t["amount"]),
                    "kind": "sell",
                    "realised_pnl": float(t.get("profit_abs", 0.0)),
                })
        return pd.DataFrame(rows)

    for _, t in df.iterrows():
        for o in t["orders"]:
            ft = o.get("ft_order_side") or o.get("side")
            ts = pd.to_datetime(o.get("order_filled_timestamp") or o.get("order_date_utc"), utc=True, unit="ms" if isinstance(o.get("order_filled_timestamp"), (int, float)) else None, errors="coerce")
            if pd.isna(ts):
                ts = pd.to_datetime(o.get("order_date") or o.get("order_date_utc"), utc=True, errors="coerce")
            cost = float(o.get("cost") or 0.0)
            amt = float(o.get("amount") or 0.0)
            if ft == "buy":
                rows.append({"date": ts, "usdt_in": cost, "btc_qty": amt, "kind": "buy"})
            else:
                rows.append({"date": ts, "usdt_in": -cost, "btc_qty": -amt, "kind": "sell", "realised_pnl": float(t.get("profit_abs", 0.0))})
    return pd.DataFrame(rows)


def yearly_breakdown(mode: str, events: pd.DataFrame, close: pd.Series) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    events = events.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    events["year"] = events["date"].dt.year

    rows = []
    cum_invested = 0.0
    cum_realised = 0.0
    cum_btc = 0.0
    for year in sorted(events["year"].unique()):
        sub = events[events["year"] == year]
        buys = sub[sub["kind"] == "buy"]
        sells = sub[sub["kind"] == "sell"]

        invested_year = float(buys["usdt_in"].sum())
        cum_invested += invested_year
        realised_year = float(sells.get("realised_pnl", pd.Series(0)).sum()) if "realised_pnl" in sub.columns else 0.0
        cum_realised += realised_year

        # Net BTC delta this year.
        cum_btc += float(buys["btc_qty"].sum() + sells["btc_qty"].sum())

        year_end = pd.Timestamp(f"{year}-12-31 23:59", tz="UTC")
        price_at_year_end = close.loc[:year_end].iloc[-1] if len(close.loc[:year_end]) else float("nan")
        mark_value = cum_btc * price_at_year_end if price_at_year_end == price_at_year_end else 0.0
        total_pnl = mark_value + cum_realised - cum_invested  # what we'd have if we cashed out today
        roi_pct = (total_pnl / cum_invested * 100.0) if cum_invested else 0.0

        rows.append({
            "mode": mode,
            "year": year,
            "buys": int((buys["kind"] == "buy").sum()),
            "invested$": round(invested_year, 0),
            "cum_invested$": round(cum_invested, 0),
            "btc_held": round(cum_btc, 4),
            "px_y_end": round(float(price_at_year_end), 0) if price_at_year_end == price_at_year_end else None,
            "mark$": round(mark_value, 0),
            "cum_realised$": round(cum_realised, 0),
            "total_pnl$": round(total_pnl, 0),
            "roi_%": round(roi_pct, 1),
        })
    return pd.DataFrame(rows)


def main() -> int:
    close = load_btc_close()
    zips = latest_n_zips(len(MODES))
    if len(zips) < len(MODES):
        print(f"WARN: expected {len(MODES)} zips, found {len(zips)}")

    all_rows = []
    for mode, zpath in zip(MODES, zips):
        print(f"\n=== {mode}  ({zpath.name}) ===")
        df = trades_from_zip(zpath)
        if df.empty:
            print("  no trades")
            continue
        events = trades_to_position_events(df)
        if events.empty:
            print("  no events extracted")
            continue
        out = yearly_breakdown(mode, events, close)
        if out.empty:
            print("  no yearly rows")
            continue
        print(out.to_string(index=False))
        all_rows.append(out)

    if not all_rows:
        print("\nNo data to summarize.")
        return 1

    final = pd.concat(all_rows, ignore_index=True)
    # Final per-mode summary = last year row.
    print("\n" + "=" * 110)
    print("WHOLE-PERIOD SUMMARY (last-row state per mode):")
    last = final.groupby("mode").tail(1).reset_index(drop=True)
    print(
        last[["mode", "cum_invested$", "btc_held", "mark$", "cum_realised$", "total_pnl$", "roi_%"]]
        .to_string(index=False)
    )

    Path("dca_results").mkdir(exist_ok=True)
    final.to_csv("dca_results/yearly_breakdown.csv", index=False)
    last.to_csv("dca_results/final_summary.csv", index=False)
    print("\nSaved: dca_results/yearly_breakdown.csv  dca_results/final_summary.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
