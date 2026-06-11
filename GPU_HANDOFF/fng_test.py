"""fng_test.py — does an ORTHOGONAL feature (Fear & Greed) add predictive power?

The investigation concluded the LSTM is redundant with its price-macro features.
This tests the recommended fix: add a genuinely orthogonal input (crypto Fear &
Greed sentiment) and measure whether walk-forward correlation improves vs the
12-feature baseline. Transformer arch, corr loss, purged folds.

USAGE:  python GPU_HANDOFF/fng_test.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import dl_train_lstm as dl

dl.MODEL_CFG = {"arch": "transformer", "hidden": 64, "layers": 2, "dropout": 0.3}
COINS = ["BTC", "ETH", "SOL", "BNB"]
FOLDS = 5
FNG = dl.REPO / "user_data" / "data" / "fng.feather"


def add_fng(df):
    df = df.copy()
    if not FNG.exists():
        df["fng"] = 50.0
        return df
    f = pd.read_feather(FNG)
    f["date"] = pd.to_datetime(f["date"], utc=True)
    f = f.set_index("date")["fng"]
    d = df["date"].dt.normalize()
    df["fng"] = d.map(f).ffill().fillna(50.0).values
    return df


def wf_corr(df, feat_cols, epochs=80, batch=256):
    valid = df.dropna(subset=feat_cols + ["fwd_30d_ret"]).reset_index(drop=True)
    n = len(valid)
    bounds = [int(n * i / (FOLDS + 1)) for i in range(FOLDS + 2)]
    res = []
    for k in range(1, FOLDS + 1):
        te, ve = bounds[k], bounds[k + 1]
        if te <= dl.SEQ_LEN + 50 or ve - te < 20:
            continue
        mean = valid[feat_cols].iloc[:te].mean()
        std = valid[feat_cols].iloc[:te].std().replace(0, 1)
        vn = valid.copy()
        vn[feat_cols] = (vn[feat_cols] - mean) / std
        feat = vn[feat_cols].values.astype(np.float32)
        targets = vn["fwd_30d_ret"].values.astype(np.float32)
        tr_idx = np.arange(dl.SEQ_LEN, te, dtype=np.int64)
        va_idx = np.arange(te, ve, dtype=np.int64)
        _, corr, _ = dl._fit_eval(feat, targets, tr_idx, va_idx, dl.SEQ_LEN, epochs, batch, loss="corr")
        res.append(corr)
    arr = np.array(res)
    return arr.mean(), arr.std()


def main():
    print("=== Fear&Greed ablation — walk-forward corr (12 feat vs +FNG) ===\n")
    print(f"{'coin':>4} | {'base 12':>14} | {'+FNG (13)':>14} | delta")
    print("-" * 52)
    deltas = []
    for coin in COINS:
        df = dl.load_coin(coin); df = dl.build_features(df); df = dl.add_macro(df); df = dl.add_halving(df)
        df = add_fng(df)
        bm, bs = wf_corr(df, dl.FEATURE_COLS)
        fm, fs = wf_corr(df, dl.FEATURE_COLS + ["fng"])
        deltas.append(fm - bm)
        print(f"{coin:>4} | {bm:+.3f} +/-{bs:.2f} | {fm:+.3f} +/-{fs:.2f} | {fm-bm:+.3f}", flush=True)
    md = float(np.mean(deltas))
    print(f"\nMean delta (+FNG - base): {md:+.4f}")
    print("VERDICT: " + ("FNG adds predictive power -> orthogonal data helps."
                         if md > 0.02 else "FNG does NOT meaningfully help (delta ~0)."))


if __name__ == "__main__":
    main()
