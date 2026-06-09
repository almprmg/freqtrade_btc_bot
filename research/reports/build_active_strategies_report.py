"""build_active_strategies_report.py — Year + month breakdown for active subs.

Only the 16 currently active Tier-1 subscriptions:
  #97, #98, #99, #100, #101, #102, #103, #104, #105, #106, #108
  #109, #110, #111, #112, #113
  (#107 Calendar XRP paused — excluded)

Output: research/reports/ACTIVE_STRATEGIES_DETAIL.html
"""
from __future__ import annotations

import json
import pandas as pd
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "research" / "comprehensive_backtest_results.json"
EXPERIMENTS = REPO / "research" / "experiments"
OUT_HTML = REPO / "research" / "reports" / "ACTIVE_STRATEGIES_DETAIL.html"

# Maps comprehensive_backtest label → live subscription #
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


def load_trades(label):
    s = short(label)
    dfs = []
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
                dfs.append(df)
            except: pass
    if not dfs: return None
    return pd.concat(dfs, ignore_index=True)


def build_strategy_section(label, sub_num, coin, yearly_results):
    trades = load_trades(label)
    if trades is None or trades.empty:
        return f"<div class='card'><h2>{sub_num} {label} ({coin})</h2><p>لا توجد بيانات صفقات</p></div>"

    # Overall stats
    n = len(trades); wins = trades["is_win"].sum()
    wr = wins/n*100; total_pnl = trades["profit_abs"].sum()
    avg_win = trades.loc[trades["is_win"], "profit_abs"].mean() if wins else 0
    avg_loss = trades.loc[~trades["is_win"], "profit_abs"].mean() if (n-wins) else 0

    html = [f"<div class='card'>",
            f"<h2 class='sub-id'>{sub_num}</h2><h2>{label}</h2>",
            f"<p class='coin-tag'>{coin}</p>"]

    # Summary box
    html.append("<div class='summary'>")
    html.append(f"<div><b>إجمالي الصفقات:</b> {n}</div>")
    html.append(f"<div><b>WR:</b> <span class='wr'>{wr:.1f}%</span> ({wins}W / {n-wins}L)</div>")
    html.append(f"<div><b>إجمالي PnL:</b> <span class='{'pos' if total_pnl>=0 else 'neg'}'>${total_pnl:+,.0f}</span></div>")
    html.append(f"<div><b>متوسط ربح/خسارة:</b> +${avg_win:.0f} / ${avg_loss:.0f}</div>")
    html.append("</div>")

    # Yearly summary
    html.append("<h3>📅 السنوي</h3>")
    html.append("<table class='yr'><thead><tr><th>السنة</th><th>ROI</th><th>الصفقات</th><th>فوز</th><th>خسارة</th><th>WR</th><th>PnL ($)</th><th>DD</th></tr></thead><tbody>")
    for yr, r in sorted(yearly_results.items()):
        if not r.get("ok"): continue
        ydf = trades[trades["year"] == int(yr)]
        y_n = len(ydf); y_w = ydf["is_win"].sum() if y_n else 0
        y_wr = y_w/y_n*100 if y_n else 0
        y_pnl = ydf["profit_abs"].sum() if y_n else 0
        roi_cls = "pos" if r["roi"] >= 0 else "neg"
        html.append(f"<tr><td><b>{yr}</b></td><td class='{roi_cls}'>{r['roi']:+.1f}%</td>"
                   f"<td>{y_n}</td><td>{y_w}</td><td>{y_n-y_w}</td>"
                   f"<td>{y_wr:.0f}%</td><td class='{'pos' if y_pnl>=0 else 'neg'}'>${y_pnl:+,.0f}</td><td>{r.get('dd',0):.1f}%</td></tr>")
    html.append("</tbody></table>")

    # Monthly breakdown per year
    html.append("<h3>📆 الشهري — تفصيل لكل سنة</h3>")
    years_in_trades = sorted(trades["year"].dropna().unique())
    for yr in years_in_trades:
        yr_int = int(yr)
        ydf = trades[trades["year"] == yr_int]
        if ydf.empty: continue
        html.append(f"<h4 class='year-h'>📅 {yr_int}</h4>")
        html.append("<table class='mo'><thead><tr><th>الشهر</th><th>صفقات</th><th>فوز</th><th>خسارة</th><th>WR</th><th>PnL ($)</th></tr></thead><tbody>")
        # All 12 months in row
        for m in range(1, 13):
            mdf = ydf[ydf["month"] == m]
            m_n = len(mdf)
            if m_n == 0:
                html.append(f"<tr class='empty'><td>{MONTHS_AR[m]}</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td></tr>")
                continue
            m_w = mdf["is_win"].sum(); m_wr = m_w/m_n*100
            m_pnl = mdf["profit_abs"].sum()
            html.append(f"<tr><td><b>{MONTHS_AR[m]}</b></td><td>{m_n}</td><td>{m_w}</td>"
                       f"<td>{m_n-m_w}</td><td>{m_wr:.0f}%</td>"
                       f"<td class='{'pos' if m_pnl>=0 else 'neg'}'>${m_pnl:+,.0f}</td></tr>")
        html.append("</tbody></table>")

    html.append("</div>")  # /card
    return "\n".join(html)


