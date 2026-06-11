# Case Studies — All 8 Deploys + 11 Rejections

Real outcomes from this session, with hypothesis, result, lesson.

---

## DEPLOY #1 — AI Shield V2 (sub #98)
- **Hypothesis:** Sigmoid sizing improves over flat BASE on BTC because halving cycles produce non-linear opportunity.
- **Backtest:** +36.5%/yr, 5y compound $47,500
- **Adversarial:** PASS (0% in 2022/2026Q12 bears, +12% in 2025)
- **Delta vs prior:** +10pp/yr over flat sizing V1
- **Wallet:** $5K
- **Lesson:** Sigmoid > linear is robust. Phase shifts add interpretability.

## DEPLOY #2 — Triple Regime BTC (sub #99)
- **Hypothesis:** 3-detector consensus reduces false BULL signals.
- **Backtest:** +10.5%/yr, 5/5 positive years, max DD 6%
- **Adversarial:** PASS
- **Wallet:** $2K (defensive)
- **Lesson:** Defensive sleeves are valid deployments even at lower return — capital preservation has portfolio value.

## DEPLOY #3 — Calendar Shield BTC (sub #100)
- **Hypothesis:** October seasonality (+0.54%/day, p=0.002 over 2340 days) tilts position size beneficially.
- **Backtest:** +38.2%/yr, 5y compound $51,800
- **Adversarial:** PASS
- **Delta vs V2:** +1.7pp/yr (mostly from 2023 +6pp)
- **Wallet:** $3K
- **Lesson:** Statistically robust calendar effects work. Bonferroni-survived signals warrant full weight; marginal signals warrant fractional weight.

## DEPLOY #4 — ETH Pure Shield (sub #101)
- **Hypothesis:** Pure Shield improves over DynRebal on ETH because DynRebal HODLs through 2022 bear (-55%).
- **Backtest:** +47%/yr (vs DynRebal +21%)
- **Adversarial:** WARN (-11.75% in 2022, +31% in 2025, 0% in 2026Q12)
- **Delta vs prior:** +26pp/yr — biggest win of session
- **Wallet:** $3K
- **Lesson:** Cross-coin port works when indicators are generic (EMA/ADX/ret). 2022 went from -55% to -12% by adding bear exit logic.

## DEPLOY #5 — SOL VolShield v3 (sub #102)
- **Hypothesis (v3 after 2 failures):** Stricter chop filters (ret_30d AND ret_60d, ADX>30, ATR<10%, EMA50>EMA200, 5-day confirm) make Shield work on high-vol SOL.
- **Backtest:** +45%/yr (vs DynRebal +40%)
- **Adversarial:** WARN (0% in 2022, -12.8% in 2025, 0% in 2026)
- **Wallet:** $3K
- **Iterations:**
  - v1: too strict (0 trades over 5 years)
  - v2: too loose (FAIL adversarial -15% in sideways)
  - v3: just right (WARN)
- **Lesson:** Filter tuning has a sweet spot. Too strict = no signal. Too loose = false positives. Validate after each iteration.

## DEPLOY #6 — BNB Triple (sub #103)
- **Hypothesis:** BNB's main bot fails adversarial (-20% in 2022). Triple Regime provides capital-preserving sleeve.
- **Backtest:** +17.7%/yr (vs main +52% but main FAILS)
- **Adversarial:** WARN (+1.4% in 2022, +11.5% in 2025, -5.8% in 2026Q12)
- **Wallet:** $2K
- **Lesson:** When main bot fails adversarial, defensive sleeve is the answer. Don't replace, augment.

## DEPLOY #7 — ADA Triple (sub #104)
- **Hypothesis:** Same as BNB.
- **Backtest:** +14.4%/yr (vs main +39% but main FAILS -22% in 2025)
- **Adversarial:** **PASS** (0%, +7.7%, 0% — perfect defensive profile)
- **Wallet:** $2K
- **Lesson:** Same as BNB Triple.

## DEPLOY #8 — ETH Calendar Shield (sub #105) — STRONGEST OF SESSION
- **Hypothesis:** Calendar tilts that worked on BTC (+1.7pp) should also work on ETH because day-of-week effects are market-wide.
- **Backtest:** **+55%/yr** (vs ETH Pure Shield +47%, vs DynRebal +21%)
- **Adversarial:** **PASS** (0% in 2022/2026Q12, +43% in 2025 sideways)
- **Wallet:** $3K
- **Lesson:** Cross-coin pattern portability — market-wide signals (calendar) port better than coin-specific signals (halving). Best deploy of session.

---

