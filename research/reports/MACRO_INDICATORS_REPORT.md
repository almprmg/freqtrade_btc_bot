# 🌍 Macro Economic Indicators — Test Report

**التاريخ:** 2026-06-05
**الفرضية:** إضافة مؤشرات الاقتصاد الكلي (الدولار، VIX، الأسهم، الفوائد) للـAI تحسّن قرارات التداول.

---

## 📊 المؤشرات الـ6 التي جُلبت (Yahoo Finance)

| الرمز | الاسم | المعنى |
|---|---|---|
| `DX-Y.NYB` | DXY — Dollar Index | قوة الدولار (سلبي مع crypto) |
| `^VIX` | VIX — مؤشر التقلب | الخوف في الأسواق |
| `SPY` | S&P 500 ETF | السوق العام |
| `^TNX` | 10-Year Treasury Yield | الفوائد |
| `GC=F` | Gold Futures | الذهب |
| `QQQ` | NASDAQ-100 ETF | الأسهم التقنية |

**البيانات:** 2017-01-03 → 2026-06-05 (~2,370 يوم لكل مؤشر)

---

## 🎯 الإشارات المحسوبة (16 إشارة)

| الإشارة | التفسير |
|---|---|
| `dxy_zscore` | z-score 30d للدولار (>1 = قوة دولار = bearish crypto) |
| `dxy_ret_30d` | عائد الدولار 30 يوم |
| `vix` | قيمة VIX المطلقة |
| `vix_regime` | calm / elevated / panic |
| `vix_is_panic` | 1 إذا VIX > 30 |
| `spy_above_ema50` | S&P فوق متوسطه 50 يوم |
| `spy_ret_30d` | عائد S&P 30 يوم |
| `tnx_change_5d` | تغيّر الفائدة 5 أيام |
| `rates_rising` | 1 إذا الفائدة ترتفع بقوة |
| `gold_ret_30d` | عائد الذهب 30 يوم |
| `qqq_above_ema50` | NASDAQ في uptrend |
| **`macro_risk_on`** | **الإشارة المركّبة [-1, +1]** |

---

## 🔬 الـCorrelations مع BTC (n=2,214)

| الإشارة | corr(ret_1d) | corr(ret_7d) | corr(ret_30d) | الحكم |
|---|---|---|---|---|
| **spy_ret_30d** | +0.026 | +0.110 | **+0.303** 🔥 | الأقوى |
| **qqq_above_ema50** | +0.067 | +0.167 | **+0.300** 🔥 | الأقوى |
| **macro_risk_on** | +0.060 | +0.166 | **+0.287** 🔥 | المركّبة قوية |
| **spy_above_ema50** | +0.041 | +0.130 | +0.284 | |
| **vix** | -0.024 | -0.115 | **-0.216** ★ | الخوف يهبط BTC |
| tnx | -0.041 | -0.076 | -0.121 | الفوائد تضرّ |
| vix_is_panic | -0.007 | -0.082 | -0.100 | |
| dxy_zscore | -0.044 | -0.081 | -0.084 | الدولار تأثيره معتدل |

### Quintile Analysis (Q1 → Q5 by macro_risk_on)

| Zone | n | BTC 30d Return | Win Rate |
|---|---|---|---|
| Q1 (risk-off) | 443 | **-7.91%** | 33% |
| Q2 | 445 | +4.34% | 54% |
| Q3 | 436 | +9.45% | 58% |
| **Q4 (risk-on)** | **441** | **+13.43%** 🔥 | **68%** |
| Q5 (extreme) | 428 | +6.61% | 61% |

**الفرق Q1 → Q4 = +21pp في 30 يوم!** إشارة حقيقية بقوة.

---

## ⚙️ الـ Strategy Integration

بنيت `BtcMacroShieldStrategy` يضيف `macro_risk_on` كـtilt على Calendar Shield:

```python
adjusted_bias = cycle_bias + phase_shift + calendar_tilt + MACRO_WEIGHT × macro_risk_on
+ hard rule: if macro_risk_on < -0.5 → exit immediately
```

اختبرت ثلاث variants:
1. **w=0.25** (ثقيل): يأخذ macro بجدية
2. **w=0.10** (خفيف): يأخذ macro بقليل
3. **on ETH** (vol أعلى، إرتباط أعلى بالأسهم)

---

## 📈 النتائج — 9 سنوات

