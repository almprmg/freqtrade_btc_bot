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

# These are overridable from main() (--timeframe/--seq/--horizon). They are
# counted in BARS of the chosen timeframe, so on 15m "FWD_HORIZON=30" means
# 30 bars = 7.5h ahead, on 1d it means 30 days. macro/halving stay daily and
# are forward-filled onto each intraday bar.
TIMEFRAME = "1d"
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
    fp = DATA / f"{coin}_USDT-{TIMEFRAME}.feather"
    if not fp.exists():
        raise FileNotFoundError(f"Missing OHLCV: {fp}")
    df = pd.read_feather(fp)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.sort_values("date").reset_index(drop=True)
    return df


# --- Pure-pandas indicators (TA-Lib's compiled DLL is blocked by Windows
#     Application Control on this GPU machine, so we reimplement the four
#     indicators build_features needs using Wilder smoothing). ---

def _wilder(s: pd.Series, period: int) -> pd.Series:
    """Wilder's RMA — the recursive smoothing TA-Lib uses for RSI/ATR/ADX."""
    return s.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    rs = _wilder(gain, period) / _wilder(loss, period)
    return 100 - 100 / (1 + rs)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return _wilder(tr, period)


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(((up > down) & (up > 0)) * up, index=df.index).clip(lower=0.0)
    minus_dm = pd.Series(((down > up) & (down > 0)) * down, index=df.index).clip(lower=0.0)
    tr = atr(df, period)
    plus_di = 100 * _wilder(plus_dm, period) / tr
    minus_di = 100 * _wilder(minus_dm, period) / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return _wilder(dx, period)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ret_1d"] = df["close"].pct_change(1)
    df["ret_7d"] = df["close"].pct_change(7)
    df["ret_30d"] = df["close"].pct_change(30)
    df["ema200"] = ema(df["close"], 200)
    df["above_ema200_pct"] = (df["close"] - df["ema200"]) / df["ema200"]
    df["rsi"] = rsi(df["close"], 14)
    df["adx"] = adx(df, 14)
    df["atr"] = atr(df, 14)
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


def prep_matrix(df: pd.DataFrame, seq_len: int):
    """Memory-safe alternative to make_sequences: return the 2D feature matrix
    + targets + dates + the end-position index of every sequence, WITHOUT
    materializing the (N, seq_len, F) cube. Needed for intraday frames where
    that cube is multiple GB. Sequence k = feat[end-seq_len:end], end=idx[k]."""
    df = df.dropna(subset=FEATURE_COLS + ["fwd_30d_ret"]).reset_index(drop=True)
    feat = df[FEATURE_COLS].values.astype(np.float32)
    targets = df["fwd_30d_ret"].values.astype(np.float32)
    dates = df["date"].values
    idx = np.arange(seq_len, len(df), dtype=np.int64)
    return feat, targets, dates, idx


class LazySeqDataset(Dataset):
    """Slices sequences from the shared feature matrix on demand."""
    def __init__(self, feat: np.ndarray, targets: np.ndarray, idx: np.ndarray, seq_len: int):
        self.feat = torch.from_numpy(feat)
        self.targets = torch.from_numpy(targets)
        self.idx = idx
        self.seq_len = seq_len

    def __len__(self):
        return len(self.idx)

    def __getitem__(self, k):
        i = int(self.idx[k])
        return self.feat[i - self.seq_len:i], self.targets[i]


# ============== Losses ==============
# MSE optimizes magnitude; our signal is directional, so a Pearson-correlation
# loss matches the eval metric (and makes best-val-loss == best-val-corr).

