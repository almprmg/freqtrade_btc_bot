"""slippage_analyzer.py — يحلّل أثر الـ slippage والـ partial fills على الاستراتيجيات.

المشكلة:
  - الأسعار في الـbacktest = close price نظري
  - في السوق الحقيقي: spread + market depth = slippage
  - الـorder كبير ممكن ما يتعبّأ بالكامل بنفس السعر

الحل:
  1. تقدير الـ slippage الواقعي لكل عملة (من الحجم + spread)
  2. إعادة الـbacktest مع slippage realistic
  3. اختبار splitting الأوامر (TWAP) كحل
  4. توصيات per-coin
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "user_data" / "data" / "binance"

# Typical Binance spot fees + spread estimates (basis points)
# Source: Binance public data + common observations
COIN_LIQUIDITY = {
    # coin: {avg_24h_vol_M_usd, typical_spread_bps, depth_at_0.1pct_M_usd}
    "BTC":  {"vol_24h": 5000, "spread_bps": 1.0,  "depth_01pct": 15.0},
    "ETH":  {"vol_24h": 3000, "spread_bps": 1.5,  "depth_01pct": 8.0},
    "BNB":  {"vol_24h": 500,  "spread_bps": 2.0,  "depth_01pct": 2.0},
    "SOL":  {"vol_24h": 1500, "spread_bps": 2.0,  "depth_01pct": 4.0},
    "XRP":  {"vol_24h": 1000, "spread_bps": 2.5,  "depth_01pct": 3.0},
    "ADA":  {"vol_24h": 300,  "spread_bps": 3.0,  "depth_01pct": 1.0},
    "DOGE": {"vol_24h": 400,  "spread_bps": 3.0,  "depth_01pct": 1.0},
    "AVAX": {"vol_24h": 200,  "spread_bps": 3.5,  "depth_01pct": 0.7},
}


def estimate_slippage(coin: str, order_size_usd: float) -> dict:
    """تقدير الـ slippage لـ market order على عملة محدّدة.

    formula:
      base_slippage = spread_bps / 2 (نصف الـspread يصير عندك)
      impact = sqrt(order_size / depth_01pct) × 0.10%
      total = base_slippage + impact
    """
    if coin not in COIN_LIQUIDITY:
        return {"slippage_bps": 50.0, "warning": "unknown coin, assuming 0.5%"}
    liq = COIN_LIQUIDITY[coin]
    base = liq["spread_bps"] / 2  # half the spread
    # Square-root market impact model
    depth_usd = liq["depth_01pct"] * 1_000_000  # convert M to USD
    if order_size_usd <= depth_usd * 0.10:
        impact_bps = 0.5  # negligible
    elif order_size_usd <= depth_usd:
        impact_bps = 5.0 * np.sqrt(order_size_usd / depth_usd)
    else:
        # Large order — sqrt scaling but doubled for cascading depth
        impact_bps = 15.0 * (order_size_usd / depth_usd) ** 0.5
    total = base + impact_bps
    return {
        "coin": coin,
        "order_size_usd": order_size_usd,
        "base_spread_bps": base,
        "market_impact_bps": impact_bps,
        "total_slippage_bps": total,
        "total_slippage_pct": total / 100,
        "expected_cost_usd": order_size_usd * (total / 10000),
    }


def analyze_strategy_impact(wallet_usd: float = 3000):
    """لكل عملة + wallet size، احسب الـ slippage cost لرحلة round-trip (دخول + خروج)."""
    print(f"\n{'=' * 80}")
    print(f"  تحليل الـ Slippage لـ wallet = ${wallet_usd:,.0f}")
    print(f"{'=' * 80}")
    print(f"{'العملة':<8}{'spread':>10}{'impact':>10}{'total':>10}{'cost (rt)':>12}{'تأثير':>20}")
    print("-" * 80)
    for coin in COIN_LIQUIDITY.keys():
        est = estimate_slippage(coin, wallet_usd)
        rt_cost = est["expected_cost_usd"] * 2  # round trip (entry + exit)
        impact_pct = (rt_cost / wallet_usd) * 100
        verdict = "ممتاز" if impact_pct < 0.05 else "جيد" if impact_pct < 0.15 else "مقبول" if impact_pct < 0.30 else "سيء"
        print(f"{coin:<8}{est['base_spread_bps']:>7.1f}bp{est['market_impact_bps']:>7.1f}bp{est['total_slippage_bps']:>7.1f}bp ${rt_cost:>8.2f}    {impact_pct:>4.2f}%  {verdict}")


def slippage_per_strategy(annual_trades: int, wallet_usd: float, coin: str) -> dict:
    """احسب الأثر السنوي للـ slippage على استراتيجية تنفّذ N صفقات/سنة."""
    est = estimate_slippage(coin, wallet_usd)
    rt_cost = est["expected_cost_usd"] * 2
    annual_cost = rt_cost * annual_trades
    annual_cost_pct = (annual_cost / wallet_usd) * 100
    return {
        "annual_trades": annual_trades,
        "slippage_bps_per_rt": est["total_slippage_bps"] * 2,
        "annual_cost_usd": annual_cost,
        "annual_cost_pct": annual_cost_pct,
    }


def compare_strategies(wallet_usd: float = 3000):
    """قارن تأثير الـ slippage على الاستراتيجيات الحالية."""
    print(f"\n{'=' * 80}")
    print(f"  تأثير الـ Slippage السنوي على الاستراتيجيات الحالية ($3K wallet)")
    print(f"{'=' * 80}")
    # Strategy → (coin, annual_trades, annual_CAGR_bps)
    strategies = [
        ("Calendar Shield BTC", "BTC", 30/9, 3090),
        ("ETH Calendar (#105)", "ETH", 27/9, 3920),
        ("AnalogV2 ETH ⭐",     "ETH", 27/9, 4220),
        ("Macro V2 BTC (#108)", "BTC", 30/9, 3300),
        ("BNB Calendar (#106)", "BNB", 28/9, 3100),
        ("XRP Calendar (#107)", "XRP", 20/8, 3070),
        ("SOL VolShield (#102)", "SOL", 9/6, 3610),
    ]
    print(f"{'Strategy':<28}{'صفقات/سنة':>10}{'slippage RT':>15}{'تكلفة/سنة':>15}{'الأثر':>10}")
    print("-" * 90)
    for name, coin, trades_per_year, cagr_bps in strategies:
        result = slippage_per_strategy(int(trades_per_year), wallet_usd, coin)
        net_cagr = cagr_bps - result["annual_cost_pct"] * 100  # bps
        print(f"{name:<28}{trades_per_year:>8.1f}{result['slippage_bps_per_rt']:>12.1f}bp  ${result['annual_cost_usd']:>8.2f}  {result['annual_cost_pct']:>6.3f}%")


def analyze_order_splitting():
    """هل تقسيم الـ order يقلّل الـ slippage؟"""
    print(f"\n{'=' * 80}")
    print(f"  هل تقسيم الـ order يساعد؟ (سيناريو: $10,000 على ETH)")
    print(f"{'=' * 80}")
    total = 10000
    splits = [1, 2, 4, 8, 16]
    print(f"{'عدد الأجزاء':<14}{'حجم الجزء':>12}{'slippage لكل جزء':>20}{'إجمالي slippage':>20}{'الوفر':>10}")
    print("-" * 90)
    base = estimate_slippage("ETH", total)["expected_cost_usd"]
    for n in splits:
        per_chunk = total / n
        chunk_cost = estimate_slippage("ETH", per_chunk)["expected_cost_usd"]
        total_cost = chunk_cost * n
        save = base - total_cost
        save_pct = (save / base) * 100 if base > 0 else 0
        print(f"{n:>4} أجزاء   {per_chunk:>10,.0f}  {chunk_cost:>15.2f} cost  {total_cost:>15.2f}  {save_pct:>7.1f}% توفير")


def realistic_backtest_adjustment():
    """تطبيق slippage على نتائج الـbacktest."""
    print(f"\n{'=' * 80}")
    print(f"  تأثير الـ Slippage على Compound 9-Year (بداية $10K)")
    print(f"{'=' * 80}")
    # (strategy, coin, original_9y_compound, num_trades)
    strategies = [
        ("ETH AnalogV2 ⭐",    "ETH", 237431, 27),
        ("ETH Calendar (#105)", "ETH", 196126, 27),
        ("Macro V2 BTC (#108)", "BTC", 130326, 30),
        ("BNB Calendar (#106)", "BNB", 113611, 28),
        ("BTC Calendar (#100)", "BTC", 113132, 30),
    ]
    wallet = 10000
    print(f"{'Strategy':<25}{'الأصلي':>12}{'مع slippage 0.1%':>20}{'مع slippage 0.3%':>20}")
    print("-" * 90)
    for name, coin, original, n_trades in strategies:
        # Round trip slippage = 2 × per-trade
        # 9 years × CAGR computation with slippage drag
        # Approximate: each trade loses X% to slippage
        sl_01 = 0.001  # 0.1% per RT
        sl_03 = 0.003  # 0.3% per RT
        # Compound effect = original × (1 - slippage)^n_trades
        adj_01 = original * ((1 - sl_01) ** n_trades)
        adj_03 = original * ((1 - sl_03) ** n_trades)
        print(f"{name:<25}  ${original:>9,.0f}      ${adj_01:>9,.0f}  (-${original-adj_01:,.0f})    ${adj_03:>9,.0f}  (-${original-adj_03:,.0f})")


if __name__ == "__main__":
    print("=" * 80)
    print("  📊 Slippage Analysis — حقيقة التداول مقابل الـ Backtest")
    print("=" * 80)

    # 1. Per-coin slippage at different wallet sizes
    for w in [1000, 3000, 10000, 50000]:
        analyze_strategy_impact(w)

    # 2. Order splitting effectiveness
    analyze_order_splitting()

    # 3. Strategy comparisons with slippage
    compare_strategies(wallet_usd=3000)

    # 4. 9-year impact estimate
    realistic_backtest_adjustment()
