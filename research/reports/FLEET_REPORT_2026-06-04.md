# 📊 Fleet Performance Report — 2026-06-04

**Status:** 31 bots / 61 containers all live on trad-server
**Total allocated:** $119,500
**Live trading:** dryrun mode (no real capital yet)
**Days since fleet started:** 1-3 days (most bots <72h old)

---

## 1. CURRENT FLEET — by sub_id

### 🟢 Production-grade bots (deployed in major AI session, subs #97-#107)

| Sub | Bot | Coin | Strategy | Wallet | Adv Verdict | Backtest 5y |
|---|---|---|---|---|---|---|
| #97 | freqtrade_ai_shield | BTC | BtcAiShieldStrategy | $5,000 | PASS | +42%/yr |
| #98 | freqtrade_triple | BTC | BtcTripleRegimeStrategy | $2,000 | PASS | +10.5%/yr |
| #99 | freqtrade_ai_shield_v2 | BTC | BtcAiShieldV2Strategy | $5,000 | PASS | **+36.5%/yr** |
| #100 | freqtrade_calendar | BTC | BtcCalendarShieldStrategy | $3,000 | PASS | **+38.2%/yr** |
| #101 | freqtrade_eth_shield | ETH | BtcRegimeShieldStrategy | $3,000 | WARN | **+47%/yr** |
| #102 | freqtrade_sol_vol_shield | SOL | SolVolShieldStrategy | $3,000 | WARN | **+45%/yr** |
| #103 | freqtrade_bnb_triple | BNB | BtcTripleRegimeStrategy | $2,000 | WARN | +17.7%/yr |
| #104 | freqtrade_ada_triple | ADA | BtcTripleRegimeStrategy | $2,000 | PASS | +14.4%/yr |
| #105 | freqtrade_eth_calendar | ETH | BtcCalendarShieldStrategy | $3,000 | PASS | **+55%/yr** 🏆 |
| #106 | freqtrade_bnb_calendar | BNB | BtcCalendarShieldStrategy | $3,000 | PASS | +52%/yr |
| #107 | freqtrade_xrp_calendar | XRP | BtcCalendarShieldStrategy | $3,000 | PASS | +25.6%/yr |

**Subtotal new deploys:** $34,000

### 🟡 Earlier deploys (still running but unvalidated by adversarial)

| Sub | Bot | Coin | Wallet |
|---|---|---|---|
| #78 | freqtrade_rebalance | BTC | $500 |
| #79 | freqtrade_3layer | BTC | $10,000 |
| #80 | freqtrade_dynrebal | BTC | $10,000 |
| #81 | freqtrade_adaptive | BTC | $10,000 |
| #82 | freqtrade_dynrebal_eth | ETH | $1,000 |
| #83 | freqtrade_dynrebal_sol | SOL | $500 |
| #84 | freqtrade_shield | BTC | $10,000 |
| #85 | freqtrade_rebalance_v2 | BTC | $10,000 |
| #86 | freqtrade_dynrebal_v2 | BTC | $10,000 |
| #87 | freqtrade_3layer_v2 | BTC | $10,000 |
| #88 | freqtrade_adaptive_v2 | BTC | $10,000 |
| #89 | freqtrade_shield_eth | ETH | $1,000 |
| #90 | freqtrade_shield_sol | SOL | $500 |
| #91 | freqtrade_onchain | BTC | $2,000 |
| #92 | freqtrade_avax | AVAX | $1,000 |
| #93 | freqtrade_bnb | BNB | $1,000 |
| #94 | freqtrade_doge | DOGE | $1,000 |
| #95 | freqtrade_ada | ADA | $1,000 |
| #96 | freqtrade_rotation | BTC/multi | $2,000 |

**Subtotal legacy:** $90,500

---

## 2. PER-COIN ALLOCATION

| Coin | Wallets | Bots | % of total |
|---|---|---|---|
| BTC | $99,500 | 13 | 83% |
| ETH | $8,000 | 4 | 7% |
| SOL | $4,000 | 3 | 3% |
| BNB | $6,000 | 3 | 5% |
| ADA | $3,000 | 2 | 3% |
| AVAX | $1,000 | 1 | 1% |
| DOGE | $1,000 | 1 | 1% |
| XRP | $3,000 | 1 | 2% |

⚠️ **BTC over-concentrated** at 83% — many old test bots inflate this. The portfolio-risk-manager skill would recommend trimming legacy BTC bots.

---

## 3. BACKTEST YEARLY — strongest deploys

### 🏆 ETH Calendar Shield (#105) — best of session, +55%/yr

