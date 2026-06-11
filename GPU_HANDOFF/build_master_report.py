"""build_master_report.py — one consolidated HTML of the whole AI investigation.

Pulls the saved JSON results together into a single styled page: the honest
journey (optimism -> overfit -> rigorous truth), every key table, and the
verdict. Self-contained HTML, no external assets.

USAGE:  python GPU_HANDOFF/build_master_report.py
Output: research/reports/MASTER_AI_REPORT.html
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TR = REPO / "research" / "dl_models" / "trading_results"
DLM = REPO / "research" / "dl_models"


def load(p, default=None):
    fp = (TR / p) if (TR / p).exists() else (DLM / p)
    return json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else default


wf = load("walkforward_verdict.json", {"coins": [], "portfolio": {}})
ov = load("overlay_summary.json", {})
vp = load("vol_predict.json", [])
sweep = load("sweep_results.json", [])

TH = "background:#16213e;color:#fff;padding:7px 10px;text-align:right;font-size:13px"
TD = "padding:6px 10px;text-align:right;border-bottom:1px solid #eee;font-size:13px"
TDL = TD + ";text-align:left;font-weight:600"


def pct(x):
    return "n/a" if x is None else f"{x*100:+.1f}%"


def row(cells, first_left=True):
    out = []
    for i, c in enumerate(cells):
        out.append(f"<td style='{TDL if (i == 0 and first_left) else TD}'>{c}</td>")
    return "<tr>" + "".join(out) + "</tr>"


def table(headers, rows_html):
    h = "".join(f"<th style='{TH}'>{x}</th>" for x in headers)
    return f"<table style='border-collapse:collapse;width:100%;margin:8px 0'><tr>{h}</tr>{rows_html}</table>"


# --- journey ---
journey = table(
    ["Stage", "What was measured", "Result", "Honest?"],
    row(["1. Single split", "corr / CAGR on last 20%", "+0.47 corr, BTC +37%", "❌ lucky window"]) +
    row(["2. Naive 'improve'", "k tuned on OOS, no costs", "+82% CAGR, OOS +42%", "❌ OVERFIT"]) +
    row(["3. Nested + costs", "tune on val, test held-out", "Portfolio -24%, CI∋0", "✅ collapsed"]) +
    row(["4. Purged walk-forward", "model+k fit on past only", "Sharpe 1.19, CI clears 0", "✅✅ gold std"]) +
    row(["5. + vol-targeting", "risk control", "DD -47%→-23.5%, Sharpe 1.12", "✅ cleaner"]) +
    row(["6. Overlay vs no-AI", "AI vs regime-only base", "same Sharpe, AI REDUNDANT", "✅ decisive"]) +
    row(["7. DL for volatility", "vs EWMA", "ML loses to EWMA", "✅ negative"]))

# --- arch sweep ---
sweep_rows = "".join(row([s["label"], f"{s['per_coin'].get('BTC',{}).get('mean',float('nan')):+.2f}",
                          f"{s['per_coin'].get('ETH',{}).get('mean',float('nan')):+.2f}",
                          f"<b>{s['avg_mean']:+.3f}</b>"]) for s in sweep)
sweep_tbl = table(["Config", "BTC corr", "ETH corr", "Avg"], sweep_rows) if sweep else "<i>no sweep data</i>"

# --- walk-forward (vol-targeted) ---
wf_rows = "".join(row([c["coin"], pct(c["cagr"]), pct(c["bh"]), f"{c['sharpe']:.2f}",
                       f"[{c['ci'][0]:.2f}, {c['ci'][1]:.2f}]", pct(c["maxdd"]),
                       "✅" if c["ci"][0] > 0 else "—"]) for c in wf.get("coins", []))
p = wf.get("portfolio", {})
if p:
    wf_rows += row([f"<b>PORTFOLIO</b>", f"<b>{pct(p['cagr'])}</b>", "—", f"<b>{p['sharpe']:.2f}</b>",
                    f"<b>[{p['ci'][0]:.2f}, {p['ci'][1]:.2f}]</b>", pct(p["maxdd"]),
                    "✅" if p["ci"][0] > 0 else "—"])
wf_tbl = table(["Coin", "AI CAGR", "Buy&Hold", "Sharpe", "Sharpe CI (5-95%)", "maxDD", "Sig?"], wf_rows)

# --- overlay ---
names = {"bh": "Buy&Hold", "regimeLong": "Regime only (NO AI)", "aiStandalone": "AI standalone",
         "ovlGate": "AI overlay (gate)", "ovlMult": "AI overlay (scale)"}
ov_rows = "".join(row([names.get(k, k), pct(v["cagr"]), f"{v['sharpe']:.2f}", pct(v["maxdd"])])
                  for k, v in ov.items())
ov_tbl = table(["Variant", "CAGR", "Sharpe", "maxDD"], ov_rows) if ov else "<i>no overlay data</i>"

# --- vol prediction ---
vp_rows = "".join(row([r["coin"], f"{r['ml']['corr']:.3f}", f"{r['naive']['corr']:.3f}",
                       f"<b>{r['ewma']['corr']:.3f}</b>"]) for r in vp)
vp_tbl = table(["Coin", "ML (LSTM) corr", "rolling-std", "EWMA"], vp_rows) if vp else "<i>no vol data</i>"

html = f"""<!doctype html><html><head><meta charset="utf-8"><title>AI Trading Investigation - Master Report</title></head>
<body style="font-family:system-ui,Segoe UI,Arial;max-width:1080px;margin:24px auto;color:#222;padding:0 18px;line-height:1.5">
<h1>🤖 AI Trading Investigation — Master Report</h1>
<p style="color:#666">Can deep learning improve the deployed crypto strategies? Full investigation on the
GPU machine. Every number below is from purged walk-forward (model trained on past only) with realistic
costs unless noted — this is the honest standard after single-split numbers misled us repeatedly.</p>

