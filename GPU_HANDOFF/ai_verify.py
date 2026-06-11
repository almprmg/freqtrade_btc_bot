"""ai_verify.py — is the AI-improved result overfit? Rigorous, realistic test.

The improvement (ai_improve.py) tuned k on the SAME OOS window it reported, with
no slippage. This script removes those optimism sources:

  1. NESTED split — model is OOS on the last 20% already; within it, tune k on
     the VALIDATION half, report ONLY on the held-out TEST half (no k leakage).
  2. REALISTIC costs — taker fee 0.075% + slippage 0.05% per side, next-bar
     execution (decide on close t, trade t+1), optional position cap.
  3. k-SENSITIVITY — is the edge robust across all k, or a magic-number artifact?
  4. BLOCK-BOOTSTRAP — 1000 resamples of test daily returns (20-day blocks) ->
     5-95% CI on annualized Sharpe. Edge is real only if the CI clears ~0.

USAGE:  python GPU_HANDOFF/ai_verify.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_strategy import ai_target, load_coin_signal, metrics

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "research" / "dl_models" / "trading_results"
COINS = ["BTC", "ETH", "SOL", "BNB", "ADA", "XRP", "DOGE"]
FEE, SLIP = 0.00075, 0.0005          # taker + slippage per side
ZW = 90
KS = [1.0, 1.5, 2.0, 3.0]
POS_CAP = 1.0
MACRO_EXIT_THR = -0.70
OOS_FRAC = 0.20
ANN = 365
SEED = 7


def causal_z(pred):
    rm = pred.rolling(ZW, min_periods=20).mean()
    rs = pred.rolling(ZW, min_periods=20).std().replace(0, np.nan)
    return ((pred - rm) / rs).fillna(0.0)


def returns(df, k, cap=POS_CAP):
    """AI-primary + safety gate, realistic costs, next-bar execution."""
    z = causal_z(df["lstm_pred"])
    pos = (1.0 / (1.0 + np.exp(-k * z))).clip(0, cap)
    _, rconf, macro = ai_target(df, use_analog=False)
    pos = pos.where((rconf != -1.0) & (macro >= MACRO_EXIT_THR), 0.0)
    ret = df["close"].pct_change().fillna(0.0)
    turn = pos.diff().abs().fillna(pos.abs())
    return pos.shift(1).fillna(0) * ret - turn * (FEE + SLIP)


def sharpe(r):
    r = pd.Series(r).dropna()
    return r.mean() / r.std() * np.sqrt(ANN) if len(r) > 2 and r.std() > 0 else float("nan")


def block_bootstrap_sharpe(r, n=1000, block=20, seed=SEED):
    r = np.asarray(pd.Series(r).dropna())
    if len(r) < block * 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    nblocks = int(np.ceil(len(r) / block))
    sh = []
    for _ in range(n):
        starts = rng.integers(0, len(r) - block, size=nblocks)
        sample = np.concatenate([r[s:s + block] for s in starts])[:len(r)]
        sd = sample.std()
        sh.append(sample.mean() / sd * np.sqrt(ANN) if sd > 0 else 0.0)
    return (float(np.percentile(sh, 5)), float(np.percentile(sh, 95)))


def main():
    print("=== Overfit verification — nested split, realistic costs, bootstrap ===")
    print(f"costs: fee {FEE:.3%} + slippage {SLIP:.3%}/side | next-bar exec | cap {POS_CAP}\n")
    hdr = (f"{'coin':>4} | {'k*':>4} {'test CAGR':>9} {'test Shrp':>9} {'Sharpe 5-95% CI':>18} | "
           f"{'k-range test Shrp':>18} | verdict")
    print(hdr); print("-" * len(hdr))
    results, port_test = [], None
    for coin in COINS:
        df = load_coin_signal(coin)
        if df is None:
            continue
        n = len(df)
        oos0 = int(n * (1 - OOS_FRAC))
        val0, val1 = oos0, oos0 + int((n - oos0) * 0.6)   # validation half
        test0 = val1                                        # held-out test
        # tune k on validation ONLY
        best_k, best_s = KS[0], -1e9
        for k in KS:
            s = sharpe(returns(df, k).iloc[val0:val1])
            s = -1e9 if s != s else s
            if s > best_s:
                best_k, best_s = k, s
        # report on held-out test
        r_test = returns(df, best_k).iloc[test0:]
        m = metrics(r_test)
        ci = block_bootstrap_sharpe(r_test)
        # k-sensitivity on test (all k)
        ks_sh = [sharpe(returns(df, k).iloc[test0:]) for k in KS]
        ks_sh = [x for x in ks_sh if x == x]
        krange = f"{min(ks_sh):+.2f}..{max(ks_sh):+.2f}" if ks_sh else "n/a"
        robust = ci[0] > 0 and (min(ks_sh) > 0 if ks_sh else False)
        verdict = "ROBUST" if robust else ("weak" if ci[1] > 0 else "OVERFIT/none")
        results.append({"coin": coin, "k": best_k, "test_cagr": m["cagr"], "test_sharpe": m["sharpe"],
                        "ci_low": ci[0], "ci_high": ci[1], "k_min": min(ks_sh) if ks_sh else None,
                        "k_max": max(ks_sh) if ks_sh else None, "test_days": len(r_test), "verdict": verdict})
        s = pd.Series(np.asarray(r_test), index=pd.to_datetime(np.asarray(df["date"].iloc[test0:])))
        port_test = s if port_test is None else port_test.add(s, fill_value=0)
        print(f"{coin:>4} | {best_k:>4} {m['cagr']*100:>8.1f}% {m['sharpe']:>9.2f} "
              f"[{ci[0]:>6.2f},{ci[1]:>6.2f}]    | {krange:>18} | {verdict}")

    counts = None
    for coin in COINS:
        df = load_coin_signal(coin)
        if df is None:
            continue
        n = len(df); test0 = int(n * (1 - OOS_FRAC)) + int((n - int(n * (1 - OOS_FRAC))) * 0.6)
        idx = pd.to_datetime(np.asarray(df["date"].iloc[test0:]))
        c = pd.Series(1, index=idx)
        counts = c if counts is None else counts.add(c, fill_value=0)
    pf = (port_test / counts).dropna()
    pci = block_bootstrap_sharpe(pf)
    pm = metrics(pf)
    print(f"\nPORTFOLIO (held-out test): CAGR {pm['cagr']*100:.1f}%  Sharpe {pm['sharpe']:.2f}  "
          f"CI[{pci[0]:.2f},{pci[1]:.2f}]  maxDD {pm['maxdd']*100:.1f}%  days {len(pf)}")

    robust_n = sum(1 for r in results if r["verdict"] == "ROBUST")
    print(f"\nVERDICT: ROBUST on {robust_n}/{len(results)} coins (CI>0 AND positive across ALL k).")
    print("Portfolio test edge is " + ("REAL (CI clears 0)." if pci[0] > 0 else "NOT significant (CI includes 0)."))
    (OUT / "verify_summary.json").write_text(json.dumps(
        {"coins": results, "portfolio": {"cagr": pm["cagr"], "sharpe": pm["sharpe"],
         "ci": pci, "maxdd": pm["maxdd"], "days": len(pf)}}, indent=2), encoding="utf-8")
    print(f"Saved -> {OUT / 'verify_summary.json'}")


if __name__ == "__main__":
    main()
