"""build_comprehensive_html.py — Build the COMPREHENSIVE strategy report HTML.

Reads from research/comprehensive_backtest_results.json + trades.csv files,
produces interactive HTML dashboard.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "research" / "comprehensive_backtest_results.json"
OUT = REPO / "research" / "reports" / "COMPREHENSIVE_DASHBOARD.html"


def find_trade_files(label):
    """Find trades.csv files for a strategy (uses 'COMPRE_' notes in metadata)."""
    short = label.replace(' ', '_').replace('(', '').replace(')', '').replace('#', 'n').replace('+', 'p').replace('/', '_')[:30]
    runs = sorted(REPO.glob(f"research/experiments/*CBT_{short}*"))
    all_trades = []
    for run in runs:
        tp = run / "trades.csv"
        if tp.exists() and tp.stat().st_size > 100:
            try:
                df = pd.read_csv(tp)
                df["open_date"] = pd.to_datetime(df["open_date"], errors="coerce")
                df["close_date"] = pd.to_datetime(df["close_date"], errors="coerce")
                df["pnl_pct"] = df["profit_ratio"] * 100
                df["is_win"] = df["profit_abs"] > 0
                df["duration"] = (df["close_date"] - df["open_date"]).dt.days
                df["month"] = df["open_date"].dt.month
                df["year"] = df["open_date"].dt.year
                all_trades.append(df)
            except: pass
    return pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()


def strategy_stats(label, results, trades):
    """Compute stats for one strategy."""
    if len(trades) == 0:
        return None
    yearly = results.get("years", {})
    compound = 1.0
    yearly_rois = []
    for yr, r in yearly.items():
        if r.get("ok"):
            compound *= (1 + r["roi"]/100)
            yearly_rois.append({"year": int(yr), "roi": r["roi"], "n": r["n"], "dd": r["dd"]})
    cagr = (compound**(1/9) - 1) * 100 if compound > 0 else -100

    # Monthly breakdown
    monthly = trades.groupby("month").agg(
        n=("profit_abs", "size"),
        wins=("is_win", "sum"),
        avg_pct=("pnl_pct", "mean"),
        total=("profit_abs", "sum"),
    ).round(2)
    monthly["losses"] = monthly["n"] - monthly["wins"]
    monthly["win_rate"] = (monthly["wins"] / monthly["n"] * 100).round(1)

    # Best/worst trades
    sorted_pnl = trades.sort_values("profit_abs", ascending=False)
    best5 = sorted_pnl.head(5)[["open_date", "close_date", "duration", "profit_abs", "pnl_pct", "open_rate", "close_rate"]]
    worst5 = sorted_pnl.tail(5)[["open_date", "close_date", "duration", "profit_abs", "pnl_pct", "open_rate", "close_rate"]]

    return {
        "label": label,
        "coin": results.get("coin", "?"),
        "compound": compound,
        "wallet_end": 10000 * compound,
        "cagr": cagr,
        "yearly": yearly_rois,
        "monthly": monthly.to_dict("index"),
        "n_trades": len(trades),
        "wins": int(trades["is_win"].sum()),
        "losses": int((~trades["is_win"]).sum()),
        "win_rate": trades["is_win"].mean() * 100,
        "total_pnl": trades["profit_abs"].sum(),
        "avg_win": trades[trades["is_win"]]["profit_abs"].mean() if (trades["is_win"]).any() else 0,
        "avg_loss": trades[~trades["is_win"]]["profit_abs"].mean() if (~trades["is_win"]).any() else 0,
        "avg_duration": trades["duration"].mean(),
        "max_win": trades["profit_abs"].max(),
        "max_loss": trades["profit_abs"].min(),
        "best5": best5.to_dict("records"),
        "worst5": worst5.to_dict("records"),
    }


def build_html(stats_list):
    """Generate the HTML."""
    # Sort by CAGR
    stats_list = sorted([s for s in stats_list if s], key=lambda x: x["cagr"], reverse=True)

    # Summary cards
    n_strats = len(stats_list)
    best = stats_list[0] if stats_list else None
    total_trades = sum(s["n_trades"] for s in stats_list)

    # Build per-strategy HTML sections
    strategy_cards = []
    months_ar = ["", "يناير","فبراير","مارس","أبريل","مايو","يونيو","يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"]
    for i, s in enumerate(stats_list):
        rank = i + 1
        medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"#{rank}"
        # Yearly table rows
        year_rows = ""
        for y in s["yearly"]:
            sign = "+" if y["roi"] >= 0 else ""
            cls = "win" if y["roi"] > 0 else "loss" if y["roi"] < 0 else "neutral"
            year_rows += f"<tr><td>{y['year']}</td><td class='{cls}'>{sign}{y['roi']:.1f}%</td><td>{y['n']}</td><td>{y['dd']:.1f}%</td></tr>"
        # Monthly table rows
        month_rows = ""
        for m in range(1, 13):
            md = s["monthly"].get(m, {})
            if md and md.get("n", 0) > 0:
                wr = md.get("win_rate", 0)
                cls = "win" if wr >= 60 else "loss" if wr < 40 else "neutral"
                avg = md.get("avg_pct", 0)
                month_rows += f"<tr><td>{months_ar[m]}</td><td>{int(md.get('n',0))}</td><td>{int(md.get('wins',0))}/{int(md.get('losses',0))}</td><td class='{cls}'>{wr:.0f}%</td><td>{avg:+.1f}%</td><td>${md.get('total', 0):+,.0f}</td></tr>"
            else:
                month_rows += f"<tr><td>{months_ar[m]}</td><td colspan='5' style='opacity:0.4'>لا صفقات</td></tr>"

        # Best/worst trade rows
        best_rows = "".join([f"<tr><td>{pd.to_datetime(t['open_date']).date()}</td><td>{pd.to_datetime(t['close_date']).date()}</td><td>{int(t['duration']) if pd.notna(t['duration']) else 0}d</td><td>${t['open_rate']:,.0f}</td><td>${t['close_rate']:,.0f}</td><td class='win'>+${t['profit_abs']:,.0f}</td><td class='win'>+{t['pnl_pct']:.1f}%</td></tr>" for t in s["best5"]])
        worst_rows = "".join([f"<tr><td>{pd.to_datetime(t['open_date']).date()}</td><td>{pd.to_datetime(t['close_date']).date()}</td><td>{int(t['duration']) if pd.notna(t['duration']) else 0}d</td><td>${t['open_rate']:,.0f}</td><td>${t['close_rate']:,.0f}</td><td class='loss'>${t['profit_abs']:,.0f}</td><td class='loss'>{t['pnl_pct']:.1f}%</td></tr>" for t in s["worst5"]])

        card = f"""
