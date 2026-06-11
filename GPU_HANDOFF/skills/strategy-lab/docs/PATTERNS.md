# Successful Patterns Library

Code skeletons and design rationale for patterns that PASSED adversarial validation in production. Copy these as starting points.

---

## Pattern 1 — Sigmoid Sizing with Phase Shifts

**Origin:** Idea D, deployed as sub #98 (AI Shield V2). +10pp/yr over flat sizing.

**When to use:**
- BTC strategies that already have a `cycle_bias` signal (-1 to +1)
- You want smooth position sizing rather than binary on/off

**Pattern:**
```python
PHASE_SHIFTS = {
    "ACCUMULATION":  0.20,
    "EARLY_BULL":    0.10,
    "PARABOLIC":    -0.15,
    "DISTRIBUTION": -0.40,
    "BEAR":         -0.60,
    "REACCUMULATION": -0.05,
}
SIGMOID_K = 4.0

def _sigmoid(x, k=SIGMOID_K, c=0.0):
    return 1.0 / (1.0 + np.exp(-k * (x - c)))

# In populate_indicators:
BASE = 0.85
shifts = df["cycle_phase"].map(PHASE_SHIFTS).fillna(0.0).astype(float)
adjusted_bias = df["cycle_bias"].astype(float) + shifts
cycle_mult = _sigmoid(adjusted_bias.values, k=SIGMOID_K, c=0.0)
df["ai_target"] = (BASE * cycle_mult).clip(0.0, BASE)
df.loc[df["anomaly"] == 1, "ai_target"] = 0.0
df.loc[df["regime_confirmed"] == "BEAR", "ai_target"] = 0.0
```

**Why it works:**
- Smooth transitions avoid all-or-nothing whipsaws
- Phase shifts encode prior knowledge (accumulation phase = boost, distribution = brake)
- Sigmoid k=4 gives ~80% probability mass within ±1 of center
- BEAR regime override is a circuit breaker

**Caveat:** Only works for BTC because `cycle_phase` derives from halving data. Don't port directly to other coins.

---

## Pattern 2 — Calendar Tilts on Cycle Bias

**Origin:** Idea J → sub #100 (BTC Calendar Shield, +1.7pp/yr over V2), then sub #105 (ETH Calendar Shield, **+55%/yr — strongest of session**).

**When to use:**
- You already have Pattern 1 working
- Adding day-of-week / month-of-year seasonality

**Pattern:**
```python
CALENDAR_TILTS = {
    "is_october":     0.15,  # Uptober — p=0.002, only one surviving Bonferroni
    "is_july":        0.05,
    "is_wednesday":   0.05,
    "is_monday":      0.05,
    "is_end_of_month": 0.05,
}
TILT_CLAMP = 0.30

# In populate_indicators:
d_idx = pd.to_datetime(df["date"], utc=True)
is_oct = (d_idx.dt.month == 10).astype(float)
is_jul = (d_idx.dt.month == 7).astype(float)
is_wed = (d_idx.dt.day_name() == "Wednesday").astype(float)
is_mon = (d_idx.dt.day_name() == "Monday").astype(float)
is_eom = (d_idx.dt.day >= 26).astype(float)
tilt = (
    is_oct * CALENDAR_TILTS["is_october"]
    + is_jul * CALENDAR_TILTS["is_july"]
    + is_wed * CALENDAR_TILTS["is_wednesday"]
    + is_mon * CALENDAR_TILTS["is_monday"]
    + is_eom * CALENDAR_TILTS["is_end_of_month"]
).clip(-TILT_CLAMP, TILT_CLAMP)
df["calendar_tilt"] = tilt.values

# Then in sigmoid sizing:
adjusted_bias = df["cycle_bias"].astype(float) + shifts + df["calendar_tilt"]
```

**Why it works:**
- October pattern is statistically robust (n=8 Octobers in dataset, p<0.01)
- Day-of-week effects are market-wide (work on ETH too)
- Total clamp of ±0.30 prevents calendar from dominating cycle_phase
- Adds to existing bias smoothly via sigmoid

