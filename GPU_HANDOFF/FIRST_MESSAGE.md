# 🤖 First Message — انسخ هذا والصقه في Claude الجديد

> **كيف تستخدمه:**
> 1. افتح Claude Code على الجهاز الجديد: `claude`
> 2. انسخ النص بالأسفل **كامل** (من `---` إلى `---`)
> 3. الصقه كأوّل رسالة
> 4. اضغط Enter

---

```
أنت Claude يكمل مشروع تداول كبير من جهاز آخر (CPU). الآن انت على جهاز GPU.

# 📚 اقرأ أولاً (مهم — لا تتخطّى)

1. اقرأ `CLAUDE.md` في الـroot
2. اقرأ `GPU_HANDOFF/CONTEXT_FOR_GPU_AI.md` — يحتوي ملخّص ما عمل Claude السابق
3. راجع `C:\Users\<name>\.claude\projects\d--pythone-trad-system\memory\MEMORY.md` — 8 ذاكرات
4. تذكّر الـ15 Skill المتاحة (strategy-architect, bot-builder, strategy-critic، إلخ)

# 🎯 من أنا (الـuser)

- المالك: Hareth Almaqtari
- اللغة: عربي + إنجليزي تقني
- أحب: ردود قصيرة، أرقام بدل وصف طويل، تقارير في جداول
- لا أحب: شرح ما هو معلوم، تكرار، مقدمات طويلة

# 🤖 كيف تتصرّف معي (مهم)

1. ✅ **افعل قبل ما تشرح** — لو طلبت "اختبر X"، شغّله، لا تشرح كيف ستشغّله
2. ✅ **استخدم TodoWrite** للمهام المركّبة (3+ خطوات)
3. ✅ **commit + push بعد كل إنجاز كبير** — لا تنتظر إذني
4. ✅ **اعرض الأرقام صراحة** — جداول، CAGR، WR، PnL
5. ✅ **اكتشف المشاكل وأظهرها** — لا تخفيها
6. ✅ **إذا في خطأ، أصلحه أولاً ثم أبلغني** بإيجاز
7. 🔴 **لا تعمل destructive ops** (DELETE من DB، rm -rf، docker rm) بدون موافقتي الصريحة
8. 🔴 **لا تنشر على trad-server** بدون إذن
9. 🔴 **لا تستهلك الـcontext في tests يدوية** — استخدم scripts + Monitor

# 🎯 مهمّتك الأولى الآن

## المهمة: LSTM Embedding يحلّ مكان KNN في AnalogV2

**السياق:**
- AnalogV2 الحالي يستخدم KNN raw → correlation +0.06 → CAGR +42% on ETH
- نريد LSTM يقرأ آخر 60 يوم → embedding → predict fwd_30d return
- الهدف: correlation ≥ +0.15 (2.5x KNN)

**الخطوات:**

### 1. تحقّق من البيئة
```powershell
# GPU شغّال؟
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# البيانات موجودة؟
ls user_data/data/binance/BTC_USDT-1d.feather
ls user_data/data/macro_signals.feather
ls user_data/data/halving_cycle.feather
```

لو شيء ناقص — أخبرني فورًا قبل ما تكمل.

### 2. شغّل تدريب LSTM على BTC أولاً
```powershell
python GPU_HANDOFF\dl_train_lstm.py --coin BTC --epochs 50
```

استخدم Monitor للمراقبة بدل ما تنتظر يدويًا.

### 3. حلّل النتيجة

افتح `research/dl_models/lstm_v1_BTC_metrics.json` واعرض لي:
- Best validation correlation
- مقارنة مع KNN baseline (+0.06)
- إذا CORR ≥ +0.10 → ✅ نجح → كمل للمرحلة 4
- إذا CORR < +0.10 → ❌ فشل → جرّب hyperparameters مختلفة (hidden=128, epochs=100)

### 4. كرّر على كل العملات
```powershell
foreach ($c in @("ETH","SOL","BNB","ADA","XRP","DOGE")) {
    python GPU_HANDOFF\dl_train_lstm.py --coin $c --epochs 50
}
```

### 5. بنّ استراتيجية AnalogV3 جديدة
- مكان: `user_data/strategies/btc_analog_v3_strategy.py`
- مماثلة لـ`btc_analog_v2_strategy.py` لكن تستخدم `dl_signals_lstm_*.feather` بدل `historical_analogs_v2.feather`
- اختبرها 9 سنوات backtest
- قارن بـAnalogV2

### 6. التقرير النهائي

اعرضه بهذا الشكل:

```
=== LSTM vs KNN ===
Coin    KNN_CORR  LSTM_CORR  IMPROVE   KNN_CAGR  LSTM_CAGR
BTC     +0.06     +X.XX      +Y.YY     +32.4%    +XX.X%
ETH     +0.06     +X.XX      +Y.YY     +42.2%    +XX.X%
SOL     ...       ...        ...       ...       ...
```

### 7. Commit + push
```powershell
git add research/dl_models/ user_data/data/dl_signals_lstm_*.feather user_data/strategies/btc_analog_v3_strategy.py research/reports/LSTM_VS_KNN.md
git commit -m "feat(dl): LSTM AnalogV3 — corr +XX vs KNN +0.06"
git push
```

# ⚠️ في حال علقت

- **GPU memory error** → قلّل `--batch 64` بدل 256
- **Training بطيء جدًا** → تحقّق `nvidia-smi` (هل GPU مشغّل؟ لو 0% — مش شغّال)
- **NaN في loss** → قلّل `--lr 1e-4` بدل 1e-3
- **البيانات ناقصة** → اطلب منّي rsync أو أعطيك مسار للنسخ

# 🏆 المتوقّع منك

في الـ4 ساعات القادمة:
- ✅ تدريب LSTM على 7 عملات
- ✅ تقرير LSTM_VS_KNN.md
- ✅ AnalogV3 strategy جاهزة
- ✅ 7 backtests × 9 سنوات نتائج
- ✅ git push النهائي

ابدأ الآن بالخطوة 1 (التحقّق من البيئة).
```

---

## 💡 نصائح إضافية

### لو تريد توجيهات أخرى وقت التشغيل:

| ما تريد | قلّه بهذا الشكل |
|---|---|
| تغيير التركيز | "لا، أبدأ بـETH أولاً (أقوى CAGR)" |
| إيقاف ما يفعله | "أوقف هذا، جرّب shorter sequence 30 days بدل 60" |
| توجيه الأولويّات | "خلّينا نختبر فقط top 3 strategies، تجاهل الباقي" |
| طلب تقرير | "اعطني تقرير شامل HTML للنتائج" |

### حفظ المحادثة + الذاكرة:

كل ما تنجزه Claude يُحفظ تلقائيًا في:
- المحادثة: `~/.claude/projects/d--pythone-trad-system/*.jsonl`
- ذاكرات جديدة: `~/.claude/projects/d--pythone-trad-system/memory/`

إذا نقلت الجهاز مرة أخرى — كل شيء يبقى محفوظ.
