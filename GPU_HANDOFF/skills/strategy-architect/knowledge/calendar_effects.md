# Calendar Effects in Crypto

Statistical findings from `calendar_analyzer.py` over 2340 days of BTC daily returns (2020-2026).

## Summary

| Effect | Avg daily ROI | p-value | Bonferroni? | Tilt weight |
|---|---|---|---|---|
| October | +0.54% | 0.0023 | ✅ YES | +0.15 |
| Days 90-365 post-halving | +0.39% | 0.006 | ❌ marginal | (in halving phase) |
| Wednesday | +0.49% | 0.010 | ❌ marginal | +0.05 |
| Monday | +0.45% | 0.032 | ❌ marginal | +0.05 |
| End-of-month (26-31) | +0.28% | 0.048 | ❌ marginal | +0.05 |
| July | +0.35% | 0.048 | ❌ marginal | +0.05 |

**31 tests run total.** Bonferroni alpha = 0.05/31 = 0.00161.

## What this means

### October (the only Bonferroni-survived signal)
- Statistically robust
- Plausible mechanism: post-summer return-to-trading + ETF/macro narratives often peak in Q4
- Gets the LARGEST tilt: +0.15

### Days/months/EoM (marginal signals)
- p < 0.05 but NOT < 0.00161
- Risk of false discovery
- Get SMALLER tilts: +0.05 each
- Combined effect is bounded by `TILT_CLAMP = 0.30`

## Code (reference)

```python
CALENDAR_TILTS = {
    "is_october":     0.15,
    "is_july":        0.05,
    "is_wednesday":   0.05,
    "is_monday":      0.05,
    "is_end_of_month": 0.05,
}
TILT_CLAMP = 0.30

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
```

## Cross-coin portability

These calendar effects PORT to other coins (verified on ETH — sub #105 Calendar Shield got +55%/yr, the strongest deploy of the session).

**Why they port:**
- Day-of-week patterns reflect TRADER BEHAVIOR (Mon-Fri schedule), not coin-specific dynamics
- October patterns reflect MACRO calendar (ETF flows, year-end positioning), market-wide

**Have NOT tested on:** BNB, ADA, SOL, AVAX, DOGE. Worth testing.

## What does NOT port

- Halving phase shifts: BTC-only by definition
- Coin-specific anomaly thresholds: each coin has different normal-range
- Volatility-driven tilts: per-coin calibration

## Pre-deployment checklist for calendar tilts

Before adding calendar tilts to a new coin's strategy:

- [ ] Verify the coin has data going back to at least 2020 (need ≥ 4 Octobers)
- [ ] Run `calendar_analyzer.py` adapted to the coin's daily returns
- [ ] Check if same patterns hold (especially October)
- [ ] If patterns DIFFER significantly, use coin-specific tilt weights
- [ ] Test the new combination via 6-window + adversarial as usual

## Edge cases and gotchas

### "What if December is also strong?"
We tested 12 months. December came up marginal (p=0.07) but didn't make the cut. If you add December tilt later, document it as "added based on additional N years of data" — don't add without re-running stats.

### "What about Easter / Chinese New Year?"
Holiday effects: NOT TESTED YET. Calendar_analyzer.py covers DOW + month + DOM + halving-phase. Holiday effects would be a separate analyzer.

### "Why these specific tilt magnitudes?"
The 0.15 for October was tuned to make `adjusted_bias` shift by enough to matter in the sigmoid but not dominate `cycle_phase`. The 0.05 marginal tilts compose safely because TILT_CLAMP caps the total at 0.30.

### Don't add tilts > 0.20 individually
Single tilts above 0.20 start dominating cycle_phase, defeating the layered design. The sweet spot is small additive contributions.

## Future work (calendar-related ideas)

1. **Holiday effects** — Dec/Jan transition, Easter, Lunar New Year
2. **End-of-quarter rebalancing** — Mar/Jun/Sep/Dec last week
3. **Weekend effects** — different exit logic if held over weekend vs weekday
4. **Time-of-day** — only relevant if moving to 4h or 1h timeframe (NOT for 1d strategies)
