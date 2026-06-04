# 🪙 Per-Coin Breakdown — Strategies & Performance

What we have for each coin, why, and how it performed in backtest.

---

## 🟠 BTC — 5 strategies live

Why so many: BTC is the cleanest coin (vol ~55%, halving cycle, calendar effects strongest). It's our research lab.

| Sub | Strategy | Wallet | Backtest 5y | Adv | Notes |
|---|---|---|---|---|---|
| #97 | BTC AI Shield V1 | $5,000 | +42%/yr | PASS | Original AI shield |
| #98 | BTC Triple Regime | $2,000 | +10.5%/yr | PASS | Defensive sleeve |
| #99 | BTC AI Shield V2 | $5,000 | **+36.5%/yr** | PASS | Sigmoid + halving |
| #100 | BTC Calendar Shield | $3,000 | **+38.2%/yr** | PASS | V2 + calendar tilts |
| #97-prefix legacy | various rebalancers | ~$50K | unverified | — | Pre-AI session |

**BTC total exposure: ~$99,500 (83% of portfolio)** ← overconcentrated, legacy cleanup recommended

---

## 🔷 ETH — 3 strategies live

| Sub | Strategy | Wallet | Backtest 5y | Adv | Notes |
|---|---|---|---|---|---|
| #82, #89 | ETH DynRebal | $1,000 | unverified | — | Legacy HODL-style |
| #101 | ETH Pure Shield | $3,000 | **+47%/yr** | WARN | Bear protection |
| #105 | **ETH Calendar Shield** | $3,000 | **+55.5%/yr** 🏆 | PASS | Strongest of session |

**ETH total: $8,000**

Why ETH gets Calendar AND Pure Shield: ETH 2022 was -77%. Even with Shield it lost -12% (acceptable per WARN gate). Calendar version improves to 0% in 2022 by riding cycle_phase shifts.

---

## 🟣 SOL — 2 strategies live

| Sub | Strategy | Wallet | Backtest 5y | Adv | Notes |
|---|---|---|---|---|---|
| #83, #90 | SOL DynRebal | $500 | unverified | — | Legacy |
| #102 | **SOL VolShield v3** | $3,000 | **+45%/yr** | WARN | Custom vol-aware |

**SOL total: $4,000**

SOL is the chop king (vol ~95%). Took 3 design iterations before VolShield v3 passed adversarial. Three previous SOL variants ALL failed CATASTROPHICALLY (-32 to -43%).

---

## 🟡 BNB — 2 strategies live

| Sub | Strategy | Wallet | Backtest 5y | Adv | Notes |
|---|---|---|---|---|---|
| #93 | BNB Regime Shield SLOW (legacy) | $1,000 | unverified | FAIL recent | Bear -20% |
| #103 | BNB Triple Regime | $2,000 | +17.7%/yr | WARN | Defensive |
| #106 | **BNB Calendar Shield** | $3,000 | **+51.7%/yr** | PASS | Strongest BNB |

**BNB total: $6,000**

BNB Calendar shows nearly identical compound to legacy (52% vs 52%) but PASSES adversarial vs legacy FAIL (bear DD -1.5% vs -20%).

---

## 🟢 ADA — 2 strategies live

| Sub | Strategy | Wallet | Backtest 5y | Adv | Notes |
|---|---|---|---|---|---|
| #95 | ADA Meta Adaptive (legacy) | $1,000 | unverified | FAIL recent | Sideways -22% |
| #104 | **ADA Triple Regime** | $2,000 | +14.4%/yr | **PASS** | Defensive |

**ADA total: $3,000**

ADA had 3 candidates fail: Calendar -44%, AI Shield V2 -44%. Only Triple Regime survives (low return but PASSES).

---

## 🟤 DOGE — 1 strategy live (OPEN CHALLENGE)

| Sub | Strategy | Wallet | Backtest 5y | Adv | Notes |
|---|---|---|---|---|---|
| #94 | DOGE Regime Shield DEFENSIVE | $1,000 | unverified | FAIL recent | Bear -32%/-19% |

