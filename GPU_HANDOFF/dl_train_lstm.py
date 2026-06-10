"""dl_train_lstm.py — LSTM embedding model for Historical Analog signals.

GOAL: Replace the KNN-based AnalogV2 (CAGR 32-42%) with an LSTM that
encodes the last 60 days into a dense embedding + predicts fwd_30d return.

Expected uplift: KNN correlation +0.06 → LSTM target +0.15-0.25.

USAGE:
    python GPU_HANDOFF/dl_train_lstm.py --epochs 50 --batch 256
    python GPU_HANDOFF/dl_train_lstm.py --epochs 100 --batch 512 --coin BTC

OUTPUTS:
    research/dl_models/lstm_v1_{coin}.pt           — model weights
    research/dl_models/lstm_v1_{coin}_metrics.json  — train/val metrics
    user_data/data/dl_signals_lstm.feather          — per-day signal + embedding

CONTEXT: Read CONTEXT_FOR_GPU_AI.md first if you're a new agent.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "user_data" / "data" / "binance"
MACRO = REPO / "user_data" / "data" / "macro_signals.feather"
HALVING = REPO / "user_data" / "data" / "halving_cycle.feather"
MODELS_DIR = REPO / "research" / "dl_models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

SEQ_LEN = 60
FWD_HORIZON = 30
FEATURE_COLS = [
    "ret_1d", "ret_7d", "ret_30d",
    "above_ema200_pct", "rsi", "adx", "atr_pct",
    "dxy_zscore", "vix", "spy_above_ema50", "macro_risk_on",
    "phase_code",
]


# ============== Data prep ==============

def load_coin(coin: str) -> pd.DataFrame:
    fp = DATA / f"{coin}_USDT-1d.feather"
    if not fp.exists():
        raise FileNotFoundError(f"Missing OHLCV: {fp}")
    df = pd.read_feather(fp)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.sort_values("date").reset_index(drop=True)
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    import talib.abstract as ta
    df = df.copy()
    df["ret_1d"] = df["close"].pct_change(1)
    df["ret_7d"] = df["close"].pct_change(7)
    df["ret_30d"] = df["close"].pct_change(30)
    df["ema200"] = ta.EMA(df, timeperiod=200)
    df["above_ema200_pct"] = (df["close"] - df["ema200"]) / df["ema200"]
    df["rsi"] = ta.RSI(df, timeperiod=14)
    df["adx"] = ta.ADX(df, timeperiod=14)
    df["atr"] = ta.ATR(df, timeperiod=14)
    df["atr_pct"] = df["atr"] / df["close"]
    df["fwd_30d_ret"] = df["close"].pct_change(FWD_HORIZON).shift(-FWD_HORIZON)
    return df


def add_macro(df: pd.DataFrame) -> pd.DataFrame:
    if not MACRO.exists():
        for c in ["dxy_zscore", "vix", "spy_above_ema50", "macro_risk_on"]:
            df[c] = 0.0
        return df
    macro = pd.read_feather(MACRO)
    macro["date"] = pd.to_datetime(macro["date"], utc=True)
    macro = macro.set_index("date")
    idx = df["date"].dt.normalize()
    for c in ["dxy_zscore", "vix", "spy_above_ema50", "macro_risk_on"]:
        df[c] = idx.map(macro[c].ffill() if c in macro.columns else pd.Series()).ffill().fillna(0)
    return df


def add_halving(df: pd.DataFrame) -> pd.DataFrame:
    if not HALVING.exists():
        df["phase_code"] = 0
        return df
    hc = pd.read_feather(HALVING)
    hc["date"] = pd.to_datetime(hc["date"], utc=True)
    hc = hc.set_index("date")
    phase_map = {"ACCUMULATION": 1, "EARLY_BULL": 2, "PARABOLIC": 3,
                 "DISTRIBUTION": 4, "BEAR": 5, "REACCUMULATION": 6, "NEUTRAL": 0}
    idx = df["date"].dt.normalize()
    df["phase_code"] = idx.map(hc["phase"]).map(phase_map).fillna(0).astype(int)
    return df


def make_sequences(df: pd.DataFrame, seq_len: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (X: [N, seq_len, F], y: [N], dates: [N])."""
    df = df.dropna(subset=FEATURE_COLS + ["fwd_30d_ret"]).reset_index(drop=True)
    feat = df[FEATURE_COLS].values
    targets = df["fwd_30d_ret"].values
    dates = df["date"].values

    X, y, d = [], [], []
    for i in range(seq_len, len(df)):
        X.append(feat[i - seq_len:i])
        y.append(targets[i])
        d.append(dates[i])
    return np.asarray(X, dtype=np.float32), np.asarray(y, dtype=np.float32), np.asarray(d)