<div class="strategy-card" id="strat-{i}">
  <div class="strategy-header">
    <div>
      <span class="rank">{medal}</span>
      <span class="strategy-name">{s['label']}</span>
      <span class="coin-badge">{s['coin']}</span>
    </div>
    <div class="big-stats">
      <span class="stat-pill">$10K → ${s['wallet_end']:,.0f}</span>
      <span class="stat-pill {'win' if s['cagr'] >= 0 else 'loss'}">{s['cagr']:+.1f}%/yr</span>
      <span class="stat-pill">{s['n_trades']} صفقة</span>
      <span class="stat-pill">{s['win_rate']:.0f}% فوز</span>
    </div>
  </div>
  <div class="strategy-body">
    <div class="grid-2">
      <div>
        <h4>📅 السنوي</h4>
        <table>
          <thead><tr><th>السنة</th><th>ROI</th><th>صفقات</th><th>DD</th></tr></thead>
          <tbody>{year_rows}</tbody>
        </table>
      </div>
      <div>
        <h4>📆 الشهري</h4>
        <table>
          <thead><tr><th>الشهر</th><th>صفقات</th><th>W/L</th><th>%فوز</th><th>متوسط</th><th>إجمالي</th></tr></thead>
          <tbody>{month_rows}</tbody>
        </table>
      </div>
    </div>
    <div class="grid-2">
      <div>
        <h4>🟢 أفضل 5 صفقات</h4>
        <table>
          <thead><tr><th>دخول</th><th>خروج</th><th>مدّة</th><th>سعر دخول</th><th>سعر خروج</th><th>الربح</th><th>%</th></tr></thead>
          <tbody>{best_rows}</tbody>
        </table>
      </div>
      <div>
        <h4>🔴 أسوأ 5 صفقات</h4>
        <table>
          <thead><tr><th>دخول</th><th>خروج</th><th>مدّة</th><th>سعر دخول</th><th>سعر خروج</th><th>الخسارة</th><th>%</th></tr></thead>
          <tbody>{worst_rows}</tbody>
        </table>
      </div>
    </div>
    <div class="quick-stats">
      <span>متوسط الربح: <b class="win">${s['avg_win']:,.0f}</b></span>
      <span>متوسط الخسارة: <b class="loss">${s['avg_loss']:,.0f}</b></span>
      <span>أكبر ربح: <b class="win">${s['max_win']:,.0f}</b></span>
      <span>أكبر خسارة: <b class="loss">${s['max_loss']:,.0f}</b></span>
      <span>متوسط المدّة: <b>{s['avg_duration']:.0f} يوم</b></span>
    </div>
  </div>
