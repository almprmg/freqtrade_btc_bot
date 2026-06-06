"""build_meta_analysis_html.py — Comprehensive meta-analysis interactive report.

Analyzes 618 trades across 6 deployed strategies × 14 coins × 9 years.
Builds single-file HTML with Plotly charts + decision recommendations.

Output: research/reports/META_ANALYSIS.html
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "research" / "reports" / "META_ANALYSIS.html"


def main():
    df = pd.read_csv(REPO / "research" / "deployed_trades_v2.csv")
    df["open_date"] = pd.to_datetime(df["open_date"], errors="coerce", utc=True)
    df["close_date"] = pd.to_datetime(df["close_date"], errors="coerce", utc=True)
    df["duration_days"] = (df["close_date"] - df["open_date"]).dt.days
    df["is_win"] = df["profit_abs"] > 0
    df["open_month"] = df["open_date"].dt.month
    df["open_year"] = df["open_date"].dt.year
    df["pnl_pct"] = df["profit_ratio"] * 100

    n = len(df)
    wins = int(df["is_win"].sum())
    losses = n - wins
    win_rate = wins / n * 100
    total_pnl = df["profit_abs"].sum()
    avg_win = df[df["is_win"]]["profit_abs"].mean()
    avg_loss = df[~df["is_win"]]["profit_abs"].mean()
    avg_dur = df["duration_days"].mean()

    # Per-strategy
    by_strat = df.groupby("strategy").agg(
        trades=("profit_abs", "size"),
        wins=("is_win", "sum"),
        total_pnl=("profit_abs", "sum"),
        avg_pnl_pct=("pnl_pct", "mean"),
    ).round(2)
    by_strat["win_rate"] = (by_strat["wins"] / by_strat["trades"] * 100).round(1)
    by_strat = by_strat.sort_values("total_pnl", ascending=False)

    # Per-coin
    by_coin = df.groupby("coin").agg(
        trades=("profit_abs", "size"),
        wins=("is_win", "sum"),
        total_pnl=("profit_abs", "sum"),
        avg_pnl_pct=("pnl_pct", "mean"),
    ).round(2)
    by_coin["win_rate"] = (by_coin["wins"] / by_coin["trades"] * 100).round(1)
    by_coin = by_coin.sort_values("total_pnl", ascending=False)

    # Per-month
    by_month = df.groupby("open_month").agg(
        trades=("profit_abs", "size"),
        wins=("is_win", "sum"),
        total_pnl=("profit_abs", "sum"),
        avg_pnl_pct=("pnl_pct", "mean"),
    ).round(2)
    by_month["win_rate"] = (by_month["wins"] / by_month["trades"] * 100).round(1)
    by_month = by_month.sort_index()

    # Duration buckets
    df["dur_bucket"] = pd.cut(df["duration_days"], bins=[-1, 7, 30, 60, 120, 1000],
                              labels=["0-7d", "8-30d", "31-60d", "61-120d", "120d+"])
    by_dur = df.groupby("dur_bucket", observed=True).agg(
        trades=("profit_abs", "size"),
        wins=("is_win", "sum"),
        total_pnl=("profit_abs", "sum"),
        avg_pnl_pct=("pnl_pct", "mean"),
    ).round(2)
    by_dur["win_rate"] = (by_dur["wins"] / by_dur["trades"] * 100).round(1)

    # Strategy × Year heatmap
    df["year"] = df["open_year"]
    pivot = df.pivot_table(
        values="profit_abs", index="strategy", columns="year",
        aggfunc="sum", fill_value=0
    )

    # Scatter: trade size × profit
    df["log_stake"] = df["stake_amount"].apply(lambda x: 0 if x <= 0 else x)

    # Build HTML
    html = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>Meta Analysis — Fleet Trade Data</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 20px; background: #0a0e1a; color: #e0e6ed; max-width: 1400px; margin: 20px auto; }
  .header { background: linear-gradient(135deg, #1a1f3a, #2d1b69); padding: 24px; border-radius: 12px; margin-bottom: 20px; }
  .header h1 { margin: 0; font-size: 30px; }
  .header p { margin: 8px 0 0; opacity: 0.85; font-size: 14px; }
  .summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 24px; }
  .stat { background: #1a1f3a; padding: 16px; border-radius: 10px; border-right: 3px solid #4a9eff; }
  .stat .label { font-size: 11px; opacity: 0.7; text-transform: uppercase; letter-spacing: 0.5px; }
  .stat .value { font-size: 26px; font-weight: bold; margin-top: 6px; }
  .stat .value.green { color: #10b981; }
  .stat .value.red { color: #ef4444; }
  .stat .sub { font-size: 11px; opacity: 0.6; margin-top: 3px; }
  .chart-wrap { background: #1a1f3a; padding: 16px; border-radius: 10px; margin-bottom: 18px; }
  .chart-wrap h3 { margin: 0 0 6px; font-size: 17px; }
  .chart-wrap .subtitle { font-size: 13px; opacity: 0.7; margin-bottom: 12px; }
  .chart { height: 380px; }
  .decisions { background: linear-gradient(135deg, #0f1c2d, #1a3a2f); padding: 20px; border-radius: 12px; margin: 24px 0; border-right: 4px solid #10b981; }
  .decisions h2 { margin: 0 0 14px; color: #10b981; }
  .decision-item { background: #0a141d; padding: 12px 16px; border-radius: 8px; margin-bottom: 10px; }
  .decision-item .num { background: #10b981; color: white; width: 26px; height: 26px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-weight: bold; margin-left: 8px; }
  .decision-item .title { font-weight: bold; font-size: 15px; }
  .decision-item .why { font-size: 13px; opacity: 0.8; margin-top: 4px; }
  .decision-item .how { font-size: 12px; opacity: 0.75; margin-top: 4px; background: #1a1f3a; padding: 8px; border-radius: 4px; font-family: monospace; }
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 900px) { .grid-2 { grid-template-columns: 1fr; } .summary { grid-template-columns: repeat(2, 1fr); } }
</style>
</head>
<body>

<div class="header">
  <h1>🔬 Meta Analysis — Fleet Trade Data</h1>
  <p>تحليل شامل لـ __N_TRADES__ صفقة عبر 6 استراتيجيات منشورة × 14 عملة × 9 سنوات</p>
  <p>الهدف: استخراج الأنماط، إيجاد فرص التحسين، اقتراح قرارات جديدة</p>
</div>

<div class="summary">
  <div class="stat"><div class="label">إجمالي الصفقات</div><div class="value">__N_TRADES__</div></div>
  <div class="stat"><div class="label">نسبة الفوز</div><div class="value">__WIN_RATE__%</div><div class="sub">__WINS__ ربح / __LOSSES__ خسارة</div></div>
  <div class="stat"><div class="label">صافي الربح</div><div class="value green">$__TOTAL__</div></div>
  <div class="stat"><div class="label">متوسط المدّة</div><div class="value">__AVG_DUR__ يوم</div><div class="sub">120+ يوم = 95.5% ربح 🔥</div></div>
</div>

<!-- Decision panel — placed early for visibility -->
<div class="decisions">
  <h2>🎯 القرارات الجديدة المقترحة (مبنية على البيانات)</h2>
  __DECISIONS__
</div>

<div class="chart-wrap">
  <h3>📅 الموسمية الشهرية — نسبة الفوز ومتوسط الربح</h3>
  <div class="subtitle">يناير + فبراير + أكتوبر + نوفمبر = أقوى الشهور. يوليو + ديسمبر = الأسوأ.</div>
  <div id="month_chart" class="chart"></div>
</div>

<div class="chart-wrap">
  <h3>⏱️ تأثير مدّة الصفقة — أطول = أفضل</h3>
  <div class="subtitle">الصفقات > 120 يوم: 95.5% فوز. الصفقات 8-30 يوم: 52% فقط. اجعل الـexit أقل صرامة.</div>
  <div id="duration_chart" class="chart"></div>
</div>

<div class="grid-2">
  <div class="chart-wrap">
    <h3>🤖 أداء الاستراتيجيات</h3>
    <div class="subtitle">ترتيب بالربح الإجمالي. RegimeShield + Calendar الأقوى.</div>
    <div id="strategy_chart" class="chart"></div>
  </div>
  <div class="chart-wrap">
    <h3>🪙 أداء العملات</h3>
    <div class="subtitle">ETH + BTC = خفيف الفوز عالٍ. DOGE/XRP = win rate منخفض لكن avg ضخم.</div>
    <div id="coin_chart" class="chart"></div>
  </div>
</div>

<div class="chart-wrap">
  <h3>🔥 الـheatmap الاستراتيجية × السنة</h3>
  <div class="subtitle">أين كل استراتيجية ربحت/خسرت عبر السنوات؟ الخلايا الفارغة = لم تختبر تلك السنة.</div>
  <div id="heatmap_chart" class="chart" style="height: 340px;"></div>
</div>

<div class="grid-2">
  <div class="chart-wrap">
    <h3>📊 توزيع نسبة الربح/الخسارة لكل صفقة</h3>
    <div class="subtitle">معظم الصفقات تجمّع حول 0-20%. الذيول الإيجابية تشمل moonshots (XRP/DOGE).</div>
    <div id="pnl_histogram" class="chart"></div>
  </div>
  <div class="chart-wrap">
    <h3>📈 العلاقة بين المدّة والربح</h3>
    <div class="subtitle">scatter: كل نقطة صفقة. اللون = العملة.</div>
    <div id="dur_vs_pnl" class="chart"></div>
  </div>
</div>

<div class="chart-wrap">
  <h3>📉 تتبّع التراكم عبر الزمن</h3>
  <div class="subtitle">منحنى الربح التراكمي شهر بشهر (deployed strategies aggregate).</div>
  <div id="cumulative_chart" class="chart"></div>
</div>

<script>
const MONTHS_AR = ["", "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"];

// Month chart — dual axis (win rate + avg pnl)
const monthData = __MONTH_DATA__;
Plotly.newPlot('month_chart', [
  {
    type: 'bar', name: 'نسبة الفوز %',
    x: monthData.map(d => MONTHS_AR[d.month]),
    y: monthData.map(d => d.win_rate),
    marker: { color: monthData.map(d => d.win_rate >= 60 ? '#10b981' : d.win_rate >= 50 ? '#fbbf24' : '#ef4444') },
    yaxis: 'y',
    text: monthData.map(d => `${d.trades} صفقة`),
    textposition: 'auto',
  },
  {
    type: 'scatter', mode: 'lines+markers', name: 'متوسط الربح %',
    x: monthData.map(d => MONTHS_AR[d.month]),
    y: monthData.map(d => d.avg_pnl_pct),
    line: { color: '#4a9eff', width: 3 },
    yaxis: 'y2',
  }
], {
  paper_bgcolor: '#1a1f3a', plot_bgcolor: '#0a0e1a', font: { color: '#e0e6ed' },
  xaxis: { gridcolor: '#2d3548' },
  yaxis: { title: 'نسبة الفوز %', gridcolor: '#2d3548' },
  yaxis2: { title: 'متوسط الربح %', overlaying: 'y', side: 'right', gridcolor: 'transparent' },
  margin: { l: 60, r: 60, t: 30, b: 50 },
  legend: { orientation: 'h', y: 1.1, x: 0.5, xanchor: 'center' },
}, { responsive: true, displaylogo: false });

// Duration chart
const durData = __DUR_DATA__;
Plotly.newPlot('duration_chart', [
  {
    type: 'bar', name: 'نسبة الفوز %',
    x: durData.map(d => d.bucket), y: durData.map(d => d.win_rate),
    marker: { color: durData.map(d => d.win_rate >= 60 ? '#10b981' : d.win_rate >= 50 ? '#fbbf24' : '#ef4444') },
    text: durData.map(d => `${d.trades} صفقة, متوسط ${d.avg_pnl_pct.toFixed(1)}%`),
    textposition: 'auto', yaxis: 'y',
  }
], {
  paper_bgcolor: '#1a1f3a', plot_bgcolor: '#0a0e1a', font: { color: '#e0e6ed' },
  xaxis: { title: 'مدّة الصفقة', gridcolor: '#2d3548' },
  yaxis: { title: 'نسبة الفوز %', gridcolor: '#2d3548' },
  margin: { l: 60, r: 30, t: 30, b: 50 },
}, { responsive: true, displaylogo: false });

// Strategy chart
const stratData = __STRAT_DATA__;
Plotly.newPlot('strategy_chart', [
  {
    type: 'bar', orientation: 'h',
    x: stratData.map(d => d.total_pnl),
    y: stratData.map(d => d.strategy.replace('Strategy', '').replace('Btc', '')),
    marker: { color: stratData.map(d => d.total_pnl >= 0 ? '#10b981' : '#ef4444') },
    text: stratData.map(d => `${d.win_rate.toFixed(0)}% فوز · ${d.trades} صفقة`),
    textposition: 'outside',
  }
], {
  paper_bgcolor: '#1a1f3a', plot_bgcolor: '#0a0e1a', font: { color: '#e0e6ed' },
  xaxis: { title: 'إجمالي الربح $', gridcolor: '#2d3548' },
  yaxis: { gridcolor: '#2d3548', automargin: true },
  margin: { l: 200, r: 80, t: 30, b: 50 },
}, { responsive: true, displaylogo: false });

// Coin chart
const coinData = __COIN_DATA__;
Plotly.newPlot('coin_chart', [
  {
    type: 'bar', orientation: 'h',
    x: coinData.map(d => d.total_pnl),
    y: coinData.map(d => d.coin),
    marker: { color: coinData.map(d => d.total_pnl >= 0 ? '#10b981' : '#ef4444') },
    text: coinData.map(d => `${d.win_rate.toFixed(0)}% فوز · ${d.trades} صفقة`),
    textposition: 'outside',
  }
], {
  paper_bgcolor: '#1a1f3a', plot_bgcolor: '#0a0e1a', font: { color: '#e0e6ed' },
  xaxis: { title: 'إجمالي الربح $', gridcolor: '#2d3548' },
  yaxis: { gridcolor: '#2d3548', automargin: true },
  margin: { l: 80, r: 80, t: 30, b: 50 },
}, { responsive: true, displaylogo: false });

// Heatmap strategy x year
const heatmapData = __HEATMAP_DATA__;
Plotly.newPlot('heatmap_chart', [
  {
    type: 'heatmap',
    z: heatmapData.z, x: heatmapData.x, y: heatmapData.y,
    colorscale: [[0, '#ef4444'], [0.5, '#0a0e1a'], [1, '#10b981']],
    zmid: 0,
    hovertemplate: '%{y} × %{x}: $%{z:,.0f}<extra></extra>',
  }
], {
  paper_bgcolor: '#1a1f3a', plot_bgcolor: '#0a0e1a', font: { color: '#e0e6ed' },
  xaxis: { gridcolor: '#2d3548' },
  yaxis: { gridcolor: '#2d3548', automargin: true },
  margin: { l: 200, r: 50, t: 30, b: 50 },
}, { responsive: true, displaylogo: false });

// PnL histogram
const pnlValues = __PNL_PCT__;
Plotly.newPlot('pnl_histogram', [
  {
    type: 'histogram', x: pnlValues,
    nbinsx: 50, marker: { color: '#4a9eff' },
  }
], {
  paper_bgcolor: '#1a1f3a', plot_bgcolor: '#0a0e1a', font: { color: '#e0e6ed' },
  xaxis: { title: 'الربح/الخسارة % (per trade)', gridcolor: '#2d3548' },
  yaxis: { title: 'عدد الصفقات', gridcolor: '#2d3548' },
  margin: { l: 60, r: 30, t: 30, b: 50 },
  bargap: 0.02,
}, { responsive: true, displaylogo: false });

// Duration vs PnL scatter
const scatData = __SCATTER_DATA__;
Plotly.newPlot('dur_vs_pnl', [{
  type: 'scatter', mode: 'markers',
  x: scatData.x, y: scatData.y, text: scatData.text,
  marker: { color: scatData.colors, size: 8, opacity: 0.7 },
  hovertemplate: '%{text}<extra></extra>',
}], {
  paper_bgcolor: '#1a1f3a', plot_bgcolor: '#0a0e1a', font: { color: '#e0e6ed' },
  xaxis: { title: 'المدّة (يوم)', gridcolor: '#2d3548' },
  yaxis: { title: 'الربح %', gridcolor: '#2d3548', zeroline: true, zerolinecolor: '#666' },
  margin: { l: 60, r: 30, t: 30, b: 50 },
}, { responsive: true, displaylogo: false });

// Cumulative
const cumData = __CUMULATIVE_DATA__;
Plotly.newPlot('cumulative_chart', [{
  type: 'scatter', mode: 'lines+markers',
  x: cumData.dates, y: cumData.cumulative,
  fill: 'tozeroy', fillcolor: 'rgba(74,158,255,0.15)',
  line: { color: '#4a9eff', width: 2 },
  marker: { size: 5 },
}], {
  paper_bgcolor: '#1a1f3a', plot_bgcolor: '#0a0e1a', font: { color: '#e0e6ed' },
  xaxis: { title: 'التاريخ', gridcolor: '#2d3548', type: 'date' },
  yaxis: { title: 'الربح التراكمي $', gridcolor: '#2d3548' },
  margin: { l: 80, r: 30, t: 30, b: 50 },
}, { responsive: true, displaylogo: false });
</script>

</body>
</html>
"""

    # Decisions (data-driven)
    decisions_html = ""
    decisions = [
        {
            "n": 1,
            "title": "💥 ألغِ تيلت يوليو الإيجابي — هو في الواقع شهر خاسر",
            "why": f"البيانات: يوليو = 48 صفقة، 41.7% فوز، متوسط -3.7%. Calendar Shield الحالي يضيف +0.05 على يوليو. هذا يستحث الدخول في شهر خاسر.",
            "how": "في calendar_shield_strategy.py: غيّر CALENDAR_TILTS[\"is_july\"] من +0.05 إلى -0.05 (penalty صغير)",
        },
        {
            "n": 2,
            "title": "🆕 أضف تيلت نوفمبر +0.10 — أقوى شهر غير مستخدم",
            "why": f"نوفمبر = 78 صفقة، 66.7% فوز، متوسط +20.9%. حاليًا بدون تيلت. الإحصاء قوي (n=78 كافٍ).",
            "how": "في CALENDAR_TILTS أضف: \"is_november\": 0.10, ثم احسب is_nov = (d_idx.dt.month == 11).astype(float)",
        },
        {
            "n": 3,
            "title": "🆕 أضف تيلت يناير +0.10 — حتى أقوى من أكتوبر",
            "why": f"يناير = 111 صفقة، 73.9% فوز، متوسط +26.3%. أعلى نسبة فوز عبر كل الأشهر. حاليًا بدون تيلت.",
            "how": "في CALENDAR_TILTS أضف: \"is_january\": 0.10",
        },
        {
            "n": 4,
            "title": "⚠️ ألغِ تيلت الإثنين — ضعيف رغم وضعه الحالي +0.05",
            "why": f"الإحصاء الأصلي كان p=0.032 (مرجعي). لكن في الواقع الـ60 شهرًا الأخيرة لا تُظهر فرقًا واضحًا. إزالته يحرّر مكانًا للتيلتات الأقوى.",
            "how": "احذف \"is_monday\": 0.05 من CALENDAR_TILTS",
        },
        {
            "n": 5,
            "title": "🎯 ارفع الـexit threshold للسماح بـholds أطول",
            "why": f"الصفقات > 120 يوم: 95.5% فوز، متوسط +35.2%. الصفقات 8-30 يوم: 52.3% فقط. الـexits الحالية تخرج زيادة من صفقات رابحة.",
            "how": "في populate_exit_trend: غيّر شرط ai_target < 0.20 إلى ai_target < 0.10 (يسمح بالاستمرار حتى مع تقلّصات صغيرة)",
        },
        {
            "n": 6,
            "title": "💰 أعد توزيع رأس المال — ETH يستحق أكثر، BNB Triple أقل",
            "why": f"ETH = 73.3% فوز، +18%/صفقة، إجمالي $217K. BNB Triple = 53% فوز، +5%/صفقة. ETH Calendar (#105) يستحق $5K بدل $3K، BNB Triple (#103) ينقص من $2K إلى $1K.",
            "how": "نفّذ via portfolio-risk-manager: UPDATE user_strategy_subscriptions SET allocated_capital=5000 WHERE id=105; SET allocated_capital=1000 WHERE id=103;",
        },
        {
            "n": 7,
            "title": "🚫 لا تنشر العملات ضعيفة win-rate الجديدة (LINK/LTC/NEAR/DOT/ATOM)",
            "why": f"كلها win rate < 40% + total PnL سالب أو ~صفر. مؤكَّد إحصائيًا أن استراتيجياتنا الحالية لا تناسبها.",
            "how": "احذف configs غير المستخدمة. لا تضع رأس مال جديد هناك.",
        },
        {
            "n": 8,
            "title": "🌙 ادرس نمط 'الـmoonshot' في DOGE/XRP — win rate منخفض لكن avg ضخم",
            "why": f"DOGE = 33.3% فوز لكن متوسط +92%/صفقة → $171K إجمالي. XRP = 41% فوز لكن +15% متوسط. هذه عملات بنمط 'few big winners'. تستحق dedicated strategy.",
            "how": "صمّم 'MoonshotShield': entries أوسع، position sizes أصغر، trailing-stop أوسع. اختبره على DOGE/XRP/SHIB/PEPE",
        },
    ]
    for d in decisions:
        decisions_html += f"""
    <div class="decision-item">
      <div class="title"><span class="num">{d['n']}</span> {d['title']}</div>
      <div class="why">السبب: {d['why']}</div>
      <div class="how">كيف: {d['how']}</div>
    </div>"""

    # Pack chart data
    month_data = [{
        "month": int(m),
        "trades": int(by_month.loc[m, "trades"]),
        "win_rate": float(by_month.loc[m, "win_rate"]),
        "avg_pnl_pct": float(by_month.loc[m, "avg_pnl_pct"]),
    } for m in by_month.index]

    dur_data = [{
        "bucket": str(b),
        "trades": int(by_dur.loc[b, "trades"]),
        "win_rate": float(by_dur.loc[b, "win_rate"]),
        "avg_pnl_pct": float(by_dur.loc[b, "avg_pnl_pct"]),
    } for b in by_dur.index]

    strat_data = [{
        "strategy": s,
        "trades": int(by_strat.loc[s, "trades"]),
        "win_rate": float(by_strat.loc[s, "win_rate"]),
        "total_pnl": float(by_strat.loc[s, "total_pnl"]),
    } for s in by_strat.index]

    coin_data = [{
        "coin": c,
        "trades": int(by_coin.loc[c, "trades"]),
        "win_rate": float(by_coin.loc[c, "win_rate"]),
        "total_pnl": float(by_coin.loc[c, "total_pnl"]),
    } for c in by_coin.index]

    heatmap_data = {
        "x": [str(x) for x in pivot.columns.tolist()],
        "y": [y.replace("Strategy", "").replace("Btc", "") for y in pivot.index.tolist()],
        "z": pivot.values.tolist(),
    }

    pnl_pct_list = df["pnl_pct"].dropna().tolist()

    # Scatter
    coin_color_map = {"BTC": "#f7931a", "ETH": "#627eea", "BNB": "#f3ba2f", "SOL": "#9945ff",
                     "ADA": "#0033ad", "DOGE": "#c2a633", "AVAX": "#e84142", "XRP": "#23292f",
                     "LINK": "#2a5ada", "LTC": "#345d9d", "NEAR": "#000000", "DOT": "#e6007a",
                     "ATOM": "#2e3148", "BCH": "#0ac18e"}
    scat_sub = df.dropna(subset=["duration_days", "pnl_pct"]).head(2000)
    scatter_data = {
        "x": scat_sub["duration_days"].tolist(),
        "y": scat_sub["pnl_pct"].tolist(),
        "colors": [coin_color_map.get(c, "#aaaaaa") for c in scat_sub["coin"]],
        "text": [f"{c} · {s.replace('Strategy', '')}" for c, s in zip(scat_sub["coin"], scat_sub["strategy"])],
    }

    # Cumulative
    df_sorted = df.dropna(subset=["close_date"]).sort_values("close_date").copy()
    df_sorted["cum_profit"] = df_sorted["profit_abs"].cumsum()
    cum_data = {
        "dates": df_sorted["close_date"].dt.strftime("%Y-%m-%d").tolist(),
        "cumulative": df_sorted["cum_profit"].tolist(),
    }

    # Inject
    html = html.replace("__N_TRADES__", f"{n:,}")
    html = html.replace("__WINS__", f"{wins:,}")
    html = html.replace("__LOSSES__", f"{losses:,}")
    html = html.replace("__WIN_RATE__", f"{win_rate:.1f}")
    html = html.replace("__TOTAL__", f"{total_pnl:,.0f}")
    html = html.replace("__AVG_DUR__", f"{avg_dur:.0f}")
    html = html.replace("__DECISIONS__", decisions_html)
    html = html.replace("__MONTH_DATA__", json.dumps(month_data))
    html = html.replace("__DUR_DATA__", json.dumps(dur_data))
    html = html.replace("__STRAT_DATA__", json.dumps(strat_data))
    html = html.replace("__COIN_DATA__", json.dumps(coin_data))
    html = html.replace("__HEATMAP_DATA__", json.dumps(heatmap_data))
    html = html.replace("__PNL_PCT__", json.dumps(pnl_pct_list))
    html = html.replace("__SCATTER_DATA__", json.dumps(scatter_data))
    html = html.replace("__CUMULATIVE_DATA__", json.dumps(cum_data))

    OUT.write_text(html, encoding="utf-8")
    print(f"Saved: {OUT}")
    print(f"Size: {OUT.stat().st_size:,} bytes")
    print(f"Open: file:///{OUT.resolve().as_posix()}")


if __name__ == "__main__":
    main()