# ============== Model ==============

class LstmAnalogModel(nn.Module):
    def __init__(self, input_dim: int = 12, hidden: int = 64, embed_dim: int = 32,
                 n_layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden, num_layers=n_layers,
                            dropout=dropout if n_layers > 1 else 0,
                            batch_first=True)
        self.embed = nn.Linear(hidden, embed_dim)
        self.head = nn.Linear(embed_dim, 1)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        # x: (batch, seq_len, features)
        _, (h, _) = self.lstm(x)
        h = h[-1]                       # last layer's final hidden state
        emb = torch.tanh(self.embed(h))
        pred = self.head(emb)
        return pred.squeeze(-1), emb


class SeqDataset(Dataset):
    def __init__(self, X: np.ndarray, y: np.ndarray):
        self.X = torch.from_numpy(X)
        self.y = torch.from_numpy(y)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, i):
        return self.X[i], self.y[i]


# ============== Training loop ==============

def train(coin: str, epochs: int, batch: int, lr: float = 1e-3, val_split: float = 0.2):
    print(f"\n=== Training LSTM for {coin}/USDT ===")
    print(f"Device: {DEVICE} | Epochs: {epochs} | Batch: {batch}")

    # Build features
    df = load_coin(coin)
    df = build_features(df)
    df = add_macro(df)
    df = add_halving(df)
    print(f"  Rows after feature build: {len(df)}")

    # Normalize features
    feat_mean = df[FEATURE_COLS].mean()
    feat_std = df[FEATURE_COLS].std().replace(0, 1)
    df[FEATURE_COLS] = (df[FEATURE_COLS] - feat_mean) / feat_std

    # Sequences
    X, y, dates = make_sequences(df, SEQ_LEN)
    print(f"  Sequences: {X.shape}, targets: {y.shape}")

    # Time-based split (no shuffling — avoid lookahead!)
    split = int(len(X) * (1 - val_split))
    X_tr, X_val = X[:split], X[split:]
    y_tr, y_val = y[:split], y[split:]
    print(f"  Train: {len(X_tr)} | Val: {len(X_val)}")

    train_loader = DataLoader(SeqDataset(X_tr, y_tr), batch_size=batch, shuffle=True)
    val_loader = DataLoader(SeqDataset(X_val, y_val), batch_size=batch, shuffle=False)

    # Model
    model = LstmAnalogModel(input_dim=len(FEATURE_COLS)).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    loss_fn = nn.MSELoss()
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

    history = []
    best_val = float("inf")

    for ep in range(epochs):
        # Train
        model.train()
        tr_loss = 0; n_batches = 0
        for xb, yb in train_loader:
            xb, yb = xb.to(DEVICE), yb.to(DEVICE)
            pred, _ = model(xb)
            loss = loss_fn(pred, yb)
            opt.zero_grad()
            loss.backward()
            opt.step()
            tr_loss += loss.item(); n_batches += 1
        tr_loss /= max(n_batches, 1)

        # Val
        model.eval()
        val_loss = 0; n_val = 0
        val_preds, val_ys = [], []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(DEVICE), yb.to(DEVICE)
                pred, _ = model(xb)
                loss = loss_fn(pred, yb)
                val_loss += loss.item(); n_val += 1
                val_preds.append(pred.cpu().numpy())
                val_ys.append(yb.cpu().numpy())
        val_loss /= max(n_val, 1)
        val_preds = np.concatenate(val_preds)
        val_ys = np.concatenate(val_ys)
        val_corr = float(np.corrcoef(val_preds, val_ys)[0, 1]) if len(val_preds) > 1 else 0

        sched.step()
        history.append({
            "epoch": ep, "train_loss": tr_loss, "val_loss": val_loss, "val_corr": val_corr,
            "lr": sched.get_last_lr()[0],
        })
        print(f"  Epoch {ep+1:>3}/{epochs}  train={tr_loss:.6f}  val={val_loss:.6f}  corr={val_corr:+.4f}")

        if val_loss < best_val:
            best_val = val_loss
            torch.save({
                "model_state": model.state_dict(),
                "feat_mean": feat_mean.to_dict(),
                "feat_std": feat_std.to_dict(),
                "seq_len": SEQ_LEN,
                "feature_cols": FEATURE_COLS,
            }, MODELS_DIR / f"lstm_v1_{coin}.pt")

    # Save metrics
    with open(MODELS_DIR / f"lstm_v1_{coin}_metrics.json", "w") as f:
        json.dump({
            "coin": coin, "seq_len": SEQ_LEN, "epochs": epochs, "batch": batch,
            "best_val_loss": best_val, "history": history,
            "final_corr": history[-1]["val_corr"],
        }, f, indent=2)

    print(f"\n=== Done ===")
    print(f"Best val loss: {best_val:.6f}")
    print(f"Final correlation: {history[-1]['val_corr']:+.4f}  (KNN baseline: +0.06)")
    print(f"Saved: {MODELS_DIR / f'lstm_v1_{coin}.pt'}")


