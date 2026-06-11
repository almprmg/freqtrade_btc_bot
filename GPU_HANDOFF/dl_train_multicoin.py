"""dl_train_multicoin.py — Joint multi-coin LSTM with a per-coin embedding.

README GPU task #2. One model trained across all coins at once; a learned
coin embedding lets it specialize while sharing cross-coin patterns. The
hope (vs the 7 separate models in dl_train_lstm.py) is lower per-coin
variance because weak/short-history coins borrow strength from the rest.

Reuses the feature pipeline + corr loss from dl_train_lstm.py.

USAGE:  python GPU_HANDOFF/dl_train_multicoin.py --epochs 80 --loss corr
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

from dl_train_lstm import (
    DEVICE, FEATURE_COLS, MODELS_DIR, REPO, SEQ_LEN,
    add_halving, add_macro, build_features, load_coin, make_loss, make_sequences,
)

COINS = ["BTC", "ETH", "SOL", "BNB", "ADA", "XRP", "DOGE"]


class MultiCoinLstm(nn.Module):
    def __init__(self, input_dim=12, n_coins=7, hidden=64, embed_dim=32,
                 coin_emb=8, n_layers=2, dropout=0.3):
        super().__init__()
        self.coin_emb = nn.Embedding(n_coins, coin_emb)
        self.lstm = nn.LSTM(input_dim, hidden, num_layers=n_layers,
                            dropout=dropout if n_layers > 1 else 0, batch_first=True)
        self.embed = nn.Linear(hidden + coin_emb, embed_dim)
        self.head = nn.Linear(embed_dim, 1)

    def forward(self, x, coin_idx):
        _, (h, _) = self.lstm(x)
        h = h[-1]
        c = self.coin_emb(coin_idx)
        emb = torch.tanh(self.embed(torch.cat([h, c], dim=1)))
        return self.head(emb).squeeze(-1), emb


class MultiSeqDataset(Dataset):
    def __init__(self, X, c, y):
        self.X = torch.from_numpy(X)
        self.c = torch.from_numpy(c)
        self.y = torch.from_numpy(y)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, i):
        return self.X[i], self.c[i], self.y[i]


def build_pooled(val_split=0.2):
    """Per-coin train-only normalization + time split, then pool. Returns
    train arrays and val arrays (val keeps coin labels for per-coin corr)."""
    Xtr, ctr, ytr = [], [], []
    Xva, cva, yva = [], [], []
    for ci, coin in enumerate(COINS):
        df = load_coin(coin)
        df = build_features(df)
        df = add_macro(df)
        df = add_halving(df)
        valid = df.dropna(subset=FEATURE_COLS + ["fwd_30d_ret"]).reset_index(drop=True)
        split_row = int(len(valid) * (1 - val_split))
        mean = valid[FEATURE_COLS].iloc[:split_row].mean()
        std = valid[FEATURE_COLS].iloc[:split_row].std().replace(0, 1)
        df[FEATURE_COLS] = (df[FEATURE_COLS] - mean) / std
        X, y, _ = make_sequences(df, SEQ_LEN)
        s = int(len(X) * (1 - val_split))
        Xtr.append(X[:s]); ytr.append(y[:s]); ctr.append(np.full(s, ci, dtype=np.int64))
        Xva.append(X[s:]); yva.append(y[s:]); cva.append(np.full(len(X) - s, ci, dtype=np.int64))
        print(f"  {coin}: {len(X)} seq -> train {s}, val {len(X)-s}")
    return (np.concatenate(Xtr), np.concatenate(ctr), np.concatenate(ytr),
            np.concatenate(Xva), np.concatenate(cva), np.concatenate(yva))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--loss", choices=["mse", "corr", "combo"], default="corr")
    args = ap.parse_args()

    print(f"=== Multi-coin joint LSTM ({len(COINS)} coins) | loss={args.loss} | {DEVICE} ===")
    Xtr, ctr, ytr, Xva, cva, yva = build_pooled()
    print(f"  Pooled train: {len(Xtr)} | val: {len(Xva)}")

    model = MultiCoinLstm(input_dim=len(FEATURE_COLS), n_coins=len(COINS), dropout=0.3).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=3e-4)
    loss_fn = make_loss(args.loss)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)

    tr_loader = DataLoader(MultiSeqDataset(Xtr, ctr, ytr), batch_size=args.batch, shuffle=True)
    va_loader = DataLoader(MultiSeqDataset(Xva, cva, yva), batch_size=args.batch, shuffle=False)

    best_val, best_state, best_epoch, no_improve, patience = float("inf"), None, 0, 0, 12
    for ep in range(args.epochs):
        model.train()
        for xb, cb, yb in tr_loader:
            xb, cb, yb = xb.to(DEVICE), cb.to(DEVICE), yb.to(DEVICE)
            loss = loss_fn(model(xb, cb)[0], yb)
            opt.zero_grad(); loss.backward(); opt.step()
        model.eval()
        vl, nb, preds, ys, cs = 0.0, 0, [], [], []
        with torch.no_grad():
            for xb, cb, yb in va_loader:
                xb, cb, yb = xb.to(DEVICE), cb.to(DEVICE), yb.to(DEVICE)
                p, _ = model(xb, cb)
                vl += loss_fn(p, yb).item(); nb += 1
                preds.append(p.cpu().numpy()); ys.append(yb.cpu().numpy()); cs.append(cb.cpu().numpy())
        vl /= max(nb, 1)
        preds, ys, cs = np.concatenate(preds), np.concatenate(ys), np.concatenate(cs)
        overall = float(np.corrcoef(preds, ys)[0, 1])
        sched.step()
        flag = ""
        if vl < best_val:
            best_val, best_epoch, no_improve = vl, ep + 1, 0
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            flag = " *"
        else:
            no_improve += 1
        print(f"  Epoch {ep+1:>3}/{args.epochs}  val_loss={vl:.5f}  overall_corr={overall:+.4f}{flag}")
        if no_improve >= patience:
            print(f"  Early stop (best @ epoch {best_epoch})."); break

    # Per-coin val corr at best checkpoint
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        p_all, _ = model(torch.from_numpy(Xva).to(DEVICE), torch.from_numpy(cva).to(DEVICE))
        p_all = p_all.cpu().numpy()
    per_coin = {}
    for ci, coin in enumerate(COINS):
        m = cva == ci
        per_coin[coin] = float(np.corrcoef(p_all[m], yva[m])[0, 1]) if m.sum() > 1 else 0.0

    torch.save({"model_state": best_state, "coins": COINS, "seq_len": SEQ_LEN,
                "feature_cols": FEATURE_COLS}, MODELS_DIR / "lstm_multicoin.pt")
    with open(MODELS_DIR / "lstm_multicoin_metrics.json", "w") as f:
        json.dump({"loss": args.loss, "best_epoch": best_epoch, "best_val_loss": best_val,
                   "per_coin_val_corr": per_coin,
                   "mean_per_coin": float(np.mean(list(per_coin.values())))}, f, indent=2)

    print("\n=== Per-coin val corr (joint model, best ckpt) ===")
    for coin, c in per_coin.items():
        print(f"  {coin:>4}: {c:+.4f}")
    print(f"  MEAN: {np.mean(list(per_coin.values())):+.4f}")
    print(f"Saved: {MODELS_DIR / 'lstm_multicoin.pt'}")


if __name__ == "__main__":
    main()
