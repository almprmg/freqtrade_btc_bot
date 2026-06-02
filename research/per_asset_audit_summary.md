# Per-Asset Audit — Findings (Idea C)

## TL;DR

Scanned 1,266 backtest records (1,210 from freqtrade native results + 56 from experiment logger).

**Coverage limitation (honest):** coin-specific shield variants (`EthRegimeShield`,
`SolRegimeShield`, `BnbShieldSlow`, `DogeShieldDefensive`, `AvaxMetaReliable`,
`AdaMetaBalanced`) are deployed in production but were each tested in dedicated
single runs that didn't go through `experiment_logger`. They're absent from the
archive, so we **cannot compare them against the BTC-prefix strategies that show up here**.

The audit is meaningful only for cases where the archive has ≥5 runs *and* the
current live strategy appears in the table.

---

## Per-coin findings

### BTC ✅ aligned
| Strategy | Runs | Med ROI | Worst ROI | Med DD | Sharpe |
|---|---|---|---|---|---|
| Btc3Layer | 35 | +65% | **-49%** | 17% | 0.09 |
| BtcRegimeShield | 16 | +53% | +28% | 11% | 0.12 |
| BtcAiShield (v1) | 8 | +68% | +33% | 12% | 0.30 |
| **BtcCalendarShield (NEW)** | 6 | **+50%** | **+36%** | 13% | **0.47** 🏆 |
| BtcAiShieldV3 | 12 | +31% | +11% | 18% | 0.21 |

**Verdict:** Calendar Shield has the highest Sharpe AND the best worst-case in
the data — keep it. V2 stays as fallback. **No change.**

---

### AVAX ⚠️ potential upgrade
| Strategy | Runs | Med ROI | Worst ROI | Med DD | Sharpe |
|---|---|---|---|---|---|
| **Btc3LayerStrategy** | 15 | **+107%** | -47% | 14% | **0.79** ⭐ |
| BtcMetaAdaptive | 13 | +33% | -19% | 7% | 0.11 |
| MultiCycleShield | 3 | +62% | -35% | 33% | 0.11 |

`AvaxMetaReliableStrategy` (live) not in archive — can't compare directly.
But `Btc3LayerStrategy` shows **0.79 Sharpe over 15 runs** on AVAX, which is
exceptional. Worth A/B test on AVAX pair.

---

### DOGE ⚠️ small-sample candidate
| Strategy | Runs | Med ROI | Worst ROI | Med DD | Sharpe |
|---|---|---|---|---|---|
| BtcRegimeShield | 14 | +96% | -25% | 27% | 0.09 |
| Btc3Layer | 22 | +27% | -46% | 24% | 0.08 |
| **BtcAdaptive** | 4 | **+56%** | **+46%** | **0%** ⭐ | 0.14 |

`BtcAdaptive` shows ZERO median drawdown across 4 runs, all positive. But n=4
is small — needs more validation before betting on it. `DogeShieldDefensive`
(live) absent from archive.

---

### ETH / SOL / BNB / ADA — inconclusive
Coin-native strategies (`EthRegimeShield` etc.) absent from archive. The
"BTC-prefix strategies running on these pairs" rows in the table tell us
nothing about whether the current Pure-Shield / Meta-Balanced / Slow-Shield
live deployments are right or wrong.

To produce a real verdict for these, we'd need to backtest each coin's
dedicated strategy via experiment_logger across the same 5y window.

---

## Recommended actions

1. **AVAX A/B test** — clone `Btc3LayerStrategy` for `AVAX/USDT`, run 5y
   backtest via experiment_logger, run Adversarial Validator. If passes,
   deploy as `freqtrade_avax_3layer` alongside the current Meta_REL bot.

2. **DOGE careful test** — same with `BtcAdaptiveStrategy` on DOGE/USDT.
   Small sample, so weight worst-case heavily.

3. **Coverage backfill** — re-run all 7 coin-native shield variants through
   `experiment_logger` over 2021-2026 so future audits have complete data.
   ~14 backtests, ~30 min total.

4. **No changes for BTC** — Calendar Shield (just deployed) is the best
   risk-adjusted option in the archive.

5. **No data, no action** for ETH/SOL/BNB/ADA — proposing changes without
   evidence would just be guessing.