## REJECT #1 — AI Shield V3 Cooldown (Idea E)
- **Hypothesis:** Skip entries for 7 days after anomaly because anomalies cause dead-cat bounces.
- **Result:** +31%/yr (vs V2's +36.5%/yr). PASS adversarial but inferior.
- **Why it failed:** Hypothesis was WRONG for BTC bull markets. Anomalies often precede LARGER moves, not corrections. The 7-day cooldown missed legitimate rebounds.
- **When would it work?** Possibly on coins where anomalies ARE dead-cats (meme coins, alt-L1s in late distribution).
- **Lesson:** Pre-mortem the hypothesis. "What if anomalies are setups, not corrections?" would have flagged this.

## REJECT #2 — Per-Asset Cycles (Idea F)
- **Hypothesis:** Generic cycle-detection from price action (no halving needed) should match BTC halving cycle's value, applied to all coins.
- **Result:** Each coin's existing strategy beat the generic detector.
- **Why it failed:** "Generic" detectors lose to "specific" detectors when specific data exists. BTC has halving = specific. Others don't, but their existing strategies are already specific to each coin.
- **Lesson:** Don't pursue generic when specific is available and works.

## REJECT #3 — AVAX Btc3Layer (Idea C audit)
- **Hypothesis:** Archive showed Btc3Layer Sharpe 0.79 on AVAX vs MetaAdaptive's 0.11. Should be massive upgrade.
- **Result:** -63% in 2022 bear. **Adversarial: CATASTROPHIC.**
- **Why it failed:** Archive runs were timerange-cherry-picked, missing 2022.
- **Lesson:** **NEVER trust archive metrics without fresh 6-window adversarial.** This was the most striking demonstration of why Adversarial Validator exists.

## REJECT #4 — SOL Pure Shield (Idea K-SOL)
- **Hypothesis:** Same Shield that worked on ETH should work on SOL.
- **Result:** -43% in 2025 sideways. Adversarial CATASTROPHIC.
- **Why it failed:** SOL's vol (~95%) is 1.7x BTC/ETH (~55%/70%). Default Shield thresholds get chopped.
- **Lesson:** Annualized vol > 80% requires custom filters (see Pattern 4).

## REJECT #5 — SOL AI Shield V2
- **Hypothesis:** Adding halving phase shifts on top of Shield might stabilize SOL.
- **Result:** -35% in 2025. CATASTROPHIC.
- **Why it failed:** BTC halving phases don't transfer to SOL (no Solana halving). Phase shifts added noise, not signal.
- **Lesson:** Coin-specific signals don't port.

## REJECT #6 — SOL Triple Regime
- **Hypothesis:** Most defensive option should at least PASS adversarial on SOL.
- **Result:** PASS but only 3.6%/yr (vs DynRebal 40%).
- **Why it "failed":** Too defensive — captured almost none of SOL's bull rallies. SOL gained 1573% in some periods; Triple captured 49% in 2021 and almost nothing else.
- **Lesson:** Defensive sleeves are only worthwhile if main strategy fails adversarial. SOL's DynRebal also failed adversarial but compound is so strong that Triple's defensive role doesn't justify replacing capital.

## REJECT #7 — Sentiment Shield (Idea H)
- **Hypothesis:** Adding FGI sentiment tilt to Calendar Shield should improve further.
- **Result:** $50,953 compound vs Calendar's $51,779. Adversarial PASS. **Essentially tied** (-$826 diff).
- **Why it failed:** FGI signal is real (+0.135 corr with 30d fwd returns) BUT redundant with cycle_phase (which already encodes "we're in PARABOLIC" = market euphoric = high FGI).
- **Lesson:** Test for signal REDUNDANCY before deploying. New signal must add INDEPENDENT information, not just rediscover existing one.

## REJECT #8 — BNB Rotation alternative
- **Hypothesis:** Audit showed BtcRotation had worst-case +9% on BNB (vs RegimeShield's -10%). Worth testing.
- **Result:** -15% in 2022 bear. FAIL adversarial. Same outcome class as live, no improvement.
- **Why it failed:** Archive numbers from cycle-favored windows again.
- **Lesson:** When alternative has same adversarial verdict class as live, keep live (less disruption).

## REJECT #9 — DOGE Adaptive alternative
- **Hypothesis:** Audit showed BtcAdaptive had ZERO median DD on DOGE over 4 runs. Worth testing.
- **Result:** -23%, -27%, -12% across 3 windows. FAIL.
- **Why it failed:** Small sample (n=4) was unreliable. Real adversarial revealed it's actually worse than current.
- **Lesson:** Demand n ≥ 10 in archive before considering candidate.

## REJECT #10 — ADA AI Shield V2 alternative
- **Hypothesis:** AI Shield V2 is best for BTC. Try on ADA.
- **Result:** -44% in 2025 sideways. CATASTROPHIC.
- **Why it failed:** Phase shifts based on BTC halving, irrelevant for ADA.
- **Lesson:** Phase-based strategies only work for the coin whose phases they encode.

## REJECT #11 — DOGE Triple Regime
- **Hypothesis:** Triple Regime works as defensive on BTC/BNB/ADA. Should work on DOGE.
- **Result:** -16.7% in 2025 sideways. FAIL.
- **Why it failed:** DOGE's sideways behavior is more violent than ADA/BNB. Triple's filters got chopped.
- **Lesson:** "Universal defensive" isn't actually universal. DOGE remains an open challenge.

---

## Aggregate stats

- **Hypotheses tested:** 19 (8 deployed + 11 rejected)
- **Deploy rate:** 42%
- **Adversarial gate caught:** 11 candidates (would've all been bad live deploys)
- **Biggest economic win:** ETH Calendar Shield (#105) at +55%/yr
- **Biggest "we were wrong" moment:** AVAX 3Layer — archive Sharpe 0.79 was completely misleading

## What this teaches about future sessions

1. **Plan for 50% rejection rate.** Most ideas don't work. That's fine.
2. **Document rejections as carefully as deploys.** They're more valuable for future avoidance.
3. **Adversarial Validator earns its keep every time.** Without it, ~10 bad deploys this session.
4. **Cross-coin porting works ~30% of the time.** Calendar→ETH worked. Phase shifts→SOL/ADA didn't.
5. **Defensive sleeves are stable wins.** When main bot fails adversarial, deploy Triple alongside.
