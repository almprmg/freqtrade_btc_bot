"""backtest_strategy.py — vectorized 9-year backtest of AnalogV3 (LSTM) logic.

MISSION KPI is AnalogV3 (LSTM) vs AnalogV2 (KNN) 9-year CAGR. freqtrade won't
install here (TA-Lib DLL blocked), so this is a faithful vectorized PROXY of the
strategy's ai_target -> position sizing, WITH fees. Not the freqtrade engine —
run that on the CPU machine for the official number.

Per coin it compares:
  AnalogV3   — full strategy with the LSTM analog tilt
  no-analog  — same strategy, analog tilt zeroed (isolates the LSTM's marginal value)
  buy&hold
and reports CAGR / Sharpe / maxDD / win-rate / #trades, for BOTH the full
history (LSTM params are in-sample on the first 80% -> optimistic) and the
out-of-sample tail (honest). AnalogV2 reference CAGR (documented): BTC +32.4%, ETH +42.2%.

USAGE:  python GPU_HANDOFF/backtest_strategy.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from dl_train_lstm import adx as adx_ind, ema as ema_ind

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "user_data" / "data"
COINS = ["BTC", "ETH", "SOL", "BNB", "ADA", "XRP", "DOGE"]
FEE = 0.0006          # per side, fraction (Binance-ish, limit orders)
ANN = 365
VAL_SPLIT = 0.20
ANALOGV2_REF = {"BTC": 32.4, "ETH": 42.2}   # documented KNN 9y CAGR (pp)

W_ANALOG, W_MACRO, W_SPY_TREND = 0.40, 0.20, 0.10
MACRO_EXIT_THR, BASE, SIGMOID_K, N_CONFIRM = -0.70, 0.85, 4.0, 3
LSTM_Z_WINDOW, TILT_CLAMP = 90, 0.45
PHASE_SHIFTS = {"ACCUMULATION": 0.20, "EARLY_BULL": 0.10, "PARABOLIC": -0.15,
                "DISTRIBUTION": -0.40, "BEAR": -0.60, "REACCUMULATION": -0.05}
CAL = {"oct": 0.15, "jul": -0.05, "jan": 0.10, "wed": 0.05, "mon": 0.05, "eom": 0.05}


def _aux(name):
    p = DATA / name
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_feather(p)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df.set_index("date").sort_index()


_MACRO = _aux("macro_signals.feather")
_HALVING = _aux("halving_cycle.feather")


def _sigmoid(x, k=SIGMOID_K):
    return 1.0 / (1.0 + np.exp(-k * x))


def ai_target(df, use_analog: bool, w_analog: float = W_ANALOG):
    """Replicate BtcAnalogV3Strategy.populate_indicators -> ai_target.
    w_analog scales the LSTM tilt (tuning knob)."""
    d = df["date"].dt.normalize()
    close = df["close"]
    ema200 = ema_ind(close, 200)
    adx = adx_ind(df, 14)
    ret30 = close.pct_change(30)

    bull = (close > ema200) & (ret30 > 0.05) & (adx > 20)
    bear = (close < ema200) & (ret30 < -0.10)
    rcode = pd.Series(0.0, index=df.index)
    rcode[bull] = 1.0; rcode[bear] = -1.0
    rmin = rcode.rolling(N_CONFIRM, min_periods=N_CONFIRM).min()
    rmax = rcode.rolling(N_CONFIRM, min_periods=N_CONFIRM).max()
    rconf = rcode.where(rmin == rmax, other=np.nan).ffill().fillna(0)

    phase = d.map(_HALVING["phase"]).ffill().fillna("NEUTRAL") if not _HALVING.empty else pd.Series("NEUTRAL", index=df.index)
    shifts = phase.map(PHASE_SHIFTS).fillna(0.0).astype(float)

    macro_risk = pd.Series(0.0, index=df.index)
    spy = pd.Series(0.0, index=df.index)
    if not _MACRO.empty:
        macro_risk = d.map(_MACRO["macro_risk_on"].ffill()).ffill().fillna(0).astype(float)
        spy = d.map(_MACRO["spy_above_ema50"].ffill()).ffill().fillna(0).astype(float)
    macro_tilt = W_MACRO * macro_risk + W_SPY_TREND * (spy * 2 - 1)

    analog_tilt = pd.Series(0.0, index=df.index)
    if use_analog and "lstm_pred" in df.columns:
        rm = df["lstm_pred"].rolling(LSTM_Z_WINDOW, min_periods=20).mean()
        rs = df["lstm_pred"].rolling(LSTM_Z_WINDOW, min_periods=20).std().replace(0, np.nan)
        z = ((df["lstm_pred"] - rm) / rs).fillna(0.0)
        analog_tilt = (w_analog * np.tanh(z)).clip(-0.45, 0.45)

    dt = df["date"].dt
    cal = ((dt.month == 10) * CAL["oct"] + (dt.month == 7) * CAL["jul"] + (dt.month == 1) * CAL["jan"]
           + (dt.day_name() == "Wednesday") * CAL["wed"] + (dt.day_name() == "Monday") * CAL["mon"]
           + (dt.day >= 26) * CAL["eom"])

    total_tilt = (cal + analog_tilt + macro_tilt).clip(-TILT_CLAMP, TILT_CLAMP)
    target = (BASE * _sigmoid((shifts + total_tilt).values)).clip(0.0, BASE)
    target = pd.Series(target, index=df.index)
    target[rconf == -1.0] = 0.0
    target[macro_risk < MACRO_EXIT_THR] = 0.0
    return target, rconf, macro_risk


def simulate(df, target, rconf, macro_risk):
    """Stateful entry/exit + rebalance to target; returns daily strat returns + #trades."""
    ret = df["close"].pct_change().fillna(0.0).values
    tgt = target.values; rc = rconf.values; mr = macro_risk.values
    n = len(df)
    pos = np.zeros(n)        # fraction held entering day t
    holding = False
    trades = 0
    for t in range(n):
        if holding:
            if rc[t] == -1.0 or tgt[t] < 0.20 or mr[t] < MACRO_EXIT_THR:
                holding = False
            else:
                pos[t] = tgt[t]
        if not holding and rc[t] == 1.0 and tgt[t] > 0.15:
            holding = True
            pos[t] = tgt[t]
            trades += 1
    pos = pd.Series(pos, index=df.index)
    turnover = pos.diff().abs().fillna(pos.abs())
    strat_ret = pos.shift(1).fillna(0) * ret - turnover * FEE
    return strat_ret, int(trades)