**Surprising result:** Works BETTER on ETH (+55%/yr) than BTC (+38%/yr). ETH has more sideways periods where calendar boosts help.

---

## Pattern 3 — N-Day Regime Confirmation (Anti-Whipsaw)

**Origin:** Every shield strategy uses this. Prevents single-day false signals from triggering position changes.

**Pattern:**
```python
# Compute raw regime
bull = (df["close"] > df["ema200"]) & (df["ret_30d"] > 0.05) & (df["adx"] > 20)
bear = (df["close"] < df["ema200"]) & (df["ret_30d"] < -0.10)
rcode = pd.Series(0.0, index=df.index)
rcode[bull] = 1.0
rcode[bear] = -1.0

# Require N consecutive days agreeing
N = 3  # 3 for BTC, 5 for SOL (higher vol)
rmin = rcode.rolling(N, min_periods=N).min()
rmax = rcode.rolling(N, min_periods=N).max()
stable = rmin == rmax
df["regime_confirmed_code"] = rcode.where(stable, other=pd.NA).ffill().fillna(0)
df["regime_confirmed"] = df["regime_confirmed_code"].map({
    1.0: "BULL", -1.0: "BEAR", 0.0: "NEUTRAL"
})
```

**Why N varies by coin:**
- BTC: N=3 (vol ~55%/yr, signals are clean)
- ETH: N=3 (similar to BTC)
- SOL: N=5 (vol ~95%/yr — needs more confirmation to avoid chop)
- DOGE: N=4 (high vol but trends are sharper than SOL)

**Critical:** Use integer codes (1, -1, 0) NOT strings. Pandas `.rolling().apply()` on string Series fails.

---

## Pattern 4 — Volatility-Aware Filters (High-Vol Coins)

**Origin:** Idea L → sub #102 (SOL VolShield v3). After 3 failed SOL Shield variants, this finally passed adversarial.

**When to use:**
- Coin's annualized volatility > 80%
- Pure Shield gets chopped in sideways

**Pattern:**
```python
df["ema200"] = ta.EMA(df, timeperiod=200)
df["ema50"] = ta.EMA(df, timeperiod=50)        # Golden cross filter
df["adx"] = ta.ADX(df, timeperiod=14)
df["ret_30d"] = df["close"].pct_change(30)
df["ret_60d"] = df["close"].pct_change(60)     # Longer window
df["atr14"] = ta.ATR(df, timeperiod=14)
df["atr_pct"] = df["atr14"] / df["close"]      # Normalized vol

bull = (
    (df["close"] > df["ema200"])
    & (df["ema50"] > df["ema200"])              # Golden cross-like
    & (df["ret_30d"] > 0.05)                    # Short trend
    & (df["ret_60d"] > 0.15)                    # Long trend
    & (df["adx"] > 30)                          # Strong trend (vs 20 for BTC)
    & (df["atr_pct"] < 0.10)                    # NOT in chop
)
bear = (
    (df["close"] < df["ema200"])
    & (df["ret_60d"] < -0.10)
)
# N=5 confirmation for SOL
```

**Why it works:**
- Triple filter (EMA200 + EMA50 cross + ret_60d) catches only genuine trends
- ADX > 30 (vs 20) eliminates weak/trending periods
- ATR_pct ceiling rejects entries during volatility spikes
- 5-day confirmation absorbs SOL's typical 2-3 day false moves

**Tuning notes:**
- atr_pct threshold: 0.10 for SOL works. Tune up to 0.12 if too few trades, down to 0.08 if too many false signals.
- If 0 trades over 5 years, your filters are too strict (we hit this with v1).
- If trades fire on every false signal, filters are too loose (v2 had this).

---

## Pattern 5 — Triple Regime Consensus (Defensive Sleeve)

**Origin:** Idea G → sub #99 (BTC Triple), then #103 (BNB Triple), #104 (ADA Triple).