def _pearson_loss(pred: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    pred = pred - pred.mean()
    y = y - y.mean()
    denom = torch.sqrt((pred ** 2).sum() * (y ** 2).sum() + 1e-8)
    return 1.0 - (pred * y).sum() / denom


def make_loss(name: str):
    if name == "corr":
        return _pearson_loss
    if name == "combo":
        mse = nn.MSELoss()
        return lambda p, y: mse(p, y) + 0.5 * _pearson_loss(p, y)
    return nn.MSELoss()


# ============== Training loop ==============

def _tag(coin: str) -> str:
    """1d keeps the bare name (back-compat with AnalogV3); intraday adds the tf."""
    return coin if TIMEFRAME == "1d" else f"{coin}_{TIMEFRAME}"


def train(coin: str, epochs: int, batch: int, lr: float = 1e-3, val_split: float = 0.2,
          loss: str = "mse"):
    print(f"\n=== Training LSTM for {coin}/USDT ===")
    print(f"Device: {DEVICE} | Epochs: {epochs} | Batch: {batch}")

    # Build features
    df = load_coin(coin)
    df = build_features(df)
    df = add_macro(df)
    df = add_halving(df)
    print(f"  Rows after feature build: {len(df)}")

    # Normalize features — fit the scaler on the TRAIN portion only (no
    # val-period leakage). make_sequences drops NaN rows, so mirror that here.
    valid = df.dropna(subset=FEATURE_COLS + ["fwd_30d_ret"]).reset_index(drop=True)
    split_row = int(len(valid) * (1 - val_split))
    feat_mean = valid[FEATURE_COLS].iloc[:split_row].mean()
    feat_std = valid[FEATURE_COLS].iloc[:split_row].std().replace(0, 1)
    df[FEATURE_COLS] = (df[FEATURE_COLS] - feat_mean) / feat_std

    # Sequences (lazy — memory-safe for intraday frames)
    feat, targets, dates, idx = prep_matrix(df, SEQ_LEN)
    print(f"  Samples: {len(idx)} | seq_len={SEQ_LEN} horizon={FWD_HORIZON} tf={TIMEFRAME}")

    # Time-based split (no shuffling — avoid lookahead!)
    split = int(len(idx) * (1 - val_split))
    tr_idx, va_idx = idx[:split], idx[split:]
    y_val = targets[va_idx]
    print(f"  Train: {len(tr_idx)} | Val: {len(va_idx)}")

    train_loader = DataLoader(LazySeqDataset(feat, targets, tr_idx, SEQ_LEN), batch_size=batch, shuffle=True)
    val_loader = DataLoader(LazySeqDataset(feat, targets, va_idx, SEQ_LEN), batch_size=batch, shuffle=False)

    # Model (dropout 0.3 + weight_decay 3e-4 to curb the overfitting seen in v0)
    model = LstmAnalogModel(input_dim=len(FEATURE_COLS), dropout=0.3).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=3e-4)
    loss_fn = make_loss(loss)
    print(f"  Loss: {loss}")
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

    history = []
    best_val = float("inf")
    corr_at_best = 0.0       # val_corr at the best-val_loss epoch (what we ship)
    best_corr = -1.0         # best val_corr seen anywhere (diagnostic)
    best_epoch = 0
    patience = 12            # early-stop if val_loss stalls this many epochs
    no_improve = 0

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
        best_corr = max(best_corr, val_corr)
        flag = ""
        if val_loss < best_val:
            best_val = val_loss
            corr_at_best = val_corr
            best_epoch = ep + 1
            no_improve = 0
            flag = " *"
            torch.save({
                "model_state": model.state_dict(),
                "feat_mean": feat_mean.to_dict(),
                "feat_std": feat_std.to_dict(),
                "seq_len": SEQ_LEN,
                "feature_cols": FEATURE_COLS,
            }, MODELS_DIR / f"lstm_v1_{_tag(coin)}.pt")
        else:
            no_improve += 1
        print(f"  Epoch {ep+1:>3}/{epochs}  train={tr_loss:.6f}  val={val_loss:.6f}  corr={val_corr:+.4f}{flag}")

        if no_improve >= patience:
            print(f"  Early stop: val_loss stalled {patience} epochs (best @ epoch {best_epoch}).")
            break

    # Save metrics
    with open(MODELS_DIR / f"lstm_v1_{_tag(coin)}_metrics.json", "w") as f:
        json.dump({
            "coin": coin, "timeframe": TIMEFRAME, "seq_len": SEQ_LEN,
            "fwd_horizon": FWD_HORIZON, "epochs": epochs, "batch": batch,
            "best_val_loss": best_val, "best_epoch": best_epoch,
            "corr_at_best_val_loss": corr_at_best, "best_val_corr": best_corr,
            "history": history,
        }, f, indent=2)

    print(f"\n=== Done ({coin} {TIMEFRAME}) ===")
    print(f"Best val loss: {best_val:.6f} @ epoch {best_epoch}")
    print(f"Shipped correlation (at best checkpoint): {corr_at_best:+.4f}")
    print(f"Best val correlation seen:                {best_corr:+.4f}  (KNN baseline: +0.06)")
    print(f"Saved: {MODELS_DIR / f'lstm_v1_{_tag(coin)}.pt'}")


