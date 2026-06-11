"""ai_stats.py — reusable performance statistics for daily return series.

Standard risk/return metrics so every report uses the same definitions:
CAGR, annualized vol, Sharpe, Sortino, Calmar, max drawdown, Ulcer index,
win rate, and a block-bootstrap CI for Sharpe (significance).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ANN = 365


def _clean(r):
    return pd.Series(np.asarray(r, dtype=float)).dropna()


def cagr(r):
    r = _clean(r)
    if len(r) < 2:
        return float("nan")
    eq = (1 + r).cumprod().iloc[-1]
    yrs = len(r) / ANN
    return eq ** (1 / yrs) - 1 if (yrs > 0 and eq > 0) else -1.0


def ann_vol(r):
    r = _clean(r)
    return r.std() * np.sqrt(ANN) if len(r) > 1 else float("nan")


def sharpe(r):
    r = _clean(r)
    return r.mean() / r.std() * np.sqrt(ANN) if (len(r) > 2 and r.std() > 0) else float("nan")


def sortino(r):
    r = _clean(r)
    downside = r[r < 0].std()
    return r.mean() / downside * np.sqrt(ANN) if (len(r) > 2 and downside > 0) else float("nan")


def max_drawdown(r):
    r = _clean(r)
    if len(r) < 2:
        return float("nan")
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def calmar(r):
    dd = max_drawdown(r)
    c = cagr(r)
    return c / abs(dd) if (dd and dd < 0 and c == c) else float("nan")


def ulcer_index(r):
    r = _clean(r)
    if len(r) < 2:
        return float("nan")
    eq = (1 + r).cumprod()
    dd = (eq / eq.cummax() - 1) * 100
    return float(np.sqrt((dd ** 2).mean()))


def win_rate(r):
    r = _clean(r)
    nz = r[r != 0]
    return float((nz > 0).mean()) if len(nz) else float("nan")


def bootstrap_sharpe_ci(r, n=1000, block=20, seed=7):
    r = _clean(r).to_numpy()
    if len(r) < block * 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(len(r) / block))
    out = []
    for _ in range(n):
        s = rng.integers(0, len(r) - block, size=nb)
        x = np.concatenate([r[i:i + block] for i in s])[:len(r)]
        out.append(x.mean() / x.std() * np.sqrt(ANN) if x.std() > 0 else 0.0)
    return (float(np.percentile(out, 5)), float(np.percentile(out, 95)))


def full_stats(r):
    return {
        "cagr": cagr(r), "ann_vol": ann_vol(r), "sharpe": sharpe(r), "sortino": sortino(r),
        "calmar": calmar(r), "max_dd": max_drawdown(r), "ulcer": ulcer_index(r),
        "win_rate": win_rate(r), "sharpe_ci": bootstrap_sharpe_ci(r),
    }


if __name__ == "__main__":
    import numpy as np
    rng = np.random.default_rng(0)
    demo = rng.normal(0.001, 0.03, 1000)
    for k, v in full_stats(demo).items():
        print(f"{k:>12}: {v}")
