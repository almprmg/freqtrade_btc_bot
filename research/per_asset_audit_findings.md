# Per-Asset Audit — Final Findings (Idea C complete)

## Phase 1: Archive scan
Identified candidates for upgrade by mining 1,266 historical backtest records.

## Phase 2: Backfill via experiment_logger
Ran candidates through the full 5-year + adversarial windows.

### AVAX 3Layer A/B test
Hypothesis from archive: `Btc3LayerStrategy` showed 0.79 Sharpe and +107% median ROI on AVAX. Worth trying as upgrade vs `BtcMetaAdaptiveStrategy` (live).

Reality from fresh backfill:

| Window | ROI | Verdict |
|---|---|---|
| 2021 | +285% | ✅ |
| **2022** | **-63%** | 🔴 catastrophic |
| 2023 | +180% | ✅ |
| 2024 | -7% | ⚠️ |
| **2025** | **-46%** | 🔴 |
| **2026 Q12** | **-24%** | 🔴 |

**Adversarial Verdict: CATASTROPHIC — fail on all 3 bear/sideways windows.**

Archive scores were biased — early backtests covered favorable timeranges.
3Layer's archive Sharpe of 0.79 was the average across cycle-favorable windows
only. **DO NOT DEPLOY.** AVAX stays on MetaAdaptive.

### ETH/SOL DynRebal coverage backfill (honest documentation)
Both deployed live; both essentially HODL with 1 trade/year per backtest.

| Year | ETH DynRebal | SOL DynRebal |
|---|---|---|
| 2021 | +271% | +637% |
| **2022** | **-55%** | **-87%** 💀 |
| 2023 | +65% | +509% |
| 2024 | +32% | +58% |
| **2025** | **-3%** | **-22%** |
| **2026 Q12** | **-25%** | **-26%** |

Both fail Adversarial Validator. **They're effectively HODL — bull market
gains compound through, but a single bad year could be devastating to a fresh
deployment.** No protection from bear regimes (unlike BTC's shield variants).

## Final actions taken
1. ✅ No deployments — all candidates failed Adversarial
2. ✅ Archive now has ETH/SOL DynRebal coverage (was missing)
3. ✅ Confirmed: BTC Calendar Shield, BNB RegimeShield, DOGE RegimeShield, AVAX
   MetaAdaptive, ADA MetaAdaptive are best-available for their coins given
   adversarial-validation discipline.

## Future work surfaced
- **ETH and SOL need a shield layer** before next bear. Currently they're
  HODL-with-rebalance. Either:
  - port BtcRegimeShieldStrategy to ETH/SOL configs (Sh-based exit during BEAR), or
  - design coin-specific cycle / regime detectors.
- Track this as Idea K candidate for future batch.