# ============== Inference (generate signals) ==============

def inference(coin: str):
    """Load trained model + generate per-bar signal/embedding for backtest use."""
    print(f"\n=== Generating signals for {coin} {TIMEFRAME} ===")
    ckpt = torch.load(MODELS_DIR / f"lstm_v1_{_tag(coin)}.pt", map_location=DEVICE)
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

    feat, _, dates, idx = prep_matrix(df, SEQ_LEN)
    loader = DataLoader(LazySeqDataset(feat, np.zeros(len(feat), np.float32), idx, SEQ_LEN),
                        batch_size=512, shuffle=False)
    preds, embeds = [], []
    with torch.no_grad():
        for xb, _ in loader:
            p, e = model(xb.to(DEVICE))
            preds.append(p.cpu().numpy())
            embeds.append(e.cpu().numpy())
    preds = np.concatenate(preds)
    embeds = np.concatenate(embeds)
    sig_dates = dates[idx]

    out = pd.DataFrame({"date": sig_dates, "lstm_pred_fwd30": preds})
    out["coin"] = coin
    out_path = REPO / "user_data" / "data" / f"dl_signals_lstm_{_tag(coin)}.feather"
    out.to_feather(out_path)
    print(f"  Saved: {out_path}  ({len(out)} signals)")

    emb_path = REPO / "user_data" / "data" / f"dl_embeddings_lstm_{_tag(coin)}.npz"
    np.savez_compressed(emb_path, dates=sig_dates.astype(str), embeddings=embeds)
    print(f"  Embeddings: {emb_path}")


# ============== Walk-forward validation ==============

def _fit_eval(feat, targets, tr_idx, va_idx, seq_len, epochs, batch, lr=1e-3, patience=12, loss="mse"):
    """Train one model on the train indices; return best val_loss + corr at that
    checkpoint + best corr seen. Lazy (memory-safe) — used by walk-forward folds."""
    model = LstmAnalogModel(input_dim=feat.shape[1], dropout=0.3).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=3e-4)
    loss_fn = make_loss(loss)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    tr_loader = DataLoader(LazySeqDataset(feat, targets, tr_idx, seq_len), batch_size=batch, shuffle=True)
    val_loader = DataLoader(LazySeqDataset(feat, targets, va_idx, seq_len), batch_size=batch, shuffle=False)

    best_val, corr_at_best, best_corr, no_improve = float("inf"), 0.0, -1.0, 0
    for _ in range(epochs):
        model.train()
        for xb, yb in tr_loader:
            xb, yb = xb.to(DEVICE), yb.to(DEVICE)
            loss_v = loss_fn(model(xb)[0], yb)
            opt.zero_grad(); loss_v.backward(); opt.step()
        model.eval()
        vl, nb, preds, ys = 0.0, 0, [], []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(DEVICE), yb.to(DEVICE)
                p, _ = model(xb)
                vl += loss_fn(p, yb).item(); nb += 1
                preds.append(p.cpu().numpy()); ys.append(yb.cpu().numpy())
        vl /= max(nb, 1)
        preds, ys = np.concatenate(preds), np.concatenate(ys)
        corr = float(np.corrcoef(preds, ys)[0, 1]) if len(preds) > 1 else 0.0
        sched.step()
        best_corr = max(best_corr, corr)
        if vl < best_val:
            best_val, corr_at_best, no_improve = vl, corr, 0
        else:
            no_improve += 1
            if no_improve >= patience:
                break
    return best_val, corr_at_best, best_corr


