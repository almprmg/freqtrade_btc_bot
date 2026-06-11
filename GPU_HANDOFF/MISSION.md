# 🎯 الهدف الواضح — لا تنحرف

## ❌ ما لا نريد

- ❌ **لا تبحث عن استراتيجيات جديدة من الصفر** — عندنا 92 مختبرة
- ❌ **لا تقترح أساليب تداول جديدة** (RSI، MACD، إلخ) — مرّت
- ❌ **لا تنسخ ما عمله Claude السابق** — ابني عليه
- ❌ **لا تعمل backtests عشوائية** — عندنا 3500+ archive
- ❌ **لا تنشر شيء جديد على trad-server** بدون إذن صريح

## ✅ ما نريد بالضبط

**الهدف:** تحسين الاستراتيجيات الـ15 المنشورة باستخدام Deep Learning.

نريد **تحسين** ما هو موجود، **مش بناء جديد**.

---

## 📊 ما عندنا الآن (اقرأها أولاً!)

اقرأ هذه التقارير بالترتيب لتفهم وضع المشروع:

| الترتيب | الملف | لماذا |
|---|---|---|
| 1 | `research/reports/ACTIVE_STRATEGIES_DETAIL.html` | **التفصيل السنوي/الشهري للـ15 استراتيجية المنشورة** |
| 2 | `research/reports/PORTFOLIO_AGGREGATE.html` | المحفظة المجمّعة + سنوي تراكمي ($10K → $102K) |
| 3 | `research/reports/COMPREHENSIVE_REPORT.md` | كل الـ92 استراتيجية مع CAGR + WR |
| 4 | `research/reports/UNIFIED_REPORT.md` | freqtrade + signals موحّد |
| 5 | `research/reports/STAR_STRATEGIES.md` | الاستراتيجية النجمة AnalogV2 ETH ⭐ |
| 6 | `research/reports/HISTORICAL_ANALOGS_REPORT.md` | كيف بنينا AnalogV2 (KNN approach) |
| 7 | `research/reports/MACRO_INDICATORS_REPORT.md` | DXY/VIX/SPY signals |
| 8 | `research/reports/META_ANALYSIS_DECISIONS.md` | القرارات التي اتخذناها |
| 9 | `research/reports/SHELF_REPORT.md` | 39 محفوظة للمستقبل |
| 10 | `research/reports/TIER2_STRATEGIES.md` | 8 خاسرة (WR<50%) - تنتظر تحليل |
| 11 | `research/reports/FUTURE_GPU_TASKS.md` | **الـDL roadmap (هذا اللي ستعمله!)** |

---

## 🎯 المهمّة المحدّدة

### Phase 1: LSTM للـHistorical Analogs (الأولوية القصوى)

**الوضع الحالي:**
- AnalogV2 يستخدم **KNN raw** على state vector ثابت (10 features)
- KNN correlation مع fwd_30d_ret = **+0.06** ضعيف
- لكن مع كل الـtilts، CAGR = **+42%/yr** على ETH
- **السؤال:** لو زدنا الـcorrelation 2-3×، كم سيرتفع CAGR؟

**ما تفعله:**
1. شغّل `python GPU_HANDOFF\dl_train_lstm.py --coin BTC --epochs 50`
2. التارجت: validation correlation ≥ **+0.15** (KNN baseline +0.06)
3. لو نجح، كرّر على ETH (الاستراتيجية النجمة)
4. لو نجح على ETH، كرّر على باقي العملات
5. ابنِ `BtcAnalogV3Strategy` يستخدم LSTM بدل KNN
6. اختبر 9 سنوات
7. **قارن صراحةً:** AnalogV2 (+42% ETH) vs AnalogV3 (+X% ETH)

**النجاح:** AnalogV3 يتفوّق على AnalogV2 بـ ≥ +5pp CAGR.
**الفشل:** AnalogV3 لا يتفوّق → فهم ليه (ربما KNN كافٍ للـ1d timeframe، نحتاج intraday).

### Phase 2: تحسين Calendar Shield بـDL (لاحقًا)

Calendar Shield الحالي يعتمد على tilts ثابتة (شهرية + halving phase). يمكن نتعلّم الـtilts بدل ما نضعها يدويًا.

### Phase 3: Cross-asset learning

نموذج واحد يتعلّم من BTC+ETH+SOL+BNB+ADA+XRP+DOGE معًا — لكن نحتاج Phase 1 ينجح أولاً.

---

## 🧠 طريقة التفكير المطلوبة

### قبل التشغيل:
1. **اقرأ** `ACTIVE_STRATEGIES_DETAIL.html` و `PORTFOLIO_AGGREGATE.html` لتفهم وضع المحفظة
2. **افتح** `HISTORICAL_ANALOGS_REPORT.md` لتفهم AnalogV2 الحالي
3. **افهم** أن AnalogV2 ETH هي ⭐ — لو حسّنّاها +5pp، يعني $250K → $300K في 9 سنوات

### أثناء التشغيل:
1. لا تنتظر يدويًا — استخدم `Monitor` tool
2. لو الـCorrelation يطلع ضعيف (<0.10) → جرّب hyperparameters مختلفة قبل ما تستسلم:
   - `hidden=128` بدل 64
   - `embedding_dim=64` بدل 32
   - `epochs=100` بدل 50
   - `seq_len=90` بدل 60
3. لو حتى مع التجارب يطلع <0.10 → الـDL مش مفيد على daily data → بلّغني واقترح بدائل

### بعد التشغيل:
1. **حسّن وضّح** الفرق بالأرقام:
```
=== AnalogV3 LSTM vs AnalogV2 KNN ===
Coin    KNN_CORR  LSTM_CORR  IMPROVE   KNN_CAGR    LSTM_CAGR   DELTA
BTC     +0.06     +X.XX      +Y.YY     +32.4%      +XX.X%      +Z.Z pp
ETH ⭐  +0.06     +X.XX      +Y.YY     +42.2%      +XX.X%      +Z.Z pp
```

2. **HTML report** يقارن سنويًا الـ9 سنوات لكلتيهما (مثل ACTIVE_STRATEGIES_DETAIL.html)

3. **commit + push** كل شيء على main

---

## 🚫 الـoutput الذي لا أريده

❌ "أنشأت 5 استراتيجيات جديدة بـRSI و MACD"
❌ "اقترحت 10 ideas جديدة..."
❌ "اختبرت كل العملات بـ 100 طريقة"
❌ "هل تريد أن أبدأ بـ X؟"

---

## ✅ الـoutput الذي أريده

✅ "LSTM BTC: corr +0.18 ✓ (KNN was +0.06). أكمل على ETH..."
✅ "AnalogV3 ETH: CAGR +48% vs AnalogV2 +42% = +6pp تحسّن"
✅ "All 7 coins trained. HTML report at research/reports/LSTM_VS_KNN.html"
✅ "commit pushed. النتيجة النهائية: محفظة محسّنة من $102K → $X estimated"

---

## 🎯 KPI النجاح

| المقياس | الحد الأدنى للنجاح | الهدف |
|---|---|---|
| LSTM BTC val correlation | ≥ +0.10 | +0.15-0.25 |
| LSTM ETH val correlation | ≥ +0.10 | +0.15-0.25 |
| AnalogV3 ETH 9y CAGR | ≥ AnalogV2 (+42%) | +47%+ |
| تحسين المحفظة | ≥ +2pp CAGR | +5pp |
| Reports + Commits | كاملة | مفصّلة + مُلوّنة |

ابدأ الآن بالخطوة 1: قراءة `ACTIVE_STRATEGIES_DETAIL.html` لتفهم وضعنا.
