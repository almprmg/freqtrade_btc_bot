"""intraday_funding_test.py — can an intraday-native feature rescue 1h signal?

On 1h/4h the daily-macro LSTM was ~noise (corr ~+0.05). Hypothesis: it lacks
intraday information. Test by adding perp FUNDING RATE (8h, reflects basis +
leverage pressure) and comparing walk-forward corr WITH vs WITHOUT funding.

Reuses dl_train_lstm's pipeline + _fit_eval. Standalone so it doesn't disturb
the module's global FEATURE_COLS.

USAGE:  python GPU_HANDOFF/intraday_funding_test.py --timeframe 1h
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import dl_train_lstm as dl

EXTRA = "funding_rate"


def add_funding(df: pd.DataFrame, coin: str) -> pd.DataFrame:
    fp = dl.REPO / "user_data" / "data" / f"funding_{coin}.feather"
    df = df.copy()
    if not fp.exists():
        df[EXTRA] = 0.0
        return df
    f = pd.read_feather(fp)
    f["date"] = pd.to_datetime(f["date"], utc=True)
    f = f.set_index("date")["funding_rate"].sort_index()
    # align each bar to the last known funding rate (causal ffill)
    df[EXTRA] = df["date"].map(f.reindex(f.index.union(df["date"])).ffill()).fillna(0.0).values
    return df


def wf(df: pd.DataFrame, feat_cols, folds, epochs, batch, lr=1e-3):
    valid = df.dropna(subset=feat_cols + ["fwd_30d_ret"]).reset_index(drop=True)
    n = len(valid)
    bounds = [int(n * i / (folds + 1)) for i in range(folds + 2)]
    res = []
    for k in range(1, folds + 1):
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
        _, corr, _ = dl._fit_eval(feat, targets, tr_idx, va_idx, dl.SEQ_LEN,
                                  epochs, batch, lr, loss="corr")
        res.append(corr)
    arr = np.array(res)
    return arr.mean(), arr.std(), len(arr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--coins", nargs="+", default=["BTC", "ETH"])
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=1024)
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()

    dl.TIMEFRAME = args.timeframe
    print(f"=== Funding rescue test @ {args.timeframe} (WF corr, with vs without funding) ===")
    for coin in args.coins:
        df = dl.load_coin(coin)
        df = dl.build_features(df)
        df = dl.add_macro(df)
        df = dl.add_halving(df)
        df = add_funding(df, coin)
        base = wf(df, dl.FEATURE_COLS, args.folds, args.epochs, args.batch)
        plus = wf(df, dl.FEATURE_COLS + [EXTRA], args.folds, args.epochs, args.batch)
        print(f"  {coin}: base {base[0]:+.4f}±{base[1]:.3f}  |  +funding {plus[0]:+.4f}±{plus[1]:.3f}  "
              f"(delta {plus[0]-base[0]:+.4f})")


if __name__ == "__main__":
    main()
