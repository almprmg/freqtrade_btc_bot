"""build_unified_report.py — Unified HTML + Markdown report covering ALL strategies.

Combines:
  - freqtrade strategies (research/comprehensive_backtest_results.json)
  - trading_engine strategies (../trading_engine/research/te_backtest_results.json)

Output:
  - research/reports/UNIFIED_DASHBOARD.html
  - research/reports/UNIFIED_REPORT.md
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FT_RESULTS = REPO / "research" / "comprehensive_backtest_results.json"
TE_RESULTS = Path("d:/pythone/trading_engine/research/te_backtest_results.json")
OUT_HTML = REPO / "research" / "reports" / "UNIFIED_DASHBOARD.html"
OUT_MD = REPO / "research" / "reports" / "UNIFIED_REPORT.md"


def compute_stats(years_data: dict, sys_name: str, label: str, extra: dict) -> dict:
    compound = 1.0
    yearly = []
    total_trades = 0
    ok_years = 0
    for yr, r in years_data.items():
        if not r.get("ok"):
            continue
        compound *= (1 + r["roi"] / 100)
        yearly.append({"year": int(yr), "roi": r["roi"], "n": r.get("n", 0), "dd": r.get("dd", 0)})
        total_trades += r.get("n", 0)
        ok_years += 1
    if ok_years == 0:
        return None
    cagr = (compound ** (1 / max(ok_years, 1)) - 1) * 100
    return {
        "label": label,
        "system": sys_name,
        "compound": 10000 * compound,
        "cagr": cagr,
        "n_trades": total_trades,
        "yearly": yearly,
        "ok_years": ok_years,
        **extra,
    }


def main():
    all_stats = []

    # Load freqtrade results
    ft = json.loads(FT_RESULTS.read_text(encoding="utf-8")) if FT_RESULTS.exists() else {}
    for label, info in ft.items():
        s = compute_stats(info.get("years", {}), "freqtrade", label,
                          {"coin": info.get("coin", "?"), "kind": "production"})
        if s:
            all_stats.append(s)

    # Load trading_engine results
    te = json.loads(TE_RESULTS.read_text(encoding="utf-8")) if TE_RESULTS.exists() else {}
    for name, info in te.items():
        coin = info.get("symbol", "BTCUSDT").replace("USDT", "")
        s = compute_stats(info.get("years", {}), "trading_engine", name,
                          {"coin": coin, "kind": "signal", "timeframe": info.get("timeframe", "1h")})
        if s:
            all_stats.append(s)

    all_stats.sort(key=lambda x: x["cagr"], reverse=True)
    print(f"Total strategies in report: {len(all_stats)}")

    # ---------- MARKDOWN ----------
    md = [
        "# 🌐 التقرير الموحّد الشامل — كل الاستراتيجيات\n",
        "**التاريخ:** 2026-06-08\n",
        f"**عدد الاستراتيجيات:** {len(all_stats)}\n",
        f"**يشمل:** freqtrade production bots + trading_engine signals\n\n",
        "---\n\n## 📊 الترتيب الكامل (مرتّب بالـCAGR من $10K)\n\n",
        "| # | الاستراتيجية | نظام | عملة/TF | $10K → 9y | CAGR | صفقات |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, s in enumerate(all_stats):
        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}"
        kind_tag = "🤖 prod" if s["kind"] == "production" else "📡 signal"
        tf = f" {s.get('timeframe','')}" if s.get("kind") == "signal" else ""
        md.append(
            f"| {medal} | **{s['label']}** | {kind_tag} | {s['coin']}{tf} | "
            f"${s['compound']:,.0f} | **{s['cagr']:+.1f}%/yr** | {s['n_trades']} |"
        )

    # Top per system
    md.append("\n## 🏆 الأفضل لكل نظام:\n")
    for sys in ["production", "signal"]:
        sys_top = [s for s in all_stats if s["kind"] == sys][:5]
        if not sys_top:
            continue
        md.append(f"\n### {('🤖 freqtrade production' if sys=='production' else '📡 trading_engine signals')}\n")
        for s in sys_top:
            md.append(f"- **{s['label']}** ({s['coin']}): {s['cagr']:+.1f}%/yr → ${s['compound']:,.0f}")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"Markdown: {OUT_MD}")

    # ---------- HTML ----------
    html = [
        "<!DOCTYPE html><html lang='ar' dir='rtl'><head><meta charset='UTF-8'>",
        "<title>التقرير الموحّد — كل الاستراتيجيات</title>",
        "<script src='https://cdn.plot.ly/plotly-latest.min.js'></script>",
        "<style>",
        "body{font-family:Arial,sans-serif;background:#0a0e1a;color:#e0e6f0;margin:0;padding:20px;}",
        "h1{color:#5dade2;border-bottom:3px solid #5dade2;padding-bottom:10px;}",
        "h2{color:#48c9b0;margin-top:30px;}",
        ".sumbox{background:#1a2332;border-radius:8px;padding:20px;margin:20px 0;border-left:4px solid #f39c12;}",
        ".tag-prod{background:#1abc9c;color:white;padding:2px 8px;border-radius:4px;font-size:0.85em;}",
        ".tag-sig{background:#9b59b6;color:white;padding:2px 8px;border-radius:4px;font-size:0.85em;}",
        "table{width:100%;border-collapse:collapse;margin:15px 0;background:#1a2332;}",
        "th{background:#2c3e50;padding:12px;text-align:right;border:1px solid #34495e;color:#5dade2;}",
        "td{padding:10px;border:1px solid #34495e;text-align:right;}",
        "tr:nth-child(even){background:#222d3e;}",
        "tr:hover{background:#2c3e50;}",
        ".pos{color:#2ecc71;font-weight:bold;}",
        ".neg{color:#e74c3c;}",
        ".medal{font-size:1.4em;}",
        ".filter-bar{margin:20px 0;padding:15px;background:#1a2332;border-radius:8px;}",
        ".filter-bar button{background:#34495e;color:white;border:none;padding:8px 16px;margin:5px;border-radius:4px;cursor:pointer;}",
        ".filter-bar button.active{background:#3498db;}",
        "</style></head><body>",
        f"<h1>🌐 التقرير الموحّد — كل الاستراتيجيات ({len(all_stats)})</h1>",
        f"<div class='sumbox'><b>عدد الاستراتيجيات:</b> {len(all_stats)} | "
        f"<b>الـSystems:</b> freqtrade production + trading_engine signals | "
        f"<b>الإطار:</b> 9 سنوات (2018-2026) | <b>التاريخ:</b> 2026-06-08</div>",
    ]

    # Chart data
    labels_short = [s["label"][:25] for s in all_stats[:30]]
    cagrs = [round(s["cagr"], 1) for s in all_stats[:30]]
    colors = ["#2ecc71" if s["kind"] == "production" else "#9b59b6" for s in all_stats[:30]]
    html.extend([
        "<h2>📈 Top 30 — مقارنة الـCAGR</h2>",
        "<div id='chart' style='height:600px;'></div>",
        "<script>",
        f"const labels = {json.dumps(labels_short, ensure_ascii=False)};",
        f"const cagrs = {json.dumps(cagrs)};",
        f"const colors = {json.dumps(colors)};",
        "Plotly.newPlot('chart', [{x:labels, y:cagrs, type:'bar', marker:{color:colors}, "
        "text:cagrs.map(v=>v+'%'), textposition:'auto'}], "
        "{paper_bgcolor:'#0a0e1a', plot_bgcolor:'#1a2332', font:{color:'#e0e6f0'}, "
        "xaxis:{tickangle:-45}, yaxis:{title:'CAGR %'}});",
        "</script>",
    ])

    # Filter buttons
    html.extend([
        "<h2>📋 الجدول الكامل</h2>",
        "<div class='filter-bar'>",
        "<b>فلتر:</b>",
        "<button onclick='filterRows(\"all\")' class='active' id='btn-all'>الكل</button>",
        "<button onclick='filterRows(\"production\")' id='btn-production'>🤖 Production</button>",
        "<button onclick='filterRows(\"signal\")' id='btn-signal'>📡 Signals</button>",
        "</div>",
        "<table id='maintable'>",
        "<thead><tr><th>#</th><th>الاستراتيجية</th><th>النظام</th><th>عملة</th>"
        "<th>TF</th><th>$10K → 9y</th><th>CAGR</th><th>صفقات</th></tr></thead><tbody>",
    ])

    for i, s in enumerate(all_stats):
        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else str(i + 1)
        tag = "<span class='tag-prod'>prod</span>" if s["kind"] == "production" else "<span class='tag-sig'>signal</span>"
        cagr_cls = "pos" if s["cagr"] > 0 else "neg"
        tf = s.get("timeframe", "—") if s["kind"] == "signal" else "—"
        html.append(
            f"<tr data-kind='{s['kind']}'>"
            f"<td class='medal'>{medal}</td>"
            f"<td><b>{s['label']}</b></td>"
            f"<td>{tag}</td>"
            f"<td>{s['coin']}</td>"
            f"<td>{tf}</td>"
            f"<td>${s['compound']:,.0f}</td>"
            f"<td class='{cagr_cls}'>{s['cagr']:+.1f}%/yr</td>"
            f"<td>{s['n_trades']}</td>"
            f"</tr>"
        )

    html.extend([
        "</tbody></table>",
        "<script>",
        "function filterRows(kind) {",
        "  document.querySelectorAll('#maintable tbody tr').forEach(r => {",
        "    r.style.display = (kind === 'all' || r.dataset.kind === kind) ? '' : 'none';",
        "  });",
        "  document.querySelectorAll('.filter-bar button').forEach(b => b.classList.remove('active'));",
        "  document.getElementById('btn-' + kind).classList.add('active');",
        "}",
        "</script>",
        "</body></html>",
    ])

    OUT_HTML.write_text("\n".join(html), encoding="utf-8")
    print(f"HTML: {OUT_HTML}")
    print(f"Size: {OUT_HTML.stat().st_size:,} bytes")

    # Top 10 summary
    print("\nTOP 10:")
    for i, s in enumerate(all_stats[:10]):
        sys_tag = "prod" if s["kind"] == "production" else "sig "
        print(f"  {i+1:>2}. [{sys_tag}] {s['label']:<32} {s['coin']:<6} ${s['compound']:>12,.0f}  {s['cagr']:+.1f}%/yr")


if __name__ == "__main__":
    main()
