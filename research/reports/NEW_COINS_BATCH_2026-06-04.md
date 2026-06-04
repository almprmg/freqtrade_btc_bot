# 🪙 New Coins Batch Report — 2026-06-04

**Goal:** اختبار 7 عملات قوية جديدة لإضافتها للفليت.
**Coins:** LINK, LTC, DOT, XRP, ATOM, NEAR, BCH
**Archetypes per coin:** Calendar Shield, Triple Regime, Pure Shield, VolShield
**Total tests:** 24 backtests + 24 adversarial verdicts

---

## 🎯 النتيجة الكلية: 1 deploy / 6 رفض

**XRP Calendar Shield = الفائز الوحيد** → sub #107 ($3K wallet)

---

## 📋 جدول التفصيل الكامل — لكل عملة × archetype

### LINK (Chainlink) — vol 109%

| Archetype | 2021 | 2022 | 2023 | 2024 | 2025 | 2026Q12 | Compound | Annual | Adv | Decision |
|---|---|---|---|---|---|---|---|---|---|---|
| Calendar | — | — | — | — | — | — | — | — | **FAIL** (-29% sideways) | ❌ |
| Triple | -4.3% | -5.9% | -1.6% | +3.0% | -0.3% | 0% | **$9,101** | **-1.9%/yr** | WARN | ❌ ضعيف |
| Pure Shield | — | — | — | — | — | — | — | — | **CATASTROPHIC** (-30% bear) | ❌ |
| VolShield | — | — | — | — | — | — | — | — | **FAIL** (-20% sideways) | ❌ |

**النتيجة: LINK لا يصلح. كل archetypes تفشل أو تخسر.**

---

### LTC (Litecoin) — vol 85%

| Archetype | 2021 | 2022 | 2023 | 2024 | 2025 | 2026Q12 | Compound | Annual | Adv | Decision |
|---|---|---|---|---|---|---|---|---|---|---|
| Calendar | — | — | — | — | — | — | — | — | **FAIL** (-21% sideways) | ❌ |
| Triple | -3.2% | -14.9% | +3.0% | 0% | -5.6% | 0% | **$8,000** | **-4.4%/yr** | WARN | ❌ يخسر |
| Pure Shield | — | — | — | — | — | — | — | — | **FAIL** (-24% sideways) | ❌ |
| VolShield | -2.3% | 0% | +7.4% | +1.8% | -2.4% | 0% | **$10,428** | **+0.8%/yr** | PASS | ❌ بلا فائدة |

**النتيجة: LTC VolShield يمر adversarial لكن يربح 0.8%/yr فقط — بنك الادخار أفضل.**

---

### DOT (Polkadot) — vol 98%

| Archetype | 2021 | 2022 | 2023 | 2024 | 2025 | 2026Q12 | Compound | Annual | Adv | Decision |
|---|---|---|---|---|---|---|---|---|---|---|
| Calendar | — | — | — | — | — | — | — | — | **CATASTROPHIC** (-44%) | ❌ |
| Triple | -5.5% | 0% | 0% | 0% | 0% | 0% | **$9,450** | **-1.1%/yr** | **PASS** | ❌ يخسر |
| Pure Shield | — | — | — | — | — | — | — | — | **CATASTROPHIC** (-42%) | ❌ |
| VolShield | 0% | 0% | +5.8% | -11.4% | 0% | 0% | **$9,375** | **-1.3%/yr** | **PASS** | ❌ يخسر |

**النتيجة: DOT — حتى الـ PASSes يخسرون. Triple "مر" بدون أي صفقات تقريبًا.**

---

### XRP (Ripple) — vol 102% (لكن مكبوت قضائيًا) 🏆

