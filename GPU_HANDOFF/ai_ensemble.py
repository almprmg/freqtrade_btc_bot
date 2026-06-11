"""ai_ensemble.py — merge the NO-AI strategy with the AI strategy (user's idea).

The overlay test put AI *inside* the strategy and found it redundant. This tests
a different thing: treat the no-AI regime strategy and the AI strategy as TWO
separate return streams and COMBINE them (50/50 capital, daily rebalanced). If
they make money at different times (low correlation), the blend's Sharpe beats
either alone — classic diversification. Uses cached purged-WF returns (honest).

USAGE:  python GPU_HANDOFF/ai_ensemble.py
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ai_overlay import boot, build, COINS, OUT
from backtest_strategy import metrics


def main():
    print("=== Ensemble: NO-AI regime strategy + AI strategy (2 streams, 50/50) ===\n")
    print(f"{'coin':>4} | {'corr(reg,ai)':>12} | {'regime Shrp':>11} {'ai Shrp':>8} {'COMBO Shrp':>10}")
    print("-" * 56)
    pr = {"regime": None, "ai": None, "combo": None}
    counts = None
    corrs = []
    for coin in COINS:
        b = build(coin)
        if b is None:
            continue
        dates, rets = b
        reg, ai = rets["regimeLong"], rets["aiStandalone"]
        combo = 0.5 * reg + 0.5 * ai
        # correlation of the two daily streams (where both active)
        aligned = pd.DataFrame({"r": reg.values, "a": ai.values}).dropna()
        cc = float(np.corrcoef(aligned["r"], aligned["a"])[0, 1]) if len(aligned) > 2 else float("nan")
        corrs.append(cc)
        print(f"{coin:>4} | {cc:>12.2f} | {metrics(reg)['sharpe']:>11.2f} {metrics(ai)['sharpe']:>8.2f} "
              f"{metrics(combo)['sharpe']:>10.2f}")
        idx = pd.to_datetime(np.asarray(dates))
        for key, series in [("regime", reg), ("ai", ai), ("combo", combo)]:
            s = pd.Series(np.asarray(series), index=idx)
            pr[key] = s if pr[key] is None else pr[key].add(s, fill_value=0)
        c = pd.Series(1, index=idx); counts = c if counts is None else counts.add(c, fill_value=0)

    print("\n=== PORTFOLIO ===")
    print(f"{'variant':>8} | {'CAGR':>7} {'Sharpe':>7} {'maxDD':>7} {'Sharpe CI':>16}")
    print("-" * 52)
    summ = {}
    for key in ("regime", "ai", "combo"):
        pf = (pr[key] / counts).dropna()
        m = metrics(pf); ci = boot(pf)
        summ[key] = {"cagr": m["cagr"], "sharpe": m["sharpe"], "maxdd": m["maxdd"], "ci": ci}
        print(f"{key:>8} | {m['cagr']*100:>6.1f}% {m['sharpe']:>7.2f} {m['maxdd']*100:>6.1f}% "
              f"[{ci[0]:>5.2f},{ci[1]:>5.2f}]")

    base = max(summ["regime"]["sharpe"], summ["ai"]["sharpe"])
    gain = summ["combo"]["sharpe"] - base
    print(f"\nMean stream correlation: {np.nanmean(corrs):.2f}")
    print(f"Combo Sharpe {summ['combo']['sharpe']:.2f} vs best-single {base:.2f}  -> "
          + ("DIVERSIFICATION HELPS (+{:.2f})".format(gain) if gain > 0.05
             else "no meaningful diversification benefit"))
    print(f"Combo maxDD {summ['combo']['maxdd']*100:.1f}% vs regime {summ['regime']['maxdd']*100:.1f}%")
    (OUT / "ensemble_summary.json").write_text(json.dumps(
        {"mean_corr": float(np.nanmean(corrs)), "portfolio": summ}, indent=2), encoding="utf-8")
    print(f"Saved -> {OUT / 'ensemble_summary.json'}")


if __name__ == "__main__":
    main()
