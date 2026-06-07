# 🚀 مهام مستقبلية تحتاج GPU

**التاريخ:** 2026-06-07
**الحالة:** محفوظة للتنفيذ لما يتوفّر GPU (NVIDIA + CUDA)
**ما تم على CPU:** Out-of-sample validation ✅ (PASS)

---

## 📋 الموقف الحالي

| المهمة | تنفذ على CPU؟ | الحالة |
|---|---|---|
| Multi-asset context (DXY+VIX+SPY+macro) | ✅ نعم | **مُنفّذ** |
| Per-coin training (BTC+ETH+BNB pool) | ✅ نعم | **مُنفّذ** |
| Out-of-sample validation | ✅ نعم | **مُنفّذ** (OOS corr +0.10 ✓) |
| Deep Learning embeddings | ❌ GPU مطلوب | **معلّقة** |
| Transformer / LSTM sequence model | ❌ GPU مطلوب | **معلّقة** |
| Large-scale autoencoder | ❌ GPU مطلوب | **معلّقة** |
| Reinforcement Learning Allocator | ⚠️ بطيء جدًا على CPU | **معلّقة** |
| Multi-coin DL training (ETH+SOL+...) | ❌ GPU مطلوب | **معلّقة** |

---

## 🎯 المهمة 1: Deep Learning Sequence Embeddings

### الفكرة
بدل KNN raw على state vector ثابت، نستخدم **LSTM/GRU** لترميز آخر 60-90 يوم من البيانات إلى embedding كثيف. هذا يلتقط:
- patterns متعدّدة الأبعاد
- الـ time-dependent dynamics
- non-linear relationships

### المعمارية المقترحة

```python
import torch
import torch.nn as nn

class TimeSeriesEncoder(nn.Module):
    def __init__(self, input_dim=10, hidden_dim=64, embedding_dim=32):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers=2, dropout=0.2)
        self.embedding = nn.Linear(hidden_dim, embedding_dim)
        self.head = nn.Linear(embedding_dim, 1)  # predicts fwd_30d_ret

    def forward(self, x):  # x: (seq_len=60, batch, features=10)
        _, (h, _) = self.lstm(x)
        emb = self.embedding(h[-1])
        pred = self.head(emb)
        return emb, pred
```

### Training Loop
```python
# Train autoencoder + predictor jointly
loss_fn = nn.MSELoss()
optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)

for epoch in range(50):
    for x_seq, y_fwd in dataloader:  # 60-day sequences + 30d forward returns
        emb, pred = model(x_seq.cuda())
        loss = loss_fn(pred, y_fwd.cuda())
        loss.backward()
        optimizer.step()
```

### نتائج متوقّعة:
- Correlation potential: +0.15 إلى +0.25 (vs KNN +0.06)
- CAGR uplift: +5-10pp/yr إذا نجح
- Risk: overfit (يحتاج OOS strict)

### متطلبات
- GPU: NVIDIA 8GB+ VRAM (RTX 3060 fine, prefer 4070/4080)
- PyTorch + CUDA installation
- Training time: 2-6 ساعات لكل model
- Data: نفس الـ8,873 يوم + إمكانية إضافة minute data

### تنفيذ متى يأتي GPU:
```bash
# Setup
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install lightning  # PyTorch Lightning للـboilerplate

# Build dataset
python -m research.ai.dl_dataset_builder

# Train
python -m research.ai.dl_train --epochs 50 --batch 256

# Generate embeddings for all dates
python -m research.ai.dl_inference --output dl_signals.feather

# Build strategy using DL signals
# Backtest + OOS test
```

**الكود الأساسي محفوظ كـ template في:** `research/ai/dl_template.py` (سأبنيه لما نحتاجه)

---

## 🎯 المهمة 2: Transformer Sequence Model

### الفكرة
بدل LSTM، استخدم **Transformer attention** لـ:
- التقاط long-range dependencies
- multi-head attention على الميزات المختلفة
- ربط BTC داخل سياق macro (cross-attention على SPY/DXY)

