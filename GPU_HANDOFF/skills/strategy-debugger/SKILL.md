---
name: strategy-debugger
description: Debugger for strategies that behave unexpectedly. Investigates "why didn't bot X enter on date Y", "why did it exit early", "why is live different from backtest", trace through populate_indicators output, inspect trade-level details. Use when user asks "debug this bot", "trace why X happened", "inspect a trade", "explain this behavior", "find the bug". Read-write inspection (no code changes without approval).
---

# Strategy Debugger — Investigation Engine

The forensic skill. When a strategy does something unexpected, this skill traces back the WHY.

For monitoring (no specific investigation), use `fleet-monitor`. For research-level pattern mining, use `strategy-researcher`. For deploy decisions after findings, use `strategy-critic`.

## When to invoke

- "Why didn't bot X enter on date Y?"
- "Why did it exit so early?"
- "Why is live different from backtest?"
- "Inspect trade #N"
- "Debug this behavior"
- "Trace the regime detection"
- "Why is target_position 0?"
- "Find the bug"

## Investigation playbooks

### Playbook 1: "Why didn't it enter?"

User reports: "I expected bot X to be long on date Y, but it's flat."

Steps:
1. Pull `trades.csv` for the run (or live DB) — confirm no trade exists
2. Pull `raw_payload.json` from experiment archive — get the dataframe snapshot if available
3. Re-run `populate_indicators` for that date:
```python
# in freqtrade backtest with --enable-trade-export, dataframe dumps are available
import pandas as pd
df = pd.read_feather("user_data/data/binance/<COIN>_USDT-1d.feather")
df["date"] = pd.to_datetime(df["date"], utc=True)
df_subset = df[df["date"] <= "2025-XX-YY"].tail(250)
# Re-run strategy's populate_indicators manually
from user_data.strategies.<file> import <ClassName>Strategy
strat = <ClassName>Strategy()
result = strat.populate_indicators(df_subset, {"pair": "<COIN>/USDT"})
print(result.tail(10)[["close", "regime_confirmed", "ai_target", "anomaly"]])
```

4. Check each entry condition:
   - `df["regime_confirmed"] == "BULL"`?
   - `df["ai_target"] > 0.15`?
   - `df["anomaly"] == 0`?
5. Find which condition FAILED → that's the answer

Common findings:
- regime_confirmed = NEUTRAL (not enough days of BULL signal)
- ai_target < 0.15 (cycle_phase = BEAR drove target low)
- anomaly = 1 (Isolation Forest flagged the day)
- Data not yet caught up (last row is older than expected)

### Playbook 2: "Why did it exit early?"

User: "Bot X exited on date Y but I expected it to hold."

Steps:
1. Pull the specific trade from `trades.csv` (look at `exit_tag`)
2. The exit_tag tells you WHY:
   - `<strategy>:exit` (regime → BEAR) → check `regime_confirmed` on exit date
   - `<strategy>:exit` (anomaly) → check `anomaly_flags.feather` for that date
   - `<strategy>:exit` (target < 0.20) → cycle_phase shift mid-trade
3. Cross-reference with price action: was the exit "right" given hindsight?

If exit was "wrong" (price went up after), the strategy might be too sensitive. Note for future tuning.

### Playbook 3: "Live diverges from backtest"

User: "I deployed bot X with +47%/yr backtest, but live is -5% after 60 days."

Steps:
1. Pull live trades from `trad_pg.trades` for that subscription
2. Pull recent backtest from `INDEX.csv` for same strategy + similar timerange
3. Compare metrics:

| Metric | Backtest | Live | Diff |
|---|---|---|---|
| n_trades / 60d | ? | ? | ? |
| Avg trade duration | ? | ? | ? |
| Win rate | ? | ? | ? |
| Avg PnL per trade | ? | ? | ? |

4. If n_trades differs by 2x+ → ENTRY CONDITIONS are firing differently → check current data vs backtest data for the same date
5. If win rate differs → STRATEGY IS WORKING but market shifted → expected drift, monitor
6. If avg duration differs → EXIT TIMING differs → check exit_tag distribution

### Playbook 4: "Why is the dataframe wrong?"

User: "I think populate_indicators is computing something wrong."

Steps:
1. Reproduce the dataframe slice that's problematic:
```python
import pandas as pd
import talib.abstract as ta
from user_data.strategies.<file> import <ClassName>Strategy

df = pd.read_feather("user_data/data/binance/<COIN>_USDT-1d.feather")
df["date"] = pd.to_datetime(df["date"], utc=True)
df = df.sort_values("date").reset_index(drop=True)

# Limit to a specific window
df = df[(df["date"] >= "2025-01-01") & (df["date"] <= "2025-03-01")].copy()

strat = <ClassName>Strategy()
result = strat.populate_indicators(df, {"pair": "<COIN>/USDT"})
print(result[["date", "close", "ema200", "ret_30d", "adx", "regime_confirmed", "ai_target"]].to_string())
```

2. Walk through column by column, verify values are sensible
3. Common bugs:
   - **NaN propagation**: ema200 needs 200 candles of warmup; if data starts late, first 200 rows are NaN
   - **Wrong rolling window**: `.rolling(30)` with insufficient data → NaN
   - **Timezone mismatch**: comparing UTC with naive datetime → silent wrong filter
   - **Path resolution**: aux file (anomaly, halving) not loaded → all 0s
   - **String rolling**: `.rolling().apply()` on string Series → silent crash to NaN

