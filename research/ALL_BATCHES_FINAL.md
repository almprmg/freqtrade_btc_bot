# All Batches — Final Report

**Session:** AI Integration master batch run
**Date:** 2026-06-02 → 2026-06-03
**Ideas tested:** 11 of 18 + 1 emergent (K)
**Deployments:** 4 new bots (subs #98, #99, #100, #101)
**Net fleet change:** +4 bots, +8 containers (now 25 bots / 49 containers)

---

## Scoreboard

| | Idea | Outcome | Live? |
|---|---|---|---|
| ✅ | A — Pair combo correlation | data extracted, no deploy | — |
| ✅ | B — Adversarial Validator | tool built, gates every deploy | gate |
| ✅ | **C — Per-asset audit** | exposed missing coverage; surfaced Idea K | research |
| ✅ | **D — Sigmoid Sizing (AI Shield V2)** | **+10pp/yr over V1** | **#98** 🏆 |
| ✅ | E — Anomaly Cooldown | hypothesis wrong for BTC bull | — |
| ✅ | F — Per-asset Cycles | generic detector beaten by per-coin winners | — |
| ✅ | **G — Triple Regime (defensive)** | passed adversarial; sub deployed as defensive sleeve | **#99** 🏆 |
| ✅ | **J — Calendar Effects** | **+1.7pp/yr over V2** | **#100** 🏆 |
| ✅ | **K — ETH Shield port (emergent)** | **+26pp/yr over DynRebal** | **#101** 🏆 |
| ✅ | H — Sentiment via FGI | real signal but redundant with cycle phase | — |
| ✅ | I — RL Meta-Allocator | gap < 5pp/yr — heuristic meta-allocator scheduled instead | cron weekly |

Skipped (not run): C variants for ETH/SOL custom cycle design, SOL volatility-aware shield, BNB/DOGE A/B (current winners by archive).

---

## Honest failures (rejected deployments)

| Candidate | Why rejected |
|---|---|
| Cooldown V3 | Hypothesis was wrong — BTC bull rallies don't dead-cat after anomalies |
| Per-asset cycles | Generic detector underperformed each coin's existing winner |
| AVAX 3Layer | Archive showed Sharpe 0.79 but Adversarial CATASTROPHIC (-63% in 2022) — pure overfit |
| SOL Pure Shield | -43% in 2025 sideways — Pure Shield indicators get chopped by SOL volatility |
| SOL AI Shield V2 | -35% in 2025 sideways — same overfit pattern, BTC halving phases don't transfer |
| SOL Triple Regime | passes adversarial but yields only 3.6%/yr (vs DynRebal 40%/yr) — too defensive |
| Sentiment Shield | beats nothing — FGI signal duplicates cycle_phase information |

Adversarial Validator caught 4 of 7 of these. Honest reporting >> deploying overfit candidates.

---

## Deployments — economic impact

Assuming each new bot achieves its 5y backtest annual return on its $3K wallet:

| Bot | 5y backtest annual | $3K wallet 5y projection |
|---|---|---|
| #98 AI Shield V2 (sub-100) | +36.5%/yr | $14,200 |
| #99 Triple Regime | +10.5%/yr | $4,900 |
| #100 Calendar Shield | +38.2%/yr | $15,300 |
| #101 ETH Shield | +47%/yr | $20,700 |
| **Total new exposure** | | **~$55K projected from $12K** |

Caveat: backtests aren't promises. Actual live results may diverge.

---

## Tooling delivered

1. **experiment_logger** — every backtest auto-archives trades, orders, metadata, payload.
2. **adversarial_validator** — 3-window bear/sideways gate; verdicts PASS/WARN/FAIL/CATASTROPHIC.
3. **calendar_analyzer** — finds DOW/DOM/Month/halving-phase patterns with Bonferroni correction.
4. **per_asset_audit** — scans 1,266 historical backtests, ranks by robustness.
5. **backfill_per_coin** — yearly backtest sweep for any (strategy, coin) combo via experiment_logger.
6. **sentiment_test** — Fear&Greed Index feasibility tester (output: +13.5% corr with 30d fwd ret).
7. **portfolio_simulator** — yearly-ROI matrix → multiple allocation comparisons + RL upside ceiling.
8. **meta_allocator** — heuristic scoring (sharpe * sqrt(win_rate) * (1-DD)), now scheduled weekly cron on server.

---

## Open follow-ups

- **SOL bear protection**: needs volatility-aware regime detector (not Pure Shield, not Triple Regime). Active investigation deferred.
- **Meta-allocator activation**: scheduled cron will produce its first meaningful reallocation after ~30 days of live trade data accumulates in trad_pg.
- **Idea backlog**: H proper (FinBERT) skipped because FGI test shows sentiment signal already captured by cycle_phase. Could revisit if intraday sentiment shows different behavior than daily.

---

## Methodology takeaways (for future batches)

1. **Always run Adversarial before deploying.** It caught AVAX 3Layer overfit, SOL variants, others.
2. **Archive everything.** experiment_logger + INDEX.csv made the per-asset audit possible.
3. **Test cheap signals first.** FGI (free, daily, historical) before FinBERT (download + pipeline + scraping).
4. **Honest failure > silent overfit.** 7 rejected candidates documented openly.
5. **Heuristic before ML.** Portfolio simulator showed top-3-trailing-Sharpe captures most realistic gains.