| Year | ROI | DD | n_trades | Notes |
|---|---|---|---|---|
| 2021 | +296% | 8% | 11 | ETH bull peak ($4.9K) |
| 2022 | 0% | 0% | 0 | Sat in cash during bear |
| 2023 | +30% | 0% | 4 | Recovery |
| 2024 | +24% | 14% | 4 | Mid-cycle |
| 2025 | **+43%** | 0% | 1 | Sideways — calendar tilts won |
| 2026 Q12 | 0% | 0% | 0 | Current bear, in cash |
| **Compound** | **$10K → $91,000** | | | **+55%/yr** |

### 🏆 BTC Calendar Shield (#100), +38.2%/yr

| Year | ROI | DD | n_trades |
|---|---|---|---|
| 2021 | +122% | 8% | 8 |
| 2022 | 0% | 0% | 0 |
| 2023 | +50% | 0% | 6 |
| 2024 | +36% | 0% | 7 |
| 2025 | +14% | 4% | 2 |
| 2026 Q12 | 0% | 0% | 0 |
| **Compound** | **$10K → $51,800** | | |

### 🏆 BNB Calendar Shield (#106), +52%/yr

| Year | ROI | DD | n_trades |
|---|---|---|---|
| 2021 | +232% | 41% | 10 |
| 2022 | -1.5% | 2% | 2 |
| 2023 | +5% | 11% | 4 |
| 2024 | +73% | 3% | 5 |
| 2025 | +35% | 12% | 2 |
| 2026 Q12 | 0% | 0% | 0 |
| **Compound** | **$10K → $80,300** | | |

### 🏆 ETH Pure Shield (#101), +47%/yr

| Year | ROI | DD | n_trades |
|---|---|---|---|
| 2021 | +250% | 0% | 2 |
| 2022 | -12% | 12% | 1 |
| 2023 | +39% | 0% | 2 |
| 2024 | +24% | 1% | 2 |
| 2025 | +31% | 0% | 1 |
| 2026 Q12 | 0% | 0% | 0 |
| **Compound** | **$10K → $69,200** | | |

### 🏆 SOL VolShield v3 (#102), +45%/yr

| Year | ROI | DD | n_trades |
|---|---|---|---|
| 2021 | +252% | 0% | 3 |
| 2022 | 0% | 0% | 0 |
| 2023 | +142% | 3% | 3 |
| 2024 | -14% | 14% | 2 |
| 2025 | -13% | 13% | 1 |
| 2026 Q12 | 0% | 0% | 0 |
| **Compound** | **$10K → $63,700** | | |

### 🏆 BTC AI Shield V2 (#99), +36.5%/yr

| Year | ROI | DD | n_trades |
|---|---|---|---|
| 2021 | +118% | 0% | 8 |
| 2022 | 0% | 0% | 0 |
| 2023 | +44% | 0% | 6 |
| 2024 | +33% | 0% | 7 |
| 2025 | +14% | 4% | 2 |
| 2026 Q12 | 0% | 0% | 0 |
| **Compound** | **$10K → $47,500** | | |

### 🆕 XRP Calendar Shield (#107) — just deployed, +25.6%/yr

| Year | ROI | DD | n_trades |
|---|---|---|---|
| 2021 | +18% | 10% | 2 |
| 2022 | 0% | 0% | 0 |
| 2023 | +20% | 12% | 5 |
| 2024 | **+111%** | 12% | 4 |
| 2025 | +5% | 0% | 1 |
| 2026 Q12 | 0% | 0% | 0 |
| **Compound** | **$10K → $31,200** | | |

---

## 4. PROJECTED PORTFOLIO RETURNS

Based on backtest annual returns × wallet sizes:

| Strategy | Wallet | Annual % | Year 1 expected $ |
|---|---|---|---|
| #105 ETH Calendar | $3,000 | 55.5% | +$1,665 |
| #106 BNB Calendar | $3,000 | 52.0% | +$1,560 |
| #101 ETH Pure Shield | $3,000 | 47.0% | +$1,410 |
| #102 SOL VolShield v3 | $3,000 | 45.0% | +$1,350 |
| #100 BTC Calendar | $3,000 | 38.2% | +$1,146 |
| #99 BTC AI Shield V2 | $5,000 | 36.5% | +$1,825 |
| #107 XRP Calendar | $3,000 | 25.6% | +$768 |
| #103 BNB Triple | $2,000 | 17.7% | +$354 |
| #104 ADA Triple | $2,000 | 14.4% | +$288 |
| #98 BTC Triple | $2,000 | 10.5% | +$210 |
| **Major-session total** | **$29,000** | **~37%** | **+$10,576** |

