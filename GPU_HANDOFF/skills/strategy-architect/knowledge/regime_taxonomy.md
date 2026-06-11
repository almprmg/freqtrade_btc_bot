# Regime Taxonomy

Crypto market states and the detectors that identify them.

## The 4 regimes

| Regime | Signature | Strategy response |
|---|---|---|
| BULL | close > EMA200, ret_30d > +5%, ADX > 20 | LONG, size up |
| BEAR | close < EMA200, ret_30d < -10% | EXIT all, hold cash |
| SIDEWAYS | within ±5% of EMA200, ADX < 20 | EXIT or reduce — chop kills profit |
| CHOP | rapid regime flips within 7 days | NEUTRAL (no position) — wait it out |

## Detector implementations

### Single-detector (Pure Shield)
```python
bull = (df["close"] > df["ema200"]) & (df["ret_30d"] > 0.05) & (df["adx"] > 20)
bear = (df["close"] < df["ema200"]) & (df["ret_30d"] < -0.10)
# Otherwise NEUTRAL
```
- Pros: simple, fast, easy to debug
- Cons: gets chopped on high-vol coins, single-day false signals
- Use for: BTC, ETH, BNB (vol < 80%)

### Triple-consensus (Triple Regime)
Three INDEPENDENT detectors must agree:
```python
det1 = EMA-based (above)
det2 = Donchian-channel breakout (close near 60d high)
det3 = MACD positive (MACD > signal AND MACD > 0)
bull = det1 AND det2 AND det3
```
- Pros: very few false signals → PASS adversarial reliably
- Cons: slow to enter, misses early bull legs → lower compound
- Use for: defensive sleeves on coins where primary bot fails adversarial

### Volatility-aware (VolShield)
Pure Shield + chop filters:
```python
bull = (
    Pure Shield conditions
    & (df["ema50"] > df["ema200"])     # golden-cross-like
    & (df["ret_60d"] > 0.15)            # longer-term confirmation
    & (df["atr_pct"] < 0.10)            # NOT during high vol
)
N_CONFIRM = 5  # longer regime confirmation
```
- Pros: catches sideways/chop, works on high-vol coins
- Cons: misses some bull rallies (5-day delay)
- Use for: SOL, AVAX (vol > 80%)

## N-day confirmation pattern

CRITICAL for any regime detector. Don't act on single-day signals.

```python
# Compute raw regime as int (NOT string — pandas can't .rolling() strings)
rcode = pd.Series(0.0, index=df.index)
rcode[bull] = 1.0
rcode[bear] = -1.0

# Require N consecutive days agreeing
rmin = rcode.rolling(N, min_periods=N).min()
rmax = rcode.rolling(N, min_periods=N).max()
stable = rmin == rmax
df["regime"] = rcode.where(stable, other=pd.NA).ffill().fillna(0).map({
    1.0: "BULL", -1.0: "BEAR", 0.0: "NEUTRAL"
})
```

| Coin | N | Reason |
|---|---|---|
| BTC | 3 | Vol low, signals clean |
| ETH | 3 | Similar to BTC |
| BNB | 3 | Similar to BTC |
| ADA | 3 | Borderline; 4 if you want extra safety |
| DOGE | 4 | Higher vol, false moves slightly longer |
| SOL | 5 | Vol ~95%, false moves last 2-3 days |
| AVAX | 5 | Same as SOL |

## Regime-specific anti-patterns

### Don't enter during DISTRIBUTION
Distribution phase = late bull where most holders are selling. Even if BULL detector fires, the move is exhausted. PHASE_SHIFTS["DISTRIBUTION"] = -0.40 captures this.

### Don't fight BEAR with mean-reversion
"BTC dropped 10% in 3 days, it'll bounce" — DOES happen, but inconsistently. Adversarial-passed strategies all EXIT on BEAR, no bounce-buying.

### Don't ignore CHOP — treat as NEUTRAL
SIDEWAYS markets eat into capital via fees + small drawdowns. Better to sit out.

## Phase shifts (BTC halving-specific)

```python
PHASE_SHIFTS = {
    "ACCUMULATION":  +0.20,  # before halving — early buy zone
    "EARLY_BULL":    +0.10,  # post-halving rally building
    "PARABOLIC":     -0.15,  # late-cycle euphoria, brake position
    "DISTRIBUTION":  -0.40,  # sellers dominate, exit
    "BEAR":          -0.60,  # bear phase, stay out
    "REACCUMULATION": -0.05, # bottom forming
}
```

Added to `cycle_bias` before sigmoid: lifts target_position during accumulation, brakes during distribution.

**ONLY for BTC.** Don't apply to ETH/SOL/etc — they don't have halving.

## How regime detection FAILS

Common failure modes (each was observed in this session):

1. **Whipsaw**: regime flips daily → N-day confirmation fixes
2. **Lagging**: bull confirmed after 30% move already happened → tighter ret_30d threshold
3. **False positive in chop**: ADX > 20 even in chop → add ATR_pct ceiling
4. **False negative in slow bull**: ret_30d > 5% missed if move was gradual over 60d → add ret_60d > 15% OR
5. **BEAR exit too late**: ret_30d < -10% requires already-significant drop → consider exit on close < EMA200 alone

Most "improved" strategies fix exactly one of these. The Adversarial Validator catches the fix's side effects.
