# Methodology — The 5-Phase Pipeline (Deep Dive)

## Why this exists

Crypto strategy development is dominated by survivorship bias and cherry-picking. Strategies that look great in backtests fail live because:

1. The backtest window happened to cover the strategy's good era
2. Indicators were tuned to past noise (overfit)
3. Bear-market behavior was never tested
4. Single metric (ROI or Sharpe alone) hid catastrophic drawdowns

This methodology forces the answers OUT into the open before money is at risk.

---

## Phase 1 — Hypothesis

### Why a sentence

If you can't say "X improves over Y on Z because W" in one sentence, you don't have a hypothesis — you have an experiment. Experiments are fine, but call them that.

### Good hypotheses (from this session)

| Strategy | Hypothesis |
|---|---|
| AI Shield V2 | Sigmoid sizing improves over flat BASE on BTC because halving cycles produce non-linear opportunity |
| Calendar Shield | October tilt improves over V2 on BTC because Oct +0.54%/day p=0.002 |
| ETH Pure Shield | Shield improves over DynRebal on ETH because DynRebal HODLs through 2022 bear |
| SOL VolShield v3 | Stricter chop filters improve over Pure Shield on SOL because SOL vol = 95% (vs BTC 55%) |

### Bad hypotheses (smell test)

- "X might be interesting to try" — no claim, no test
- "X works in 2021" — single window
- "X is more sophisticated than Y" — sophistication ≠ improvement
- "X uses ML" — algorithm choice isn't a hypothesis

### Pre-mortem question

Before running anything, ask: **"If this strategy fails Adversarial, what specifically would the failure look like?"**

If you can't answer, you're not ready to run.

Example pre-mortem (AVAX 3Layer):
- Hypothesis: 3Layer's higher Sharpe transfers to AVAX
- Pre-mortem: "Could fail if archive results came from cycle-favorable windows"
- This warning saved no money (we ran anyway and got -63% in 2022) BUT the pre-mortem made it easy to interpret the failure.

---

## Phase 2 — Build

### Start from a template

Templates encode the proven scaffolding:
- `populate_indicators` with stable EMA + ADX + ret_Nd
- N-day regime confirmation pattern (3 for BTC, 5 for SOL)
- `custom_stake_amount` reading from the indicator dataframe
- `adjust_trade_position` with drift-based rebalance (5% buy, 10% sell trigger)

### What to customize

ONLY change what the hypothesis names:
- Hypothesis: "calendar tilt" → ADD `is_october` etc, KEEP everything else
- Hypothesis: "vol filter" → ADD `atr_pct`, KEEP regime detection

### What NOT to add

- Stoploss tuning (use the universal -0.99 — exits happen via regime/anomaly signals, not SL)
- ROI table (use `{"0": 10.0}` — exits via signals)
- Stochastic / RSI / etc unless the hypothesis specifically uses them
- "Just one more indicator" — every added feature multiplies overfit risk

### Code anti-patterns to flag

```python
# WRONG: rolling on string Series
df["regime_3d"] = df["regime_str"].rolling(3).apply(...)  # crashes

# RIGHT: use integer codes, ffill, then map back
rcode = pd.Series(0.0, index=df.index)
rcode[bull] = 1.0
rcode[bear] = -1.0
rmin = rcode.rolling(3, min_periods=3).min()
rmax = rcode.rolling(3, min_periods=3).max()
stable = rmin == rmax
df["regime_code"] = rcode.where(stable, other=pd.NA).ffill().fillna(0)
df["regime"] = df["regime_code"].map({1.0: "BULL", -1.0: "BEAR", 0.0: "NEUTRAL"})
```

```python
# WRONG: assuming column exists when it's actually the index
btc_anom = _ANOMALY[_ANOMALY["coin"] == "BTC"][["date", "is_anomaly"]].set_index("date")
# _ANOMALY already has date as index, so "date" isn't a column — silently fails

# RIGHT: use the existing index
btc_anom = _ANOMALY[_ANOMALY["coin"] == "BTC"][["is_anomaly"]]
```

```python
# WRONG: hardcoded path
df = pd.read_feather("user_data/data/foo.feather")  # breaks inside docker

# RIGHT: candidate paths
candidates = [
    Path("/freqtrade/user_data/data") / name,           # docker
    Path(__file__).resolve().parents[1] / "data" / name, # local strategies/
    Path(__file__).resolve().parents[2] / "user_data" / "data" / name,
]
for p in candidates:
    if p.exists():
        return pd.read_feather(p)
```

---

## Phase 3 — Backtest

### The yearly grid is non-negotiable

```
2021    bull peak (everything wins here)
2022    BEAR (this is where most strategies die)
2023    recovery (volatile but trending)
2024    mid-cycle (chop + smaller moves)
2025    SIDEWAYS (this is where overfit shows up)
2026Q12 current bear continuation
```

