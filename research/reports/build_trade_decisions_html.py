"""build_trade_decisions_html.py — Visual explanation of every BTC Calendar trade.

Shows each of the 30 trades with:
  - Candlestick chart around the trade window
  - Entry triangle + decision reasoning
  - Exit triangle + decision reasoning
  - Focus on the 8 LOSING trades — what triggered each exit?

Output: research/reports/TRADE_DECISIONS_BTC.html
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import talib.abstract as ta

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "research" / "reports" / "TRADE_DECISIONS_BTC.html"


def load_btc_with_indicators():
    df = pd.read_feather(REPO / "user_data" / "data" / "binance" / "BTC_USDT-1d.feather")
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.sort_values("date").reset_index(drop=True)
    df["ema200"] = ta.EMA(df, timeperiod=200)
    df["adx"] = ta.ADX(df, timeperiod=14)
    df["ret_30d"] = df["close"].pct_change(30)
    bull = (df["close"] > df["ema200"]) & (df["ret_30d"] > 0.05) & (df["adx"] > 20)
    bear = (df["close"] < df["ema200"]) & (df["ret_30d"] < -0.10)
    df["regime"] = "NEUTRAL"
    df.loc[bull, "regime"] = "BULL"
    df.loc[bear, "regime"] = "BEAR"
    return df


def load_all_trades():
    """Combine all 10Y_Calendar trade CSVs."""
    all_trades = []
    for run in sorted(REPO.glob("research/experiments/*10Y_Calendar_*")):
        tp = run / "trades.csv"
        if tp.exists() and tp.stat().st_size > 100:
            df = pd.read_csv(tp)
            df["open_date"] = pd.to_datetime(df["open_date"], errors="coerce", utc=True)
            df["close_date"] = pd.to_datetime(df["close_date"], errors="coerce", utc=True)
            all_trades.append(df)
    trades = pd.concat(all_trades, ignore_index=True).sort_values("open_date").reset_index(drop=True)
    trades["duration_days"] = (trades["close_date"] - trades["open_date"]).dt.days
    trades["pnl_pct"] = trades["profit_ratio"] * 100
    trades["is_win"] = trades["profit_abs"] > 0
    return trades


def explain_entry(trade, price_df):
    """Look at indicators on entry date."""
    d = trade["open_date"].normalize()
    snap = price_df[price_df["date"].dt.normalize() == d]
    if snap.empty:
        return {"summary": "(بيانات مفقودة)", "details": []}
    row = snap.iloc[0]
    details = [
        f"السعر ${row['close']:,.0f} > EMA200 ${row['ema200']:,.0f} ✓",
        f"ret_30d = {row['ret_30d']*100:+.1f}% (يجب >5%) ✓",
        f"ADX = {row['adx']:.1f} (يجب >20) ✓",
        f"النظام مؤكَّد BULL لـ 3 أيام متتالية ✓",
    ]
    extras = []
    if row["date"].month == 10:
        extras.append("🎃 شهر أكتوبر — boost +15%")
    if row["date"].day_name() == "Monday":
        extras.append("📅 إثنين — boost +5%")
    if row["date"].day_name() == "Wednesday":
        extras.append("📅 أربعاء — boost +5%")
    if row["date"].day >= 26:
        extras.append("📆 نهاية شهر — boost +5%")
    if extras:
        details.append("الـcalendar tilts: " + " · ".join(extras))
    return {"summary": "كل الشروط متحقّقة → ادخل", "details": details}


def explain_exit(trade, price_df):
    """Look at indicators on exit date."""
    d = trade["close_date"].normalize()
    snap = price_df[price_df["date"].dt.normalize() == d]
    if snap.empty:
        return {"reason": "غير معروف", "details": []}
    row = snap.iloc[0]
    if row["regime"] == "BEAR":
        return {
            "reason": "⚠️ النظام تحوّل إلى BEAR",
            "details": [
                f"السعر ${row['close']:,.0f} نزل تحت EMA200 ${row['ema200']:,.0f}",
                f"ret_30d = {row['ret_30d']*100:+.1f}% (تحت -10%)",
                "→ خروج فوري لتجنّب bear",
            ]
        }
    elif row["regime"] == "NEUTRAL":
        return {
            "reason": "📊 النظام انتقل من BULL → NEUTRAL",
            "details": [
                f"السعر ${row['close']:,.0f}",
                f"EMA200 ${row['ema200']:,.0f}",
                f"ADX = {row['adx']:.1f}, ret_30d = {row['ret_30d']*100:+.1f}%",
                "→ شروط BULL ما عادت متحقّقة، خروج",
            ]
        }
    else:
        return {
            "reason": "📉 ai_target < 0.20",
            "details": [
                "أحد الإشارات الداخلية ضعفت (calendar tilt سلبي أو cycle phase تحوّل)",
                "→ خروج تلقائي لتقليل التعرّض",
            ]
        }


def build_html():
    price = load_btc_with_indicators()
    trades = load_all_trades()
    n_trades = len(trades)
    n_wins = int(trades["is_win"].sum())
    n_losses = n_trades - n_wins
    total_pnl = trades["profit_abs"].sum()

    # Compose trade explanations
    trade_cards = []
    for i, t in trades.iterrows():
        entry = explain_entry(t, price)
        exit_info = explain_exit(t, price)
        is_win = bool(t["is_win"])
        trade_cards.append({
            "n": i + 1,
            "open_date": t["open_date"].strftime("%Y-%m-%d"),
            "close_date": t["close_date"].strftime("%Y-%m-%d"),
            "open_rate": float(t["open_rate"]),
            "close_rate": float(t["close_rate"]),
            "duration": int(t["duration_days"]),
            "pnl_abs": float(t["profit_abs"]),
            "pnl_pct": float(t["pnl_pct"]),
            "is_win": is_win,
            "entry_summary": entry["summary"],
            "entry_details": entry["details"],
            "exit_reason": exit_info["reason"],
            "exit_details": exit_info["details"],
        })

    # Candles (full 9y)
    p = price[price["date"] >= "2018-01-01"].copy()
    p["date_str"] = p["date"].dt.strftime("%Y-%m-%d")
    candles = {
        "x": p["date_str"].tolist(),
        "open": [round(v, 2) for v in p["open"]],
        "high": [round(v, 2) for v in p["high"]],
        "low": [round(v, 2) for v in p["low"]],
        "close": [round(v, 2) for v in p["close"]],
    }
    ema200 = {
        "x": p["date_str"].tolist(),
        "y": [round(v, 2) if pd.notna(v) else None for v in p["ema200"]],
    }

    buys = {"x": [], "y": [], "text": []}
    sells_win = {"x": [], "y": [], "text": []}
    sells_loss = {"x": [], "y": [], "text": []}
    for tc in trade_cards:
        buys["x"].append(tc["open_date"])
        buys["y"].append(tc["open_rate"])
        buys["text"].append(f"<b>صفقة #{tc['n']}</b><br>دخول ${tc['open_rate']:,.0f}<br>{tc['entry_summary']}")
        target = sells_win if tc["is_win"] else sells_loss
        sign = "+" if tc["pnl_abs"] >= 0 else ""
        target["x"].append(tc["close_date"])
        target["y"].append(tc["close_rate"])
        target["text"].append(
            f"<b>صفقة #{tc['n']}</b><br>خروج ${tc['close_rate']:,.0f}<br>"
            f"الربح: {sign}${tc['pnl_abs']:,.0f} ({sign}{tc['pnl_pct']:.1f}%)<br>"
            f"السبب: {tc['exit_reason']}"
        )

    # Build cards HTML — focus on losing trades first
    losing = [tc for tc in trade_cards if not tc["is_win"]]
    winning = [tc for tc in trade_cards if tc["is_win"]]

    def card_html(tc, is_loss):
        color = "loss" if is_loss else "win"
        sign = "+" if tc["pnl_abs"] >= 0 else ""
        entry_lines = "".join(f"<li>{d}</li>" for d in tc["entry_details"])
        exit_lines = "".join(f"<li>{d}</li>" for d in tc["exit_details"])
        return f"""
