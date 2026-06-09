"""build_portfolio_aggregate.py — Combined portfolio view across 16 active strategies.

Aggregates ALL trades from all 16 active Tier-1 subscriptions, then shows:
  - Per year totals (trades, wins, losses, WR, PnL)
  - Per month within each year (with 12-month grid)
  - Per month across all years (seasonality pattern)

Each strategy gets normalized to $10K starting capital so contributions
sum meaningfully.

Output: research/reports/PORTFOLIO_AGGREGATE.html
"""
from __future__ import annotations

import json
import pandas as pd
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "research" / "comprehensive_backtest_results.json"
EXPERIMENTS = REPO / "research" / "experiments"
OUT_HTML = REPO / "research" / "reports" / "PORTFOLIO_AGGREGATE.html"

ACTIVE = {
    "AI Shield V1 (#97)":      ("#97",  "BTC"),
    "Triple Regime BTC (#98)": ("#98",  "BTC"),
    "AI Shield V2 (#99)":      ("#99",  "BTC"),
    "Calendar BTC (#100)":     ("#100", "BTC"),
    "ETH Pure Shield (#101)":  ("#101", "ETH"),
    "SOL VolShield (#102)":    ("#102", "SOL"),
    "Triple Regime BNB (#103)":("#103", "BNB"),
    "Triple Regime ADA (#104)":("#104", "ADA"),
    "Calendar ETH (#105)":     ("#105", "ETH"),
    "Calendar BNB (#106)":     ("#106", "BNB"),
    "Macro V2 BTC (#108)":     ("#108", "BTC"),
    "AnalogV2 BTC":            ("#109", "BTC"),
    "AnalogV2 ETH STAR":       ("#110", "ETH ⭐"),
    "Calendar V2 BTC":         ("#111", "BTC"),
    "AnalogShield V1 BTC":     ("#112", "BTC"),
    "Quantum AI":              ("#113", "BTC"),
}

MONTHS_AR = ["", "يناير","فبراير","مارس","أبريل","مايو","يونيو",
             "يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"]


def short(label):
    return label.replace(' ', '_').replace('(', '').replace(')', '').replace('#', 'n').replace('+', 'p').replace('/', '_')[:30]


def load_all_trades():
    """Load trades from all 16 active strategies, tag with strategy + sub#."""
    all_dfs = []
    for label, (sub, coin) in ACTIVE.items():
        s = short(label)
        for run in EXPERIMENTS.glob(f"*CBT_{s}*"):
            tp = run/"trades.csv"
            if tp.exists() and tp.stat().st_size > 100:
                try:
                    df = pd.read_csv(tp)
                    df["open_date"] = pd.to_datetime(df["open_date"], errors="coerce", utc=True)
                    df["close_date"] = pd.to_datetime(df["close_date"], errors="coerce", utc=True)
                    df["year"] = df["close_date"].dt.year
                    df["month"] = df["close_date"].dt.month
                    df["is_win"] = df["profit_abs"] > 0
                    df["strategy_label"] = label
                    df["sub_id"] = sub
                    df["strategy_coin"] = coin
                    all_dfs.append(df)
                except: pass
    return pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()


