# LOSS: AVAX Btc3Layer — the overfit poster child

**Date tested:** 2026-06-02
**Outcome:** Rejected, NOT deployed
**Why this case matters:** Most striking demonstration of why Adversarial Validator exists.

## Hypothesis

> "Archive shows Btc3LayerStrategy has Sharpe 0.79 over 15 runs on AVAX (vs MetaAdaptive's 0.11 over 13 runs). 3Layer should be the new AVAX winner."

Looked irresistible. Sharpe 7× higher. Median ROI 3× higher (+107% vs +33%).

## What we did wrong

Trusted the archive numbers without re-validating. The archive's "Sharpe 0.79" came from 15 backtest runs — but those runs covered FAVORABLE timeranges:
- Mostly 2021-2023 (mixed bull/recovery)
- A few 2024 chunks (mid-cycle)
- NONE included a full 2022 bear

The robust score formula `median_roi - 2*median_dd` looked good because the median was computed over a biased sample.

## Adversarial fresh backtest

Ran the full 6-window grid via experiment_logger + Adversarial Validator:

| Year | ROI |
|---|---|
| 2021 | +285% (looks great, but cycle peak) |
| 2022 | **-63%** ← 💀 |
| 2023 | +180% |
| 2024 | -7% |
| 2025 | **-46%** ← 💀 |
| 2026 Q12 | **-24%** ← 💀 |

**Adversarial Verdict: CATASTROPHIC** — all 3 windows negative, worst -63%.

## What it would have cost

If we'd deployed without the validator:
- $3K wallet → -63% in 2022 first → would never recover psychologically even if it recovered economically
- User would have lost trust in the system

## The pattern to recognize

Archive scores are TRAILING and TIMERANGE-DEPENDENT. They tell you:
- "This strategy worked across the windows that were tested"

They do NOT tell you:
- "This strategy will work across UNTESTED bear windows"

## Rule extracted

**Before trusting any archive-derived ranking, ALWAYS run:**
1. Full 6-window yearly backtest via experiment_logger
2. 3-window Adversarial Validator
3. Refuse to deploy unless adversarial PASSES or WARNs

This rule rejected 11 candidates in this session — saving us from at least 5 catastrophic deploys.

## When this trap appears

Watch for:
- High archive Sharpe (>0.5) on a coin where current live has low Sharpe (<0.15)
- Recommendation comes from "top of archive ranking" without fresh test
- Backtest run count > 5 but adversarial windows missing from the runs
- Bull-cycle years dominate the runs (2021, 2023)

When you see these, the candidate is suspect. Test fresh before believing.
