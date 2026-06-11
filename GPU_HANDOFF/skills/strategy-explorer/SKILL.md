---
name: strategy-explorer
description: Hypothesis generator. Combines market expertise with research findings to propose NEW strategy ideas worth testing. Generates ranked hypotheses with pre-mortems, expected impact, and concrete test plans. Use when user asks "give me new ideas", "what should we try next", "propose strategies", "what experiments are worth running", "I want to expand the bot fleet". Generates the IDEA — does not build or validate. Hand off to bot-builder and strategy-critic.
---

# Strategy Explorer — Hypothesis Generator

The idea factory. Combines `strategy-architect`'s market knowledge with `strategy-researcher`'s data findings to propose specific, testable hypotheses.

For DESIGN context, use `strategy-architect`.
For DATA mining, use `strategy-researcher`.
For BUILDING, use `bot-builder`.
For VALIDATION, use `strategy-critic`.

## When to invoke

- "What should we try next?"
- "Give me new ideas"
- "Propose strategies to expand the fleet"
- "What experiments are worth running?"
- "Anything else we could improve?"
- "Help me brainstorm"

## Output format (always)

Every invocation produces a RANKED LIST of hypotheses, each formatted:

```markdown
## H<N>: <1-sentence hypothesis>

**Type:** transfer / fix / new-archetype / new-feature / capital-allocation

**Source of idea:**
- (data point from researcher) or
- (gap in architect knowledge) or
- (failure mode analysis from critic)

**Pre-mortem:** "Would fail if..."

**Test plan:**
1. <specific steps using bot-builder template X>
2. <backtest 6-window>
3. <adversarial gate>
4. <deploy if PASS/WARN>

**Cost:** ~45 min (build + backtest + adversarial)

**Expected outcome:**
- Win case: +<N> pp/yr over current best
- Lose case: documented in examples/loss_*.md
- Risk: <specific overfit risk>

**Confidence:** low / medium / high
```

## Hypothesis sources (where ideas come from)

### Source 1: Cross-coin transfer gaps

Look for: winning archetype on coin A that has not been tried on coin B with similar vol profile.