### Playbook 5: "Bot has 0 trades over 5 years"

User: "Backtest shows 0 trades."

This is usually a build issue, not a strategy issue. Check:

1. Strategy file syntax (`import` errors, missing class)
2. Config has correct `strategy` name matching class
3. Pair whitelist matches available data
4. Timerange has data for that pair
5. Entry conditions are not impossibly strict (e.g. atr_pct < 0.05 on a coin with 10% daily vol)

The SOL VolShield v1 had this exact issue. Loosen thresholds incrementally.

### Playbook 6: "Trade was opened but PnL is wrong"

User: "Live shows trade opened but PnL doesn't match my math."

Steps:
1. Pull the trade row from `trad_pg.trades`
2. Check `entry_price`, `exit_price`, `amount`, `pnl` columns
3. Compare to expected: `pnl = (exit_price - entry_price) * amount - fees`
4. If wrong:
   - Was `amount` reduced via `adjust_trade_position`? Look for partial fills
   - Were fees deducted? Binance spot ~0.1%, USDT pairs
   - Was this a multi-leg position? (rebalance trades)

### Playbook 7: "Container crashed / restart loop"

User: "Bot X keeps restarting."

Steps:
1. SSH and inspect logs:
```bash
ssh trad-server 'docker logs freqtrade_X --tail 200'
```
2. Common crashes:
   - **Module import error**: strategy file has syntax error → fix code, restart
   - **API connection refused**: Binance rate-limit or DNS → wait, monitor
   - **Database locked**: SQLite file corruption → restart, rebuild SQLite
   - **Out of memory**: large rolling window or memory leak → reduce window
3. If unfixable in code: stop the container, leave for investigation

## Tools

### Existing in repo
- `research/ai/logged_backtest.py` — run focused backtests on small windows
- `research/experiments/INDEX.csv` — archive of all backtests
- `research/experiments/<run>/trades.csv` — per-trade detail
- `research/experiments/<run>/raw_payload.json` — full freqtrade output

### Provided by this skill
- `scripts/inspect_dataframe.py` — re-runs populate_indicators for any (strategy, coin, date_range)
- `scripts/why_no_entry.py` — for a given date, walks through entry conditions and prints which failed
- `scripts/trace_trade.py` — given trade_id, reconstructs the decision chain
- `scripts/live_vs_backtest_trade_diff.py` — compares a specific trade to expected

## Output style

For each investigation, produce:

```
=== Debug: <issue summary> ===

Subject: <strategy> on <coin>, date(s) <range>

Findings:
1. <Finding 1>
2. <Finding 2>
...

Root cause: <one sentence>

Evidence:
- <data point 1>
- <data point 2>

Recommended action:
[ ] Bug fix in code: <specific file + line>
[ ] Parameter tuning: <which parameter, what value>
[ ] Data refresh: <which feather file>
[ ] No action (expected behavior)
[ ] Escalate to <skill>

Confidence in diagnosis: low/medium/high
```

## Common bugs catalogue (from prior debugging sessions)

### Bug 1: Rolling on string Series
```python
# WRONG (silently produces NaN)
df["regime_rolled"] = df["regime_str"].rolling(3).apply(...)

# RIGHT (use int codes)
rcode = pd.Series(0.0, ...); rcode[bull] = 1.0; rcode[bear] = -1.0
df["regime"] = rcode.rolling(3, min_periods=3)...
```

### Bug 2: Set_index on already-indexed DataFrame
```python
# WRONG (KeyError or silent failure)
_ANOMALY[["date", "is_anomaly"]].set_index("date")  # if date is already index

# RIGHT
_ANOMALY[["is_anomaly"]]  # date is preserved as index
```

### Bug 3: Path resolution inside docker
```python
# WRONG (relative path)
df = pd.read_feather("user_data/data/foo.feather")

# RIGHT (candidate paths)
for p in [Path("/freqtrade/user_data/data/foo.feather"),
          Path(__file__).parents[2] / "user_data" / "data" / "foo.feather"]:
    if p.exists(): df = pd.read_feather(p); break
```

### Bug 4: Anomaly coin filter mismatch
```python
# WRONG (using BTC anomalies on ETH bot)
anom = _ANOMALY  # no coin filter

# RIGHT (filter by coin)
anom = _ANOMALY[_ANOMALY["coin"] == COIN][["is_anomaly"]]
```

### Bug 5: Off-by-one in rolling confirmation
```python
# WRONG (N=3 requires 3 confirmations, but min_periods missing means partial windows count)
rmin = rcode.rolling(3).min()

# RIGHT
rmin = rcode.rolling(3, min_periods=3).min()
```

## When debugging requires user input

Pause and ask the user when:
- Behavior MIGHT be intentional (e.g. WARN strategy has -12% in 2022; user might find this acceptable)
- Multiple plausible causes need user judgment to pick
- Code fix would change strategy semantics (require re-validation through critic)
- Investigation suggests deeper architectural issue (escalate to `strategy-architect`)
