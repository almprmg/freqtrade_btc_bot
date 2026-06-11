"""ai_overlay.py — use the AI signal as an OVERLAY, not a standalone strategy.

Diagnosis showed standalone-AI mostly underperforms buy&hold in absolute terms
(it sits in cash). Better question: does the AI signal add value as a RISK
OVERLAY on a long position — stay invested but step aside when AI is bearish?

Uses the cached purged-walk-forward OOS signals (trading_results/wf_signal_*),
so this is fully out-of-sample and instant (no retraining). Same realistic
costs + vol-targeting + bootstrap as ai_walkforward_backtest.py.

Variants (all vol-targeted, fees+slippage):
  bh          full long
  regimeLong  long only when regime ok (no AI)            [V2-style base proxy]
  aiStandalone position = AI confidence, regime-gated     [current standalone]
  ovlGate     long, but FLAT when AI bearish (z<0)         [overlay: dodge]
  ovlMult     regimeLong * AI confidence                  [overlay: scale]

USAGE:  python GPU_HANDOFF/ai_overlay.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import dl_train_lstm as dl
from backtest_strategy import ai_target, metrics

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "research" / "dl_models" / "trading_results"
COINS = ["BTC", "ETH", "SOL", "BNB", "ADA", "XRP", "DOGE"]
FEE, SLIP = 0.00075, 0.0005
ZW, K_FIXED, ANN = 90, 1.5, 365
MACRO_EXIT_THR = -0.70
VOL_TARGET_D, VOL_WIN, VOL_CAP, POS_CAP = 0.025, 30, 1.0, 0.8


def vol_scale(ret):
    rvol = ret.rolling(VOL_WIN, min_periods=10).std().shift(1)
    return (VOL_TARGET_D / rvol).clip(0, VOL_CAP).fillna(0.0)


def build(coin):
    sig = OUT / f"wf_signal_{coin}.feather"
    if not sig.exists():
        return None
    s = pd.read_feather(sig)
    s["date"] = pd.to_datetime(s["date"], utc=True)
    df = dl.load_coin(coin); df = dl.build_features(df); df = dl.add_macro(df); df = dl.add_halving(df)
    df = df.merge(s, on="date", how="inner").sort_values("date").reset_index(drop=True)
    z = ((df["lstm_pred"] - df["lstm_pred"].rolling(ZW, min_periods=20).mean())
         / df["lstm_pred"].rolling(ZW, min_periods=20).std().replace(0, np.nan)).fillna(0.0)
    conf = 1.0 / (1.0 + np.exp(-K_FIXED * z))
    _, rconf, macro = ai_target(df, use_analog=False)
    ok = (rconf != -1.0) & (macro >= MACRO_EXIT_THR)
    ret = df["close"].pct_change().fillna(0.0)
    vs = vol_scale(ret)
    pos = {
        "bh": pd.Series(1.0, index=df.index),
        "regimeLong": ok.astype(float),
        "aiStandalone": conf.where(ok, 0.0),
        "ovlGate": ok.astype(float).where(z >= 0, 0.0),
        "ovlMult": ok.astype(float) * conf,
    }
    rets = {}
    for name, p in pos.items():
        p = (p * vs).clip(0, POS_CAP)
        turn = p.diff().abs().fillna(p.abs())
        rets[name] = p.shift(1).fillna(0) * ret - turn * (FEE + SLIP)
    return df["date"], rets


def boot(r, n=1000, block=20, seed=7):
    r = np.asarray(pd.Series(r).dropna())
    if len(r) < block * 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed); nb = int(np.ceil(len(r) / block)); sh = []
    for _ in range(n):
        idx = rng.integers(0, len(r) - block, size=nb)
        x = np.concatenate([r[i:i + block] for i in idx])[:len(r)]
        sh.append(x.mean() / x.std() * np.sqrt(ANN) if x.std() > 0 else 0.0)
    return (float(np.percentile(sh, 5)), float(np.percentile(sh, 95)))


VARIANTS = ["bh", "regimeLong", "aiStandalone", "ovlGate", "ovlMult"]


def main():
    port = {v: None for v in VARIANTS}
    counts = None
    print("=== AI as OVERLAY — purged WF, vol-targeted, real costs (Sharpe per coin) ===\n")
    hdr = f"{'coin':>4} | " + " ".join(f"{v:>12}" for v in VARIANTS)
    print(hdr); print("-" * len(hdr))
    for coin in COINS:
        b = build(coin)
        if b is None:
            continue
        dates, rets = b
        line = f"{coin:>4} | " + " ".join(f"{metrics(rets[v])['sharpe']:>12.2f}" for v in VARIANTS)
        print(line)
        idx = pd.to_datetime(np.asarray(dates))
        for v in VARIANTS:
            s = pd.Series(np.asarray(rets[v]), index=idx)
            port[v] = s if port[v] is None else port[v].add(s, fill_value=0)
        c = pd.Series(1, index=idx); counts = c if counts is None else counts.add(c, fill_value=0)

    print("\n=== PORTFOLIO (equal-weight) ===")
    print(f"{'variant':>12} | {'CAGR':>7} {'Sharpe':>7} {'maxDD':>7} {'Sharpe CI':>16}")
    print("-" * 56)
    summary = {}
    for v in VARIANTS:
        pf = (port[v] / counts).dropna()
        m = metrics(pf); ci = boot(pf)
        summary[v] = {"cagr": m["cagr"], "sharpe": m["sharpe"], "maxdd": m["maxdd"], "ci": ci}
        print(f"{v:>12} | {m['cagr']*100:>6.1f}% {m['sharpe']:>7.2f} {m['maxdd']*100:>6.1f}% "
              f"[{ci[0]:>5.2f},{ci[1]:>5.2f}]")

    best = max(summary, key=lambda v: summary[v]["sharpe"])
    base = summary["regimeLong"]["sharpe"]
    print(f"\nBest variant by portfolio Sharpe: {best} ({summary[best]['sharpe']:.2f})")
    ov = max(("ovlGate", "ovlMult"), key=lambda v: summary[v]["sharpe"])
    verdict = ("ADDS value" if summary[ov]["sharpe"] > base and summary[ov]["sharpe"] > summary["aiStandalone"]["sharpe"]
               else "does NOT clearly beat the no-AI base")
    print(f"AI overlay ({ov}) Sharpe {summary[ov]['sharpe']:.2f} vs regimeLong {base:.2f} "
          f"vs standalone {summary['aiStandalone']['sharpe']:.2f} -> overlay {verdict}.")
    (OUT / "overlay_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Saved -> {OUT / 'overlay_summary.json'}")


if __name__ == "__main__":
    main()
