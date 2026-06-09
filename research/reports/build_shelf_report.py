"""build_shelf_report.py — Dashboard for the 39 strategies kept on the shelf.

Focus: production-ready code, tested OK (CAGR >= 2%), but NOT in deployed
subscriptions #97-#108. These are deployment candidates.

Output: research/reports/SHELF_DASHBOARD.html + SHELF_REPORT.md
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FT_RESULTS = REPO / "research" / "comprehensive_backtest_results.json"
TE_RESULTS = Path("d:/pythone/trading_engine/research/te_backtest_results.json")
OUT_HTML = REPO / "research" / "reports" / "SHELF_DASHBOARD.html"
OUT_MD = REPO / "research" / "reports" / "SHELF_REPORT.md"

DEPLOYED = {
    "AI Shield V1 (#97)", "Triple Regime BTC (#98)", "AI Shield V2 (#99)",
    "Calendar BTC (#100)", "ETH Pure Shield (#101)", "SOL VolShield (#102)",
    "Triple Regime BNB (#103)", "Triple Regime ADA (#104)", "Calendar ETH (#105)",
    "Calendar BNB (#106)", "Calendar XRP (#107)", "Macro V2 BTC (#108)",
}

# Strategies running as legacy bots on server (vs purely prototype)
LEGACY_RUNNING = {
    "Rotation Multi", "BNB Regime Shield SLOW", "Shield SOL (legacy)",
    "OnChain BTC", "DOGE Regime Shield DEFENSIVE", "ADA Meta Adaptive BAL",
    "AVAX Meta Adaptive RELAX", "Shield BTC (original)", "DynRebal BTC",
    "DynRebal ETH", "DynRebal SOL", "Rebalance BTC", "Adaptive BTC",
    "3Layer BTC", "DCA Hold BTC", "MetaAdaptive LINK",
}


def stats(years):
    c = 1.0; ok = 0; n = 0
    yearly = []
    for yr, r in years.items():
        if not r.get("ok"): continue
        c *= (1 + r["roi"]/100); ok += 1; n += r.get("n", 0)
        yearly.append({"yr": int(yr), "roi": r["roi"], "n": r.get("n", 0), "dd": r.get("dd", 0)})
    if ok == 0: return None
    return {"end": 10000*c, "cagr": (c**(1/ok)-1)*100, "trades": n, "yrs": ok, "yearly": yearly}


def main():
    ft = json.loads(FT_RESULTS.read_text(encoding="utf-8"))
    te = json.loads(TE_RESULTS.read_text(encoding="utf-8"))

    shelf = []
    for label, info in ft.items():
        s = stats(info.get("years", {}))
        if not s or s["cagr"] < 2 or label in DEPLOYED:
            continue
        shelf.append({
            "label": label, "coin": info.get("coin", "?"), "tf": "1d",
            "kind": "legacy_bot" if label in LEGACY_RUNNING else "prototype",
            "system": "freqtrade",
            **s,
        })

    for name, info in te.items():
        s = stats(info.get("years", {}))
        if not s or s["cagr"] < 2: continue
        shelf.append({
            "label": name, "coin": info.get("symbol", "BTCUSDT").replace("USDT", ""),
            "tf": info.get("timeframe", "1h"), "kind": "signal", "system": "trading_engine",
            **s,
        })

    shelf.sort(key=lambda x: x["cagr"], reverse=True)
    print(f"Strategies on the shelf: {len(shelf)}")

    # ---------- MARKDOWN ----------
    md = [
        "# 📦 تقرير الاستراتيجيات المحفوظة للمستقبل\n",
        "**تاريخ الإصدار:** 2026-06-09  \n",
        f"**العدد:** {len(shelf)} استراتيجية  \n",
        "**المعيار:** مختبرة 9 سنوات + CAGR ≥ 2% + ليست ضمن المنشورة #97-#108\n\n",
        "---\n\n",
        "## الفئات\n\n",
    ]

    cats = [
        ("legacy_bot", "🔄 Legacy Bots — شغّالة على السيرفر بدون subscription رسمية"),
        ("prototype", "🧪 Prototypes — كود جاهز لكن لم تُنشر"),
        ("signal", "📡 Signal-Only — استراتيجيات dashboard من trading_engine"),
    ]

    for kind, title in cats:
        items = [s for s in shelf if s["kind"] == kind]
        if not items: continue
        md.append(f"### {title}  ({len(items)})\n")
        md.append("| # | الاستراتيجية | عملة | TF | $10K → | CAGR | صفقات | سنوات |")
        md.append("|---|---|---|---|---|---|---|---|")
        for i, s in enumerate(items):
            star = " ⭐" if "STAR" in s["label"] else ""
            md.append(
                f"| {i+1} | **{s['label']}**{star} | {s['coin']} | {s['tf']} | "
                f"${s['end']:,.0f} | **{s['cagr']:+.1f}%/yr** | {s['trades']} | {s['yrs']} |"
            )
        md.append("")

    md.append("\n## 🎯 توصيات الترقية للـProduction\n")
    md.append("الاستراتيجيات المرشّحة للترقية لـsubscription رسمي (أعلى من +25% CAGR):\n")
    promotion_candidates = [s for s in shelf if s["cagr"] >= 25 and s["system"] == "freqtrade"]
    md.append("| # | الاستراتيجية | عملة | CAGR | الحالة الحالية |")
    md.append("|---|---|---|---|---|")
    for i, s in enumerate(promotion_candidates):
        status = "Legacy bot شغّال" if s["kind"] == "legacy_bot" else "Code محفوظ"
        md.append(f"| {i+1} | **{s['label']}** | {s['coin']} | **{s['cagr']:+.1f}%/yr** | {status} |")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"Markdown: {OUT_MD}")

    # ---------- HTML ----------
    html = [
        "<!DOCTYPE html><html lang='ar' dir='rtl'><head><meta charset='UTF-8'>",
        "<title>الاستراتيجيات المحفوظة — Shelf Dashboard</title>",
        "<script src='https://cdn.plot.ly/plotly-latest.min.js'></script>",
        "<style>",
        "body{font-family:Arial,sans-serif;background:#0a0e1a;color:#e0e6f0;margin:0;padding:20px;}",
        "h1{color:#f39c12;border-bottom:3px solid #f39c12;padding-bottom:10px;}",
        "h2{color:#48c9b0;margin-top:30px;}",
        ".sumbox{background:#1a2332;border-radius:8px;padding:20px;margin:20px 0;border-left:4px solid #f39c12;}",
        ".tag-legacy{background:#3498db;color:white;padding:2px 8px;border-radius:4px;font-size:0.85em;}",
        ".tag-proto{background:#e67e22;color:white;padding:2px 8px;border-radius:4px;font-size:0.85em;}",
        ".tag-signal{background:#9b59b6;color:white;padding:2px 8px;border-radius:4px;font-size:0.85em;}",
        "table{width:100%;border-collapse:collapse;margin:15px 0;background:#1a2332;}",
        "th{background:#2c3e50;padding:12px;text-align:right;border:1px solid #34495e;color:#5dade2;}",
        "td{padding:10px;border:1px solid #34495e;text-align:right;}",
        "tr:nth-child(even){background:#222d3e;}",
        "tr:hover{background:#2c3e50;}",
        ".pos{color:#2ecc71;font-weight:bold;}",
        ".star{color:#f1c40f;font-size:1.2em;}",
        ".filter-bar button{background:#34495e;color:white;border:none;padding:8px 16px;margin:5px;border-radius:4px;cursor:pointer;}",
        ".filter-bar button.active{background:#3498db;}",
        ".rec-box{background:#27ae60;color:white;padding:15px;border-radius:8px;margin:20px 0;}",
        ".rec-box ul{margin:10px 0;}",
        "</style></head><body>",
        f"<h1>📦 الاستراتيجيات المحفوظة للمستقبل ({len(shelf)})</h1>",
        "<div class='sumbox'>",
        "<b>الفلسفة:</b> هذه استراتيجيات نجحت في الـbacktest (CAGR ≥ 2% على 9 سنوات) "
        "لكنها <b>ليست منشورة</b> كـsubscription رسمي حاليًا. يمكن ترقيتها للإنتاج أو دمجها مع أخرى أو الإبقاء عليها كـreserve.",
        f"<br><b>التاريخ:</b> 2026-06-09 | <b>العدد الإجمالي:</b> {len(shelf)}",
        "</div>",
    ]

    # Chart: top 20 by CAGR
    top = shelf[:20]
    labels = [s["label"][:30] for s in top]
    cagrs = [round(s["cagr"], 1) for s in top]
    colors = [{"legacy_bot": "#3498db", "prototype": "#e67e22", "signal": "#9b59b6"}[s["kind"]] for s in top]
    html.extend([
        "<h2>📈 أفضل 20 — مقارنة CAGR</h2>",
        "<div id='chart' style='height:500px;'></div>",
        "<script>",
        f"Plotly.newPlot('chart', [{{x: {json.dumps(labels, ensure_ascii=False)}, y: {json.dumps(cagrs)}, type:'bar', marker:{{color: {json.dumps(colors)}}}, text: {json.dumps([f'{v}%' for v in cagrs])}, textposition:'auto'}}], "
        "{paper_bgcolor:'#0a0e1a', plot_bgcolor:'#1a2332', font:{color:'#e0e6f0'}, xaxis:{tickangle:-45}, yaxis:{title:'CAGR %'}});",
        "</script>",
    ])

    # Promotion recommendations
    promo = [s for s in shelf if s["cagr"] >= 25 and s["system"] == "freqtrade"]
    html.append("<div class='rec-box'>")
    html.append(f"<h2 style='margin-top:0;color:white'>🎯 توصيات الترقية للإنتاج ({len(promo)} استراتيجية)</h2>")
    html.append("<ul>")
    for s in promo[:8]:
        star = " ⭐" if "STAR" in s["label"] else ""
        html.append(f"<li><b>{s['label']}{star}</b> ({s['coin']}) — <b>{s['cagr']:+.1f}%/yr</b> | الحالة: {'🔄 Legacy bot' if s['kind']=='legacy_bot' else '🧪 Prototype'}</li>")
    html.append("</ul></div>")

    # Filter buttons + table
    html.extend([
        "<h2>📋 الجدول الكامل</h2>",
        "<div class='filter-bar'>",
        "<button onclick='filt(\"all\")' class='active' id='b-all'>الكل</button>",
        "<button onclick='filt(\"legacy_bot\")' id='b-legacy_bot'>🔄 Legacy</button>",
        "<button onclick='filt(\"prototype\")' id='b-prototype'>🧪 Prototype</button>",
        "<button onclick='filt(\"signal\")' id='b-signal'>📡 Signal</button>",
        "</div>",
        "<table id='maintbl'>",
        "<thead><tr><th>#</th><th>الاستراتيجية</th><th>الفئة</th><th>عملة</th><th>TF</th>"
        "<th>$10K → 9y</th><th>CAGR</th><th>صفقات</th><th>سنوات</th></tr></thead><tbody>",
    ])

    for i, s in enumerate(shelf):
        tag_class = {"legacy_bot": "tag-legacy", "prototype": "tag-proto", "signal": "tag-signal"}[s["kind"]]
        tag_label = {"legacy_bot": "Legacy", "prototype": "Prototype", "signal": "Signal"}[s["kind"]]
        star = "<span class='star'>⭐</span>" if "STAR" in s["label"] else ""
        html.append(
            f"<tr data-kind='{s['kind']}'>"
            f"<td>{i+1}</td>"
            f"<td><b>{s['label']}</b> {star}</td>"
            f"<td><span class='{tag_class}'>{tag_label}</span></td>"
            f"<td>{s['coin']}</td>"
            f"<td>{s['tf']}</td>"
            f"<td>${s['end']:,.0f}</td>"
            f"<td class='pos'>{s['cagr']:+.1f}%/yr</td>"
            f"<td>{s['trades']}</td>"
            f"<td>{s['yrs']}</td>"
            f"</tr>"
        )

    html.extend([
        "</tbody></table>",
        "<script>",
        "function filt(k){document.querySelectorAll('#maintbl tbody tr').forEach(r=>r.style.display=(k==='all'||r.dataset.kind===k)?'':'none');document.querySelectorAll('.filter-bar button').forEach(b=>b.classList.remove('active'));document.getElementById('b-'+k).classList.add('active');}",
        "</script>",
        "</body></html>",
    ])

    OUT_HTML.write_text("\n".join(html), encoding="utf-8")
    print(f"HTML: {OUT_HTML} ({OUT_HTML.stat().st_size:,} bytes)")

    # Summary
    print(f"\n=== الفئات ===")
    for kind, title in cats:
        items = [s for s in shelf if s["kind"] == kind]
        print(f"  {title}: {len(items)}")


if __name__ == "__main__":
    main()
