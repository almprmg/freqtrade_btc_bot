# Overfit Signs Checklist

Concrete red flags to look for when reviewing any candidate. Each item below was observed at least once during the major session and led to a rejection.

## Red Flag 1: Archive cherry-picks

**Pattern:** Archive shows high Sharpe / high ROI from N runs, but all runs cover bull-favored timeranges (2021, 2023).

**How to detect:**
- Look at INDEX.csv runs for the strategy
- Check what `timerange` values are present
- If `2022-` or `bear` timeranges are absent → suspect

**Real case:** AVAX Btc3Layer. Archive Sharpe 0.79 over 15 runs. ALL runs covered 2021-2024 favorable periods. Fresh 2022 backtest: -63%. Rejected CATASTROPHIC.

**Mitigation:** ALWAYS run fresh 6-window backtest + 3-window adversarial before trusting archive.

## Red Flag 2: Suspiciously-tuned thresholds

**Pattern:** Parameters have weirdly specific values like `0.0537` or `27.3` or `0.117`.

**How to detect:**
- Read the strategy file
- Look for thresholds that aren't "round numbers" (5%, 10%, 0.15, etc.)

**Why it's a red flag:** Round numbers come from hypotheses ("require 5% momentum"). Specific numbers come from optimizer overfit ("require 5.37% because that's what worked in training").

**Mitigation:** Demand justification for any non-round threshold. If "I just tried different values until it worked" → reject.

## Red Flag 3: Feature stack > 4

**Pattern:** Strategy has many added features on top of base archetype.

**Example bad design:**
```python
bull = (
    pure_shield_conditions
    & calendar_filter
    & sentiment_filter
    & onchain_signal
    & volume_acceleration
    & social_momentum
    & macd_confirm
)
```

**Why bad:** Each feature has overfit probability ε. 7 features = 7×ε ≈ high overfit risk.

**Mitigation:** Hypothesis must justify EACH added feature. If more than 4 features are "new" (beyond Pure Shield base), break into separate strategies and A/B them.

## Red Flag 4: Single-trade results

**Pattern:** A year shows huge ROI but with only 1-2 trades.

**Example:** SOL DynRebal 2021 → +637% with 1 trade. 2023 → +509% with 1 trade.

**Why suspicious:** Single trades = HODL + exit timing luck. The strategy did very little; the market did the work.

**Mitigation:** Inspect trades.csv. If "strategy" is essentially HODL with timing, decide if that's acceptable for the deployment goal.

## Red Flag 5: Win rate vs profit-factor mismatch

**Pattern:** Win rate 80% but profit factor ~1.0 (every loss equals all wins combined).

**Why suspicious:** Strategy wins often but loses big. Hides tail risk in mean stats.

**Mitigation:** Check max drawdown explicitly. If win rate is high AND max DD is high → tail risk is being hidden.

## Red Flag 6: No bear data in coin's history

**Pattern:** Coin's data only goes back to last bull (e.g. new memecoin).

**Why bad:** Adversarial can't test bear behavior because there IS no historical bear.

**Mitigation:**
- For coins with < 2 years of data: REFUSE deployment, period.
- For coins with < 4 years (no full cycle): require stress-test against simulated -50% scenario.

## Red Flag 7: Hypothesis can't articulate failure

**Pattern:** "X improves Y because... it's better."

**Why bad:** No mechanism = no understanding = blind hope.

**Mitigation:** Demand "If this fails, the failure will look like: ___" before approving.

## Red Flag 8: Backtest period matches strategy's "good era"

**Pattern:** Strategy designer says "I designed this for the post-halving rally period" and the backtest covers exactly that period.

**Why bad:** Selection bias built in.

**Mitigation:** Demand 6-window evaluation. Strategy must perform reasonably across BOTH its designed-for period AND other periods.

## Red Flag 9: Win rate degrades with more data

**Pattern:** First-year backtest = 80% win rate. 5-year backtest = 55%.

**Why bad:** The "wins" were concentrated in one regime. Adding more data dilutes them.

**Mitigation:** Always compare 1y vs 5y stats. If win rate drops > 15pp → overfit signal.

## Red Flag 10: Sharpe relies on small denominator

**Pattern:** Sharpe = 2.0 but it's mean(returns) / std(returns) with only 3 returns.

**Why bad:** Statistical artifact. Real Sharpe needs ≥ 30 samples.

**Mitigation:** Disregard Sharpe when n_trades < 10. Use compound + max DD instead.

## Red Flag 11: "Just one more parameter" fixing

**Pattern:** Original strategy fails on year Y. Designer adds `if year >= Y: special_rule` to fix.

**Why bad:** Doesn't fix the root cause. Will fail on year Y+1.

**Mitigation:** Demand fix at the FILTER/REGIME logic level, not via year-specific conditionals. If the fix is "year-aware," reject.

## Red Flag 12: New feature with no ablation

**Pattern:** Strategy adds feature F. Tester runs WITH F (passes) but never runs WITHOUT F.

**Why bad:** We don't know if F actually helped or hurt.

**Mitigation:** Demand A/B comparison. Same strategy WITH and WITHOUT feature F. Decide if F's marginal contribution justifies its complexity.

## Red Flag 13: Comparison vs HODL not shown

**Pattern:** Strategy compares only to other strategies, never to HODL.

**Why bad:** Many strategies make < HODL net of fees. Hidden in peer comparison.

**Mitigation:** Always include `holdfair` baseline in adversarial validation. Strategy must beat HODL net of all fees over the full backtest.

## Red Flag 14: Code smell — extreme constants

**Pattern:** `stoploss = -0.99`, `minimal_roi = {"0": 10.0}`, etc.

**Why suspicious-LOOKING but actually OK:** Our strategies use these because we exit via regime signals, not SL/ROI. Verify the EXIT logic actually fires.

**Mitigation:** Read populate_exit_trend carefully. Confirm exit conditions trigger in backtests (look at trades.csv for exit_tag).

## Red Flag 15: Pre-mortem skipped

**Pattern:** Strategy proposed without any pre-mortem.

**Mitigation:** Demand 60-second pre-mortem: "How will this fail?"

Common honest pre-mortems:
- "Could fail if signal is redundant with cycle_phase" (Sentiment Shield prediction — correct)
- "Could fail if archive results came from cycle-favorable windows" (AVAX 3Layer — correct)
- "Could fail if BTC indicators don't transfer to SOL's higher vol" (SOL Pure Shield — correct)

When pre-mortem PROVES correct, you saved a deploy. When it proves wrong, you learn something new.

## How to use this checklist

For every candidate review:
1. Print the strategy file
2. Walk through items 1-15 above
3. Flag each present red flag
4. If ≥ 2 red flags → demand answer/fix before approving
5. If ≥ 4 red flags → VETO

Most "false alarms" turn out to be real issues on closer inspection. Trust the checklist.
