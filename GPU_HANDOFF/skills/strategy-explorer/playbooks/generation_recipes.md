# Hypothesis Generation Recipes

5 recipes for producing new hypotheses, with concrete examples.

---

## Recipe 1: Cross-Coin Transfer Scanner

**Goal:** find a winning archetype on coin A that hasn't been tried on coin B.

**Inputs:**
- List of deployed bots (from trad_pg or live deploys log)
- Coin vol profiles (from `strategy-architect/knowledge/coin_profiles.md`)
- Adversarial verdicts (from `research/adversarial/`)

**Procedure:**
```python
deployed = list_active_subs()  # via psycopg
verdicts = load_adversarial_verdicts()
profiles = load_coin_profiles()

candidates = []
for archetype in ALL_ARCHETYPES:
    coins_with_archetype = {bot.coin for bot in deployed if bot.archetype == archetype}
    coins_passing = {bot.coin for bot in deployed if bot.archetype == archetype and verdicts[bot] in ("PASS", "WARN")}

    # Find untested coins with similar vol
    for coin in ALL_COINS:
        if coin in coins_with_archetype:
            continue
        source_vols = [profiles[c]["vol"] for c in coins_passing]
        if not source_vols:
            continue
        if min(abs(profiles[coin]["vol"] - s) for s in source_vols) < 15:
            candidates.append({
                "archetype": archetype,
                "source_coins": list(coins_passing),
                "target_coin": coin,
                "vol_diff": min(abs(profiles[coin]["vol"] - s) for s in source_vols),
                "expected_pp_yr": 5,  # default for transfers
                "confidence": "high" if len(coins_passing) >= 2 else "medium",
            })
```