### المعمارية
```python
class TransformerForecaster(nn.Module):
    def __init__(self, input_dim=10, d_model=128, nhead=8, num_layers=4):
        super().__init__()
        self.input_proj = nn.Linear(input_dim, d_model)
        self.pos_encoding = PositionalEncoding(d_model, max_len=90)
        encoder_layer = nn.TransformerEncoderLayer(d_model, nhead, dim_feedforward=512, dropout=0.1, batch_first=True)
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers)
        self.head = nn.Linear(d_model, 1)

    def forward(self, x):  # (batch, seq=90, features=10)
        x = self.input_proj(x) + self.pos_encoding(x)
        x = self.transformer(x)
        pred = self.head(x[:, -1, :])  # use last position
        return pred
```

### متطلبات
- GPU: 12GB+ VRAM (RTX 4070/4080 ideal)
- Training time: 4-12 ساعات
- Hyperparameter tuning: 1-2 أيام لإيجاد الأفضل

### نتائج متوقّعة
- أفضل من LSTM إذا data كافية
- Correlation potential: +0.20-0.30
- Best for multi-asset attention

---

## 🎯 المهمة 3: RL-based Capital Allocator

### الفكرة
بدل rule-based meta_allocator (الحالي)، استخدم **Reinforcement Learning agent** يتعلّم:
- كم capital يخصّص لكل bot في الفليت
- متى يزيد/ينقص من bot معيّن
- كيف يستجيب لـ regime changes

### Algorithm: PPO أو SAC
```python
from stable_baselines3 import PPO

env = FleetAllocationEnv(
    bots=["calendar_btc", "macro_v2", "analog_v2_eth", ...],
    initial_capital=50000,
    rebalance_freq=7,  # weekly
)

model = PPO("MlpPolicy", env, verbose=1)
model.learn(total_timesteps=1_000_000)  # 1M steps for convergence
```

### متطلبات
- GPU: 8GB+ (training acceleration)
- CPU: 8+ cores (parallel env stepping)
- Training time: 6-24 ساعة
- Data: live trade history (لا بيانات تكفي حاليًا — يحتاج 3-6 شهور live trading أولًا)

### الموقف:
**معلّقة حتى تتوفّر بيانات live trades كافية** (6 شهور+) من البوتات الحالية على trad-server.

---

## 🎯 المهمة 4: Multi-Coin Joint Training

### الفكرة
ندرّب نموذج واحد على بيانات كل العملات (BTC + ETH + SOL + BNB + ADA + XRP + DOGE) في وقت واحد، مع coin_embedding لكل عملة. النموذج يتعلّم:
- patterns عامة عبر crypto
- specific patterns لكل عملة
- cross-correlations بين العملات

### المعمارية
```python
class MultiCoinEncoder(nn.Module):
    def __init__(self, n_coins=7):
        super().__init__()
        self.coin_emb = nn.Embedding(n_coins, 16)
        self.lstm = nn.LSTM(input_dim + 16, hidden_dim, num_layers=3)
        self.head = nn.Linear(hidden_dim, 1)

    def forward(self, x_seq, coin_id):
        coin_e = self.coin_emb(coin_id).expand(x_seq.shape[0], -1, -1)
        x_with_coin = torch.cat([x_seq, coin_e], dim=-1)
        _, (h, _) = self.lstm(x_with_coin)
        return self.head(h[-1])
```

### نتائج متوقّعة
- معرفة عميقة لكل عملة + أنماط عامة
- استفادة من data كل العملات (~24,000 يوم بدل 8,873)
- قد يكشف cross-asset signals (ETH leading BTC، إلخ)

### متطلبات
- GPU: 16GB+ VRAM (نموذج أكبر، sequences متعدّدة)
- Training: 8-24 ساعة
- Data: متاحة (لدينا 7 عملات)

---

## 📦 GPU Setup Checklist (لما يصير عندك GPU)