</div>
"""
        strategy_cards.append(card)

    # Build summary comparison data
    chart_data = [{"label": s["label"], "cagr": s["cagr"], "compound": s["wallet_end"],
                   "trades": s["n_trades"], "wr": s["win_rate"], "coin": s["coin"]} for s in stats_list]

    html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>التقرير الشامل - كل الاستراتيجيات</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  body {{ font-family: 'Segoe UI', Tahoma, sans-serif; margin: 20px; background: #0a0e1a; color: #e0e6ed; max-width: 1500px; margin: 20px auto; }}
  .header {{ background: linear-gradient(135deg, #1a1f3a, #2d1b69); padding: 28px; border-radius: 12px; margin-bottom: 24px; }}
  .header h1 {{ margin: 0; font-size: 30px; }}
  .header p {{ margin: 8px 0 0; opacity: 0.85; }}
  .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 24px; }}
  .stat {{ background: #1a1f3a; padding: 16px; border-radius: 10px; border-right: 3px solid #4a9eff; }}
  .stat .label {{ font-size: 11px; opacity: 0.7; text-transform: uppercase; }}
  .stat .value {{ font-size: 24px; font-weight: bold; margin-top: 6px; }}
  .stat .green {{ color: #10b981; }}
  .chart-section {{ background: #1a1f3a; padding: 16px; border-radius: 10px; margin-bottom: 24px; }}
  .chart {{ height: 500px; }}
  .strategy-card {{ background: #1a1f3a; padding: 18px; border-radius: 10px; margin-bottom: 20px; border-right: 4px solid #4a9eff; }}
  .strategy-card:nth-child(1) {{ border-right-color: gold; }}
  .strategy-card:nth-child(2) {{ border-right-color: silver; }}
  .strategy-card:nth-child(3) {{ border-right-color: #cd7f32; }}
  .strategy-header {{ display: flex; justify-content: space-between; align-items: center; padding-bottom: 12px; border-bottom: 1px solid #2d3548; margin-bottom: 14px; flex-wrap: wrap; gap: 10px; }}
  .rank {{ font-size: 22px; }}
  .strategy-name {{ font-size: 18px; font-weight: bold; margin: 0 8px; }}
  .coin-badge {{ background: #2d1b69; padding: 3px 10px; border-radius: 12px; font-size: 12px; }}
  .big-stats {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .stat-pill {{ background: #0a141d; padding: 6px 12px; border-radius: 8px; font-size: 13px; font-weight: bold; }}
  .stat-pill.win {{ color: #10b981; }}
  .stat-pill.loss {{ color: #ef4444; }}
  .strategy-body table {{ width: 100%; border-collapse: collapse; font-size: 12px; background: #0f1320; border-radius: 6px; overflow: hidden; margin-bottom: 8px; }}
  .strategy-body th {{ background: #2d1b69; padding: 6px 8px; text-align: right; }}
  .strategy-body td {{ padding: 5px 8px; border-bottom: 1px solid #2d3548; }}
  .strategy-body h4 {{ margin: 10px 0 6px; }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 12px; }}
  @media (max-width: 900px) {{ .grid-2 {{ grid-template-columns: 1fr; }} .summary {{ grid-template-columns: repeat(2, 1fr); }} }}
  .win {{ color: #10b981; }}
  .loss {{ color: #ef4444; }}
  .neutral {{ color: #fbbf24; }}
  .quick-stats {{ display: flex; gap: 16px; flex-wrap: wrap; padding: 10px; background: #0f1320; border-radius: 6px; font-size: 13px; margin-top: 8px; }}
  .toc {{ background: #1a1f3a; padding: 16px; border-radius: 10px; margin-bottom: 24px; }}
  .toc a {{ color: #4a9eff; text-decoration: none; display: block; padding: 4px 0; }}
  .toc a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>

<div class="header">
  <h1>🏆 التقرير الشامل — جميع الاستراتيجيات</h1>
  <p>اختبار {n_strats} استراتيجية على 9 سنوات (2018-2026) — {total_trades:,} صفقة موثّقة</p>
</div>

<div class="summary">
  <div class="stat"><div class="label">عدد الاستراتيجيات</div><div class="value">{n_strats}</div></div>
  <div class="stat"><div class="label">الأقوى</div><div class="value green">{best['label'] if best else '-'}</div></div>
  <div class="stat"><div class="label">أعلى CAGR</div><div class="value green">{best['cagr']:.1f}%/yr</div></div>
  <div class="stat"><div class="label">إجمالي الصفقات</div><div class="value">{total_trades:,}</div></div>
</div>

<div class="chart-section">
  <h3>📊 ترتيب الاستراتيجيات (CAGR + إجمالي الربح)</h3>
  <div id="comparison-chart" class="chart"></div>
</div>

<div class="toc">
  <h3>📋 فهرس</h3>
  {"".join(f'<a href="#strat-{i}">{i+1}. {s["label"]} — {s["coin"]} — {s["cagr"]:+.1f}%/yr</a>' for i, s in enumerate(stats_list))}
</div>

{"".join(strategy_cards)}

<script>
const data = {json.dumps(chart_data, default=str)};

// Comparison chart: dual-axis with CAGR + Wallet
Plotly.newPlot('comparison-chart', [
  {{
    type: 'bar', name: 'CAGR %/yr',
    x: data.map(d => d.label),
    y: data.map(d => d.cagr),
    marker: {{ color: data.map(d => d.cagr >= 30 ? '#10b981' : d.cagr >= 10 ? '#fbbf24' : d.cagr >= 0 ? '#94a3b8' : '#ef4444') }},
    text: data.map(d => `${{d.coin}}`),
    textposition: 'auto',
    yaxis: 'y',
  }},
  {{
    type: 'scatter', mode: 'lines+markers', name: '$10K → نهاية',
    x: data.map(d => d.label),
    y: data.map(d => d.compound),
    line: {{ color: '#4a9eff', width: 2 }},
    marker: {{ size: 8 }},
    yaxis: 'y2',
  }},
], {{
  paper_bgcolor: '#1a1f3a', plot_bgcolor: '#0a0e1a', font: {{ color: '#e0e6ed' }},
  xaxis: {{ tickangle: -45, automargin: true }},
  yaxis: {{ title: 'CAGR %/yr', gridcolor: '#2d3548' }},
  yaxis2: {{ title: 'النتيجة النهائية $', overlaying: 'y', side: 'right', gridcolor: 'transparent' }},
  margin: {{ l: 60, r: 60, t: 30, b: 150 }},
  legend: {{ orientation: 'h', y: 1.1, x: 0.5, xanchor: 'center' }},
}}, {{ responsive: true, displaylogo: false }});
</script>

</body>
</html>
"""
    return html


def main():
    if not RESULTS.exists():
        print(f"ERROR: {RESULTS} not found. Run comprehensive_backtest.py first.")
        return 1

    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    print(f"Loading {len(results)} strategies...")

    stats_list = []
    for label, info in results.items():
        trades = find_trade_files(label)
        if len(trades) == 0:
            print(f"  {label}: no trades found")
            continue
        s = strategy_stats(label, info, trades)
        if s:
            stats_list.append(s)
            print(f"  {label}: {s['n_trades']} trades, {s['cagr']:+.1f}%/yr")

    print(f"\nGenerating HTML...")
    html = build_html(stats_list)
    OUT.write_text(html, encoding="utf-8")
    print(f"Saved: {OUT}")
    print(f"Size: {OUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