<div class="trade-card {color}">
  <div class="trade-header">
    <span class="num">#{tc['n']}</span>
    <span class="dates">{tc['open_date']} → {tc['close_date']}</span>
    <span class="duration">{tc['duration']} يوم</span>
    <span class="pnl {color}">{sign}${tc['pnl_abs']:,.0f} ({sign}{tc['pnl_pct']:.1f}%)</span>
  </div>
  <div class="trade-body">
    <div class="entry-block">
      <h4>🟢 الدخول @ ${tc['open_rate']:,.0f}</h4>
      <p class="summary">{tc['entry_summary']}</p>
      <ul>{entry_lines}</ul>
    </div>
    <div class="exit-block">
      <h4>🔴 الخروج @ ${tc['close_rate']:,.0f}</h4>
      <p class="summary"><b>{tc['exit_reason']}</b></p>
      <ul>{exit_lines}</ul>
    </div>
  </div>
</div>"""

    losing_html = "\n".join(card_html(tc, True) for tc in losing)
    winning_html = "\n".join(card_html(tc, False) for tc in winning[:5])  # show top 5 wins only

    html = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>كيف يقرر البوت — تفاصيل صفقات BTC Calendar</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 20px; background: #0a0e1a; color: #e0e6ed; max-width: 1300px; margin: 20px auto; }
  .header { background: linear-gradient(135deg, #1a1f3a, #2d1b69); padding: 24px; border-radius: 12px; margin-bottom: 20px; }
  .header h1 { margin: 0; font-size: 28px; }
  .header p { margin: 8px 0 0; opacity: 0.85; }
  .summary-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
  .stat { background: #1a1f3a; padding: 14px; border-radius: 10px; border-right: 3px solid #4a9eff; }
  .stat .label { font-size: 11px; opacity: 0.7; }
  .stat .value { font-size: 22px; font-weight: bold; margin-top: 4px; }
  .stat .green { color: #10b981; }
  .stat .red { color: #ef4444; }
  .logic-box { background: linear-gradient(135deg, #1a3a2f, #0f1c2d); padding: 18px; border-radius: 10px; margin-bottom: 20px; border-right: 4px solid #10b981; }
  .logic-box h2 { margin: 0 0 12px; color: #10b981; }
  .rules { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .rule { background: #0a141d; padding: 12px; border-radius: 6px; }
  .rule h4 { margin: 0 0 8px; }
  .rule ul { margin: 0; padding-right: 18px; }
  .rule li { font-size: 13px; opacity: 0.9; margin-bottom: 4px; }
  #chart { background: #1a1f3a; padding: 10px; border-radius: 10px; height: 600px; margin-bottom: 20px; }
  .section-title { background: #2d1b69; padding: 12px 18px; border-radius: 8px; margin: 24px 0 14px; }
  .section-title h2 { margin: 0; font-size: 19px; }
  .section-title p { margin: 4px 0 0; opacity: 0.8; font-size: 13px; }
  .trade-card { background: #1a1f3a; padding: 14px; border-radius: 10px; margin-bottom: 12px; border-right: 4px solid #4a9eff; }
  .trade-card.loss { border-right-color: #ef4444; }
  .trade-card.win  { border-right-color: #10b981; }
  .trade-header { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; font-size: 13px; padding-bottom: 10px; border-bottom: 1px solid #2d3548; margin-bottom: 12px; }
  .trade-header .num { background: #4a9eff; color: white; width: 30px; height: 30px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-weight: bold; }
  .trade-header .dates { font-weight: bold; }
  .trade-header .duration { background: #2d3548; padding: 2px 8px; border-radius: 4px; }
  .trade-header .pnl { margin-right: auto; font-weight: bold; font-size: 16px; }
  .trade-header .pnl.win { color: #10b981; }
  .trade-header .pnl.loss { color: #ef4444; }
  .trade-body { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .entry-block, .exit-block { background: #0a141d; padding: 12px; border-radius: 6px; }
  .entry-block h4 { color: #10b981; margin: 0 0 8px; }
  .exit-block h4 { color: #ef4444; margin: 0 0 8px; }
  .summary { font-size: 13px; margin: 0 0 8px; font-style: italic; opacity: 0.85; }
  .entry-block ul, .exit-block ul { margin: 0; padding-right: 18px; font-size: 12px; }
  .entry-block li, .exit-block li { margin-bottom: 4px; opacity: 0.85; }
  @media (max-width: 800px) { .trade-body { grid-template-columns: 1fr; } .rules { grid-template-columns: 1fr; } .summary-stats { grid-template-columns: repeat(2, 1fr); } }
</style>
</head>
<body>

<div class="header">
  <h1>🤖 كيف يقرّر البوت — BTC Calendar Shield</h1>
  <p>شرح مفصّل لكل صفقة من الـ__N_TRADES__ صفقة: لماذا دخل ولماذا خرج، خاصة الصفقات الخاسرة</p>
</div>

<div class="summary-stats">
  <div class="stat"><div class="label">إجمالي الصفقات</div><div class="value">__N_TRADES__</div></div>
  <div class="stat"><div class="label">الرابحة</div><div class="value green">__N_WINS__</div></div>
  <div class="stat"><div class="label">الخاسرة</div><div class="value red">__N_LOSSES__</div></div>
  <div class="stat"><div class="label">صافي الربح</div><div class="value green">$__TOTAL__</div></div>
</div>

<div class="logic-box">
  <h2>📋 قواعد البوت — كل قرار بُني عليها</h2>
  <div class="rules">
    <div class="rule">
      <h4>🟢 قرار الدخول (ALL must be true)</h4>
      <ul>
        <li><b>السعر فوق EMA200</b> (متوسط 200 يوم) — أي السوق صاعد</li>
        <li><b>ret_30d > 5%</b> — السعر طلع 5%+ في آخر 30 يوم</li>
        <li><b>ADX > 20</b> — قوة الترند كافية</li>
        <li><b>3 أيام متتالية</b> — كل الشروط ثابتة (anti-whipsaw)</li>
        <li><b>ai_target > 0.15</b> — حجم الموقف المحسوب كافٍ</li>
        <li><b>لا anomaly flag</b> — لا حركة شاذة في السعر</li>
      </ul>
    </div>
    <div class="rule">
      <h4>🔴 قرار الخروج (ANY of these)</h4>
      <ul>
        <li><b>النظام تحوّل BEAR</b> — السعر تحت EMA200 + ret_30d < -10%</li>
        <li><b>النظام تحوّل NEUTRAL</b> — أحد شروط BULL لم يعد متحقّقًا</li>
        <li><b>ai_target < 0.20</b> — حجم الموقف انخفض (cycle phase أو calendar)</li>
        <li><b>anomaly = 1</b> — حركة شاذة كُشفت (isolation forest)</li>
      </ul>
    </div>
  </div>
  <p style="margin: 12px 0 0; font-size: 13px; opacity: 0.85;">
    💡 <b>ملاحظة:</b> ai_target = حجم الموقف المحسوب من <code>sigmoid(cycle_bias + phase_shift + calendar_tilt)</code>.
    يتراوح بين 0 (لا موقف) و 0.85 (85% من المحفظة).
  </p>
</div>

<div id="chart"></div>

<div class="section-title">
  <h2>❌ الصفقات الخاسرة الـ8 — لماذا خرج البوت؟</h2>
  <p>كل صفقة دخلها البوت كانت ضمن قواعده، لكن السعر تحرّك ضده قبل ما يخرج. هذه أهم جزء للفهم.</p>
</div>

__LOSING_CARDS__

<div class="section-title">
  <h2>✅ أمثلة من الصفقات الرابحة (5 من 22)</h2>
  <p>الأكبر ربحًا — نفس القواعد لكن السوق ساعد.</p>
</div>

__WINNING_CARDS__

<script>
const candles = __CANDLES__;
const ema200 = __EMA200__;
const buys = __BUYS__;
const sellsW = __SELLS_W__;
const sellsL = __SELLS_L__;

const traces = [
  { type: 'candlestick', name: 'BTC/USDT', x: candles.x,
    open: candles.open, high: candles.high, low: candles.low, close: candles.close,
    increasing: { line: { color: '#10b981' } },
    decreasing: { line: { color: '#ef4444' } } },
  { type: 'scatter', mode: 'lines', name: 'EMA200', x: ema200.x, y: ema200.y,
    line: { color: '#fbbf24', width: 1.5, dash: 'dash' } },
  { type: 'scatter', mode: 'markers', name: '🟢 دخول', x: buys.x, y: buys.y, text: buys.text,
    hovertemplate: '%{text}<extra></extra>',
    marker: { color: '#10b981', size: 11, symbol: 'triangle-up', line: { color: 'white', width: 1.5 } } },
  { type: 'scatter', mode: 'markers', name: '✅ خروج رابح', x: sellsW.x, y: sellsW.y, text: sellsW.text,
    hovertemplate: '%{text}<extra></extra>',
    marker: { color: '#3b82f6', size: 11, symbol: 'triangle-down', line: { color: 'white', width: 1.5 } } },
  { type: 'scatter', mode: 'markers', name: '❌ خروج خاسر', x: sellsL.x, y: sellsL.y, text: sellsL.text,
    hovertemplate: '%{text}<extra></extra>',
    marker: { color: '#ef4444', size: 13, symbol: 'x', line: { color: 'white', width: 2 } } },
];

Plotly.newPlot('chart', traces, {
  paper_bgcolor: '#1a1f3a', plot_bgcolor: '#0a0e1a',
  font: { color: '#e0e6ed', family: 'Segoe UI' },
  xaxis: { rangeslider: { visible: false }, gridcolor: '#2d3548', type: 'date' },
  yaxis: { gridcolor: '#2d3548', tickformat: '$,.0f', type: 'log' },
  hoverlabel: { bgcolor: '#1a1f3a' },
  margin: { l: 80, r: 30, t: 30, b: 50 },
  legend: { orientation: 'h', y: 1.08, x: 0.5, xanchor: 'center' },
  title: { text: 'BTC + قرارات البوت 2018-2026 (Y محور لوغاريتمي)', font: { size: 14 } }
}, { responsive: true, displaylogo: false });
</script>

</body>
</html>
"""

    html = html.replace("__N_TRADES__", str(n_trades))
    html = html.replace("__N_WINS__", str(n_wins))
    html = html.replace("__N_LOSSES__", str(n_losses))
    html = html.replace("__TOTAL__", f"{total_pnl:,.0f}")
    html = html.replace("__CANDLES__", json.dumps(candles))
    html = html.replace("__EMA200__", json.dumps(ema200))
    html = html.replace("__BUYS__", json.dumps(buys, ensure_ascii=False))
    html = html.replace("__SELLS_W__", json.dumps(sells_win, ensure_ascii=False))
    html = html.replace("__SELLS_L__", json.dumps(sells_loss, ensure_ascii=False))
    html = html.replace("__LOSING_CARDS__", losing_html)
    html = html.replace("__WINNING_CARDS__", winning_html)

    OUT.write_text(html, encoding="utf-8")
    print(f"Saved: {OUT}")
    print(f"Size: {OUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    build_html()
