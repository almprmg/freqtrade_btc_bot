"""ai_riskctl.py — drive the drawdown DOWN (user: maxDD too high).

Adds, on top of the purged-WF AI signal, risk controls the fleet's VolShield
does NOT have: a drawdown CIRCUIT-BREAKER (go flat after equity falls DD_LIMIT
from its peak; resume when it recovers to within RESUME of peak) + tighter
vol-targeting. Uses cached WF OOS signals (honest, instant).

Compares 3 configs and reports full risk stats (Sharpe/Sortino/Calmar/maxDD/Ulcer).

USAGE:  python GPU_HANDOFF/ai_riskctl.py
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

import dl_train_lstm as dl
from ai_stats import bootstrap_sharpe_ci, full_stats
from backtest_strategy import ai_target
from ai_overlay import OUT

COINS = ["BTC", "ETH", "SOL", "BNB", "ADA", "XRP", "DOGE"]
FEE, SLIP, ZW, K = 0.00075, 0.0005, 90, 1.5
MACRO_EXIT_THR = -0.70
CONFIGS = {
    "A_current":  {"vt": 0.025, "cap": 0.8, "dd": None},
    "B_tighter":  {"vt": 0.020, "cap": 0.6, "dd": None},
    "C_breaker":  {"vt": 0.020, "cap": 0.6, "dd": 0.15, "resume": 0.05},
}


def base_position(coin):
    sig = OUT / f"wf_signal_{coin}.feather"
    if not sig.exists():
        return None
    s = pd.read_feather(sig); s["date"] = pd.to_datetime(s["date"], utc=True)
    df = dl.load_coin(coin); df = dl.build_features(df); df = dl.add_macro(df); df = dl.add_halving(df)
    df = df.merge(s, on="date", how="inner").sort_values("date").reset_index(drop=True)
    z = ((df["lstm_pred"] - df["lstm_pred"].rolling(ZW, min_periods=20).mean())
         / df["lstm_pred"].rolling(ZW, min_periods=20).std().replace(0, np.nan)).fillna(0.0)
    conf = 1.0 / (1.0 + np.exp(-K * z))
    _, rconf, macro = ai_target(df, use_analog=False)
    conf = conf.where((rconf != -1.0) & (macro >= MACRO_EXIT_THR), 0.0)
    return df["date"].values, df["close"].pct_change().fillna(0.0).values, conf.values


def simulate(ret, conf, vt, cap, dd_limit=None, resume=0.05):
    n = len(ret)
    rvol = pd.Series(ret).rolling(30, min_periods=10).std().shift(1).values
    vscal = np.clip(np.where(rvol > 0, vt / rvol, 0.0), 0, 1.0)
    base_pos = np.clip(conf * vscal, 0, cap)
    eq, peak, halt, prev = 1.0, 1.0, False, 0.0
    out = np.zeros(n)
    for t in range(n):
        ddown = eq / peak - 1
        if dd_limit is not None:
            if halt and ddown >= -resume:
                halt = False
            elif (not halt) and ddown <= -dd_limit:
                halt = True
        target = 0.0 if halt else base_pos[t]
        r_t = prev * ret[t] - abs(target - prev) * (FEE + SLIP)
        eq *= (1 + r_t); peak = max(peak, eq)
        out[t] = r_t; prev = target
    return pd.Series(out)


def main():
    print("=== Drawdown control — purged-WF AI signal, 3 configs ===\n")
    port = {k: None for k in CONFIGS}
    counts = None
    for coin in COINS:
        b = base_position(coin)
        if b is None:
            continue
        dates, ret, conf = b
        idx = pd.to_datetime(dates)
        for name, c in CONFIGS.items():
            r = simulate(ret, conf, c["vt"], c["cap"], c.get("dd"), c.get("resume", 0.05))
            s = pd.Series(r.values, index=idx)
            port[name] = s if port[name] is None else port[name].add(s, fill_value=0)
        cc = pd.Series(1, index=idx); counts = cc if counts is None else counts.add(cc, fill_value=0)

    print(f"{'config':>10} | {'CAGR':>7} {'Sharpe':>7} {'Sortino':>7} {'Calmar':>7} {'maxDD':>7} {'Ulcer':>6} {'CI':>14}")
    print("-" * 78)
    summ = {}
    for name in CONFIGS:
        pf = (port[name] / counts).dropna()
        st = full_stats(pf)
        summ[name] = st
        print(f"{name:>10} | {st['cagr']*100:>6.1f}% {st['sharpe']:>7.2f} {st['sortino']:>7.2f} "
              f"{st['calmar']:>7.2f} {st['max_dd']*100:>6.1f}% {st['ulcer']:>6.1f} "
              f"[{st['sharpe_ci'][0]:.2f},{st['sharpe_ci'][1]:.2f}]")
    a, c = summ["A_current"], summ["C_breaker"]
    print(f"\nDrawdown: {a['max_dd']*100:.1f}% -> {c['max_dd']*100:.1f}%  "
          f"({(c['max_dd']-a['max_dd'])*100:+.1f}pp)")
    print(f"Calmar (CAGR/|DD|): {a['calmar']:.2f} -> {c['calmar']:.2f}  "
          + ("(better risk-adjusted)" if c['calmar'] > a['calmar'] else "(worse)"))
    (OUT / "riskctl_summary.json").write_text(
        json.dumps({k: {kk: vv for kk, vv in v.items() if kk != 'sharpe_ci'} | {"sharpe_ci": v["sharpe_ci"]}
                    for k, v in summ.items()}, indent=2), encoding="utf-8")
    print(f"Saved -> {OUT / 'riskctl_summary.json'}")


if __name__ == "__main__":
    main()
