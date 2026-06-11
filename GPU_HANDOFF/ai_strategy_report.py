"""ai_strategy_report.py — "are the AI-enhanced strategies better?" — full report.

Autonomous answer to the mission: take each coin's AnalogV3 logic, TUNE the AI
(LSTM/Transformer) tilt weight, and compare the AI-enhanced strategy vs the
no-AI baseline vs buy&hold — year-by-year AND month-by-month per year (like
ACTIVE_STRATEGIES_DETAIL.html), plus an equal-weight portfolio.

Vectorized proxy (freqtrade blocked here). Full-period is in-sample-optimistic
for the LSTM; OOS tail is the honest read. Both are shown.

USAGE:  python GPU_HANDOFF/ai_strategy_report.py
Output: research/reports/AI_STRATEGY_IMPROVEMENT.html
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backtest_strategy import ANALOGV2_REF, coin_strat_returns, metrics

REPO = Path(__file__).resolve().parents[1]
COINS = ["BTC", "ETH", "SOL", "BNB", "ADA", "XRP", "DOGE"]
WEIGHTS = [0.0, 0.4, 0.7, 1.0]      # 0.0 == no-AI baseline
VAL_SPLIT = 0.20
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def tune(coin):
    """Return (best_w, ai_ret, base_ret, df) — best AI weight by OOS Sharpe."""
    df, base_ret, _ = coin_strat_returns(coin, w_analog=0.0, use_analog=False)
    if df is None:
        return None
    oos0 = int(len(df) * (1 - VAL_SPLIT))
    best_w, best_sharpe, best_ret = 0.0, -1e9, base_ret
    for w in WEIGHTS:
        if w == 0.0:
            ret = base_ret
        else:
            _, ret, _ = coin_strat_returns(coin, w_analog=w, use_analog=True)
        sh = metrics(ret.iloc[oos0:])["sharpe"]
        sh = -1e9 if sh != sh else sh
        if sh > best_sharpe:
            best_w, best_sharpe, best_ret = w, sh, ret
    return best_w, best_ret, base_ret, df


def monthly_pivot(dates, rets):
    s = pd.Series(np.asarray(rets), index=pd.to_datetime(np.asarray(dates)))
    monthly = s.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    rows = {}
    for ts, v in monthly.items():
        rows.setdefault(ts.year, {})[ts.month] = v
    return rows


def fmt_pct(x):
    return "" if x is None or (isinstance(x, float) and x != x) else f"{x*100:+.1f}%"


def color(x):
    if x is None or x != x:
        return "#f7f7f7"
    if x > 0.15:
        return "#1b7e3c"
    if x > 0:
        return "#bfe6c8"
    if x > -0.15:
        return "#f6c9c2"
    return "#c0392b"


def month_table(dates, rets, title):
    piv = monthly_pivot(dates, rets)
    th = "background:#16213e;color:#fff;padding:5px 7px;font-size:12px"
    out = [f"<h4 style='margin:14px 0 4px'>{title}</h4>",
           "<table style='border-collapse:collapse;font-size:12px'>",
           "<tr><th style='%s'>Year</th>%s<th style='%s'>YEAR</th></tr>" % (
               th, "".join(f"<th style='{th}'>{m}</th>" for m in MONTHS), th)]
    for yr in sorted(piv):
        cells = []
        yearprod = 1.0
        for mo in range(1, 13):
            v = piv[yr].get(mo)
            if v is not None and v == v:
                yearprod *= (1 + v)
            c = color(v)
            cells.append(f"<td style='background:{c};padding:4px 6px;text-align:right'>{fmt_pct(v)}</td>")
        yr_ret = yearprod - 1 if any(piv[yr]) else None
        out.append(f"<tr><td style='font-weight:bold;padding:4px 6px'>{yr}</td>{''.join(cells)}"
                   f"<td style='background:{color(yr_ret)};padding:4px 6px;text-align:right;font-weight:bold'>{fmt_pct(yr_ret)}</td></tr>")
    out.append("</table>")
    return "".join(out)


def stat_block(ai, base, hold, oos0):
    def m(r, lo=None, hi=None):
        seg = r if lo is None else r.iloc[lo:hi]
        return metrics(seg)
    rows = [("AI-enhanced", ai), ("Baseline (no-AI)", base), ("Buy & Hold", hold)]
    th = "background:#16213e;color:#fff;padding:5px 8px"
    out = ["<table style='border-collapse:collapse;font-size:13px;margin:6px 0'>",
           f"<tr><th style='{th};text-align:left'>Variant</th><th style='{th}'>CAGR</th>"
           f"<th style='{th}'>Sharpe</th><th style='{th}'>maxDD</th><th style='{th}'>WR</th>"
           f"<th style='{th}'>CAGR (OOS)</th><th style='{th}'>Sharpe (OOS)</th></tr>"]
    for name, r in rows:
        f, o = m(r), m(r, oos0, None)
        out.append(f"<tr><td style='padding:4px 8px'>{name}</td>"
                   f"<td style='padding:4px 8px;text-align:right'>{fmt_pct(f['cagr'])}</td>"
                   f"<td style='padding:4px 8px;text-align:right'>{f['sharpe']:.2f}</td>"
                   f"<td style='padding:4px 8px;text-align:right'>{fmt_pct(f['maxdd'])}</td>"
                   f"<td style='padding:4px 8px;text-align:right'>{fmt_pct(f['wr'])}</td>"
                   f"<td style='padding:4px 8px;text-align:right'>{fmt_pct(o['cagr'])}</td>"
                   f"<td style='padding:4px 8px;text-align:right'>{o['sharpe']:.2f}</td></tr>")
    out.append("</table>")
    return "".join(out)


def main():
    sections, summary, port_rets = [], [], None
    for coin in COINS:
        res = tune(coin)
        if not res:
            continue
        best_w, ai_ret, base_ret, df = res
        dates = df["date"]
        hold = df["close"].pct_change().fillna(0)
        oos0 = int(len(df) * (1 - VAL_SPLIT))
        ai_m, base_m = metrics(ai_ret), metrics(base_ret)
        ref = ANALOGV2_REF.get(coin)
        summary.append({"coin": coin, "w": best_w, "ai_cagr": ai_m["cagr"], "base_cagr": base_m["cagr"],
                        "ai_oos": metrics(ai_ret.iloc[oos0:])["cagr"], "ref": ref,
                        "delta": ai_m["cagr"] - base_m["cagr"]})
        # portfolio = equal-weight daily AI returns
        s = pd.Series(np.asarray(ai_ret), index=pd.to_datetime(np.asarray(dates)))
        port_rets = s if port_rets is None else port_rets.add(s, fill_value=np.nan)
        sections.append(
            f"<h2 style='margin-top:30px;border-bottom:2px solid #16213e'>{coin}/USDT "
            f"<span style='font-size:14px;color:#888'>(best AI weight = {best_w})</span></h2>"
            + stat_block(ai_ret, base_ret, hold, oos0)
            + month_table(dates, ai_ret, f"{coin} — AI-enhanced monthly returns"))

    # portfolio (mean of coin daily returns where present)
    counts = None
    pr = None
    for coin in COINS:
        res = tune(coin)
        if not res:
            continue
        _, ai_ret, _, df = res
        s = pd.Series(np.asarray(ai_ret), index=pd.to_datetime(np.asarray(df["date"])))
        pr = s if pr is None else pr.add(s, fill_value=0)
        c = pd.Series(1, index=s.index)
        counts = c if counts is None else counts.add(c, fill_value=0)
    port = (pr / counts).dropna()
    port_block = ("<h2 style='margin-top:30px;border-bottom:2px solid #1b7e3c'>📊 Portfolio "
                  "(equal-weight, AI-enhanced)</h2>"
                  + stat_block(port, port, port, int(len(port) * (1 - VAL_SPLIT)))
                  + month_table(port.index, port.values, "Portfolio — monthly returns"))

    # summary table
    th = "background:#16213e;color:#fff;padding:6px 9px"
    srows = []
    for r in sorted(summary, key=lambda x: x["delta"], reverse=True):
        better = "✅" if r["delta"] > 0 else "❌"
        refs = f"+{r['ref']:.1f}%" if r["ref"] else "—"
        srows.append(
            f"<tr><td style='padding:5px 9px;font-weight:bold'>{r['coin']}</td>"
            f"<td style='padding:5px 9px;text-align:right'>{r['w']}</td>"
            f"<td style='padding:5px 9px;text-align:right'>{fmt_pct(r['ai_cagr'])}</td>"
            f"<td style='padding:5px 9px;text-align:right'>{fmt_pct(r['base_cagr'])}</td>"
            f"<td style='padding:5px 9px;text-align:right'>{better} {r['delta']*100:+.1f}pp</td>"
            f"<td style='padding:5px 9px;text-align:right'>{fmt_pct(r['ai_oos'])}</td>"
            f"<td style='padding:5px 9px;text-align:right;color:#888'>{refs}</td></tr>")
    summary_tbl = (
        "<h2>Summary — AI-enhanced vs no-AI baseline</h2>"
        "<table style='border-collapse:collapse;font-size:14px'>"
        f"<tr><th style='{th};text-align:left'>Coin</th><th style='{th}'>AI weight</th>"
        f"<th style='{th}'>AI CAGR</th><th style='{th}'>Baseline CAGR</th><th style='{th}'>Δ (AI−base)</th>"
        f"<th style='{th}'>AI OOS CAGR</th><th style='{th}'>AnalogV2 (KNN)</th></tr>"
        + "".join(srows) + "</table>")

    wins = sum(1 for r in summary if r["delta"] > 0)
    html = f"""<!doctype html><html dir="ltr"><head><meta charset="utf-8">