def main():
    results = json.loads(RESULTS.read_text(encoding="utf-8"))

    html = [
        "<!DOCTYPE html><html lang='ar' dir='rtl'><head><meta charset='UTF-8'>",
        "<title>الاستراتيجيات النشطة — تفصيل سنوي + شهري</title>",
        "<style>",
        "body{font-family:Arial,sans-serif;background:#0a0e1a;color:#e0e6f0;margin:0;padding:20px;line-height:1.5;}",
        "h1{color:#5dade2;border-bottom:3px solid #5dade2;padding-bottom:10px;}",
        "h2{color:#48c9b0;display:inline-block;margin:0 10px 0 0;}",
        "h2.sub-id{color:#f39c12;font-size:1.2em;}",
        "h3{color:#5dade2;border-bottom:1px solid #34495e;padding-bottom:5px;margin-top:20px;}",
        "h4.year-h{color:#f39c12;margin-top:15px;}",
        ".coin-tag{display:inline-block;background:#3498db;color:white;padding:3px 10px;border-radius:4px;font-size:0.9em;}",
        ".card{background:#1a2332;border-radius:8px;padding:20px;margin:20px 0;border-left:4px solid #f39c12;}",
        ".summary{display:flex;gap:20px;background:#222d3e;padding:15px;border-radius:6px;margin:15px 0;flex-wrap:wrap;}",
        ".summary > div{font-size:1em;}",
        ".wr{color:#48c9b0;font-weight:bold;}",
        ".pos{color:#2ecc71;font-weight:bold;}",
        ".neg{color:#e74c3c;}",
        "table{border-collapse:collapse;width:100%;margin:10px 0;background:#1a2332;}",
        "th{background:#2c3e50;padding:8px;text-align:right;border:1px solid #34495e;color:#5dade2;}",
        "td{padding:7px;border:1px solid #34495e;text-align:right;}",
        "tr.empty td{color:#566573;}",
        "table.mo th{background:#7f5c00;}",
        ".toc{background:#1a2332;padding:15px;border-radius:8px;margin:20px 0;}",
        ".toc a{color:#5dade2;text-decoration:none;display:inline-block;margin:5px 10px;}",
        ".toc a:hover{color:#48c9b0;}",
        "</style></head><body>",
        f"<h1>📊 تفصيل الاستراتيجيات النشطة ({len(ACTIVE)}) — السنوي + الشهري</h1>",
        f"<p><b>التاريخ:</b> 2026-06-09 | <b>التغطية:</b> 9 سنوات (2018-2026) | <b>السنوي + الشهري لكل واحدة</b></p>",
    ]

    # TOC
    html.append("<div class='toc'><b>الانتقال السريع:</b><br>")
    for label, (sub_num, coin) in ACTIVE.items():
        anchor = sub_num.replace("#", "")
        html.append(f"<a href='#s{anchor}'>{sub_num} {label}</a>")
    html.append("</div>")

    # Each strategy
    for label, (sub_num, coin) in ACTIVE.items():
        if label not in results:
            continue
        anchor = sub_num.replace("#", "")
        html.append(f"<a id='s{anchor}'></a>")
        html.append(build_strategy_section(label, sub_num, coin, results[label].get("years", {})))

    html.append("</body></html>")
    OUT_HTML.write_text("\n".join(html), encoding="utf-8")
    print(f"HTML: {OUT_HTML}")
    print(f"Size: {OUT_HTML.stat().st_size:,} bytes")
    print(f"Strategies covered: {len(ACTIVE)}")


if __name__ == "__main__":
    main()
