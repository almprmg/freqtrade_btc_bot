# Playbook: Generating Hypotheses from Archive Data

Recipe for extracting NEW hypotheses worth testing from existing data — no LLM creativity needed.

## Step 1: Establish baseline patterns

Run `scripts/find_common_factors.py` to get the current pass/fail factor table.

What we know about PASS vs FAIL strategies from this:
- Universal across PASS: regime detector + N-day confirmation + BEAR exit
- Differentiating: ret_60d filter, ATR ceiling, calendar tilts
- BTC-only: phase shifts

## Step 2: Find absent-where-it-could-help

Read the factor analysis and ask:

> "Which features are present in PASS strategies for ONE coin but ABSENT from PASS strategies on ANOTHER coin?"

Example finding (from current data):
- Calendar tilts: present in BTC (#100), ETH (#105). ABSENT in BNB/ADA bots.
- Hypothesis: "Calendar tilts ported to BNB should improve over current BnbShieldSlow"

Example finding:
- Triple Regime: deployed on BTC/BNB/ADA. ABSENT on DOGE.
- BUT: DOGE Triple was tested and FAILED. Note this — absence ≠ untested.

## Step 3: Find present-where-it-fails

> "Which features are present in FAIL strategies but not present in PASS strategies for that coin?"

Example:
- Aggressive sizing > 0.85: present in some FAILs.
- Hypothesis: "Reducing BASE to 0.70 might convert FAIL to WARN"

## Step 4: Find correlated negative outcomes

Look for pairs of features where having BOTH correlates with FAIL more than either alone.

```python
# Pseudo-analysis
for feat_A in features:
    for feat_B in features:
        if feat_A == feat_B: continue
        pass_rate_both = pass_rate_when(A=True, B=True)
        pass_rate_neither = pass_rate_when(A=False, B=False)
        if pass_rate_both - pass_rate_neither < -0.3:
            print(f"Avoid combining {feat_A} + {feat_B}")
```

Example (hypothetical from current session):
- AI Shield V3 cooldown + bull rallies → FAIL
- "Don't combine cooldown with rally-capture strategies"

## Step 5: Cross-coin transfer candidates

For each (winning_strategy, source_coin, target_coin):
- IF target_coin has no version of this strategy
- AND source_coin has it passing adversarial
- AND target_coin's vol profile is similar to source_coin's
- THEN: hypothesis = "port winning_strategy to target_coin"

Example (currently untested):
- Calendar Shield on BNB (BNB vol ~65%, similar to BTC/ETH)
- Calendar Shield on ADA (ADA vol ~80%, borderline)

## Step 6: Failed-with-fix candidates

For each FAILED strategy:
- Was the failure due to ONE specific filter being too loose?
- Could ONE parameter change convert it?

Example (from session):
- SOL Pure Shield: -43% in 2025 (CATASTROPHIC)
- Fix: stricter filters → became VolShield v3 (WARN)
- This pattern: "X failed adversarial; try X' with tighter Y"

## Step 7: Anti-redundancy check

For each candidate, check redundancy:
- Does the feature add INDEPENDENT information vs existing features?
- Calendar tilts add info beyond cycle_phase? YES (different time-scales)
- FGI sentiment add info beyond cycle_phase? NO (both peak in PARABOLIC)

If REDUNDANT → don't pursue.

## Step 8: Rank by expected impact

Score each hypothesis:
- Backtest improvement potential (from similar past results)
- Sample size of supporting evidence
- Cost to test (1 hr backtest vs 1 day pipeline build)
- Risk of overfit (more features = higher risk)

Top 3-5 hypotheses → test in next batch.

## Output template

For each candidate hypothesis, document:

```markdown
## H<N>: <one-sentence hypothesis>

**Type:** transfer / fix / new-archetype / new-feature

**Evidence:**
- Source: <where in data>
- n: <sample size>
- Effect size: <expected pp/yr or DD reduction>

**Test plan:**
1. Build via bot-builder using template <X>
2. Backtest 6-window
3. Adversarial gate
4. If PASS/WARN: deploy with $<Z> wallet

**Expected outcome:**
- Pre-mortem: <how would this fail?>
- If succeeds: <what we learn>
- If fails: <what we learn>

**Cost:**
- Backtest time: ~30 min
- Build time: ~15 min (from template)
- Total: ~45 min
```

## Anti-patterns (don't do these)

1. **"AI/ML for the sake of it"** — if heuristic suffices (gap < 5pp/yr), skip ML
2. **"Combine all features into a mega-strategy"** — untraceable, overfit-prone
3. **"This new indicator looks cool"** — must derive from data analysis, not vibes
4. **"It worked once in 2023"** — single-window not enough
5. **"FGI showed signal so add sentiment everywhere"** — check redundancy first

## When you find a high-impact hypothesis

Hand off to:
- `bot-builder` to construct
- `strategy-critic` to validate
- `strategy-lab` to orchestrate end-to-end
