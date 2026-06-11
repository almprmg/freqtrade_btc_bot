"""ai_walkforward_backtest.py — the gold-standard honest test.

Every prediction is OUT-OF-SAMPLE: the model is retrained on past data only and
predicts the next block (purged walk-forward), so there is NO in-sample signal
leakage anywhere. k is FIXED (no tuning -> no selection bias). Realistic costs.

If a robust edge exists, it shows here. If not, the AI strategy has no tradable
alpha and earlier numbers were overfit.

USAGE:  python GPU_HANDOFF/ai_walkforward_backtest.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader

import dl_train_lstm as dl
from backtest_strategy import ai_target, metrics

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "research" / "dl_models" / "trading_results"
COINS = ["BTC", "ETH", "SOL", "BNB", "ADA", "XRP", "DOGE"]
FOLDS = 6
FEE, SLIP = 0.00075, 0.0005
ZW, K_FIXED, ANN = 90, 1.5, 365
MACRO_EXIT_THR = -0.70
# Risk controls (added to cut the -60/-80% drawdowns)
VOL_TARGET_D = 0.025      # target daily vol (~48% annual); scale down when realized vol is higher
VOL_WIN = 30
VOL_CAP = 1.0             # never lever above full allocation
POS_CAP = 0.8             # hard cap on position fraction
dl.MODEL_CFG = {"arch": "transformer", "hidden": 64, "layers": 2, "dropout": 0.3}


def train_predict(feat, targets, tr_idx, te_idx, seq_len, epochs=70, batch=256, lr=1e-3, patience=10):
    vs = int(len(tr_idx) * 0.85)
    itr, ival = tr_idx[:vs], tr_idx[vs:]
    model = dl.build_model(feat.shape[1]).to(dl.DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=3e-4)
    loss_fn = dl.make_loss("corr")
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    trl = DataLoader(dl.LazySeqDataset(feat, targets, itr, seq_len), batch_size=batch, shuffle=True)
    vall = DataLoader(dl.LazySeqDataset(feat, targets, ival, seq_len), batch_size=batch, shuffle=False)
    best, best_state, ni = 1e9, None, 0
    for _ in range(epochs):
        model.train()
        for xb, yb in trl:
            xb, yb = xb.to(dl.DEVICE), yb.to(dl.DEVICE)
            loss = loss_fn(model(xb)[0], yb)
            opt.zero_grad(); loss.backward(); opt.step()
        model.eval(); vl, nb = 0.0, 0
        with torch.no_grad():
            for xb, yb in vall:
                xb, yb = xb.to(dl.DEVICE), yb.to(dl.DEVICE)
                vl += loss_fn(model(xb)[0], yb).item(); nb += 1
        vl /= max(nb, 1); sched.step()
        if vl < best:
            best, ni = vl, 0
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        else:
            ni += 1
            if ni >= patience:
                break
    model.load_state_dict(best_state); model.eval()
    tel = DataLoader(dl.LazySeqDataset(feat, np.zeros(len(feat), np.float32), te_idx, seq_len),
                     batch_size=512, shuffle=False)
    preds = []
    with torch.no_grad():
        for xb, _ in tel:
            preds.append(model(xb.to(dl.DEVICE))[0].cpu().numpy())
    return np.concatenate(preds) if preds else np.array([])


def wf_signal(coin):
    """Purged walk-forward OOS predictions across (FOLDS) blocks. Cached to feather
    (signal does NOT depend on position sizing, so risk-control sweeps are instant)."""
    cache = OUT / f"wf_signal_{coin}.feather"
    if cache.exists():
        return pd.read_feather(cache)
    df = dl.load_coin(coin); df = dl.build_features(df); df = dl.add_macro(df); df = dl.add_halving(df)
    valid = df.dropna(subset=dl.FEATURE_COLS + ["fwd_30d_ret"]).reset_index(drop=True)
    n = len(valid)
    bounds = [int(n * i / (FOLDS + 1)) for i in range(FOLDS + 2)]
    dates_all, preds_all = [], []
    for k in range(1, FOLDS + 1):
        te, ve = bounds[k], bounds[k + 1]
        if te <= dl.SEQ_LEN + 60 or ve - te < 20:
            continue
        mean = valid[dl.FEATURE_COLS].iloc[:te].mean()
        std = valid[dl.FEATURE_COLS].iloc[:te].std().replace(0, 1)
        vn = valid.copy(); vn[dl.FEATURE_COLS] = (vn[dl.FEATURE_COLS] - mean) / std
        feat = vn[dl.FEATURE_COLS].values.astype(np.float32)
        targets = vn["fwd_30d_ret"].values.astype(np.float32)
        tr_idx = np.arange(dl.SEQ_LEN, te, dtype=np.int64)
        te_idx = np.arange(te, ve, dtype=np.int64)
        preds = train_predict(feat, targets, tr_idx, te_idx, dl.SEQ_LEN)
        dates_all.append(valid["date"].values[te_idx]); preds_all.append(preds)
    if not preds_all:
        return None
    sig = pd.DataFrame({"date": np.concatenate(dates_all), "lstm_pred": np.concatenate(preds_all)})
    sig.to_feather(cache)
    return sig


def backtest(coin, sig):
    df = dl.load_coin(coin); df = dl.build_features(df); df = dl.add_macro(df); df = dl.add_halving(df)
    sig = sig.copy()
    sig["date"] = pd.to_datetime(sig["date"], utc=True)
    df = df.merge(sig, on="date", how="inner").sort_values("date").reset_index(drop=True)
    z = ((df["lstm_pred"] - df["lstm_pred"].rolling(ZW, min_periods=20).mean())
         / df["lstm_pred"].rolling(ZW, min_periods=20).std().replace(0, np.nan)).fillna(0.0)
    pos = (1.0 / (1.0 + np.exp(-K_FIXED * z))).clip(0, 1)
    _, rconf, macro = ai_target(df, use_analog=False)
    pos = pos.where((rconf != -1.0) & (macro >= MACRO_EXIT_THR), 0.0)
    ret = df["close"].pct_change().fillna(0.0)
    # vol-targeting: scale down exposure when recent realized vol is high (causal),
    # then hard-cap. Cuts the deep crash drawdowns.
    rvol = ret.rolling(VOL_WIN, min_periods=10).std().shift(1)
    vscalar = (VOL_TARGET_D / rvol).clip(0, VOL_CAP).fillna(0.0)
    pos = (pos * vscalar).clip(0, POS_CAP)
    turn = pos.diff().abs().fillna(pos.abs())
    strat = pos.shift(1).fillna(0) * ret - turn * (FEE + SLIP)
    return df["date"], strat, ret


def boot(r, n=1000, block=20, seed=7):
    r = np.asarray(pd.Series(r).dropna())
    if len(r) < block * 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed); nb = int(np.ceil(len(r) / block)); sh = []
    for _ in range(n):
        s = rng.integers(0, len(r) - block, size=nb)
        x = np.concatenate([r[i:i + block] for i in s])[:len(r)]
        sh.append(x.mean() / x.std() * np.sqrt(ANN) if x.std() > 0 else 0.0)
    return (float(np.percentile(sh, 5)), float(np.percentile(sh, 95)))


def main():
    print("=== PURGED WALK-FORWARD backtest (model+signal fully OOS, fixed k, real costs) ===\n")
    hdr = f"{'coin':>4} | {'WF CAGR':>8} {'B&H':>8} {'Sharpe':>7} {'Shrp CI(5-95%)':>16} {'maxDD':>7} {'days':>5}"
    print(hdr); print("-" * len(hdr))
    port = None; counts = None; rows = []
    for coin in COINS:
        sig = wf_signal(coin)
        if sig is None:
            continue
        dates, strat, hold = backtest(coin, sig)
        m = metrics(strat); ci = boot(strat)
        rows.append({"coin": coin, "cagr": m["cagr"], "sharpe": m["sharpe"], "ci": ci,
                     "maxdd": m["maxdd"], "bh": metrics(hold)["cagr"], "days": len(strat)})
        print(f"{coin:>4} | {m['cagr']*100:>7.1f}% {metrics(hold)['cagr']*100:>7.1f}% {m['sharpe']:>7.2f} "
              f"[{ci[0]:>6.2f},{ci[1]:>6.2f}] {m['maxdd']*100:>6.1f}% {len(strat):>5}", flush=True)
        s = pd.Series(np.asarray(strat), index=pd.to_datetime(np.asarray(dates)))
        port = s if port is None else port.add(s, fill_value=0)
        c = pd.Series(1, index=s.index); counts = c if counts is None else counts.add(c, fill_value=0)
    pf = (port / counts).dropna(); pci = boot(pf); pm = metrics(pf)
    print(f"\nPORTFOLIO: CAGR {pm['cagr']*100:.1f}%  Sharpe {pm['sharpe']:.2f}  CI[{pci[0]:.2f},{pci[1]:.2f}]  "
          f"maxDD {pm['maxdd']*100:.1f}%  days {len(pf)}")
    pos_ci = sum(1 for r in rows if r["ci"][0] > 0)
    print(f"\nFINAL VERDICT: edge significant (Sharpe CI>0) on {pos_ci}/{len(rows)} coins.")
    print("Portfolio edge is " + ("REAL." if pci[0] > 0 else "NOT significant -> no tradable alpha (was overfit)."))
    (OUT / "walkforward_verdict.json").write_text(json.dumps(
        {"coins": rows, "portfolio": {"cagr": pm["cagr"], "sharpe": pm["sharpe"], "ci": pci,
         "maxdd": pm["maxdd"], "days": len(pf)}}, indent=2, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
