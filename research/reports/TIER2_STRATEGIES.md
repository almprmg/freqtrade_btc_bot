# 🟡 Tier-2 Strategies — Low Win Rate (< 50%)

**التاريخ:** 2026-06-09
**المعيار:** Win Rate < 50% (حتى لو CAGR قوي)
**القرار:** **لا تُنشر** — تنتظر تحليلًا أعمق للسبب

---

## 📋 القائمة (8 استراتيجيات)

| # | الاستراتيجية | عملة | WR | CAGR | صفقات | الحالة السابقة |
|---|---|---|---|---|---|---|
| 1 | **Calendar XRP (#107)** | XRP | **45.0%** | +26.8%/yr | 20 | 🔴 **كانت منشورة → موقوفة** |
| 2 | DOGE Regime Shield DEFENSIVE | DOGE | 28.6% | +28.1%/yr | 21 | 🛑 legacy bot موقوف |
| 3 | AVAX Meta Adaptive RELAX | AVAX | 31.2% | +14.1%/yr | 16 | 🛑 legacy bot موقوف |
| 4 | BNB Regime Shield SLOW | BNB | 46.2% | +42.7%/yr | 13 | 🛑 legacy bot موقوف |
| 5 | OnChain BTC | BTC | 44.1% | +36.0%/yr | 34 | 🛑 legacy bot موقوف |
| 6 | DynRebal SOL | SOL | 33.3% | +9.3%/yr | 9 | 🛑 legacy bot موقوف |
| 7 | MetaAdaptive LINK | LINK | 23.3% | +6.2%/yr | 30 | ⚪ لم تُنشر |
| 8 | Swing DCA V1 (أُرشفت سابقًا) | BTC | 16.7% | -3.6%/yr | 6 | 🗑️ مؤرشفة |

---

## 🤔 لماذا CAGR قوي مع WR ضعيف؟

بعض الاستراتيجيات (BNB Shield SLOW +42.7%، OnChain BTC +36%، DOGE +28%) تربح **قليل من الصفقات الكبيرة جدًا** التي تغطّي خسائر متعدّدة. هذا الـ"asymmetric returns" مقبول رياضيًا لكن:

- ⚠️ **ضغط نفسي عالٍ على المستخدم** — يرى خسائر متتالية
- ⚠️ **اعتماد على timing** — صفقة كبيرة واحدة قد تختفي بـluck بدّلاً من skill
- ⚠️ **خطر الـoverfit** — قد يكون الـCAGR العالي مدفوع بـ outliers

## 📊 التحليل المقترح (للمستقبل)

| الفحص | الغرض |
|---|---|
| **Distribution of profits** | هل الـreturns positively skewed؟ (asymmetric vs balanced) |
| **Largest trade contribution** | أكبر صفقة كم % من الـtotal PnL؟ (إذا > 50% فالاستراتيجية هشّة) |
| **Drawdown duration** | كم يوم متوسط من peak إلى recovery؟ |
| **Adversarial walk-forward** | اختبار على فترات لم يتدرّب عليها الـmodel |
| **Better entry/exit rules** | إعادة هندسة لـimprove WR دون فقدان upside |

## 🎯 الخطة

1. **حاليًا:** لا نُنشر، لا نسوّق
2. **بعد أسبوع:** نراجع الـlive performance للـ5 المنشورة الجديدة (#109-#113)
3. **شهر:** نختار 1-2 من Tier-2 ونحاول إصلاحها (مثل: إضافة filter للـlosing trades)
4. **3 شهور:** إن نجح الإصلاح → نرفّعهم إلى Tier-1

---

## ✅ الإستراتيجيات المنشورة الآن (Tier-1 — WR ≥ 50% + CAGR ≥ 2%)

| # | الاستراتيجية | عملة | WR | CAGR |
|---|---|---|---|---|
| #97 | AI Shield V1 | BTC | 71% | +26.9% |
| #98 | Triple Regime BTC | BTC | 60% | +11.2% |
| #99 | AI Shield V2 | BTC | 73% | +29.9% |
| #100 | Calendar BTC | BTC | 73% | +30.9% |
| #101 | ETH Pure Shield | ETH | 62% | +34.2% |
| #102 | SOL VolShield | SOL | 56% | +22.8% |
| #103 | Triple Regime BNB | BNB | 68% | +12.1% |
| #104 | Triple Regime ADA | ADA | 50% | +7.1% |
| #105 | Calendar ETH | ETH | 82% | +39.2% 🏆 |
| #106 | Calendar BNB | BNB | 68% | +31.0% |
| ~~#107~~ | ~~Calendar XRP~~ | XRP | **45%** | +26.8% ❌ تـ Tier-2 |
| #108 | Macro V2 BTC | BTC | 73% | +33.0% |
| **#109** | **BTC AnalogV2** | BTC | 73% | +32.4% ✨ |
| **#110** | **ETH AnalogV2 ⭐** | ETH | **78%** | **+42.2%** ✨ |
| **#111** | **BTC Calendar V2** | BTC | 73% | +31.6% ✨ |
| **#112** | **BTC AnalogShield V1** | BTC | 73% | +31.2% ✨ |
| **#113** | **BTC Quantum AI** | BTC | 72% | +30.5% ✨ |

**Tier-1 الحالي:** 16 استراتيجية نشطة (12 - 1 + 5 = 16)
