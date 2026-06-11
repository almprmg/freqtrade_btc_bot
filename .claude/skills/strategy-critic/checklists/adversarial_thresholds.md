# Adversarial Validator Thresholds

The deploy-gate verdict logic, documented.

## Source

`research/ai/adversarial_validator.py` in the freqtrade_btc_bot repo.

## Windows tested

| Window key | Date range | Why this window |
|---|---|---|
| BEAR_2022 | 2022-01-01 → 2023-01-01 | Worst recent bear: BTC -65%, ETH -77%, SOL -94% |
| SIDEWAYS_2025 | 2025-01-01 → 2026-01-01 | Low-direction chop; kills mean-reversion overfit |
| BEAR_2026Q12 | 2026-01-01 → 2026-06-01 | Current ongoing bear, includes today |

These were chosen because they:
- Cover the 3 hardest market conditions
- Are recent enough that current strategy assumptions still apply
- Have different microstructure (one bear, one sideways, one continuation bear)
- A strategy surviving all 3 demonstrates SOMETHING resembling robustness

## Verdict thresholds

```python
def verdict(roi_b22, dd_b22, roi_s25, dd_s25, roi_b26, dd_b26):
    rois = [roi_b22, roi_s25, roi_b26]
    dds = [dd_b22, dd_s25, dd_b26]
    worst_roi = min(rois)
    worst_dd = max(dds)
    n_negative = sum(1 for r in rois if r < 0)
    
    if worst_roi < -30 or worst_dd > 30:
        return "CATASTROPHIC"
    if n_negative >= 2 or worst_roi < -15:
        return "FAIL"
    if n_negative == 1 and worst_roi >= -15:
        return "WARN"
    return "PASS"
```

## Real-world examples (from major session)

| Strategy | BEAR_2022 | SIDEWAYS_2025 | BEAR_2026Q12 | Verdict |
|---|---|---|---|---|
| AI Shield V2 | 0%/0% | +12%/4% | 0%/0% | **PASS** |
| Calendar Shield (BTC) | 0%/0% | +14%/0% | 0%/0% | **PASS** |
| ETH Pure Shield (#101) | -12%/12% | +31%/0% | 0%/0% | **WARN** |
| SOL VolShield v3 (#102) | 0%/0% | -13%/13% | 0%/0% | **WARN** |
| BNB Triple (#103) | +1%/0% | +11%/2% | -6%/6% | **WARN** |
| ADA Triple (#104) | 0%/0% | +8%/2% | 0%/0% | **PASS** |
| ETH Calendar (#105) | 0%/0% | +43%/0% | 0%/0% | **PASS** |
| AVAX 3Layer | -63%/63% | -46%/49% | -24%/24% | **CATASTROPHIC** |
| SOL Pure Shield | -32%/32% | -43%/43% | 0%/0% | **CATASTROPHIC** |
| SOL AIShV2 | 0%/0% | -35%/38% | 0%/0% | **CATASTROPHIC** |
| Sentiment Shield | 0%/0% | +12%/4% | 0%/0% | **PASS** (but redundant) |
| BNB Rotation | -15%/15% | +2%/0% | -4%/4% | **FAIL** |
| DOGE Triple | 0%/0% | -17%/17% | 0%/0% | **FAIL** |

## Wallet sizing by verdict

| Verdict | Default wallet | Max wallet | Notes |
|---|---|---|---|
| PASS | $3,000 | $5,000 | Standard deploy |
| WARN | $2,000 | $3,000 | Reduce + monitor closely |
| FAIL | $0 | $0 | NO DEPLOYMENT |
| CATASTROPHIC | $0 | $0 | NO DEPLOYMENT + redesign architecture |

For PASS exceeding $5K, require explicit user authorization (sign-off in chat).

## Why these thresholds

- **-15% worst ROI**: empirically the threshold where deployment becomes psychologically painful for a fresh user. Below this, users hit the "kill the bot" button regardless of long-term math.

- **-30% / 30% DD**: empirically the threshold where DRAWDOWN itself is the failure (not just temporary loss). Bots with 30%+ DD almost never recover to ATH within reasonable timeframe.

- **2+ negative windows**: any single negative window could be bad luck. TWO suggests the strategy doesn't handle non-bull market structurally.

## Edge cases

### What if a strategy passes but is identical to existing?
PASS adversarial is necessary but not sufficient. Critic must ALSO check:
- Does it differ meaningfully from existing live bot on same coin?
- Does the new version add INDEPENDENT signal?
- Is the marginal improvement worth the operational overhead?

If "no" to any → likely VETO despite PASS.

### What if a strategy has 0 trades?
0 trades means:
- BEAR_2022: 0% (no trades = no loss = "passes" mechanically)
- But the strategy isn't doing anything

If across ALL backtests the trade count is < 3/year average, the strategy is essentially HODL or no-op. Don't deploy.

Minimum trade activity for deployment: ≥ 5 trades total over the 5-year backtest.

### What if WARN was caused by ONE outlier trade?
Read the trades.csv for that window. If WARN came from a single anomalous trade that exited at the worst possible moment, the strategy's logic might be sound but unlucky.

- If trade entry/exit looked WRONG → strategy has a bug, redesign
- If trade entry/exit looked RIGHT but market moved against → unfortunate but acceptable for WARN
- If trade should never have entered → strategy filter is wrong, fix

## When the thresholds need adjusting

The 2022/2025/2026Q12 windows will become stale. As of any review date, ask:
- Has the most recent bear (within 12 months) been included?
- Has a "current sideways" window been added if we're in one?
- Are old windows still RELEVANT to current market structure?

If windows are stale → update `ADVERSARIAL_WINDOWS` in `adversarial_validator.py` AND re-validate all currently-deployed bots against the new windows.

Stale gate → false sense of security.