def main():
    trades = load_all_trades()
    if trades.empty:
        print("No trades loaded!"); return
    trades = trades[trades["close_date"].notna()]
    trades = trades[trades["year"].between(2018, 2026)]
    print(f"Total trades aggregated: {len(trades):,} across {trades['strategy_label'].nunique()} strategies")

    html = [
        "<!DOCTYPE html><html lang='ar' dir='rtl'><head><meta charset='UTF-8'>",
        "<title>تجميع المحفظة — كل الاستراتيجيات النشطة</title>",
        "<script src='https://cdn.plot.ly/plotly-latest.min.js'></script>",
        "<style>",
        "body{font-family:Arial,sans-serif;background:#0a0e1a;color:#e0e6f0;margin:0;padding:20px;line-height:1.5;}",
        "h1{color:#5dade2;border-bottom:3px solid #5dade2;padding-bottom:10px;}",
        "h2{color:#48c9b0;margin-top:30px;}",
        "h3{color:#f39c12;}",
        ".card{background:#1a2332;border-radius:8px;padding:20px;margin:20px 0;}",
        ".kpi-row{display:flex;gap:20px;flex-wrap:wrap;}",
        ".kpi{background:#222d3e;padding:15px 25px;border-radius:6px;flex:1;min-width:160px;}",
        ".kpi-label{color:#95a5a6;font-size:0.85em;}",
        ".kpi-value{font-size:1.6em;font-weight:bold;margin-top:5px;}",
        ".pos{color:#2ecc71;}",
        ".neg{color:#e74c3c;}",
        ".neutral{color:#f39c12;}",
        "table{border-collapse:collapse;width:100%;margin:10px 0;background:#1a2332;}",
        "th{background:#2c3e50;padding:10px;text-align:right;border:1px solid #34495e;color:#5dade2;}",
        "td{padding:8px;border:1px solid #34495e;text-align:right;}",
        "tr.empty td{color:#566573;}",
        "tr.totals{background:#2c3e50;font-weight:bold;color:#f39c12;}",
        ".heatmap-cell{padding:8px 12px;text-align:center;}",
        "table.heatmap{font-size:0.9em;}",
        "</style></head><body>",
        "<h1>📊 تجميع المحفظة الكاملة — 16 استراتيجية نشطة</h1>",
        f"<p><b>التاريخ:</b> 2026-06-09 | <b>إجمالي الصفقات:</b> {len(trades):,} | <b>الاستراتيجيات:</b> {trades['strategy_label'].nunique()}</p>",
    ]

    # Overall KPIs
    total_pnl = trades["profit_abs"].sum()
    n = len(trades); w = trades["is_win"].sum()
    wr = w/n*100; avg_t = trades["profit_abs"].mean()
    html.append("<div class='card'><h2>📌 KPI الإجمالي عبر 9 سنوات</h2><div class='kpi-row'>")
    html.append(f"<div class='kpi'><div class='kpi-label'>إجمالي الصفقات</div><div class='kpi-value neutral'>{n:,}</div></div>")
    html.append(f"<div class='kpi'><div class='kpi-label'>صفقات رابحة</div><div class='kpi-value pos'>{w:,}</div></div>")
    html.append(f"<div class='kpi'><div class='kpi-label'>صفقات خاسرة</div><div class='kpi-value neg'>{n-w:,}</div></div>")
    html.append(f"<div class='kpi'><div class='kpi-label'>Win Rate</div><div class='kpi-value neutral'>{wr:.1f}%</div></div>")
    html.append(f"<div class='kpi'><div class='kpi-label'>إجمالي PnL</div><div class='kpi-value {'pos' if total_pnl>=0 else 'neg'}'>${total_pnl:+,.0f}</div></div>")
    html.append(f"<div class='kpi'><div class='kpi-label'>متوسط صفقة</div><div class='kpi-value {'pos' if avg_t>=0 else 'neg'}'>${avg_t:+,.0f}</div></div>")
    html.append("</div></div>")

    # Yearly aggregate
    yearly = trades.groupby("year").agg(
        n=("profit_abs", "size"),
        w=("is_win", "sum"),
        pnl=("profit_abs", "sum"),
        active_strats=("strategy_label", "nunique"),
    ).reset_index()
    yearly["l"] = yearly["n"] - yearly["w"]
    yearly["wr"] = yearly["w"]/yearly["n"]*100
    # Per-trade ROI%: avg of profit_ratio (already a % of position)
    yearly["roi_per_trade_pct"] = trades.groupby("year")["profit_ratio"].mean().values * 100
    # Yearly non-cumulative ROI: pnl / (active_strats × $10K per-strategy backtest capital)
    yearly["capital"] = yearly["active_strats"] * 10000
    yearly["roi_pct"] = yearly["pnl"] / yearly["capital"] * 100
    # Cumulative wallet growth: start at $10K, compound by per-strategy avg ROI each year
    # (avg ROI per strategy = pnl / num_active_that_year / 10000 — equivalent to roi_pct above)
    yearly = yearly.sort_values("year").reset_index(drop=True)
    wallet = 10000.0
    cum_wallets_start = []
    cum_wallets_end = []
    cum_roi_pct = []
    for _, r in yearly.iterrows():
        cum_wallets_start.append(wallet)
        wallet = wallet * (1 + r["roi_pct"]/100)
        cum_wallets_end.append(wallet)
        cum_roi_pct.append((wallet - 10000)/10000 * 100)
    yearly["wallet_start"] = cum_wallets_start
    yearly["wallet_end"] = cum_wallets_end
    yearly["cum_roi"] = cum_roi_pct

    # === Table 1: Per-year, NON-cumulative ===
    html.append("<div class='card'><h2>📅 السنوي (غير تراكمي) — كل سنة مستقلّة</h2>")
    html.append("<p style='color:#95a5a6;font-size:0.9em;'>كل سنة محسوبة على رأس مال جديد (\$10K × عدد الاستراتيجيات النشطة في تلك السنة). الـROI/صفقة هو متوسط ربح الصفقة كنسبة من حجم الصفقة.</p>")
    html.append("<table><thead><tr><th>السنة</th><th>الاستراتيجيات</th><th>صفقات</th><th>WR</th><th>ROI/صفقة %</th><th>PnL ($)</th><th>ROI السنوي %</th></tr></thead><tbody>")
    for _, r in yearly.iterrows():
        pnl_cls = "pos" if r["pnl"] >= 0 else "neg"
        roi_cls = "pos" if r["roi_pct"] >= 0 else "neg"
        per_trade_cls = "pos" if r["roi_per_trade_pct"] >= 0 else "neg"
        html.append(f"<tr><td><b>{int(r['year'])}</b></td><td>{int(r['active_strats'])}</td>"
                   f"<td>{int(r['n'])}</td>"
                   f"<td>{r['wr']:.0f}%</td>"
                   f"<td class='{per_trade_cls}'>{r['roi_per_trade_pct']:+.2f}%</td>"
                   f"<td class='{pnl_cls}'>${r['pnl']:+,.0f}</td>"
                   f"<td class='{roi_cls}'><b>{r['roi_pct']:+.1f}%</b></td></tr>")
    # Totals row
    total_capital_yr_sum = yearly["capital"].sum()
    total_roi_nc = total_pnl / total_capital_yr_sum * 100
    avg_per_trade_pct = trades["profit_ratio"].mean() * 100
    html.append(f"<tr class='totals'><td>المتوسط/الإجمالي</td><td>—</td>"
               f"<td>{n:,}</td><td>{wr:.0f}%</td>"
               f"<td>{avg_per_trade_pct:+.2f}%</td>"
               f"<td>${total_pnl:+,.0f}</td>"
               f"<td><b>{total_roi_nc:+.1f}%</b></td></tr>")
    html.append("</tbody></table></div>")

    # === Table 2: Cumulative wallet growth ===
    html.append("<div class='card'><h2>💰 التراكمي (Compounding) — كيف ينمو $10K</h2>")
    html.append("<p style='color:#95a5a6;font-size:0.9em;'>افتراض: تبدأ بـ\$10K، وفي نهاية كل سنة يُعاد استثمار الربح. الـROI السنوي مأخوذ من الجدول السابق ويُطبَّق على الـwallet الحالي.</p>")
    html.append("<table><thead><tr><th>السنة</th><th>رصيد البداية</th><th>ROI السنوي</th><th>الربح</th><th>رصيد النهاية</th><th>تراكمي من $10K</th></tr></thead><tbody>")
    for _, r in yearly.iterrows():
        roi_cls = "pos" if r["roi_pct"] >= 0 else "neg"
        cum_cls = "pos" if r["cum_roi"] >= 0 else "neg"
        year_gain = r["wallet_end"] - r["wallet_start"]
        gain_cls = "pos" if year_gain >= 0 else "neg"
        html.append(f"<tr><td><b>{int(r['year'])}</b></td>"
                   f"<td>${r['wallet_start']:,.0f}</td>"
                   f"<td class='{roi_cls}'>{r['roi_pct']:+.1f}%</td>"
                   f"<td class='{gain_cls}'>${year_gain:+,.0f}</td>"
                   f"<td><b>${r['wallet_end']:,.0f}</b></td>"
                   f"<td class='{cum_cls}'><b>{r['cum_roi']:+.1f}%</b></td></tr>")
    final_wallet = yearly["wallet_end"].iloc[-1]
    cagr_9y = ((final_wallet/10000) ** (1/len(yearly)) - 1) * 100
    html.append(f"<tr class='totals'><td>النهائي (9 سنوات)</td><td>$10,000 بداية</td>"
               f"<td>CAGR {cagr_9y:+.1f}%/سنة</td>"
               f"<td>${final_wallet-10000:+,.0f}</td>"
               f"<td><b>${final_wallet:,.0f}</b></td>"
               f"<td><b>{(final_wallet/10000-1)*100:+.0f}%</b></td></tr>")
    html.append("</tbody></table></div>")

    # Yearly chart
    html.append("<div id='yr-chart' style='height:400px;'></div>")
    html.append("<script>")
    yr_labels = [int(y) for y in yearly["year"]]
    html.append(f"Plotly.newPlot('yr-chart', [")
    html.append(f"  {{x: {json.dumps(yr_labels)}, y: {json.dumps(yearly['pnl'].round(0).tolist())}, type:'bar', name:'PnL $', marker:{{color: 'rgba(46,204,113,0.7)'}}}},")
    html.append(f"  {{x: {json.dumps(yr_labels)}, y: {json.dumps(yearly['n'].tolist())}, type:'scatter', mode:'lines+markers', name:'#صفقات', yaxis:'y2', line:{{color:'#f39c12', width:3}}}}")
    html.append(f"], {{paper_bgcolor:'#0a0e1a', plot_bgcolor:'#1a2332', font:{{color:'#e0e6f0'}}, title:'PnL السنوي + عدد الصفقات', yaxis:{{title:'PnL $'}}, yaxis2:{{title:'#صفقات', overlaying:'y', side:'right'}}}});")
    html.append("</script>")

    # Per-month breakdown within each year
    html.append("<div class='card'><h2>📆 الشهري — تفصيل لكل سنة</h2>")
    for yr in sorted(yearly["year"].astype(int)):
        ydf = trades[trades["year"] == yr]
        if ydf.empty: continue
        html.append(f"<h3>📅 {yr}</h3>")
        html.append("<table><thead><tr><th>الشهر</th><th>صفقات</th><th>فوز</th><th>خسارة</th><th>WR</th><th>PnL ($)</th><th>أفضل صفقة</th><th>أسوأ صفقة</th></tr></thead><tbody>")
        yr_pnl = 0; yr_n = 0; yr_w = 0
        for m in range(1, 13):
            mdf = ydf[ydf["month"] == m]
            m_n = len(mdf)
            if m_n == 0:
                html.append(f"<tr class='empty'><td>{MONTHS_AR[m]}</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td></tr>")
                continue
            m_w = mdf["is_win"].sum(); m_wr = m_w/m_n*100
            m_pnl = mdf["profit_abs"].sum()
            best = mdf["profit_abs"].max(); worst = mdf["profit_abs"].min()
            yr_pnl += m_pnl; yr_n += m_n; yr_w += m_w
            pnl_cls = "pos" if m_pnl >= 0 else "neg"
            html.append(f"<tr><td><b>{MONTHS_AR[m]}</b></td><td>{m_n}</td>"
                       f"<td class='pos'>{m_w}</td><td class='neg'>{m_n-m_w}</td>"
                       f"<td>{m_wr:.0f}%</td><td class='{pnl_cls}'>${m_pnl:+,.0f}</td>"
                       f"<td class='pos'>${best:+,.0f}</td><td class='neg'>${worst:+,.0f}</td></tr>")
        yr_wr = (yr_w/yr_n*100) if yr_n else 0
        html.append(f"<tr class='totals'><td>إجمالي {yr}</td><td>{yr_n}</td><td>{yr_w}</td><td>{yr_n-yr_w}</td>"
                   f"<td>{yr_wr:.0f}%</td><td>${yr_pnl:+,.0f}</td><td>—</td><td>—</td></tr>")
        html.append("</tbody></table>")
    html.append("</div>")

    # Seasonality: PnL by month across all years
    seasonality = trades.groupby("month").agg(
        n=("profit_abs", "size"),
        w=("is_win", "sum"),
        pnl=("profit_abs", "sum"),
        avg=("profit_abs", "mean"),
    ).reset_index()
    seasonality["wr"] = seasonality["w"]/seasonality["n"]*100
    seasonality["month_name"] = seasonality["month"].map(lambda m: MONTHS_AR[int(m)])

    html.append("<div class='card'><h2>🌍 الموسمية — كل الأشهر عبر 9 سنوات</h2>")
    html.append("<p>أي شهور تاريخيًا الأفضل/الأسوأ عبر كل المحفظة؟</p>")
    html.append("<table><thead><tr><th>الشهر</th><th>صفقات</th><th>فوز</th><th>خسارة</th><th>WR</th><th>إجمالي PnL</th><th>متوسط/صفقة</th></tr></thead><tbody>")
    seasonality_sorted = seasonality.sort_values("pnl", ascending=False)
    for _, r in seasonality_sorted.iterrows():
        pnl_cls = "pos" if r["pnl"] >= 0 else "neg"
        html.append(f"<tr><td><b>{r['month_name']}</b></td><td>{int(r['n'])}</td>"
                   f"<td class='pos'>{int(r['w'])}</td><td class='neg'>{int(r['n']-r['w'])}</td>"
                   f"<td>{r['wr']:.0f}%</td><td class='{pnl_cls}'>${r['pnl']:+,.0f}</td><td class='{pnl_cls}'>${r['avg']:+,.0f}</td></tr>")
    html.append("</tbody></table>")

    # Seasonality chart
    html.append("<div id='season-chart' style='height:400px;'></div>")
    html.append("<script>")
    season_x = [MONTHS_AR[int(m)] for m in seasonality["month"]]
    season_pnl = seasonality["pnl"].round(0).tolist()
    season_colors = ['#2ecc71' if p>0 else '#e74c3c' for p in season_pnl]
    html.append(f"Plotly.newPlot('season-chart', [{{x: {json.dumps(season_x, ensure_ascii=False)}, y: {json.dumps(season_pnl)}, type:'bar', marker:{{color: {json.dumps(season_colors)}}}, text: {json.dumps([f'${p:+,.0f}' for p in season_pnl])}, textposition:'auto'}}], {{paper_bgcolor:'#0a0e1a', plot_bgcolor:'#1a2332', font:{{color:'#e0e6f0'}}, title:'PnL الإجمالي حسب الشهر (كل السنوات)', yaxis:{{title:'PnL $'}}}});")
    html.append("</script>")
    html.append("</div>")

    # Heatmap: Year × Month PnL grid
    heatmap = trades.pivot_table(index="year", columns="month", values="profit_abs", aggfunc="sum").fillna(0)
    html.append("<div class='card'><h2>🔥 Heatmap — السنة × الشهر</h2>")
    html.append("<table class='heatmap'><thead><tr><th>السنة \\ الشهر</th>")
    for m in range(1, 13):
        html.append(f"<th>{MONTHS_AR[m][:3]}</th>")
    html.append("<th>إجمالي</th></tr></thead><tbody>")
    for yr in sorted(heatmap.index):
        html.append(f"<tr><td><b>{int(yr)}</b></td>")
        for m in range(1, 13):
            v = heatmap.loc[yr, m] if m in heatmap.columns else 0
            if v == 0:
                html.append(f"<td class='heatmap-cell empty'>—</td>")
            else:
                # Color intensity
                if v > 0:
                    intensity = min(1.0, v/3000)
                    bg = f"rgba(46,204,113,{0.2 + 0.6*intensity})"
                else:
                    intensity = min(1.0, abs(v)/3000)
                    bg = f"rgba(231,76,60,{0.2 + 0.6*intensity})"
                html.append(f"<td class='heatmap-cell' style='background:{bg};color:white;'>${v:+,.0f}</td>")
        yr_total = heatmap.loc[yr].sum()
        cls = "pos" if yr_total >= 0 else "neg"
        html.append(f"<td class='heatmap-cell {cls}'><b>${yr_total:+,.0f}</b></td></tr>")
    html.append("</tbody></table></div>")

    html.append("</body></html>")
    OUT_HTML.write_text("\n".join(html), encoding="utf-8")
    print(f"HTML: {OUT_HTML}")
    print(f"Size: {OUT_HTML.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