def walkforward(coin: str, epochs: int, batch: int, folds: int = 5, lr: float = 1e-3,
                loss: str = "mse"):
    """Expanding-window walk-forward: fold k trains on blocks[0..k], validates
    on block[k+1]. Scaler is fit on each fold's train rows only (no leakage)."""
    print(f"\n=== Walk-forward validation: {coin}/USDT {TIMEFRAME} ({folds} folds) ===")
    df = load_coin(coin)
    df = build_features(df)
    df = add_macro(df)
    df = add_halving(df)
    valid = df.dropna(subset=FEATURE_COLS + ["fwd_30d_ret"]).reset_index(drop=True)
    n = len(valid)
    if n < SEQ_LEN + (folds + 1) * 60:
        print(f"  WARNING: only {n} usable rows — folds may be tiny.")

    # (folds+1) equal blocks over the usable timeline.
    bounds = [int(n * i / (folds + 1)) for i in range(folds + 2)]
    results = []
    for k in range(1, folds + 1):
        train_end, val_end = bounds[k], bounds[k + 1]
        if train_end <= SEQ_LEN + 50 or val_end - train_end < 20:
            print(f"  Fold {k}: too few samples, skipped.")
            continue
        # Fit scaler on this fold's train rows only.
        mean = valid[FEATURE_COLS].iloc[:train_end].mean()
        std = valid[FEATURE_COLS].iloc[:train_end].std().replace(0, 1)
        vn = valid.copy()
        vn[FEATURE_COLS] = (vn[FEATURE_COLS] - mean) / std
        feat, targets, _, _ = prep_matrix(vn, SEQ_LEN)
        # sample end-position i -> belongs to train if i < train_end else val
        tr_idx = np.arange(SEQ_LEN, train_end, dtype=np.int64)
        va_idx = np.arange(train_end, val_end, dtype=np.int64)
        bv, corr_best_ckpt, corr_peak = _fit_eval(feat, targets, tr_idx, va_idx, SEQ_LEN,
                                                   epochs, batch, lr, loss=loss)
        results.append(corr_best_ckpt)
        print(f"  Fold {k}: train={len(tr_idx):>6} val={len(va_idx):>6}  "
              f"corr@best={corr_best_ckpt:+.4f}  corr_peak={corr_peak:+.4f}")

    if results:
        arr = np.array(results)
        print(f"\n  Mean corr (at best ckpt): {arr.mean():+.4f} +/- {arr.std():.4f}  "
              f"(n={len(arr)} folds, KNN +0.06)")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coin", default="BTC", help="BTC/ETH/SOL/BNB/...")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--loss", choices=["mse", "corr", "combo"], default="mse")
    parser.add_argument("--timeframe", default="1d", help="1d/4h/1h/15m (bars of this tf)")
    parser.add_argument("--seq", type=int, default=60, help="lookback length in bars")
    parser.add_argument("--horizon", type=int, default=30, help="forward target in bars")
    parser.add_argument("--mode", choices=["train", "infer", "both", "walkforward"], default="both")
    args = parser.parse_args()

    global TIMEFRAME, SEQ_LEN, FWD_HORIZON
    TIMEFRAME = args.timeframe
    SEQ_LEN = args.seq
    FWD_HORIZON = args.horizon

    if not torch.cuda.is_available():
        print("WARNING: CUDA not available! Training will be slow on CPU.")

    if args.mode == "walkforward":
        walkforward(args.coin, args.epochs, args.batch, args.folds, args.lr, args.loss)
        return
    if args.mode in ("train", "both"):
        train(args.coin, args.epochs, args.batch, args.lr, loss=args.loss)
    if args.mode in ("infer", "both"):
        inference(args.coin)


if __name__ == "__main__":
    main()