### الحد الأدنى
- [ ] NVIDIA GPU بـ8GB+ VRAM (RTX 3060 12GB ممتاز للبداية)
- [ ] CUDA 11.8 أو 12.1+
- [ ] Driver محدّث
- [ ] Python 3.10-3.12
- [ ] 32GB+ RAM (للـbatching الكبير)

### الأفضل
- [ ] NVIDIA RTX 4070 (12GB) أو 4080 (16GB)
- [ ] CUDA 12.1+
- [ ] 64GB RAM
- [ ] SSD سريع للـdataset caching

### Software Setup
```bash
# 1. Verify CUDA
nvidia-smi
nvcc --version

# 2. Install PyTorch with CUDA
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# 3. Verify
python -c "import torch; print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0))"

# 4. ML stack
pip install lightning transformers wandb stable-baselines3 gymnasium
```

---

## 📊 الأولويات (لما يصير GPU)

| الترتيب | المهمة | السبب | الوقت | التعقيد |
|---|---|---|---|---|
| 1 | LSTM embedding | جاهز للتنفيذ، أوضح فائدة | 4-8 ساعات | متوسط |
| 2 | Multi-coin joint training | يستفيد من كل البيانات | 8-12 ساعة | متوسط |
| 3 | Transformer attention | إذا LSTM نجح، نجرّب أحسن | 12-24 ساعة | عالٍ |
| 4 | RL Allocator | يحتاج live data أولاً | 24-48 ساعة | عالٍ جدًا |

---

## ✅ ما عمل CPU بالفعل (محفوظ، ناجح)

1. **Multi-asset context** — `historical_analogs_v2.py`:
   - DXY z-score
   - VIX panic
   - SPY trend
   - macro_risk_on composite

2. **Per-coin training pool** — `historical_analogs_v2.py`:
   - BTC + ETH + BNB = 8,873 days

3. **Out-of-Sample Validation** — `historical_analogs_oos.py`:
   - Train pool: ≤ 2022-12-31
   - Test period: 2023-2026 (1,220 days)
   - **OOS correlation: +0.10** (أقوى من in-sample +0.06!)
   - **Q5 vs Q1: +9.76% vs +2.04% fwd_30d** (7.7pp فرق على بيانات لم يراها الـAI)

**Conclusion: AnalogV2 ETH (+42.2%/yr) صالحة فعلًا، ليست overfit.**

---

## 🔮 الخطّة طويلة المدى

### فاز 1 (الآن، CPU): ✅ مكتمل
- Macro V2 ✓
- AnalogV2 (multi-coin + macro) ✓
- OOS validation ✓

### فاز 2 (GPU، يجب الانتظار):
- LSTM embedding → AnalogV3
- Multi-coin joint training → AnalogV4
- Transformer attention → AnalogV5

### فاز 3 (Live data accumulation، 3-6 شهور):
- جمع 1000+ trades من البوتات الحية
- RL Allocator training
- Online learning model (يتحدّث يوميًا)

### فاز 4 (Cloud GPU، اختياري):
- Hyperparameter optimization على cloud GPU (Vast.ai، Lambda، إلخ)
- $5-20/ساعة، فقط للـtuning النهائي
- نتائج محفوظة، model deployed على CPU بعدها

---

## 📁 ملفات المتابعة

```
research/ai/
├── historical_analogs.py           ← V1 (CPU، done)
├── historical_analogs_v2.py        ← V2 multi-coin (CPU، done) ⭐
├── historical_analogs_oos.py       ← OOS validation (CPU، done) ✓
├── dl_dataset_builder.py           ← لإنشاء dataset لـPyTorch (TODO)
├── dl_train.py                     ← LSTM training (TODO، GPU)
├── dl_inference.py                 ← embedding generation (TODO)
├── transformer_train.py            ← Transformer (TODO، GPU)
└── rl_allocator.py                 ← RL agent (TODO، GPU + live data)
```

**جاهز للتنفيذ:** أي وقت توفّر GPU، شغّل المهام بالترتيب.