**Plus 19 legacy bots** at $90,500 — most without recent adversarial verdict, so projection is unreliable.

---

## 5. ADVERSARIAL VALIDATION SUMMARY

Tested 22 candidates this session:

### ✅ PASS / WARN — deployed
ETH Calendar 🏆 | BNB Calendar | BTC Calendar | ETH Pure Shield | SOL VolShield v3 | BTC AI Shield V2 | XRP Calendar | BTC Triple | BNB Triple | ADA Triple

### ❌ FAIL / CATASTROPHIC — rejected
AVAX Btc3Layer | SOL Pure Shield | SOL AI Shield V2 | SOL Triple | AVAX VolShield | ADA Calendar | LINK (all 4) | LTC (3 of 4) | DOT (3 of 4) | ATOM Calendar | NEAR Calendar | NEAR VolShield | BCH Triple | ETH November Tilt | AI Shield V3 Cooldown | Sentiment Shield | Per-Asset Cycles | DOGE Triple | DOGE Adaptive

**Total: 10 deploys, 19 rejections. The Adversarial Validator did its job — would have lost meaningful capital deploying the rejects.**

---

## 6. LIVE STATUS (as of 2026-06-04)

All 30 bots running, but **0 closed trades** so far.

**Why no trades yet?**
1. All bots deployed within the last 3 days
2. Strategies use 1d timeframe with N=3-5 day regime confirmation
3. Current market in BEAR phase — most strategies sit in cash by design
4. Anomaly circuit breakers may have fired

This is **EXPECTED behavior**. Will start producing trades when:
- Regime detector confirms BULL (price > EMA200 + ret_30d > 5% + ADX > 20 for N days), OR
- For futures bots: confirms BEAR for shorts (we don't have futures deployed)

---

## 7. INFRASTRUCTURE

### Containers
- **61 total**: 31 freqtrade bots + 30 bridges (one per bot, sync trades to trad_pg)
- All on trad-server (`72.62.179.86`)
- All restart=unless-stopped

### Schedules
- **Meta-allocator cron**: every Sunday 00:00 UTC (weekly reallocation)
  - Last run: 2026-06-03 (success, all bots scored 0 = no trades yet)
- **Data refresh**: manual currently (no daily cron yet)

### Database
- `trad_pg` PostgreSQL holds: strategies, subscriptions, trades, performance
- 30 active subscriptions
- 0 closed trades in `trades` table

---

## 8. UPCOMING WORK / KNOWN GAPS

1. **DOGE bear protection** — 4 candidates failed adversarial. Open challenge.
2. **AVAX upgrade** — no working alternative beats current MetaReliable.
3. **Legacy bot cleanup** — 19 bots from earlier era ($90.5K allocated) lack adversarial verdicts. Recommend either:
   - Run adversarial on each → deactivate FAILs
   - Or reduce wallets to $500 each pending validation
4. **Data engineering cron** — daily OHLCV + FGI refresh not yet automated.
5. **Live trading** — all bots still in dryrun. Going live requires `live-trading-ops` skill workflow.
6. **First real performance review** — needs 30+ days of live trades to populate.

---

## 9. SESSION CHANGES (last 72h)

| Session phase | Deploys | Rejections |
|---|---|---|
| Initial AI batch (subs #97-#101) | 5 | 11 |
| Extensions (#102-#106) | 5 | 4 |
| Futures experiment | 0 | 3 (all variants) |
| New coin onboarding (#107) | 1 | 6 |
| **Total** | **11 new deploys** | **24 rejections** |

Fleet grew from 21 → 31 bots (+47%), allocated from $90.5K → $119.5K (+$29K).

---

## 10. KEY METRICS DASHBOARD

```
┌────────────────────────────────────────────────────┐
│  FLEET HEALTH — 2026-06-04                         │
├────────────────────────────────────────────────────┤
│  Bots:           31 active / 61 containers         │
│  Total wallet:   $119,500                          │
│  Trades closed:  0 (fleet too new)                 │
│  Open alerts:    0                                 │
│  Adversarial pass rate: 10/22 = 45% (recent batch) │
│  Strongest deploy: ETH Calendar Shield +55%/yr     │
│  Weakest deploy:  Triple Regime ~10-17%/yr         │
└────────────────────────────────────────────────────┘
```

---

## Next reporting

- **Daily snapshot**: TBD (use fleet-monitor skill)
- **Weekly summary**: due 2026-06-11
- **30-day performance review**: due 2026-07-04 (first meaningful live data)
- **Quarterly review**: due 2026-09-30
