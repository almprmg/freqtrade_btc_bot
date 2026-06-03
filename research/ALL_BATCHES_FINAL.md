# All Batches — Final Report (extended)

**Session:** AI Integration master batch run
**Final fleet:** 29 bots / 57 containers
**Date:** 2026-06-02 → 2026-06-03

---

## Final Scoreboard — 11 ideas + 4 extensions

| | Idea | Outcome | Deployed |
|---|---|---|---|
| ✅ | A — Pair combo | data only | — |
| ✅ | B — Adversarial Validator | tool built | gate |
| ✅ | C — Per-asset audit | exposed gaps + Idea K | research |
| ✅ | **D — Sigmoid V2** | +10pp/yr | **#98** 🏆 |
| ✅ | E — Cooldown | ❌ wrong hypothesis | — |
| ✅ | F — Per-asset cycles | ❌ underperformed | — |
| ✅ | **G — Triple Regime BTC** | defensive | **#99** 🏆 |
| ✅ | **J — Calendar Effects** | +1.7pp/yr | **#100** 🏆 |
| ✅ | **K — ETH Pure Shield** | +26pp/yr | **#101** 🏆 |
| ✅ | H — Sentiment FGI | real but redundant | — |
| ✅ | I — RL Allocator | gap 4pp, heuristic cron | cron weekly |
| ✅ | **L — SOL VolShield v3** | +5pp/yr + bear save | **#102** 🏆 |
| ✅ | **M — BNB Triple defensive** | WARN, capital preserve | **#103** 🏆 |
| ✅ | **N — ADA Triple defensive** | PASS, capital preserve | **#104** 🏆 |
| ✅ | **O — ETH Calendar Shield** | +8pp over Shield #101 | **#105** 🏆 |

**8 new deployments** | **7 honest rejections** | **2 research tools**

---

## Deployments — economic projections (5y from $3-5K wallets each)

| Sub | Bot | Coin | Backtest | Wallet | 5y projection |
|---|---|---|---|---|---|
| #98 | AI Shield V2 | BTC | +36.5%/yr | $5K | $23,700 |
| #99 | Triple Regime | BTC | +10.5%/yr | $2K | $3,300 |
| #100 | Calendar Shield | BTC | +38.2%/yr | $3K | $15,300 |
| #101 | ETH Pure Shield | ETH | +47%/yr | $3K | $20,700 |
| #102 | SOL VolShield v3 | SOL | +45%/yr | $3K | $19,500 |
| #103 | BNB Triple | BNB | +17.7%/yr | $2K | $4,600 |
| #104 | ADA Triple | ADA | +14.4%/yr | $2K | $3,900 |
| #105 | ETH Calendar Shield | ETH | +55%/yr | $3K | $23,800 |
| **Total** | 8 new bots | mixed | weighted ~37%/yr | **$23K** | **~$115K** |

Caveat: backtest projections aren't promises.

---

## SOL deep-dive — 4 attempts, 1 winner

| Attempt | Strategy | Adversarial | Compound | Verdict |
|---|---|---|---|---|
| 1 | Pure Shield | CATASTROPHIC -43% | — | rejected |
| 2 | AI Shield V2 | CATASTROPHIC -35% | — | rejected |
| 3 | Triple Regime | PASS but +3.6%/yr | 0.196x | too defensive |
| 4 | **VolShield v3** | **WARN** | 6.37x **(+45%/yr)** | **deployed** |

The fix: chop-aware filters (ret_30d AND ret_60d, EMA50>EMA200, ATR_pct<10%, 5-day confirmation).

---

## ETH — three layers in production

| Sub | Strategy | Compound | Sharpe |
|---|---|---|---|
| existing | DynRebal (HODL) | $26.6K (5y from $10K) | low |
| #101 | Pure Shield | $69.2K | 0.47 in 2023 |
| #105 | Calendar Shield | **$91.3K** 🏆 | 0.52+ |

ETH Calendar (+55%/yr) is the strongest single deployment of this session.

---

## Honest rejections (no deploy despite testing)

| Candidate | Reason |
|---|---|
| AI Shield V3 Cooldown | Hypothesis wrong — BTC bulls don't dead-cat after anomalies |
| Per-asset Cycles | Generic detector beaten by per-coin existing winners |
| AVAX 3Layer | Archive Sharpe 0.79 was cherry-picked; -63% in 2022 bear |
| SOL Pure Shield | -43% in 2025 sideways |
| SOL AI Shield V2 | -35% in 2025 — BTC halving doesn't transfer to SOL |
| SOL Triple Regime | PASS but only 3.6%/yr |
| Sentiment Shield | Real FGI signal but redundant with cycle_phase |
| BNB Rotation | Marginally worse than current BNB RegimeShield |
| DOGE Adaptive | Worse than current DOGE RegimeShield |
| ADA AI Shield V2 | -44% in 2025 sideways (CATASTROPHIC) |
| DOGE Triple | -16% in 2025 sideways (FAIL) |

11 rejections vs 8 deploys. **The Adversarial Validator did its job.**

---

## Tools delivered

1. `research/ai/experiment_logger.py` — every backtest auto-archives
2. `research/ai/adversarial_validator.py` — 3-window PASS/WARN/FAIL/CATASTROPHIC gate
3. `research/ai/calendar_analyzer.py` — DOW/DOM/Month with Bonferroni
4. `research/ai/per_asset_audit.py` — scans 1266+ archives
5. `research/ai/backfill_per_coin.py` — yearly+adversarial via experiment_logger
6. `research/ai/sentiment_test.py` — FGI feasibility tester
7. `research/ai/portfolio_simulator.py` — allocator comparison
8. `research/ai/meta_allocator.py` + `scripts/run_meta_allocator.sh` — weekly cron live on trad-server

---

## Per-coin live deployment map (final)

| Coin | Active strategies | Wallets |
|---|---|---|
| BTC | AI Shield V2 (#98) + Triple (#99) + Calendar Shield (#100) | $10K total |
| ETH | DynRebal (existing) + Pure Shield (#101) + **Calendar Shield (#105)** | $6K new |
| SOL | DynRebal (existing) + **VolShield v3 (#102)** | $3K new |
| BNB | Pure Shield (existing) + Triple (#103) | $2K new |
| ADA | MetaAdaptive (existing) + Triple (#104) | $2K new |
| DOGE | Pure Shield (existing) | — |
| AVAX | MetaAdaptive (existing) | — |

DOGE and AVAX got no new bots — every alternative tested failed adversarial.

---

## Open follow-ups

- DOGE bear protection design (RegimeShield CATASTROPHIC, Adaptive worse, Triple FAIL)
- meta_allocator runs in dry-run mode — first apply once 30+ days of live data accumulates
- Compare live results vs backtest in 30/60/90 day reviews

---

## Methodology takeaways

1. **Always run Adversarial before deploying.** Caught 11 overfit candidates this session.
2. **Honest failure > silent overfit.** Documented every rejection with reasoning.
3. **Archive everything.** experiment_logger + INDEX.csv made audits possible.
4. **Test cheap signals first.** FGI before FinBERT.
5. **Heuristics before ML.** Top-3 Sharpe captures most realistic gains.
6. **Defensive sleeves are valid deployments.** Even if a strategy is "only" PASS/WARN with modest returns, capital preservation has portfolio value.
7. **Volatility-aware design matters.** SOL needed custom filters; BTC indicators don't transfer to SOL.