**DOGE total: $1,000**

**Open challenge:** ALL 4 attempts (RegimeShield, Adaptive, Triple, AIShV2) failed adversarial. DOGE's meme-coin dynamics (Elon-tweet pumps + retail dumps) break technical regime detection. Needs custom design.

---

## 🔴 AVAX — 1 strategy live

| Sub | Strategy | Wallet | Backtest 5y | Adv | Notes |
|---|---|---|---|---|---|
| #92 | AVAX Meta Adaptive RELAX | $1,000 | unverified | FAIL recent | Sideways -19% |

**AVAX total: $1,000**

Tested Btc3Layer (CATASTROPHIC -63%), Calendar (CATASTROPHIC), VolShield from SOL (too defensive +1.7%/yr).
Status quo MetaReliable RELAX is the best available.

---

## ⚪ XRP — 1 strategy (NEWEST)

| Sub | Strategy | Wallet | Backtest 5y | Adv | Notes |
|---|---|---|---|---|---|
| #107 | **XRP Calendar Shield** | $3,000 | +25.6%/yr | PASS | Deployed today |

**XRP total: $3,000**

Onboarded today. Top-5 liquidity coin. Calendar pattern transferred cleanly because XRP's realized vol is suppressed by years of legal limbo.

---

## ❌ Coins TESTED but NO deploy

| Coin | Vol | Best result | Decision |
|---|---|---|---|
| LINK | 109% | Triple WARN -8.7%/5y | Too volatile |
| LTC | 85% | VolShield PASS +0.8%/yr | Useless |
| DOT | 98% | Triple PASS 0%/yr | Useless |
| ATOM | 103% | Triple PASS +0.1%/yr | Useless |
| NEAR | 120% | Triple PASS -2%/yr | Loses money |
| BCH | 96% | Calendar PASS +3.1%/yr | Marginal |
| MATIC/POL | — | Insufficient history | Rebrand 2024, only 629 days |

**Lesson:** "Strong project" ≠ "trades well with our patterns". The Calendar/Triple/VolShield archetypes work best on:
- BTC (halving cycle as anchor)
- ETH, BNB (lower vol, deep liquidity, clean trends)
- XRP (suppressed vol)

Pure high-vol altcoins resist our patterns. Would need a different design entirely.

---

## 📐 Vol vs Strategy Compatibility Map

| Vol range | Coins | Best archetype | Hit rate |
|---|---|---|---|
| < 60% | BTC | Calendar, Sigmoid V2 | 100% |
| 60-80% | ETH, BNB, LTC | Calendar, Pure Shield | 67% |
| 80-95% | SOL, ADA, AVAX, BCH | VolShield, Triple | 33% |
| > 95% | LINK, DOT, ATOM, NEAR | None reliably | 10% |
| Meme | DOGE | None reliably | 0% |

Hit rate = (PASS adversarial AND > 10%/yr) / total tested.

---

## 💰 Allocation Summary

| Coin | Wallet | % | Bots | Note |
|---|---|---|---|---|
| BTC | $99,500 | 83% | 13 | OVER-CONCENTRATED (legacy bots inflate) |
| ETH | $8,000 | 7% | 4 | Diverse strategies |
| BNB | $6,000 | 5% | 3 | Good coverage |
| SOL | $4,000 | 3% | 3 | VolShield primary |
| ADA | $3,000 | 2.5% | 2 | Triple Regime backstop |
| XRP | $3,000 | 2.5% | 1 | New |
| AVAX | $1,000 | 1% | 1 | Status quo |
| DOGE | $1,000 | 1% | 1 | Open challenge |

**Per `portfolio-risk-manager` skill: BTC should be ≤ 40% of portfolio.** Legacy BTC bot cleanup recommended.

If we trim 5 legacy BTC bots (subs #79, #80, #81, #84-86, #87, #88) by $5K each:
- BTC: $99,500 → $69,500 → 67% (still high but better)
- Free $30K to:
  - Increase top performers (ETH Calendar, BNB Calendar)
  - Or add a coin/strategy that diversifies further