<div style="background:#fff3cd;border-left:4px solid #e0a800;padding:12px 16px;border-radius:6px;margin:16px 0">
<b>VERDICT:</b> The AI signal correlation was real (+0.41) but does <b>NOT</b> produce a tradable edge after
costs on truly unseen data. For <b>direction</b> it is redundant with the macro/regime features it was trained on;
for <b>volatility</b> it loses to a one-line EWMA. The flashy +82% CAGR was overfit. <b>Lasting value:</b> the
rigorous testing methodology + vol-targeting (halved drawdown) + the practical EWMA tip.
</div>

<h2>1. The journey — escalating rigor</h2>
<p style="color:#666">Each stage stripped optimism from the previous one.</p>
{journey}

<h2>2. Model architecture sweep (1d, walk-forward correlation)</h2>
<p style="color:#666">Transformer was the best architecture; MSE the worst loss. (corr only — not yet PnL.)</p>
{sweep_tbl}

<h2>3. Purged walk-forward + vol-targeting (realistic costs)</h2>
<p style="color:#666">Every prediction out-of-sample, k fixed, fees 0.075% + slippage 0.05%, vol-targeted + 0.8 cap.</p>
{wf_tbl}

<h2>4. The decisive test — AI vs a NO-AI base (overlay)</h2>
<p style="color:#666">"Regime only" uses NO AI. It matches the AI's Sharpe at higher return ⇒ the AI adds no
risk-adjusted value; its only effect is de-risking, which vol-targeting already provides.</p>
{ov_tbl}

<h2>5. DL for volatility — also loses to EWMA</h2>
<p style="color:#666">Forward-realized-vol forecast correlation (purged WF). EWMA(0.94) wins.</p>
{vp_tbl}

<h2>6. Timeframe (earlier finding)</h2>
<p style="color:#666">The signal exists only on the daily frame — intraday (4h/1h/15m) collapses to ~+0.05 noise,
because the edge comes from daily macro/halving features.</p>

<h2>Conclusion &amp; honest next levers</h2>
<ul>
<li>DL adds <b>no edge</b> over simple methods on this daily OHLCV+macro data (direction redundant, vol &lt; EWMA).</li>
<li>Real DL value would need <b>orthogonal / higher-frequency</b> data (on-chain, order-flow, sentiment).</li>
<li><b>vol-targeting</b> (use EWMA, not rolling-std) is a genuine, model-free improvement: ~halved drawdown.</li>
<li>The official AnalogV3-vs-AnalogV2 call still needs the <b>freqtrade 9-year backtest on the CPU machine</b>.</li>
</ul>

<h2>Detailed reports</h2>
<ul>
<li>VERIFICATION_VERDICT.md — full level-by-level write-up</li>
<li>AI_IMPROVED.html / AI_STRATEGY_IMPROVEMENT.html — per-coin year + month-by-month</li>
<li>LSTM_EXPERIMENTS.md — architecture / timeframe / funding experiments</li>
<li>raw: research/dl_models/trading_results/*.json + wf_signal_*.feather</li>
</ul>
<p style="color:#999;font-size:12px;margin-top:20px">Generated on the GPU machine (RTX A3000). Branch gpu/lstm-v1-btc.
Vectorized proxy for PnL; official numbers require freqtrade on the CPU machine.</p>
</body></html>"""

out = REPO / "research" / "reports" / "MASTER_AI_REPORT.html"
out.write_text(html, encoding="utf-8")
print(f"Wrote {out}")