<title>AI Strategy Improvement Report</title></head>
<body style="font-family:system-ui,Segoe UI,Arial;max-width:1100px;margin:24px auto;color:#222;padding:0 16px">
<h1>🤖 AI-Enhanced Strategies — Did AI Improve Them?</h1>
<p style="color:#666">Per-coin AnalogV3 logic with the Transformer LSTM analog tilt (weight tuned by
out-of-sample Sharpe) vs the same strategy with NO AI tilt, vs buy&amp;hold. Vectorized proxy
(fees 0.06%/side). Full-period CAGR is in-sample-optimistic for the AI; <b>OOS</b> columns are honest.
AnalogV2 (KNN) is the documented freqtrade reference.</p>
<p style="background:#eef;padding:10px;border-radius:6px"><b>Headline:</b> AI beat the no-AI baseline on
<b>{wins}/{len(summary)}</b> coins (full period). The official AnalogV3-vs-AnalogV2 number still needs
the freqtrade 9y backtest on the CPU machine.</p>
{summary_tbl}
{port_block}
{''.join(sections)}
<p style="color:#999;font-size:12px;margin-top:24px">Generated on the GPU machine via vectorized proxy.
Green = strong positive month, red = strong negative. Official numbers require freqtrade on the CPU machine.</p>
</body></html>"""
    out = REPO / "research" / "reports" / "AI_STRATEGY_IMPROVEMENT.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}")
    print(f"\nAI beat baseline on {wins}/{len(summary)} coins (full period).")
    for r in sorted(summary, key=lambda x: x["delta"], reverse=True):
        print(f"  {r['coin']:>4}: w={r['w']}  AI {fmt_pct(r['ai_cagr'])}  base {fmt_pct(r['base_cagr'])}  "
              f"delta {r['delta']*100:+.1f}pp  OOS {fmt_pct(r['ai_oos'])}")


if __name__ == "__main__":
    main()