| Archetype | 2021 | 2022 | 2023 | 2024 | 2025 | 2026Q12 | Compound | Annual | Adv | Decision |
|---|---|---|---|---|---|---|---|---|---|---|
| **Calendar** | **+17.6%** | **0%** | **+20.0%** | **+111.5%** 🚀 | **+4.6%** | **0%** | **$31,213** | **+25.6%/yr** | ✅ **PASS** | ✅ **نُشر** (#107) |
| Triple | — | — | — | — | — | — | — | — | WARN | ❌ أضعف |
| VolShield | — | — | — | — | — | — | — | — | WARN | ❌ أضعف |

**النتيجة: XRP Calendar = الفائز الوحيد. 2024 +111% (دعوى SEC انتهت = bull). نُشر بـ $3K.**

---

### ATOM (Cosmos) — vol 103%

| Archetype | 2021 | 2022 | 2023 | 2024 | 2025 | 2026Q12 | Compound | Annual | Adv | Decision |
|---|---|---|---|---|---|---|---|---|---|---|
| Calendar | — | — | — | — | — | — | — | — | **FAIL** (-18% sideways) | ❌ |
| Triple | +0.8% | 0% | +1.1% | 0% | -1.4% | 0% | **$10,050** | **+0.1%/yr** | **PASS** | ❌ بلا فائدة |
| VolShield | — | — | — | — | — | — | — | — | **PASS** | لم يُفصَّل (متوقع ضعيف) |

**النتيجة: ATOM — Triple مر adversarial لكن يربح 0.1%/yr. لا قيمة.**

---

### NEAR (Near Protocol) — vol 120%

| Archetype | 2021 | 2022 | 2023 | 2024 | 2025 | 2026Q12 | Compound | Annual | Adv | Decision |
|---|---|---|---|---|---|---|---|---|---|---|
| Calendar | — | — | — | — | — | — | — | — | **FAIL** (-19% sideways) | ❌ |
| Triple | -16.4% | +16.9% | +9.6% | -15.9% | 0% | 0% | **$9,023** | **-2.0%/yr** | **PASS** | ❌ يخسر |
| VolShield | — | — | — | — | — | — | — | — | WARN | لم يُفصَّل |

**النتيجة: NEAR Triple "مر" adversarial لكن -2%/yr فعلاً. يفقد المال.**

---

### BCH (Bitcoin Cash) — vol 96%

| Archetype | 2021 | 2022 | 2023 | 2024 | 2025 | 2026Q12 | Compound | Annual | Adv | Decision |
|---|---|---|---|---|---|---|---|---|---|---|
| **Calendar** | -31.8% | 0% | +17.0% | +21.6% | +19.9% | 0% | **$11,647** | **+3.1%/yr** | ✅ **PASS** | ❌ ضعيف جدًا |
| Triple | — | — | — | — | — | — | — | — | WARN | ❌ |
| VolShield | — | — | — | — | — | — | — | — | **PASS** | لم يُفصَّل |

**النتيجة: BCH Calendar يمر adversarial و+3.1%/yr لكن السنة 2021 -31.8% (سيئة جدًا للبداية). لم يُنشر.**

---

## 📊 الترتيب النهائي (الـ24 اختبار)

### ✅ مرّوا Adversarial + Annual ≥ +10%/yr

| Coin × Arch | Annual | Adv | تم؟ |
|---|---|---|---|
| **XRP Calendar** | **+25.6%/yr** | PASS | ✅ نُشر #107 |

### ⚠️ مرّوا Adversarial لكن Annual ضعيف

| Coin × Arch | Annual | Adv | لماذا لم يُنشر |
|---|---|---|---|
| BCH Calendar | +3.1%/yr | PASS | السنوي ضعيف جدًا + 2021 -31.8% |
| LTC VolShield | +0.8%/yr | PASS | تقريبًا صفر |
| ATOM Triple | +0.1%/yr | PASS | لا يكاد يتاجر |
| DOT Triple | -1.1%/yr | PASS | يخسر بدفاع زائد |
| DOT VolShield | -1.3%/yr | PASS | يخسر |
| LINK Triple | -1.9%/yr | WARN | يخسر |
| NEAR Triple | -2.0%/yr | PASS | يخسر |
| LTC Triple | -4.4%/yr | WARN | يخسر |

### ❌ سقطوا في Adversarial

| Coin × Arch | Worst window | Verdict |
|---|---|---|
| DOT Pure Shield | -42% bear | CATASTROPHIC |
| DOT Calendar | -44% sideways | CATASTROPHIC |
| LINK Pure Shield | -30% bear | CATASTROPHIC |
| LINK Calendar | -29% sideways | FAIL |
| LINK VolShield | -20% sideways | FAIL |
| LTC Calendar | -21% sideways | FAIL |
| LTC Pure Shield | -24% sideways | FAIL |
| ATOM Calendar | -18% sideways | FAIL |
| NEAR Calendar | -19% sideways | FAIL |

---

## 🧠 ما تعلمناه

### القاعدة الذهبية الجديدة:
**Vol > 95%** = الـarchetypes الموجودة لا تشتغل. حتى لو الـ adversarial PASSes، الـ compound يكون 0% أو سالب.

### السبب التقني:
- BTC Calendar يستفيد من halving cycle (4-year predictable signal)
- ETH Calendar يستفيد من نظافة الـtrends + سيولة عميقة
- High-vol altcoins (LINK/DOT/ATOM/NEAR) = chop ينعش false signals باستمرار

### استثناء XRP:
XRP له **vol نظري عالي (102%)** لكن **vol محقّق منخفض** بسبب:
1. دعوى SEC كبتت السعر 2020-2024
2. سيولة عميقة (top-5 cap)
3. أنماط حركة نظيفة (يصعد ويهبط بتجمعات واضحة)

النتيجة: Calendar Shield يشتغل كأنه على عملة منخفضة الـvol.

---

## 💡 توصيات للمستقبل

1. **لا تختبر بنفس archetypes على vol > 95%** — هدر للوقت
2. **عملات قوية أخرى تستحق الاختبار** (مع تركيز على vol المحقّق):
   - **LTC** (إذا انخفض vol مستقبلاً)
   - **TRX** (vol معتدل، سيولة عميقة)
   - **TON** (لو حصلنا على بيانات كافية)
3. **بدلاً من port-and-pray**: صمّم archetype جديد للـhigh-vol altcoins:
   - مؤشرات أبطأ (EMA300، ret_90d)
   - تأكيد 7-10 أيام (لا 3-5)
   - ATR ceiling أصغر (< 0.08)
   - الدخول فقط أثناء BTC bull (cross-coin signal)

---

## 📁 الملفات المرتبطة

- Strategy code: `user_data/strategies/btc_calendar_shield_strategy.py` (المستخدمة لـXRP)
- Config: `config.calendar-XRP.json`
- Docker: `docker-compose.calendar-xrp.yml`
- Archive: 24 backtest runs في `research/experiments/` بـmodes `(LINK|LTC|DOT|XRP|ATOM|NEAR|BCH)_*`
- Adversarial: `research/adversarial/MASTER.csv` (آخر 24 سطر للجولة)
