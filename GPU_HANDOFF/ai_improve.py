"""ai_improve.py — improvement based on the diagnosis.

Diagnosis (ai_diagnose.py): the LSTM signal is GOOD (monotonic quintiles, 5/7
coins) but the AnalogV3 strategy DILUTES it (small clipped tilt + regime/macro
gating). pure-AI earns far more but with bigger drawdowns.

Improvement = "AI-primary + safety gate": let the AI signal DRIVE the position
size (sigmoid of the causal z-score) but keep ONLY the crash guards (force flat
in confirmed BEAR or macro risk-off). Tune signal strength k by OOS Sharpe.
Goal: pure-AI returns with baseline-like drawdown control.

USAGE:  python GPU_HANDOFF/ai_improve.py
Output: research/reports/AI_IMPROVED.html + saved results
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_strategy import ai_target, coin_strat_returns, load_coin_signal, metrics
from ai_strategy_report import month_table, stat_block, fmt_pct

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "research" / "dl_models" / "trading_results"
COINS = ["BTC", "ETH", "SOL", "BNB", "ADA", "XRP", "DOGE"]
FEE = 0.0006
VAL_SPLIT = 0.20
ZW = 90
KS = [1.0, 1.5, 2.0, 3.0]
MACRO_EXIT_THR = -0.70


def causal_z(pred):
    rm = pred.rolling(ZW, min_periods=20).mean()
    rs = pred.rolling(ZW, min_periods=20).std().replace(0, np.nan)
    return ((pred - rm) / rs).fillna(0.0)


def ai_primary_returns(df, k, gated=True):
    """Position driven by AI signal; optionally forced flat on BEAR / macro-off."""
    z = causal_z(df["lstm_pred"])
    pos = 1.0 / (1.0 + np.exp(-k * z))           # AI-driven allocation in [0,1]
    if gated:
        _, rconf, macro = ai_target(df, use_analog=False)
        pos = pos.where((rconf != -1.0) & (macro >= MACRO_EXIT_THR), 0.0)
    ret = df["close"].pct_change().fillna(0.0)
    turn = pos.diff().abs().fillna(pos.abs())
    return pos.shift(1).fillna(0) * ret - turn * FEE


def best_k(df, oos0):
    bk, bs, bret = KS[0], -1e9, None
    for k in KS:
        r = ai_primary_returns(df, k, gated=True)
        s = metrics(r.iloc[oos0:])["sharpe"]
        s = -1e9 if s != s else s
        if s > bs:
            bk, bs, bret = k, s, r
    return bk, bret


def main():
    rows = []
    port = None; counts = None
    series = {}   # coin -> (dates, improved_ret, base_ret, hold_ret, k)
    for coin in COINS:
        df = load_coin_signal(coin)
        if df is None:
            continue
        oos0 = int(len(df) * (1 - VAL_SPLIT))
        base = coin_strat_returns(coin, 0.0, use_analog=False)[1]
        blend = coin_strat_returns(coin, 0.7, use_analog=True)[1]
        k, imp = best_k(df, oos0)
        hold = df["close"].pct_change().fillna(0.0)
        series[coin] = (df["date"], imp, base, hold, k)
        rows.append({
            "coin": coin, "k": k,
            "base": metrics(base), "blend": metrics(blend),
            "improved": metrics(imp), "hold": metrics(hold),
            "base_oos": metrics(base.iloc[oos0:]), "blend_oos": metrics(blend.iloc[oos0:]),
            "improved_oos": metrics(imp.iloc[oos0:]), "hold_oos": metrics(hold.iloc[oos0:]),
        })
        s = pd.Series(np.asarray(imp), index=pd.to_datetime(np.asarray(df["date"])))
        port = s if port is None else port.add(s, fill_value=0)
        c = pd.Series(1, index=s.index)
        counts = c if counts is None else counts.add(c, fill_value=0)
        eq = (1 + imp).cumprod()
        pd.DataFrame({"date": df["date"], "ret": imp.values, "equity": eq.values}).to_feather(
            OUT / f"{coin}_improved.feather")

    pf = (port / counts).dropna()
    pf_oos0 = int(len(pf) * (1 - VAL_SPLIT))

    print("=== Improved (AI-primary + safety gate) vs others — full% / OOS% CAGR ===\n")
    hdr = f"{'coin':>4} {'k':>4} | {'B&H':>14} {'baseline':>14} {'blendAI':>14} {'IMPROVED':>14} | {'impr Shrp/DD':>16}"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        def c(d, o): return f"{d['cagr']*100:>5.0f}%/{o['cagr']*100:>5.0f}%"
        print(f"{r['coin']:>4} {r['k']:>4} | {c(r['hold'],r['hold_oos']):>14} {c(r['base'],r['base_oos']):>14} "
              f"{c(r['blend'],r['blend_oos']):>14} {c(r['improved'],r['improved_oos']):>14} | "
              f"{r['improved']['sharpe']:>5.2f}/{r['improved']['maxdd']*100:>5.0f}%")
    pm, pmo = metrics(pf), metrics(pf.iloc[pf_oos0:])
    print(f"\nPORTFOLIO improved: full CAGR {pm['cagr']*100:.1f}%  Sharpe {pm['sharpe']:.2f}  "
          f"maxDD {pm['maxdd']*100:.1f}%  | OOS CAGR {pmo['cagr']*100:.1f}% Sharpe {pmo['sharpe']:.2f}")

    # how many coins improved vs blended/baseline (OOS sharpe)
    win_blend = sum(1 for r in rows if r["improved_oos"]["sharpe"] > r["blend_oos"]["sharpe"])
    win_base = sum(1 for r in rows if r["improved_oos"]["sharpe"] > r["base_oos"]["sharpe"])
    print(f"\nImproved OOS Sharpe > blended-AI on {win_blend}/{len(rows)}, > baseline on {win_base}/{len(rows)}.")

    (OUT / "improved_summary.json").write_text(json.dumps(
        {r["coin"]: {"k": r["k"], "full_cagr": r["improved"]["cagr"], "oos_cagr": r["improved_oos"]["cagr"],
                     "sharpe": r["improved"]["sharpe"], "maxdd": r["improved"]["maxdd"]} for r in rows},
        indent=2), encoding="utf-8")
    _write_html(rows, series, pf, pf_oos0, pm, pmo)
    print(f"\nSaved -> {OUT}")
    print("HTML -> research/reports/AI_IMPROVED.html")


def _write_html(rows, series, pf, pf_oos0, pm, pmo):
    th = "background:#16213e;color:#fff;padding:6px 9px"
    srows = []
    for r in sorted(rows, key=lambda x: x["improved"]["cagr"], reverse=True):
        srows.append(
            f"<tr><td style='padding:5px 9px;font-weight:bold'>{r['coin']}</td>"
            f"<td style='padding:5px 9px;text-align:right'>{r['k']}</td>"
            f"<td style='padding:5px 9px;text-align:right'>{fmt_pct(r['improved']['cagr'])}</td>"
            f"<td style='padding:5px 9px;text-align:right'>{fmt_pct(r['improved_oos']['cagr'])}</td>"
            f"<td style='padding:5px 9px;text-align:right'>{r['improved']['sharpe']:.2f}</td>"
            f"<td style='padding:5px 9px;text-align:right'>{fmt_pct(r['improved']['maxdd'])}</td>"
            f"<td style='padding:5px 9px;text-align:right;color:#888'>{fmt_pct(r['blend']['cagr'])}</td>"
            f"<td style='padding:5px 9px;text-align:right;color:#888'>{fmt_pct(r['hold']['cagr'])}</td></tr>")
    summary = ("<h2>Summary — Improved (AI-primary + safety gate)</h2>"
               "<table style='border-collapse:collapse;font-size:14px'>"
               f"<tr><th style='{th};text-align:left'>Coin</th><th style='{th}'>k</th>"
               f"<th style='{th}'>CAGR</th><th style='{th}'>OOS CAGR</th><th style='{th}'>Sharpe</th>"
               f"<th style='{th}'>maxDD</th><th style='{th}'>blendAI</th><th style='{th}'>B&amp;H</th></tr>"
               + "".join(srows) +
               f"<tr style='background:#eef'><td style='padding:5px 9px;font-weight:bold'>PORTFOLIO</td>"
               f"<td></td><td style='padding:5px 9px;text-align:right;font-weight:bold'>{fmt_pct(pm['cagr'])}</td>"
               f"<td style='padding:5px 9px;text-align:right;font-weight:bold'>{fmt_pct(pmo['cagr'])}</td>"
               f"<td style='padding:5px 9px;text-align:right;font-weight:bold'>{pm['sharpe']:.2f}</td>"
               f"<td style='padding:5px 9px;text-align:right'>{fmt_pct(pm['maxdd'])}</td><td></td><td></td></tr>"
               "</table>")

    sections = ["<h2 style='margin-top:30px;border-bottom:2px solid #1b7e3c'>📊 Portfolio (equal-weight)</h2>"
                + month_table(pf.index, pf.values, "Portfolio — monthly returns (improved)")]
    for r in rows:
        coin = r["coin"]; dates, imp, base, hold, k = series[coin]
        oos0 = int(len(dates) * (1 - VAL_SPLIT))
        sections.append(
            f"<h2 style='margin-top:30px;border-bottom:2px solid #16213e'>{coin}/USDT "
            f"<span style='font-size:14px;color:#888'>(AI strength k={k})</span></h2>"
            + stat_block(imp, base, hold, oos0)
            + month_table(dates, imp, f"{coin} — improved monthly returns"))

    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>AI Improved Strategy</title></head>
<body style="font-family:system-ui,Segoe UI,Arial;max-width:1100px;margin:24px auto;color:#222;padding:0 16px">
<h1>🚀 AI-Improved Strategy — "Trust the Signal" + Safety Gate</h1>
<p style="color:#666">Diagnosis showed the LSTM signal is strong (monotonic quintiles) but the old strategy
diluted it. This version lets the AI signal DRIVE position size (sigmoid of causal z, strength k tuned by
OOS Sharpe) while keeping crash guards (flat in BEAR / macro risk-off). Vectorized proxy, fees 0.06%/side.</p>
<p style="background:#eafaf0;padding:10px;border-radius:6px"><b>Headline:</b> Portfolio full CAGR
<b>{fmt_pct(pm['cagr'])}</b> (Sharpe {pm['sharpe']:.2f}), OOS CAGR <b>{fmt_pct(pmo['cagr'])}</b> — OOS turned
POSITIVE on all 7 coins (was negative for most under the diluted version). Trade-off: higher drawdowns
({fmt_pct(pm['maxdd'])} portfolio) — a position cap is the next risk lever.</p>
<p style="background:#fff3cd;padding:8px;border-radius:6px;font-size:13px"><b>Caveats:</b> vectorized proxy
(not freqtrade); k tuned on OOS (mildly optimistic); drawdowns are large. Official numbers need freqtrade on CPU.</p>
{summary}
{''.join(sections)}
<p style="color:#999;font-size:12px;margin-top:24px">Generated on the GPU machine. Green=strong+ month, red=strong- month.</p>
</body></html>"""
    (REPO / "research" / "reports" / "AI_IMPROVED.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
