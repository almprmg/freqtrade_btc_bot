"""Build interactive HTML candlestick chart of XRP Calendar Shield trades.

Uses Plotly.js for proper Japanese candlesticks + trade markers.

Output: research/reports/xrp_trades_chart.html (open in browser)
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import talib.abstract as ta

REPO = Path(__file__).resolve().parents[2]
OUT_HTML = REPO / "research" / "reports" / "xrp_trades_chart.html"


def load_trades():
    runs = sorted(REPO.glob("research/experiments/*XRP_FULL5Y*"))
    trades = pd.read_csv(runs[-1] / "trades.csv")
    trades["open_date"] = pd.to_datetime(trades["open_date"])
    trades["close_date"] = pd.to_datetime(trades["close_date"])
    return trades


def load_price_with_indicators():
    df = pd.read_feather(REPO / "user_data" / "data" / "binance" / "XRP_USDT-1d.feather")
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
    df["month"] = df["date"].dt.month
    df["dow"] = df["date"].dt.day_name()
    return df[df["date"] >= "2021-01-01"].reset_index(drop=True)


def explain_entry(trade_row, price_df):
    entry_date = trade_row["open_date"].normalize()
    snap = price_df[price_df["date"].dt.normalize() == entry_date]
    if snap.empty:
        return "data not found"
    row = snap.iloc[0]
    parts = []
    parts.append(f"السعر ${row['close']:.4f} > EMA200 ${row['ema200']:.4f} ✓")
    parts.append(f"ret_30d {row['ret_30d']*100:+.1f}% > 5% ✓")
    parts.append(f"ADX {row['adx']:.1f} > 20 ✓")
    tilts = []
    if row['month'] == 10: tilts.append("🎃 Oct +15%")
    if row['month'] == 7: tilts.append("July +5%")
    if row['dow'] == "Monday": tilts.append("Mon +5%")
    if row['dow'] == "Wednesday": tilts.append("Wed +5%")
    if tilts:
        parts.append("Calendar boost: " + " ".join(tilts))
    return " · ".join(parts)


def explain_exit(trade_row, price_df):
    exit_date = trade_row["close_date"].normalize()
    snap = price_df[price_df["date"].dt.normalize() == exit_date]
    if snap.empty:
        return "n/a"
    row = snap.iloc[0]
    if row["regime"] == "BEAR":
        return f"⚠️ BEAR — السعر تحت EMA200 ({row['close']:.4f} < {row['ema200']:.4f}), ret_30d {row['ret_30d']*100:+.1f}%"
    elif row["regime"] == "NEUTRAL":
        return f"📊 الخروج من BULL — ADX {row['adx']:.1f}, ret_30d {row['ret_30d']*100:+.1f}%"
    else:
        return "ai_target < 0.20"


def build_html(price_df, trades):
    p = price_df.copy()
    p["date_str"] = p["date"].dt.strftime("%Y-%m-%d")

    # Candlestick data
    candles = {
        "x": p["date_str"].tolist(),
        "open": p["open"].round(4).tolist(),
        "high": p["high"].round(4).tolist(),
        "low": p["low"].round(4).tolist(),
        "close": p["close"].round(4).tolist(),
    }
    ema200 = {
        "x": p["date_str"].tolist(),
        "y": [round(e, 4) if pd.notna(e) else None for e in p["ema200"]],
    }

    # Trade markers
    trade_details = []
    buys_x, buys_y, buys_text = [], [], []
    sells_x, sells_y, sells_text = [], [], []
    for i, t in trades.iterrows():
        n = i + 1
        entry_reason = explain_entry(t, p)
        exit_reason = explain_exit(t, p)
        pnl = float(t["profit_abs"])
        pnl_pct = float(t["profit_ratio"]) * 100

        buys_x.append(t["open_date"].strftime("%Y-%m-%d"))
        buys_y.append(round(t["open_rate"], 4))
        buys_text.append(
            f"<b>صفقة #{n} — دخول</b><br>"
            f"التاريخ: {t['open_date'].date()}<br>"
            f"السعر: ${t['open_rate']:.4f}<br>"
            f"الكمية: ${t['stake_amount']:.0f}<br>"
            f"<b>المنطق:</b><br>{entry_reason}"
        )
        sells_x.append(t["close_date"].strftime("%Y-%m-%d"))
        sells_y.append(round(t["close_rate"], 4))
        win_emoji = "🟢" if pnl > 0 else "🔴"
        sells_text.append(
            f"<b>{win_emoji} صفقة #{n} — خروج</b><br>"
            f"التاريخ: {t['close_date'].date()}<br>"
            f"السعر: ${t['close_rate']:.4f}<br>"
            f"المدّة: {(t['close_date'] - t['open_date']).days} يوم<br>"
            f"<b>الربح: {'+' if pnl>0 else ''}${pnl:,.2f} ({pnl_pct:+.2f}%)</b><br>"
            f"<b>السبب:</b><br>{exit_reason}"
        )

        trade_details.append({
            "n": n,
            "open_date": t["open_date"].strftime("%Y-%m-%d"),
            "close_date": t["close_date"].strftime("%Y-%m-%d"),
            "duration_days": (t["close_date"] - t["open_date"]).days,
            "open_rate": round(t["open_rate"], 4),
            "close_rate": round(t["close_rate"], 4),
            "stake_amount": round(t["stake_amount"], 0),
            "profit_abs": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "entry_logic": entry_reason,
            "exit_logic": exit_reason,
        })

    summary = {
        "total": len(trades),
        "wins": int((trades["profit_abs"] > 0).sum()),
        "losses": int((trades["profit_abs"] <= 0).sum()),
        "win_rate": round((trades["profit_abs"] > 0).mean() * 100, 1),
        "total_pnl": round(trades["profit_abs"].sum(), 2),
        "best_trade": round(trades["profit_abs"].max(), 2),
        "worst_trade": round(trades["profit_abs"].min(), 2),
        "avg_duration": int(trades["close_date"].sub(trades["open_date"]).dt.days.mean()),
    }

    html_tmpl = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>XRP Calendar Shield — Candle Journal</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 20px; background: #0a0e1a; color: #e0e6ed; }
  .header { background: linear-gradient(135deg, #1a1f3a, #2d1b69); padding: 20px; border-radius: 10px; margin-bottom: 20px; }
  .header h1 { margin: 0; font-size: 26px; }
  .header p { margin: 5px 0 0; opacity: 0.8; }
  .summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
  .stat { background: #1a1f3a; padding: 14px; border-radius: 8px; border-right: 3px solid #4a9eff; }
  .stat .label { font-size: 11px; opacity: 0.7; }
  .stat .value { font-size: 22px; font-weight: bold; margin-top: 4px; }
  .stat .green { color: #10b981; }
  .stat .red { color: #ef4444; }
  #chart { background: #1a1f3a; padding: 10px; border-radius: 10px; height: 600px; margin-bottom: 20px; }
  table { width: 100%; border-collapse: collapse; background: #1a1f3a; border-radius: 8px; overflow: hidden; }
  th { background: #2d1b69; padding: 10px; text-align: right; font-size: 12px; position: sticky; top: 0; }
  td { padding: 10px; border-bottom: 1px solid #2d3548; font-size: 12px; vertical-align: top; }
  tr:hover { background: #232847; }
  .win { color: #10b981; font-weight: bold; }
  .loss { color: #ef4444; font-weight: bold; }
  .reasoning { font-size: 10px; opacity: 0.75; padding: 5px 8px; background: #0f1320; border-radius: 4px; margin-top: 3px; line-height: 1.5; }
  .trade-num { background: #4a9eff; color: white; width: 26px; height: 26px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: bold; }
  .legend { font-size: 12px; opacity: 0.8; margin-top: 10px; }
</style>
</head>
<body>

<div class="header">
  <h1>📊 XRP Calendar Shield — Candle Journal</h1>
  <p>الشموع اليابانية + 12 صفقة (2021-2026) — BtcCalendarShieldStrategy</p>
</div>

<div class="summary">
  <div class="stat"><div class="label">إجمالي الصفقات</div><div class="value">__TOTAL__</div></div>
  <div class="stat"><div class="label">رابحة / خاسرة</div><div class="value"><span class="green">__WINS__</span> / <span class="red">__LOSSES__</span></div></div>
  <div class="stat"><div class="label">نسبة الفوز</div><div class="value">__WINRATE__%</div></div>
  <div class="stat"><div class="label">صافي الربح</div><div class="value green">$__PNL__</div></div>
</div>

<div id="chart"></div>
<div class="legend">
  🕯️ شموع خضراء = ارتفاع | شموع حمراء = هبوط<br>
  🔺 مثلث أخضر = نقطة دخول | 🔻 مثلث أحمر = نقطة خروج<br>
  ➖ خط أصفر متقطّع = EMA200 (المرجع الرئيسي للـregime)
</div>

<h2 style="margin-top: 30px;">📋 سجلّ كل صفقة + منطق القرار</h2>
<table>
  <thead>
    <tr>
      <th>#</th>
      <th>الدخول</th>
      <th>الخروج</th>
      <th>المدّة</th>
      <th>دخول/خروج</th>
      <th>المبلغ</th>
      <th>الربح</th>
      <th>تحليل القرار</th>
    </tr>
  </thead>
  <tbody>__ROWS__</tbody>
</table>

<script>
const candles = __CANDLES__;
const ema = __EMA__;
const buys = { x: __BUYS_X__, y: __BUYS_Y__, text: __BUYS_TEXT__ };
const sells = { x: __SELLS_X__, y: __SELLS_Y__, text: __SELLS_TEXT__ };

const traces = [
  {
    type: 'candlestick',
    name: 'XRP/USDT',
    x: candles.x,
    open: candles.open,
    high: candles.high,
    low: candles.low,
    close: candles.close,
    increasing: { line: { color: '#10b981' }, fillcolor: '#10b981' },
    decreasing: { line: { color: '#ef4444' }, fillcolor: '#ef4444' },
  },
  {
    type: 'scatter',
    mode: 'lines',
    name: 'EMA200',
    x: ema.x,
    y: ema.y,
    line: { color: '#fbbf24', width: 1.5, dash: 'dash' },
  },
  {
    type: 'scatter',
    mode: 'markers',
    name: '🟢 دخول',
    x: buys.x,
    y: buys.y,
    text: buys.text,
    hovertemplate: '%{text}<extra></extra>',
    marker: { color: '#10b981', size: 14, symbol: 'triangle-up', line: { color: 'white', width: 2 } },
  },
  {
    type: 'scatter',
    mode: 'markers',
    name: '🔴 خروج',
    x: sells.x,
    y: sells.y,
    text: sells.text,
    hovertemplate: '%{text}<extra></extra>',
    marker: { color: '#ef4444', size: 14, symbol: 'triangle-down', line: { color: 'white', width: 2 } },
  },
];

const layout = {
  paper_bgcolor: '#1a1f3a',
  plot_bgcolor: '#0a0e1a',
  font: { color: '#e0e6ed', family: 'Segoe UI' },
  xaxis: { rangeslider: { visible: false }, gridcolor: '#2d3548', type: 'date' },
  yaxis: { gridcolor: '#2d3548', tickformat: '$.4f', fixedrange: false },
  hoverlabel: { bgcolor: '#1a1f3a', font: { size: 12 } },
  margin: { l: 60, r: 30, t: 30, b: 50 },
  legend: { orientation: 'h', y: 1.1, x: 0.5, xanchor: 'center' },
};

Plotly.newPlot('chart', traces, layout, { responsive: true, displaylogo: false });
</script>

</body>
</html>
"""

    rows = []
    for t in trade_details:
        cls = "win" if t["profit_abs"] > 0 else "loss"
        sign = "+" if t["profit_abs"] > 0 else ""
        rows.append(f"""
    <tr>
      <td><span class="trade-num">{t["n"]}</span></td>
      <td>{t["open_date"]}</td>
      <td>{t["close_date"]}</td>
      <td>{t["duration_days"]} يوم</td>
      <td>${t["open_rate"]} → ${t["close_rate"]}</td>
      <td>${int(t["stake_amount"]):,}</td>
      <td class="{cls}">{sign}${t["profit_abs"]:,.2f}<br><small>({sign}{t["pnl_pct"]}%)</small></td>
      <td>
        <div class="reasoning">🟢 <b>الدخول:</b> {t["entry_logic"]}</div>
        <div class="reasoning">🔴 <b>الخروج:</b> {t["exit_logic"]}</div>
      </td>
    </tr>""")

    html = html_tmpl
    html = html.replace("__TOTAL__", str(summary["total"]))
    html = html.replace("__WINS__", str(summary["wins"]))
    html = html.replace("__LOSSES__", str(summary["losses"]))
    html = html.replace("__WINRATE__", str(summary["win_rate"]))
    html = html.replace("__PNL__", f"{summary['total_pnl']:,.2f}")
    html = html.replace("__CANDLES__", json.dumps(candles))
    html = html.replace("__EMA__", json.dumps(ema200))
    html = html.replace("__BUYS_X__", json.dumps(buys_x))
    html = html.replace("__BUYS_Y__", json.dumps(buys_y))
    html = html.replace("__BUYS_TEXT__", json.dumps(buys_text, ensure_ascii=False))
    html = html.replace("__SELLS_X__", json.dumps(sells_x))
    html = html.replace("__SELLS_Y__", json.dumps(sells_y))
    html = html.replace("__SELLS_TEXT__", json.dumps(sells_text, ensure_ascii=False))
    html = html.replace("__ROWS__", "\n".join(rows))
    return html


def main():
    trades = load_trades()
    price = load_price_with_indicators()
    html = build_html(price, trades)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"✓ Saved: {OUT_HTML}")
    print(f"  Open: {OUT_HTML.resolve().as_uri()}")


if __name__ == "__main__":
    main()