def metrics(ret):
    ret = pd.Series(ret).dropna()
    if len(ret) < 5:
        return {"cagr": float("nan"), "sharpe": float("nan"), "maxdd": float("nan"), "wr": float("nan")}
    eq = (1 + ret).cumprod()
    yrs = len(ret) / ANN
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1.0
    sharpe = ret.mean() / ret.std() * np.sqrt(ANN) if ret.std() > 0 else float("nan")
    dd = (eq / eq.cummax() - 1).min()
    nz = ret[ret != 0]
    wr = (nz > 0).mean() if len(nz) else float("nan")
    return {"cagr": cagr, "sharpe": sharpe, "maxdd": dd, "wr": wr}


def load_coin_signal(coin):
    ohlcv = DATA / "binance" / f"{coin}_USDT-1d.feather"
    sig = DATA / f"dl_signals_lstm_{coin}.feather"
    if not ohlcv.exists() or not sig.exists():
        return None
    df = pd.read_feather(ohlcv)[["date", "open", "high", "low", "close", "volume"]]
    df["date"] = pd.to_datetime(df["date"], utc=True)
    s = pd.read_feather(sig)[["date", "lstm_pred_fwd30"]].rename(columns={"lstm_pred_fwd30": "lstm_pred"})
    s["date"] = pd.to_datetime(s["date"], utc=True)
    return df.merge(s, on="date", how="left").sort_values("date").reset_index(drop=True)


def coin_strat_returns(coin, w_analog=W_ANALOG, use_analog=True):
    """Daily strategy returns (with fees) for a coin under a given AI weight."""
    df = load_coin_signal(coin)
    if df is None:
        return None, None, 0
    tgt, rc, mr = ai_target(df, use_analog, w_analog)
    sret, ntr = simulate(df, tgt, rc, mr)
    return df, sret, ntr


def run_coin(coin):
    ohlcv = DATA / "binance" / f"{coin}_USDT-1d.feather"
    sig = DATA / f"dl_signals_lstm_{coin}.feather"
    if not ohlcv.exists() or not sig.exists():
        return None
    df = pd.read_feather(ohlcv)[["date", "open", "high", "low", "close", "volume"]]
    df["date"] = pd.to_datetime(df["date"], utc=True)
    s = pd.read_feather(sig)[["date", "lstm_pred_fwd30"]].rename(columns={"lstm_pred_fwd30": "lstm_pred"})
    s["date"] = pd.to_datetime(s["date"], utc=True)
    df = df.merge(s, on="date", how="left").sort_values("date").reset_index(drop=True)

    out = {"coin": coin, "days": len(df)}
    oos0 = int(len(df) * (1 - VAL_SPLIT))
    for label, use_analog in [("v3", True), ("noanalog", False)]:
        tgt, rc, mr = ai_target(df, use_analog)
        sret, ntr = simulate(df, tgt, rc, mr)
        out[f"{label}_full"] = metrics(sret)
        out[f"{label}_oos"] = metrics(sret.iloc[oos0:])
        out[f"{label}_trades"] = ntr
    out["hold_full"] = metrics(df["close"].pct_change())
    out["hold_oos"] = metrics(df["close"].pct_change().iloc[oos0:])
    return out