**Real example (from current state):**
- Archetype: Calendar Shield
- Already on: BTC (#100), ETH (#105) — both PASS
- Untested: BNB (vol 65%, close to BTC 55%)
- Hypothesis: "BNB Calendar Shield should improve over current BnbShieldSlow"

**Output format:**
```markdown
## H<N>: <Archetype> port to <Target>
**Source coins (passing):** <list>
**Target coin vol:** <X%> (within <Y>pp of nearest source)
**Confidence:** high/medium/low
```

---

## Recipe 2: Failed-with-Fix

**Goal:** for each FAIL/CATASTROPHIC strategy, propose ONE parameter change that might convert it.

**Inputs:**
- `examples/loss_*.md` (rejection writeups)
- Adversarial verdict details (which window failed, by how much)

**Procedure:**
For each rejected strategy:
1. Read its failure mode
2. Identify the SPECIFIC condition that caused failure
3. Propose ONE parameter change to fix that condition

**Real example:**
- Rejected: DOGE RegimeShield (CATASTROPHIC -32%/-19%)
- Failure mode: bear exits too late (only on ret_30d < -10%)
- Fix proposal: "Add early-exit on close < EMA200 alone (ignoring ret_30d)"
- Pre-mortem: "Could over-exit on noise — but worth testing"

**Output:**
```markdown
## H<N>: <Strategy> fix — <specific change>
**Original failure:** <window>, <ROI>%, <DD>%
**Proposed fix:** <one change>
**Pre-mortem:** <what could still go wrong>
**Expected delta:** convert CATASTROPHIC → FAIL (still no deploy) or → WARN (deployable)
```

---

## Recipe 3: Untested Combination

**Goal:** identify archetype combinations that haven't been tested.

**The 5 archetypes:**
1. Pure Shield
2. Sigmoid V2 (Pure + halving + sigmoid)
3. Calendar (V2 + tilts)
4. Triple Regime (3-detector consensus)
5. VolShield (Pure + chop filters)

**Combinations possible (5×5 = 25, minus already-tested):**

| Combo | Status | Hypothesis |
|---|---|---|
| Calendar + VolShield | UNTESTED | "Calendar tilts + vol-aware filters for SOL might unlock PASS" |
| Triple + Calendar | UNTESTED | "Triple defensive + Oct boost could improve compound w/o adversarial loss" |
| Sigmoid V2 + VolShield | UNTESTED | "Smooth sizing + chop filter for SOL" |
| VolShield + Triple consensus | UNTESTED | "Most defensive possible — for DOGE?" |

**Procedure:**
For each pair (A, B):
1. Check if either is already deployed using both
2. If neither: propose combined version
3. Estimate cost: usually 1-2 hours (combine code + test)
4. Estimate impact: usually 5-15pp/yr if both contributions are additive

**Real candidate:**
- Calendar + VolShield for SOL
- Hypothesis: "Add calendar tilts on top of VolShield v3 — October boost might convert WARN to PASS"
- Cost: 1 hour
- Expected: +3-5pp/yr if calendar effects extend to SOL

---

## Recipe 4: Capital Allocation Hypothesis

**Goal:** propose reallocation between EXISTING bots, no new code.

**Inputs:**
- Current allocated_capital per sub (from trad_pg)
- Backtest expected ROI per bot
- Live performance to date

**Procedure:**
```python
for bot in active_bots:
    expected_roi = bot.backtest_annual_pct
    actual_roi = bot.live_pnl / bot.wallet * (365 / days_live)
    delta = actual_roi - expected_roi

    if delta < -20:  # underperforming
        suggest_reduce(bot, amount=-1000)
    if delta > +20:  # overperforming
        suggest_increase(bot, amount=+1000)

# Subject to:
#   total_capital unchanged
#   no bot below $500 (operational minimum)
#   no bot above $5000 (concentration cap)
```

**Real example (will trigger after 30+ days live):**
- Calendar Shield #100 (BTC) live ROI projecting +40%/yr (vs backtest +38%) → ↑$1K
- Some underperforming bot → ↓$1K

**Cost:** Almost free. Just SQL UPDATE.

**Expected:** 2-4pp/yr from better allocation.

---

## Recipe 5: External Signal Discovery

**Goal:** identify untested external data sources that might add signal.

**Already tested:**
- Halving cycle data → useful for BTC only
- Anomaly flags (Isolation Forest) → useful as circuit breaker
- Calendar (DOW/Month/halving phase) → useful
- FGI sentiment → real but redundant with cycle_phase

**Untested (each is a candidate):**

| Source | Cost | Likely signal | Risk |
|---|---|---|---|
| Funding rates (perp) | 1 day collect | Crowding/euphoria detector | Could correlate w/ FGI |
| Options skew (Deribit) | 2 days | Fear/positioning | API auth needed |
| On-chain flows (Glassnode free tier) | 1 day | Smart money | Daily latency |
| Stablecoin supply growth | 0.5 day | Liquidity proxy | Monthly only |
| Bitcoin dominance (DOM%) | minutes | Alt vs BTC rotation | Already implicit in alt strats |
| Google Trends (keyword) | 1 day | Retail interest | Weekly granularity |

**Procedure:**
For each source:
1. Test feasibility: free? historical data? daily granularity?
2. If yes: build feature, correlate with fwd_returns (same as sentiment_test.py pattern)
3. If correlation > 0.10 AND independent from existing features: candidate
4. If correlation < 0.10: rejected as noise
5. If correlation > 0.10 but redundant: rejected as duplicate

**Real candidate:**
- Funding rates as crowding indicator
- Free historical data (Binance, Coinglass)
- Hypothesis: "When perp funding > 0.05%, market is crowded long, derate position size"
- Cost: 1 day data collection + 1 hour build/test
- Risk: might correlate with FGI (which is redundant) — must check

---

## Ranking the 5 recipes

When generating 5 candidates per session, default mix:

| Recipe | Count |
|---|---|
| 1: Cross-coin transfer | 2 (highest ROI:cost ratio) |
| 2: Failed-with-fix | 1 (uses sunk-cost data) |
| 3: Untested combination | 1 (creative space) |
| 4: Capital allocation | 1 (free, no risk) |
| 5: External signal | 0-1 (only if specific hypothesis) |

Adjust based on user's request. If user says "no new bots, just optimize" → only Recipe 4. If "I want to expand" → more from Recipes 1+3.

---

## When all recipes are exhausted

If you've genuinely run out of grounded hypotheses:

1. Wait for more live data (30+ days unlocks Recipe 4)
2. Wait for next bear/sideways window to test deployed bots adversarially against new data
3. Investigate user's domain knowledge (do they have non-public market insights?)
4. Browse academic literature: SSRN papers on "cryptocurrency strategy" can suggest new feature angles

Don't generate hypotheses without grounding. The cost of bad hypotheses is real (one wasted backtest cycle each).
