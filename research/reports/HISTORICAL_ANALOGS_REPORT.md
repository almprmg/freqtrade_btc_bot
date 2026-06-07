# 🧠 Historical Analog AI — تقرير

**التاريخ:** 2026-06-07
**الفكرة:** AI يبحث عن أيام مشابهة في السنوات السابقة عند اتخاذ القرار

---

## 🔬 المنهجية

### نوعان من التشابه:

**1. State KNN Analogs (تشابه فني):**
- لكل يوم T، نأخذ vector الحالة: [الموقع من EMA200, ret_7d, ret_30d, RSI, ADX, ATR%, cycle_phase]
- نبحث عن K=20 أيام مشابهة في التاريخ (قبل T بـ30 يوم على الأقل، لتجنّب look-ahead)
- نحسب: متوسط fwd_30d_return + win rate لتلك الأيام
- إذا متوسط هذه الأيام كان +10%، الـAI يقترح موقف أكبر

**2. Calendar Analogs (تشابه تقويمي):**
- لنفس التاريخ (شهر، يوم) في السنوات السابقة
- مثال: 7 يناير 2026 → نشوف 7 يناير 2020, 2021, 2022, 2023, 2024, 2025
- متوسط fwd_30d return لتلك التواريخ

## 📊 النتائج الإحصائية للإشارات نفسها

| الإشارة | Correlation مع fwd_30d الفعلي |
|---|---|
| analog_fwd_30d_mean (KNN) | **+0.0155** (ضعيف جدًا) |
| calendar_5y_mean | **-0.0793** (سالب!) |

**الاكتشاف:** الإشارات **ضعيفة جدًا**. السوق لا يكرّر نفسه بطريقة بسيطة.

## 🎯 نتائج الاختبار (9 سنوات BTC)

| الاستراتيجية | $10K → | CAGR | الفرق عن Calendar |
|---|---|---|---|
| **Macro V2 (المنشور #108)** | **$130,326** | **+33.0%** | +$17,194 |
| AnalogShield W=0.30 (NEW) | $115,131 | +31.2% | **+$1,999** ⚠️ هامشي |
| Calendar Shield (baseline) | $113,132 | +30.9% | — |
| AnalogShield W=0.50 (strong) | $108,760 | +30.4% | -$4,372 (أسوأ) |

## 📋 السنوي للـ AnalogShield (W=0.30)

| السنة | ROI | الصفقات | الفرق عن Calendar |
|---|---|---|---|
| 2018 (bear) | 0% | 0 | = |
| 2019 | +5.3% | 2 | -0.6pp |
| 2020 | +105% | 5 | -1.2pp |
| 2021 | +121% | 8 | -0.1pp |
| 2022 (bear) | 0% | 0 | = |
| 2023 | +54.5% | 6 | **+4.1pp** ✅ |
| 2024 | +36.4% | 7 | 0pp |
| 2025 | +14.2% | 2 | +0.3pp |
| 2026 Q12 | 0% | 0 | = |

**التحسّن الرئيسي في 2023:** AnalogShield (54.5%) > Calendar (50.4%). الـAI رأى أن 2023 شبيه بسنوات تعافي سابقة → زاد الوزن.

## 🧠 الدرس الجوهري

**الـHistorical Analog AI يضيف +0.3pp/yr فقط على BTC.** لماذا؟

### السبب الأول: BTC نادرًا ما يكرر نفسه بدقّة
- كل دورة لها سياق فريد (halving + macro + سيولة)
- التشابه التاريخي ≠ مستقبل مماثل
- correlation حقيقي +0.02 (تقريبًا صفر)

### السبب الثاني: Calendar Shield تقاطع كثيرًا مع الـanalog
- Calendar tilts (October) موجودة في كلا الاستراتيجيتين
- الـanalog يكرّر signals موجودة أصلًا
- لا new information كبير

### السبب الثالث: Macro V2 أقوى بكثير
- Macro V2 يستخدم signals **حقيقية** (S&P، VIX) بـ correlation +0.30
- الـAnalog signal +0.02 = noise
- لا منافسة

## 💡 متى يصلح الـ Historical Analog؟

النمط يصلح في حالات **التشابه القوي**:
- بيانات عالية التكرار (تداول ساعي/دقائق)
- أسواق mean-reverting (forex، commodities)
- أنماط seasonality واضحة (energy، agriculture)

لا يصلح بقوة لـ BTC الحالي لأن:
- بيانات يومية = sample size صغير
- اتجاه عام صاعد (kills mean-reversion)
- كل دورة فريدة (low repetition)

## ✅ الحالة الحالية

- **AnalogShield محفوظة** في `user_data/strategies/btc_analog_shield_strategy.py`
- **لم تُنشر** على trad-server (التحسّن غير كافٍ)
- **Macro V2 (#108) ما زال البطل** بفارق $15K

## 📁 الملفات

| الملف | المحتوى |
|---|---|
| `research/ai/historical_analogs.py` | بناء KNN + calendar analogs |
| `user_data/data/historical_analogs.feather` | 2,984 يوم مع analog signals |
| `user_data/strategies/btc_analog_shield_strategy.py` | الاستراتيجية |
| `config.analog.json` | config للـtest |

لإعادة التوليد:
```bash
./.venv/Scripts/python.exe -m research.ai.historical_analogs
```

## 🔮 الخطوة التالية (لو أردنا تحسينه فعلاً)

1. **رفع جودة الـsimilarity**: استخدم Deep Learning embedding بدل KNN raw
2. **إضافة multi-asset context**: قارن BTC مع SPY + Gold + DXY في نفس الوقت
3. **Per-coin analogs**: استخدم بيانات ETH/SOL أيضًا (المزيد من data)
4. **Cross-validation**: تدريب على 2018-2022، اختبار على 2023-2026 (avoid lookahead in design)

كل هذه مشاريع كبيرة. **حاليًا، Macro V2 + Calendar Shield يكفيان**.
