# 🎯 Welcome to the GPU Machine — Quick Start

You just `git clone`d this repo on a Windows + GPU machine. Follow these
steps in order to get from zero → first deep-learning model trained.

## 📚 Read these first (5 minutes)

1. **`CONTEXT_FOR_GPU_AI.md`** — what's been done, what we want
2. **`FUTURE_GPU_TASKS.md` (in `research/reports/`)** — full DL roadmap

## 🚀 Setup (one-time, ~15 minutes)

```powershell
# In freqtrade_btc_bot dir:
powershell -ExecutionPolicy Bypass -File GPU_HANDOFF\setup_gpu.ps1
```

This installs:
- PyTorch with CUDA 12.1
- pandas, sklearn, lightning, transformers
- freqtrade itself
- Verifies GPU is recognized

## 📦 Sync data from CPU machine

Edit `GPU_HANDOFF\sync_data.ps1` — set `$SOURCE_HOST` and `$SOURCE_USER` to your CPU machine. Then:

```powershell
powershell -ExecutionPolicy Bypass -File GPU_HANDOFF\sync_data.ps1
```

This pulls (over SSH/SCP):
- OHLCV feather files (~500MB)
- macro_signals, halving_cycle, anomaly_flags
- All 3500+ backtest experiments
- Claude Code session history + memory

Alternative if SCP fails:
- Copy via OneDrive / shared network drive
- Or USB external drive

## 🧠 First training run

```powershell
# Activate venv
.venv\Scripts\Activate.ps1

# Train LSTM on BTC (50 epochs, ~30 min on RTX 3060/12GB)
python GPU_HANDOFF\dl_train_lstm.py --coin BTC --epochs 50

# Output:
#   research/dl_models/lstm_v1_BTC.pt           (model weights)
#   research/dl_models/lstm_v1_BTC_metrics.json  (loss curves + correlation)
#   user_data/data/dl_signals_lstm_BTC.feather   (per-day signal)
#   user_data/data/dl_embeddings_lstm_BTC.npz    (60-day embeddings)
```

**Target metric:** validation correlation ≥ +0.15 (KNN baseline is +0.06).

## 🔁 Multi-coin training

```powershell
foreach ($coin in @("BTC", "ETH", "SOL", "BNB", "ADA", "XRP", "DOGE")) {
    python GPU_HANDOFF\dl_train_lstm.py --coin $coin --epochs 50
}
```

## 🤖 Resume Claude Code

Your old conversation history (with all the context) is at:

```
%USERPROFILE%\.claude\projects\d--pythone-trad-system\
```

After `sync_data.ps1` ran, Claude Code on this machine will see all
previous chats + memory.

```powershell
# Install Claude Code
npm install -g @anthropic-ai/claude-code

# Login (use same API key as old machine)
claude login

# Open project
cd freqtrade_btc_bot
claude
```

The new Claude session will have access to all 8 memories (deploy
topology, dashboard ws, postgres zombies, etc.) and 100% of prior
context.

## 🆘 Troubleshooting

| Problem | Fix |
|---|---|
| `torch.cuda.is_available() == False` | Driver mismatch — reinstall PyTorch with correct CUDA version (`nvidia-smi` shows your driver, install matching `cu121` or `cu118`) |
| Out of memory during training | Reduce `--batch` (try 64 or 32) |
| `talib` install fails | Use `pip install talib-binary` (precompiled) |
| SCP fails over SSH | Use shared OneDrive folder instead, or USB drive |
| Claude Code doesn't see history | Verify path: `%USERPROFILE%\.claude\projects\d--pythone-trad-system\` must contain `.jsonl` files |

## 📊 What's next after LSTM works

See `research/reports/FUTURE_GPU_TASKS.md` for full roadmap:

1. ✅ LSTM Embedding (you are here)
2. Multi-coin joint training (~8-12 hours on 16GB+ VRAM)
3. Transformer attention model
4. Online learning (updates daily as new data comes in)
5. RL allocator (needs more live data first)