| Strategy | $10K → | CAGR | المقارنة | Adversarial |
|---|---|---|---|---|
| **BTC Calendar (baseline)** | **$113,132** | **+30.9%/yr** | المرجع | ✅ PASS |
| BTC Macro Shield w=0.25 | $97,305 | +28.8%/yr | **-2pp/yr** ❌ | ✅ PASS |
| BTC Macro Shield w=0.10 | $90,431 | +27.7%/yr | **-3pp/yr** ❌ | ✅ PASS |
| **ETH Calendar (baseline)** | **$196,126** | **+39.2%/yr** | المرجع | ✅ PASS |
| ETH Macro Shield w=0.25 | $109,894 | +30.5%/yr | **-9pp/yr** ❌ | ⚠️ غير محتسب |

### السنة بسنة (BTC) — لماذا خسر Macro

| السنة | Calendar | Macro w=0.25 | الفرق |
|---|---|---|---|
| 2018 | 0% | 0% | = |
| 2019 | +5.9% | **+12.4%** | **+6.5pp** (macro يحسّن في recovery) |
| 2020 | +106% | +119% | +13pp (macro يحسّن في bull واضح) |
| **2021** | **+122%** | **+82%** | **-40pp** ❌ (الخسارة الكبرى) |
| 2022 | 0% | 0% | = |
| 2023 | +50% | +40% | -10pp |
| 2024 | +36% | +38% | +2pp |
| 2025 | +14% | +12% | -2pp |
| 2026 Q12 | 0% | 0% | = |

### 🎯 الـ root cause: 2021 decoupling

في 2021:
- Macro كان **risk-off** (Fed بدأ talking about hikes, yields ترتفع)
- لكن BTC كان **parabolic** ($30K → $69K) مدفوع بـretail euphoria
- Macro Shield قلّل الـposition بسبب macro tilt → فاتت الـbull

في 2024-2025:
- Macro و crypto أكثر correlated (ETF era, institutional flows)
- الفرق صغير

---

## 🧠 الـTakeaway

**الإشارة حقيقية لكن تطبيقها كـtilt يخسر** للأسباب:

1. **2021 decoupling**: crypto bulls تتفك عن macro
2. **Calendar Shield ضيق** — إضافة tilt يخفّض الـposition وقت ذروة الأداء
3. **30d correlation ≠ سببية لحظية** — تفاعل macro بطيء، crypto سريع
4. **Macro tilt يفيد في recoveries** (2019-2020) لكن يضرّ في parabolic bulls

---

## ✅ القرار النهائي

**لا أنشر Macro Shield كاستراتيجية مستقلة.** Calendar Shield يبقى البطل.

**لكن الـmacro data layer قيّم لـ:**
- ✅ تقارير المراقبة (هل السوق risk-on؟)
- ✅ قرارات يدوية (متى أضيف رأس مال؟)
- ✅ استراتيجيات مستقبلية مختلفة (filter only، لا tilt)
- ✅ تحذير من panic (VIX > 30 = إنذار مبكر)

---

## 📁 ملفات محفوظة

| المسار | الوصف |
|---|---|
| `research/ai/macro_data.py` | الأداة (fetch / signals / analyze) |
| `user_data/data/macro_daily.feather` | الـ6 raw symbols (2017+) |
| `user_data/data/macro_signals.feather` | الـ16 signals الجاهزة |
| `user_data/strategies/btc_macro_shield_strategy.py` | الاستراتيجية (للمستقبل) |

### للتحديث اليومي:
```bash
./.venv/Scripts/python.exe -m research.ai.macro_data fetch
./.venv/Scripts/python.exe -m research.ai.macro_data signals
```

أو ضع في cron يومي.

---

## 🔮 الاستخدام المقترح

بدلاً من tilt، استخدم macro كـ**filter منفصل**:

```python
# Pseudocode للمستقبل
if macro_risk_on < -0.5 AND already_in_trade:
    EXIT  # حماية من panic
elif macro_risk_on > 0.7 AND not_in_trade AND regime == "BULL":
    INCREASE_WALLET_BY_20%  # توسّع في bull واضح
else:
    follow Calendar Shield normally  # لا تتدخّل
```

هذا يستخدم macro كـ"second opinion" فقط في الحالات الواضحة، بدون التدخل في القرارات اليومية.

تنفيذه يحتاج جلسة منفصلة لو أراد المستخدم.
