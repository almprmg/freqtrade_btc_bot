"""dl_vol_predict.py — DL for VOLATILITY (not price direction).

Direction is ~efficient; volatility clusters and IS predictable. A better vol
forecast directly improves the vol-targeting that already cut drawdowns ~half.

Trains a small LSTM (purged walk-forward) to predict forward realized vol, and
compares OOS against the naive baselines vol-targeting normally uses:
  naive  = last realized 20d vol
  ewma   = RiskMetrics EWMA (lambda 0.94)
Metric: correlation + MAE of forecast vs realized forward vol (OOS).

If ML clearly beats the baselines, it's worth wiring into the strategy.

USAGE:  python GPU_HANDOFF/dl_vol_predict.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "user_data" / "data" / "binance"
OUT = REPO / "research" / "dl_models" / "trading_results"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
COINS = ["BTC", "ETH", "SOL", "BNB", "ADA", "XRP", "DOGE"]
SEQ, H, FOLDS = 30, 20, 6        # 30-bar lookback, predict 20-day forward vol
FEATS = ["ret", "absret", "rv5", "rv10", "rv20", "rv60", "atr_pct", "rng"]


def build(coin):
    fp = DATA / f"{coin}_USDT-1d.feather"
    if not fp.exists():
        return None
    df = pd.read_feather(fp)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.sort_values("date").reset_index(drop=True)
    r = df["close"].pct_change()
    df["ret"] = r
    df["absret"] = r.abs()
    for w in (5, 10, 20, 60):
        df[f"rv{w}"] = r.rolling(w).std()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - df["close"].shift()).abs(),
                    (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1)
    df["atr_pct"] = tr.rolling(14).mean() / df["close"]
    df["rng"] = (df["high"] - df["low"]) / df["close"]
    df["fwd_vol"] = r.rolling(H).std().shift(-H)      # target: realized fwd vol
    df["ewma_vol"] = r.ewm(alpha=1 - 0.94).std()
    return df.dropna(subset=FEATS + ["fwd_vol", "rv20", "ewma_vol"]).reset_index(drop=True)


class DS(Dataset):
    def __init__(self, feat, y, idx):
        self.f = torch.from_numpy(feat); self.y = torch.from_numpy(y); self.idx = idx

    def __len__(self):
        return len(self.idx)

    def __getitem__(self, k):
        i = int(self.idx[k]); return self.f[i - SEQ:i], self.y[i]


class VolLSTM(nn.Module):
    def __init__(self, d, hidden=32):
        super().__init__()
        self.lstm = nn.LSTM(d, hidden, batch_first=True)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x):
        _, (h, _) = self.lstm(x)
        return torch.nn.functional.softplus(self.head(h[-1])).squeeze(-1)   # vol > 0


def train_predict(feat, y, tr_idx, te_idx, epochs=60, batch=256, patience=8):
    vs = int(len(tr_idx) * 0.85)
    itr, iva = tr_idx[:vs], tr_idx[vs:]
    m = VolLSTM(feat.shape[1]).to(DEVICE)
    opt = torch.optim.AdamW(m.parameters(), lr=1e-3, weight_decay=1e-4)
    lossf = nn.L1Loss()
    trl = DataLoader(DS(feat, y, itr), batch_size=batch, shuffle=True)
    val = DataLoader(DS(feat, y, iva), batch_size=batch, shuffle=False)
    best, bs, ni = 1e9, None, 0
    for _ in range(epochs):
        m.train()
        for xb, yb in trl:
            xb, yb = xb.to(DEVICE), yb.to(DEVICE)
            loss = lossf(m(xb), yb); opt.zero_grad(); loss.backward(); opt.step()
        m.eval(); vl, nb = 0.0, 0
        with torch.no_grad():
            for xb, yb in val:
                xb, yb = xb.to(DEVICE), yb.to(DEVICE)
                vl += lossf(m(xb), yb).item(); nb += 1
        vl /= max(nb, 1)
        if vl < best: best, ni, bs = vl, 0, {k: v.cpu().clone() for k, v in m.state_dict().items()}
        else:
            ni += 1
            if ni >= patience: break
    m.load_state_dict(bs); m.eval()
    tel = DataLoader(DS(feat, y, te_idx), batch_size=512, shuffle=False)
    out = []
    with torch.no_grad():
        for xb, _ in tel:
            out.append(m(xb.to(DEVICE)).cpu().numpy())
    return np.concatenate(out) if out else np.array([])


def wf(coin):
    df = build(coin)
    if df is None:
        return None
    n = len(df); bounds = [int(n * i / (FOLDS + 1)) for i in range(FOLDS + 2)]
    preds, ys, naive, ewma = [], [], [], []
    for k in range(1, FOLDS + 1):
        te, ve = bounds[k], bounds[k + 1]
        if te <= SEQ + 60 or ve - te < 20:
            continue
        mean = df[FEATS].iloc[:te].mean(); std = df[FEATS].iloc[:te].std().replace(0, 1)
        f = ((df[FEATS] - mean) / std).values.astype(np.float32)
        y = df["fwd_vol"].values.astype(np.float32)
        tr_idx = np.arange(SEQ, te, dtype=np.int64); te_idx = np.arange(te, ve, dtype=np.int64)
        p = train_predict(f, y, tr_idx, te_idx)
        preds.append(p); ys.append(y[te_idx])
        naive.append(df["rv20"].values[te_idx]); ewma.append(df["ewma_vol"].values[te_idx])
    if not preds:
        return None
    P, Y, N, E = map(np.concatenate, (preds, ys, naive, ewma))
    def corr(a): return float(np.corrcoef(a, Y)[0, 1])
    def mae(a): return float(np.mean(np.abs(a - Y)))
    return {"coin": coin, "n": len(Y),
            "ml": {"corr": corr(P), "mae": mae(P)},
            "naive": {"corr": corr(N), "mae": mae(N)},
            "ewma": {"corr": corr(E), "mae": mae(E)}}


def main():
    print("=== DL volatility prediction (purged WF) vs naive / EWMA ===\n")
    hdr = f"{'coin':>4} | {'ML corr':>8} {'naive':>8} {'ewma':>8} | {'ML MAE':>9} {'naive':>9} {'ewma':>9}"
    print(hdr); print("-" * len(hdr))
    rows = []
    for coin in COINS:
        r = wf(coin)
        if not r:
            continue
        rows.append(r)
        print(f"{coin:>4} | {r['ml']['corr']:>8.3f} {r['naive']['corr']:>8.3f} {r['ewma']['corr']:>8.3f} | "
              f"{r['ml']['mae']*100:>8.3f}% {r['naive']['mae']*100:>8.3f}% {r['ewma']['mae']*100:>8.3f}%", flush=True)
    ml_corr = np.mean([r["ml"]["corr"] for r in rows])
    nv_corr = np.mean([r["naive"]["corr"] for r in rows])
    ew_corr = np.mean([r["ewma"]["corr"] for r in rows])
    ml_mae = np.mean([r["ml"]["mae"] for r in rows])
    nv_mae = np.mean([r["naive"]["mae"] for r in rows])
    beats_corr = sum(1 for r in rows if r["ml"]["corr"] > max(r["naive"]["corr"], r["ewma"]["corr"]))
    beats_mae = sum(1 for r in rows if r["ml"]["mae"] < min(r["naive"]["mae"], r["ewma"]["mae"]))
    print(f"\nMean corr: ML {ml_corr:.3f} | naive {nv_corr:.3f} | ewma {ew_corr:.3f}")
    print(f"Mean MAE:  ML {ml_mae*100:.3f}% | naive {nv_mae*100:.3f}%")
    print(f"ML beats both baselines on corr {beats_corr}/{len(rows)}, on MAE {beats_mae}/{len(rows)}.")
    verdict = "ML adds value" if (ml_corr > nv_corr and beats_corr >= len(rows) // 2) else \
              "ML does NOT beat naive vol (rolling-std already near-optimal)"
    print(f"VERDICT: {verdict}.")
    (OUT / "vol_predict.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
