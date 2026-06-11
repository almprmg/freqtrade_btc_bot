# LOSS: Sentiment Shield — real signal, redundant value

**Date tested:** 2026-06-03
**Outcome:** Rejected, NOT deployed
**Why this case matters:** Tests for SIGNAL REDUNDANCY before deploying.

## Hypothesis

> "Adding FGI sentiment tilt to Calendar Shield should improve compound because FGI shows +13.5% correlation with 30d fwd returns (n=2340)."

The FGI signal IS real. We verified with sentiment_test.py:
- X-GREED (FGI≥75): 30d fwd mean +12.0% (baseline +3.6%)
- X-FEAR (FGI≤25): 30d fwd mean +2.7% (baseline +5.2%)

Counter-intuitive finding: sentiment is MOMENTUM in crypto, not contrarian.

## What we did right

Tested cheap signal (FGI) before building FinBERT pipeline. Smart. Saved 1-2 days of news scraping work.

## What we did wrong

Didn't pre-mortem the question: "Is FGI redundant with existing features?"

It IS redundant. Halving phase = PARABOLIC implies market is euphoric implies FGI is high. The two signals largely overlap.

## Backtest comparison

Identical setup, ONE extra feature (FGI tilt):

| Year | Calendar Shield | Sentiment Shield |
|---|---|---|
| 2021 | +121.6% | +118.3% |
| 2022 | 0% | 0% |
| 2023 | +50.4% | +52.7% |
| 2024 | +36.4% | +36.6% |
| 2025 | +13.9% | +11.9% |
| 2026 Q12 | 0% | 0% |
| **Compound** | $51,779 | $50,953 |
| **Annual** | 38.9%/yr | 38.5%/yr |
| **Adversarial** | PASS | PASS |

Diff: **-$826 over 5y**. The sentiment tilt adds NOTHING positive and slightly subtracts.

## Why "PASS adversarial but don't deploy"

The strategy is fine on its own — it passes the gate. But it's WORSE than Calendar Shield (the alternative on the same coin). Deploying it would mean choosing the inferior of two strategies.

## Lessons

1. **Test for redundancy BEFORE complexity.** A new feature must add INDEPENDENT information.
2. **PASS adversarial isn't sufficient — must also beat the alternative.** "Different but worse" is still worse.
3. **FinBERT would be MORE redundant.** FGI is already smoothed sentiment. Per-headline FinBERT inference produces noisier sentiment than FGI. If FGI is redundant with cycle_phase, FinBERT is MORE redundant.

## Saved: 1-2 days

By testing FGI first (cheap), we know FinBERT won't help (expensive). The free upper-bound test is invaluable.

## Pattern for future sessions

When evaluating a new feature, ask:
1. Does it work in isolation? (Run alone)
2. Does it add value on top of existing? (Compare A vs A+feature)
3. Does it RESIST removal? (Remove from working model — does performance drop?)

Sentiment Shield failed #2. The Calendar+Cycle Shield was already capturing what sentiment provides.