def main():
    rows = [r for r in (run_coin(c) for c in COINS) if r]
    print("\n=== AnalogV3 (LSTM) vectorized 9y backtest — fees {:.2%}/side ===\n".format(FEE))
    h = f"{'coin':>4} | {'V3 CAGR':>8} {'noAnlg':>8} {'B&H':>8} | {'V3 OOS':>8} {'B&H OOS':>8} | {'V3 Shrp':>7} {'V3 DD':>7} {'trades':>6}"
    print(h); print("-" * len(h))
    for r in rows:
        print(f"{r['coin']:>4} | {r['v3_full']['cagr']*100:>7.1f}% {r['noanalog_full']['cagr']*100:>7.1f}% "
              f"{r['hold_full']['cagr']*100:>7.1f}% | {r['v3_oos']['cagr']*100:>7.1f}% {r['hold_oos']['cagr']*100:>7.1f}% | "
              f"{r['v3_full']['sharpe']:>7.2f} {r['v3_full']['maxdd']*100:>6.1f}% {r['v3_trades']:>6}")
    _write_html(rows)
    print(f"\nHTML: research/reports/ANALOGV3_BACKTEST.html")
    print("NOTE: full-period CAGR is optimistic (LSTM params in-sample on first 80%).")
    print("      OOS columns are the honest out-of-sample numbers.")
    print("      AnalogV2 (KNN) reference 9y CAGR: BTC +32.4%, ETH +42.2% (freqtrade).")


def _write_html(rows):
    def pct(x):
        return "n/a" if x != x else f"{x*100:+.1f}%"
    th = "background:#1a1a2e;color:#fff;padding:8px;text-align:right"
    td = "padding:6px 8px;text-align:right;border-bottom:1px solid #eee"
    body = []
    for r in rows:
        ref = ANALOGV2_REF.get(r["coin"])
        refs = f"+{ref:.1f}%" if ref else "—"
        body.append(
            f"<tr><td style='{td};text-align:left;font-weight:bold'>{r['coin']}</td>"
            f"<td style='{td}'>{pct(r['v3_full']['cagr'])}</td>"
            f"<td style='{td}'>{pct(r['noanalog_full']['cagr'])}</td>"
            f"<td style='{td}'>{pct(r['hold_full']['cagr'])}</td>"
            f"<td style='{td};color:#666'>{refs}</td>"
            f"<td style='{td}'>{pct(r['v3_oos']['cagr'])}</td>"
            f"<td style='{td}'>{pct(r['hold_oos']['cagr'])}</td>"
            f"<td style='{td}'>{r['v3_full']['sharpe']:.2f}</td>"
            f"<td style='{td}'>{pct(r['v3_full']['maxdd'])}</td>"
            f"<td style='{td}'>{r['v3_trades']}</td></tr>")
    html = f"""<!doctype html><html dir="rtl"><head><meta charset="utf-8">
<title>AnalogV3 LSTM Backtest</title></head>
<body style="font-family:system-ui,Segoe UI,Arial;max-width:1000px;margin:24px auto;color:#222">
<h1>AnalogV3 (LSTM) — Vectorized 9-Year Backtest</h1>
<p style="color:#666">Proxy of the freqtrade strategy (fees {FEE:.2%}/side). Full-period CAGR is
optimistic (LSTM in-sample on first 80%); the <b>OOS</b> columns are honest.
AnalogV2 (KNN) reference is the documented freqtrade 9y CAGR.</p>
<table style="border-collapse:collapse;width:100%;font-size:14px">
<tr><th style="{th};text-align:left">Coin</th><th style="{th}">V3 CAGR</th>
<th style="{th}">no-analog</th><th style="{th}">Buy&amp;Hold</th><th style="{th}">AnalogV2 (KNN)</th>
<th style="{th}">V3 OOS</th><th style="{th}">B&amp;H OOS</th><th style="{th}">Sharpe</th>
<th style="{th}">maxDD</th><th style="{th}">#trades</th></tr>
{''.join(body)}
</table>
<p style="color:#999;font-size:12px;margin-top:16px">Generated on the GPU machine.
Official numbers require the freqtrade 9y backtest on the CPU machine.</p>
</body></html>"""
    (REPO / "research" / "reports" / "ANALOGV3_BACKTEST.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
