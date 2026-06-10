# 🤖 سياق Handoff إلى Claude على جهاز الـGPU

> **اقرأ هذا أولاً** — يلخّص كل ما تم على جهاز CPU، ماذا ينقص، وماذا نريد عمله بالـGPU.

**التاريخ:** 2026-06-11
**المالك:** Hareth Almaqtari (hareth@kafaratplus.com)
**اللغة المفضّلة:** عربي + إنجليزي تقني، ردود قصيرة مباشرة، RTL في التقارير

---

## 🎯 الهدف من هذا الجهاز (GPU)

تنفيذ مهام **Deep Learning** التي كانت معلّقة بسبب عدم توفّر GPU:

1. **LSTM Embeddings** — بديل KNN لـHistorical Analogs (المهمة #1)
2. **Multi-coin Joint Training** — نموذج واحد عبر BTC+ETH+SOL+BNB+ADA+XRP+DOGE
3. **Transformer Attention** — long-range dependencies
4. **RL Allocator** — capital allocation عبر الفليت (لاحقًا)

تفاصيل كاملة في: `research/reports/FUTURE_GPU_TASKS.md`

---

## 📊 الوضع الحالي (Production Fleet)

### نظام التداول المنشور

**Server:** trad-server (72.62.179.86) — Linux، Postgres + Docker
**Stack:**
- `freqtrade_btc_bot` — production bots (Python, Freqtrade)
- `trading_engine` — signal generators (Python, 17 strategies نشطة)
- `trading_admin` — Next.js dashboard
- `trading_backend` — Node.js API

**Production Bots:** 15 استراتيجية نشطة (Tier-1)، CAGR من 6% إلى 42%/yr، WR ≥ 50%

| الترتيب | الاستراتيجية | عملة | CAGR | WR |
|---|---|---|---|---|
| 🥇 | AnalogV2 ETH ⭐ (#110) | ETH | +42.2% | 78% |
| 🥈 | Calendar ETH (#105) | ETH | +39.2% | 82% |
| 🥉 | ETH Pure Shield (#101) | ETH | +34.2% | 62% |
| 4 | Macro V2 BTC (#108) | BTC | +33.0% | 73% |
| 5 | AnalogV2 BTC (#109) | BTC | +32.4% | 73% |
| ... | (10 أخرى) | ... | ... | ... |

### 📈 أداء المحفظة (Backtest 9 سنوات)
- **$10K → $102K** (CAGR +29.5%/yr)
- 346 صفقة عبر 14 استراتيجية
- 2021 وحدها +216% (super bull cycle)

---

## ✅ ما تم على CPU (لا تكرّره)

### Backtests
- ✅ 92 استراتيجية × 9 سنوات = ~830 backtest
- ✅ Out-of-Sample validation لـAnalogV2 (corr +0.10)
- ✅ Multi-asset context (DXY/VIX/SPY/Gold)
- ✅ Multi-coin pool (BTC+ETH+BNB = 8,873 days)

### Production Deployment
- ✅ 15 bot live على trad-server (testnet/dry_run)
- ✅ 39 استراتيجية ضعيفة (CAGR<2%) أُرشفت
- ✅ 8 استراتيجيات بـWR<50% في Tier-2 (للتحليل لاحقًا)

### Cleanup
- ✅ DB cleanup: 799K سجل محذوف
- ✅ 74 zombie postgres transactions قُتلت (load 309 → 0.68)
- ✅ Calendar BNB (#106) مستبعدة من المحفظة (خسارة -$16K في صفقة)

### Reports المتاحة
- `research/reports/COMPREHENSIVE_DASHBOARD.html` — كل استراتيجية يفصّل
- `research/reports/UNIFIED_DASHBOARD.html` — freqtrade + signals
- `research/reports/SHELF_DASHBOARD.html` — المحفوظة للمستقبل
- `research/reports/PORTFOLIO_AGGREGATE.html` — مجموع المحفظة
- `research/reports/ACTIVE_STRATEGIES_DETAIL.html` — تفصيل سنوي+شهري

---

## ⏳ ما يحتاج GPU (المهمات الموكلة لك)

### 🎯 المهمة 1: LSTM Embedding للـHistorical Analogs
**الفكرة:** بدل KNN raw، نستخدم LSTM ليعمل embedding لآخر 60-90 يوم. النموذج يلتقط:
- Time-dependent dynamics
- Non-linear relationships
- Patterns متعدّدة الأبعاد

**النتيجة المتوقّعة:** Correlation +0.15-0.25 (vs KNN's +0.06)

**الكود الجاهز:** `GPU_HANDOFF/dl_train_lstm.py` — شغّله مباشرة بعد setup.

### 🎯 المهمة 2: Multi-coin Joint Training
**الفكرة:** نموذج واحد بـcoin_embedding لكل عملة، يتعلّم patterns عابرة للعملات.

**Status:** Template في `FUTURE_GPU_TASKS.md` — أُكتبه بعد ما LSTM يشتغل.

### 🎯 المهمة 3: Transformer
**Status:** للمرحلة 3 — بعد ما نتأكّد من LSTM.

---

## 🛠️ Tech Stack المُتوقّع

| Component | Version |
|---|---|
| Python | 3.10-3.12 |
| PyTorch | with CUDA 12.1+ |
| CUDA | 12.1+ |
| GPU VRAM | ≥ 8GB (12GB+ مُفضّل) |
| RAM | 32GB+ |

---

## 🔐 Secrets المطلوبة

| الـsecret | الموقع |
|---|---|
| GitHub credentials | للـpush back |
| SSH key for trad-server (لو تحتاج تنشر) | `~/.ssh/trad-server` |
| Postgres password (trad_pg) | `e763ad7f2c4924e949913f58` (للقراءة فقط من الـDB) |

**ملاحظة:** الـ`.env*` files **مش في git** — يجب نسخها يدويًا من جهاز CPU.

---

## 📚 ذاكرة المشروع (memory/)

8 ذاكرات مهمّة في `~/.claude/projects/d--pythone-trad-system/memory/`:

| الملف | الموضوع |
|---|---|
| `deploy-topology.md` | docker compose stack + gotchas |
| `dashboard-live-websocket.md` | live feed لـdashboard |
| `strategy-registration.md` | engine @register + DB row sync |
| `user-data-stream-gap.md` | Binance listen-key 410 issue |
| `remote-server-deployment.md` | SSH alias + admin patches |
| `ai-batches-complete.md` | 18 ideas, 4 deployed |
| `strategy-skills-cloud.md` | 13 specialized skills |
| `postgres-zombie-txns.md` | high load = check idle transactions |

---

## 🚀 Quick Start (بعد setup)

```powershell
# 1. تأكّد من GPU
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# 2. شغّل MENU
cd freqtrade_btc_bot
python GPU_HANDOFF/dl_train_lstm.py --task lstm --epochs 50

# 3. النتيجة في
ls user_data/data/dl_signals.feather
ls research/dl_models/
```

---

## 💬 كيف تتعامل معي

- ❌ لا تشرح ما هو معروف (راجع memory أولاً)
- ✅ نتائج رقمية بدل وصف طويل
- ✅ إذا اكتشفت مشكلة → اعرضها، لا تخبئها
- ✅ commit + push بعد كل خطوة كبيرة
- ✅ لا تنشر بدون موافقة على Production
- 🔴 لا تعمل destructive ops (DELETE من DB، rm -rf) بدون موافقة صريحة

---

## 📞 إذا احتجت

- **GitHub repos:**
  - github.com/almprmg/freqtrade_btc_bot
  - github.com/almprmg/trading_engine
  - github.com/almprmg/trading_admin
- **Server:** ssh trad-server (alias) ← key محلّي
- **Dashboard live:** http://72.62.179.86:3001