Running just one window = no information about robustness.

### Compound calculation

```python
compound = 1.0
for r in yearly_rois:  # e.g. [121.6, 0, 50.4, 36.4, 13.9, 0]
    compound *= (1 + r/100)
annual = compound ** (1/5) - 1
print(f"Compound: ${10000 * compound:,.0f}  Annual: {annual*100:.1f}%/yr")
```

### Sharpe interpretation

In single-position 1d strategies with few trades/year:
- Sharpe > 0.5 is excellent
- Sharpe 0.2-0.5 is good
- Sharpe < 0.1 is fine if compound is strong (few trades distort)
- Sharpe = -100 is a freqtrade sentinel for "not enough trades" — ignore

### Number of trades matters

- 1 trade/year = HODL with timing — easy to win in bulls, hard to validate
- 5-15 trades/year = the sweet spot for shield/regime strategies
- 30+ trades/year = scalper territory, daily 1d strategies shouldn't be here

If trades/year is wildly off, something's wrong with the entry conditions.

---

## Phase 4 — Adversarial Validation (THE GATE)

### Why these 3 specific windows

- **BEAR_2022** (20220101-20230101): the recent textbook bear, -65% on BTC, -77% on ETH, -94% on SOL
- **SIDEWAYS_2025** (20250101-20260101): low-direction chop, kills mean-reversion overfit
- **BEAR_2026Q12** (20260101-20260601): current ongoing bear, includes today

If a strategy can survive all 3, it has SOMETHING resembling robustness. If it fails 2+, it's overfit.

### Verdict logic

```python
def verdict(roi_2022, dd_2022, roi_2025, dd_2025, roi_26Q12, dd_26Q12):
    worst_roi = min(roi_2022, roi_2025, roi_26Q12)
    worst_dd  = max(dd_2022, dd_2025, dd_26Q12)
    n_negative = sum(1 for r in [roi_2022, roi_2025, roi_26Q12] if r < 0)

    if worst_roi < -30 or worst_dd > 30:
        return "CATASTROPHIC"
    if n_negative >= 2 or worst_roi < -15:
        return "FAIL"
    if n_negative == 1 and worst_roi >= -15:
        return "WARN"
    return "PASS"
```

### What to do with each verdict

| Verdict | Action |
|---|---|
| PASS | Deploy with full $3-5K wallet |
| WARN | Deploy with reduced $2-3K wallet |
| FAIL | **Do not deploy.** Document in `examples/loss_*.md` |
| CATASTROPHIC | **Do not deploy.** Document AND extract lesson |

### The temptation

When a strategy fails adversarial but has high compound (e.g. SOL DynRebal: -87% in 2022 but +40%/yr compound), the temptation is to deploy "because the bull years dominate."

This is wrong because:
- New deployments START NOW, in a possible bear
- A user putting $3K in at the wrong time experiences -87% — they don't see the future +509%
- Compound math is HISTORY, not future return

**Rule: a strategy that loses 87% in one window is a strategy that could lose 87% next year.**

---

## Phase 5 — Deploy

### The 4 artifacts

1. **DB SQL** (atomic): `strategies` row + `user_strategy_subscriptions` row
2. **Docker Compose**: freqtrade container + bridge container
3. **Env file**: bridge subscription ID, DSN, poll interval; chmod 600
4. **Server sync + up**: scp/tar to trad-server, docker compose up

### Wallet sizing

Default: $3,000 for PASS, $2,000 for WARN.

Adjustments:
- New coin entirely (no prior bot): $2,000 (be conservative)
- Coin already has 2+ bots: $2,000 (don't over-concentrate)
- Defensive sleeve (Triple-style): $2,000 (lower expected return)
- Strongest of session backtest: $3,000-5,000

NEVER exceed $5,000 on any single bot without explicit user approval.

### Post-deployment checks

After `docker compose up`:

```bash
ssh trad-server 'docker ps --filter "name=freqtrade_<name>" --format "table {{.Names}}\t{{.Status}}"'
# Both bot and bridge should show "Up X seconds"
```

After 24h, verify:
- Bot is heartbeating (check log file size growing)
- Bridge is polling (no error spam in log)
- DB subscription is `active`

If anything's wrong, `docker compose -f docker-compose.<name>.yml --env-file .env.<name> down` immediately and investigate.

---

## Phase 0 — When to NOT deploy at all

Sometimes the right answer is "don't build this."

Triggers:
- Hypothesis is vague ("AI might help")
- The signal is already captured by existing features (Sentiment was redundant with cycle_phase)
- The expected uplift is < 2pp/yr (not worth the maintenance)
- The coin's existing live bot is already passing adversarial with strong compound

When you hit these, write a 1-paragraph note and move on. Don't try to make a marginal idea work by adding complexity.