# ============== Inference (generate signals) ==============

def inference(coin: str):
    """Load trained model + generate per-day signal/embedding for backtest use."""
    print(f"\n=== Generating signals for {coin} ===")
    ckpt = torch.load(MODELS_DIR / f"lstm_v1_{coin}.pt", map_location=DEVICE)
    feat_mean = pd.Series(ckpt["feat_mean"])
    feat_std = pd.Series(ckpt["feat_std"])

    model = LstmAnalogModel(input_dim=len(FEATURE_COLS)).to(DEVICE)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    df = load_coin(coin)
    df = build_features(df)
    df = add_macro(df)
    df = add_halving(df)
    df[FEATURE_COLS] = (df[FEATURE_COLS] - feat_mean) / feat_std

    X, _, dates = make_sequences(df, SEQ_LEN)
    preds, embeds = [], []
    with torch.no_grad():
        for i in range(0, len(X), 256):
            xb = torch.from_numpy(X[i:i+256]).to(DEVICE)
            p, e = model(xb)
            preds.append(p.cpu().numpy())
            embeds.append(e.cpu().numpy())
    preds = np.concatenate(preds)
    embeds = np.concatenate(embeds)

    out = pd.DataFrame({
        "date": dates,
        "lstm_pred_fwd30": preds,
    })
    out["coin"] = coin
    out_path = REPO / "user_data" / "data" / f"dl_signals_lstm_{coin}.feather"
    out.to_feather(out_path)
    print(f"  Saved: {out_path}  ({len(out)} signals)")

    # Save embeddings separately (for later analog search)
    emb_path = REPO / "user_data" / "data" / f"dl_embeddings_lstm_{coin}.npz"
    np.savez_compressed(emb_path, dates=dates.astype(str), embeddings=embeds)
    print(f"  Embeddings: {emb_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coin", default="BTC", help="BTC/ETH/SOL/BNB/...")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--mode", choices=["train", "infer", "both"], default="both")
    args = parser.parse_args()

    if not torch.cuda.is_available():
        print("WARNING: CUDA not available! Training will be slow on CPU.")

    if args.mode in ("train", "both"):
        train(args.coin, args.epochs, args.batch, args.lr)
    if args.mode in ("infer", "both"):
        inference(args.coin)


if __name__ == "__main__":
    main()