Current gaps (as of session end):
- Calendar Shield: deployed on BTC (#100), ETH (#105). **Untested on BNB, ADA, AVAX, SOL.**
- VolShield: deployed on SOL (#102). **Untested on AVAX (similar vol profile).**
- Triple Regime: on BTC, BNB, ADA. **Untested on AVAX, DOGE (and DOGE Triple was tested → failed).**

### Source 2: Failed-with-fix candidates

For each FAILED strategy in `examples/loss_*.md`, ask: what ONE parameter change might convert it?

Examples:
- BNB RegimeShield FAILed adversarial (-20% in 2022). Fix: add bear EXIT on close < EMA200 alone (no ret_30d requirement).
- DOGE strategies all fail. Open challenge — needs custom design.

### Source 3: Common-factor extrapolation

From `strategy-researcher` Playbook 1, if a factor correlates with PASS rate, propose using it where it's absent.

Example finding: "PASS strategies all use ret_60d filter (5/5). FAILs use only ret_30d." → Hypothesis: "Add ret_60d filter to FAILing strategies."

### Source 4: Live divergence insights

Once meta_allocator weekly cron has 30+ days of data, look for live divergence (Playbook 3). Each diverged bot suggests a hypothesis:

- Bot fires far fewer trades than backtest → entry conditions met less often in current regime → "Add fallback condition X"
- Bot loses more per trade than backtest → exit timing different → "Tighten exit threshold"

### Source 5: Calendar / external signal expansion

We tested DOW + month + halving phase + EoM. **Untested:**
- Holiday effects (Easter, CNY, Christmas)
- Quarter-end effects (last 5 days of Mar/Jun/Sep/Dec)
- Weekend bridge behavior (Friday close → Monday open)
- US trading hours overlap (different active periods)

Each is a hypothesis if signal can be found in `calendar_analyzer.py` runs.

### Source 6: Architecture gaps

Current archetypes: Pure Shield, Sigmoid V2, Calendar, Triple, VolShield.

**Untested combinations:**
- Calendar + VolShield (would this PASS on SOL?)
- Triple + Calendar (defensive sleeve with seasonal boost)
- Sigmoid V2 with non-halving cycle proxy (Per-Asset Cycles V2)
- Multi-timeframe: 1d strategy with 4h confirmation

Each is a hypothesis worth proposing.

### Source 7: Capital allocation hypotheses

These don't involve new bots — they propose better USE of existing bots:

- "Move $1K from #99 Triple BTC to #100 Calendar BTC because #100 has higher backtest"
- "Add stop-deploy rule: if any bot's live ROI < -10% in 30 days, deactivate"
- "Implement meta_allocator weekly cron NOW that 30 days have passed"

## Generation method (when invoked)

Step 1: Pull recent context
- Read `strategy-researcher`'s latest output (if any)
- Read `strategy-architect/knowledge/coin_profiles.md`
- Read `examples/loss_*.md` from strategy-lab

Step 2: Generate candidates
- 2 candidates from "cross-coin transfer gaps"
- 1 candidate from "failed-with-fix"
- 1 candidate from "untested archetype combination"
- 1 candidate from "capital allocation"

Total: 5 hypotheses per generation.

Step 3: Rank by expected impact × confidence × cost

Rank formula:
```
score = (expected_pp_yr_gain * confidence) / cost_hours
```

Where:
- expected_pp_yr_gain: realistic improvement (default 3-5pp/yr for transfers, 1-2pp for fixes)
- confidence: 0.3 (low) to 0.9 (high) based on prior evidence
- cost_hours: 0.5 for template re-use, 2+ for custom design

Step 4: Top 3 → recommend for testing immediately. Bottom 2 → backlog.

## Anti-patterns to avoid

### Don't generate without grounding

BAD: "What if we used Ichimoku?" (no grounding)
GOOD: "Ret_60d filter present in all 5 PASS strategies (n=16 verdict records). Hypothesis: add ret_60d to BNB Pure Shield (currently FAIL with only ret_30d filter)."

### Don't propose unverifiable hypotheses

BAD: "The strategy will work in the next bull market"
GOOD: "Backtest will show +X pp/yr improvement over current; adversarial will PASS"

### Don't generate too many at once

BAD: List of 30 ideas
GOOD: Top 3-5 with priority

Too many ideas paralyze action. Force prioritization.

### Don't pursue ML when heuristic close

If the realistic improvement is < 5pp/yr, propose the HEURISTIC version, not ML. ML adds maintenance burden that exceeds 5pp/yr in attention drain.

## Example output

```markdown
## Top 3 hypotheses (ranked)

### H1: Calendar Shield port to BNB
**Type:** transfer
**Source:** Calendar Shield PASSes on BTC (#100) and ETH (#105). BNB vol ~65% (similar to BTC). Calendar tilts are market-wide.
**Pre-mortem:** Would fail if BNB's seasonal pattern differs significantly from BTC/ETH (unlikely but possible).
**Test plan:**
1. bot-builder: strategy_calendar template, COIN=BNB, slug=bnb_calendar
2. backtest 6-window
3. adversarial gate
4. If PASS: deploy $3K. If WARN: $2K. If FAIL: document.
**Cost:** ~45 min
**Expected:** +5-10pp/yr over current BnbShieldSlow
**Confidence:** High (similar pattern proven on 2 coins)

### H2: VolShield port to AVAX
**Type:** transfer
**Source:** VolShield v3 PASSes WARN on SOL (#102). AVAX has similar vol (~95%).
**Pre-mortem:** Would fail if AVAX microstructure differs from SOL (more volume = different chop pattern).
**Test plan:**
1. bot-builder: strategy_vol_shield template, COIN=AVAX, slug=avax_vol_shield
2. backtest 6-window
3. adversarial — note SOL was WARN, AVAX may be similar
4. Deploy if PASS/WARN
**Cost:** ~45 min
**Expected:** +5-10pp/yr over AvaxMetaReliable; bear protection
**Confidence:** Medium (vol matches but microstructure differs)

### H3: meta_allocator activation
**Type:** capital-allocation
**Source:** Cron has been running dry-run for 30+ days. Should now produce meaningful reallocation.
**Pre-mortem:** Would fail if reallocation churns capital between equally-good bots (whiplash).
**Test plan:**
1. Pull last 90 days from each bot's live trades
2. Run meta_allocator --dry-run, inspect proposed reallocation
3. Sanity check: are top-bot suggestions reasonable?
4. If yes → run with --apply
**Cost:** ~30 min review + apply
**Expected:** +2-4pp/yr from better allocation
**Confidence:** Medium (heuristic works; live data quality unknown)

## Backlog (not testing now)

### H4: Holiday effects analyzer
### H5: Multi-timeframe regime detection
```

## When to invoke strategy-explorer in a session

Naturally fit:
- Start of a new session: "what should we focus on today?"
- After major deployment: "we deployed X, what's next?"
- After analyzing results: "researcher found Y, what hypothesis follows?"
- When user feels stuck: "I don't know what to try"

Not fit:
- When user has a specific ask (skip to bot-builder)
- When user wants validation only (skip to strategy-critic)
- When user wants explanation only (skip to strategy-architect)