**When to use:**
- The coin's main bot fails adversarial (capital-preservation gap)
- You want a small "always conservative" sleeve alongside

**Pattern:** (already in `user_data/strategies/btc_triple_regime_strategy.py`)

Three independent regime detectors must ALL agree on BULL:
1. EMA + ADX based (like Pure Shield)
2. Donchian channel breakout
3. MACD crossover

If any disagree → NEUTRAL (no position). Slow to enter, slow to exit, but VERY safe.

**Expected performance:** 10-18%/yr — won't beat the main bot but provides:
- 0% or small positive in bear years
- Steady positive in sideways
- Captures only the strongest bull legs

**Wallet sizing:** Always smaller (~$2K) since it's a sleeve, not a primary.

---

## Pattern 6 — Cross-Coin Strategy Porting

**Origin:** Idea K → sub #101 (ETH Pure Shield, +47%/yr), then sub #105 (ETH Calendar Shield, +55%/yr).

**When to use:**
- A BTC strategy works (PASS or WARN)
- Another coin has an inferior live strategy
- The strategy's indicators are GENERIC (not BTC-specific like halving data)

**Process:**
1. Create `config.<strategy>-<COIN>.json` (copy BTC config, change pair_whitelist + db_url + bot_name)
2. Run full 6-window backtest
3. Adversarial validate
4. **Critically: compare to existing live bot's adversarial result.** If existing also fails adversarial but the new one passes, even with lower compound, the new one is better.

**What ports well:**
- Calendar tilts (market-wide signal)
- Regime detection patterns
- Sigmoid sizing (the math is general)

**What does NOT port:**
- Halving cycle bias (BTC-specific)
- Coin-specific anomaly thresholds (need re-tuning per coin)
- Volatility constants (SOL needs 5-day confirmation, not 3)

---

## Pattern 7 — Heuristic Meta-Allocator (instead of RL)

**Origin:** Idea I — RL was overkill (gap < 5pp/yr vs heuristic).

**Pattern:** (already in `research/ai/meta_allocator.py`)

Every week (Sundays):
1. Pull last 90d trades from each bot in `trad_pg.trades`
2. Score per bot: `s = sharpe * sqrt(win_rate) * (1 - clamp(max_dd, 0, 0.5))`
3. Top 30% of bots get 70% of total budget (weighted by score)
4. Bottom 70% share 30% (equal split for diversification)
5. Floor: 5% of current allocation (no zeroing)
6. Ceiling: 200% (no whiplash)

**Cron entry on trad-server:**
```
0 0 * * 0 /srv/trad/pythone/freqtrade_btc_bot/scripts/run_meta_allocator.sh
```

Runs in dry-run mode by default. Add `--apply` to commit changes. Wait 30+ days of live trade data before first `--apply` run.

---

## Pattern 8 — Statistical Significance with Bonferroni

**Origin:** Idea J → calendar_analyzer.py.

**When testing many signals (e.g. all 12 months, 7 days of week):**

```python
N_TESTS = 12 + 7 + 5 + 6 + 1  # months + days + DOM buckets + halving phases + quarter-end
BONFERRONI_ALPHA = 0.05 / N_TESTS  # = 0.00161

for signal in signals:
    p_value = ttest_1samp(returns_when_signal, popmean=overall_mean).pvalue
    if p_value < BONFERRONI_ALPHA:
        print(f"  {signal}: SURVIVES Bonferroni (p={p_value:.4f})")
    elif p_value < 0.05:
        print(f"  {signal}: marginal (p={p_value:.4f})")
```

**Why:** With 31 tests at alpha=0.05, you'd expect ~1.5 false positives by chance alone. Bonferroni guards against that.

In our calendar test, only October survived. We still used the marginal signals (July, Mon, Wed, EoM) at smaller tilt weights (0.05 vs October's 0.15) — they're not robust enough for full weight but contribute a little.

---

## Anti-Patterns reminder

See `ANTI_PATTERNS.md` for the WRONG patterns and why. Read both files before designing.
