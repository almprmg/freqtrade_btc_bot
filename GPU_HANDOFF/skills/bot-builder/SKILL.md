---
name: bot-builder
description: Practical bot builder for the freqtrade + trad_system architecture. Generates strategy files, configs, docker-compose, SQL inserts, deploys to trad-server. Use AFTER a hypothesis is clear and an archetype is chosen (consult strategy-architect first). Invoke when user says "build me a bot", "deploy this strategy", "generate the code for X", "create config for Y", "port BtcCalendarShield to ETH". Does NOT decide what to build — only HOW to build it.
---

# Bot Builder — Code & Deployment

The action skill. Once you know WHAT you want, this builds it.

For DESIGN decisions (which archetype, why), use `strategy-architect`.
For RESEARCH (what works historically), use `strategy-researcher`.
For VALIDATION (is it safe?), use `strategy-critic`.
For NEW IDEAS, use `strategy-explorer`.

## When to invoke

- "Build a calendar shield bot for SOL"
- "Generate the docker-compose for this strategy"
- "Deploy this to trad-server"
- "Create the SQL for sub #106"
- "Port my BTC strategy to ETH"

## What this skill produces

For a single new bot, FOUR artifacts:

1. **Strategy file** (`user_data/strategies/<slug>_strategy.py`)
2. **Config file** (`config.<slug>.json`)
3. **Docker compose** (`docker-compose.<slug>.yml`)
4. **DB SQL insert** (`d:/tmp/<slug>_insert.sql`)

Plus optional: server deploy via `scripts/deploy_bot.sh`.

## Templates

Located in `templates/`:

| Template | When to use |
|---|---|
| `strategy_pure_shield.py.tmpl` | Baseline, low-vol coins (BTC, ETH, BNB) |
| `strategy_sigmoid_v2.py.tmpl` | BTC with halving phase shifts + smooth sizing |
| `strategy_calendar.py.tmpl` | Strongest — V2 + calendar tilts (BTC, ETH) |
| `strategy_triple_regime.py.tmpl` | Defensive sleeve (any coin where primary fails adversarial) |
| `strategy_vol_shield.py.tmpl` | High-vol coins (SOL, AVAX, ann.vol > 80%) |
| `config.json.tmpl` | Universal config |
| `docker-compose.yml.tmpl` | Container deployment |
| `insert_sub.sql.tmpl` | DB strategy + subscription rows |

## Template variables

All `.tmpl` files use `{{ var }}` syntax. Common variables:

| Variable | Example | Purpose |
|---|---|---|
| `ClassName` | `EthCalendarShield` | Python class name |
| `COIN` | `ETH` | 3-4 letter coin symbol |
| `slug` | `eth_calendar` | snake_case identifier (file names, DB) |
| `bot_name` | `eth_calendar` | freqtrade `bot_name` |
| `hypothesis` | "Calendar tilts port from BTC to ETH because day-of-week is market-wide" | 1-sentence rationale |
| `tag` | `eth-calendar` | enter_tag prefix |
| `n_confirm` | `3` (BTC/ETH/BNB) `5` (SOL/AVAX) `4` (DOGE) | regime confirmation days |
| `wallet_usd` | `3000` | DB allocated_capital |
| `backtest_summary` | "+55%/yr 5y" | for compose comment |
| `adversarial_verdict` | `PASS` | for compose + SQL comment |
| `display_name` | `ETH Calendar Shield` | DB display_name |
| `description` | longer paragraph | DB description field |

## The build sequence (5 steps)

### Step 1: Gather inputs

Before generating ANY file, confirm:
- [ ] Coin symbol (BTC/ETH/SOL/etc.)
- [ ] Archetype (which template)
- [ ] Hypothesis (1 sentence)
- [ ] Backtest results (annual ROI %)
- [ ] Adversarial verdict (PASS/WARN — if FAIL/CATASTROPHIC: STOP, redirect to strategy-critic)
- [ ] Wallet size (default $3K for PASS, $2K for WARN)
- [ ] Class name (CamelCase, ends with "Strategy")
- [ ] Slug (snake_case, no "_strategy" suffix)

If any are missing, ASK before building.

### Step 2: Generate strategy file

```python
# Pseudo-code (use Edit/Write tools in practice)
import string
tmpl = read("templates/strategy_<archetype>.py.tmpl")
content = tmpl.replace("{{ ClassName }}", className) \
              .replace("{{ COIN }}", coin) \
              .replace("{{ hypothesis }}", hypothesis) \
              .replace("{{ n_confirm }}", str(n_confirm)) \
              .replace("{{ tag }}", tag)
write(f"d:/pythone/freqtrade_btc_bot/user_data/strategies/{slug}_strategy.py", content)
```

Then DISPLAY the file to user for review before continuing.

### Step 3: Generate config

```python
tmpl = read("templates/config.json.tmpl")
content = tmpl.replace("{{ ClassName }}", className) \
              .replace("{{ COIN }}", coin) \
              .replace("{{ slug }}", slug) \
              .replace("{{ bot_name }}", slug) \
              .replace("{{ hypothesis }}", hypothesis)
write(f"d:/pythone/freqtrade_btc_bot/config.{slug}.json", content)
```

### Step 4: Generate docker-compose + SQL

Same pattern with the remaining templates. The SLUG_UPPER substitution in docker-compose.yml.tmpl:

```python
slug_upper = slug.upper()
```

### Step 5: Deploy (optional, only on user request)

```bash
bash scripts/deploy_bot.sh <slug> <wallet_usd>
```

This script:
1. Tar+ssh artifacts to trad-server
2. Run SQL via docker exec on trad_pg
3. Capture sub_id, write .env file with chmod 600
4. docker compose up -d
5. Verify both bot+bridge containers Up

## Common mistakes (and how to avoid)

### Mistake 1: Wrong N_CONFIRM
Always verify via `coin_profiles.md`:
- BTC/ETH/BNB/ADA: N=3
- DOGE: N=4
- SOL/AVAX: N=5

### Mistake 2: Wrong COIN constant inside strategy
The strategy's `COIN = "..."` constant filters anomaly_flags.feather by coin. If you set COIN="BTC" when building for ETH, you'll use BTC's anomaly flags on ETH data. SILENT FAILURE.

### Mistake 3: Strategy file has BTC-specific code that needs editing
Templates use BTC-specific `_HALVING` loading. For non-BTC coins on the Sigmoid V2 or Calendar template, `_HALVING` will load but `cycle_bias` will still apply BTC's phase. This MAY produce inferior results (see Idea F failure: per-asset cycles).

If non-BTC: set PHASE_SHIFTS to all 0.0, or use `strategy_pure_shield` / `strategy_vol_shield` instead.

### Mistake 4: Wallet > $5K without explicit approval
Default is $3K (PASS) or $2K (WARN). Never go higher without the user explicitly approving the amount.

### Mistake 5: Deployment without verifying templates compiled cleanly
Always READ the generated files back and visually confirm `{{ var }}` strings are all substituted. Missed substitutions break runtime.

## Sanity checks before commit

After generating files, run these checks:

```bash
# 1. Strategy file is valid Python
./.venv/Scripts/python.exe -c "import importlib.util; \
  spec = importlib.util.spec_from_file_location('s', 'user_data/strategies/<slug>_strategy.py'); \
  m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); \
  print('OK:', m.__all__)"

# 2. Config is valid JSON
./.venv/Scripts/python.exe -c "import json; json.load(open('config.<slug>.json')); print('OK')"

# 3. Run a quick 30-day backtest to verify it doesn't crash
./.venv/Scripts/python.exe -m research.ai.logged_backtest \
  --config config.<slug>.json --strategy <ClassName>Strategy \
  --timerange 20250101-20250201 --mode SMOKE_TEST \
  --notes "smoke test for build"
```

If smoke test fails → fix before proceeding to full backtest.

## Multi-bot deployments

For deploying SEVERAL bots in one batch (like the BNB+ADA Triple + ETH Calendar batch in the major session):

1. Generate ALL artifacts first
2. Combine SQL INSERTs into one transaction
3. Use a single docker-compose.<batch_name>.yml with multiple services
4. Deploy in one `docker compose up -d` call
5. Verify ALL containers running before declaring success

Example: `docker-compose.final-batch.yml` from the major session deployed 3 bots (#103, #104, #105) at once.

## Don't build if...

The skill should REFUSE to build (or warn loudly) when:

- Adversarial verdict is FAIL or CATASTROPHIC → redirect to `strategy-critic` for review
- Wallet > $5K without explicit user approval
- Coin already has 3+ live bots (don't over-concentrate)
- Strategy name conflicts with existing class (would silently fail at deploy)
- No hypothesis provided (means user is exploring, not building — redirect to `strategy-explorer`)

## Output style

When generating, communicate concisely:

```
Generating SolNewShield for SOL/USDT...
  Template: strategy_vol_shield.py.tmpl
  Hypothesis: <hypothesis>
  
  ✓ Strategy:   d:/pythone/freqtrade_btc_bot/user_data/strategies/sol_new_shield_strategy.py
  ✓ Config:     d:/pythone/freqtrade_btc_bot/config.sol_new_shield.json
  ✓ Compose:    d:/pythone/freqtrade_btc_bot/docker-compose.sol_new_shield.yml
  ✓ SQL:        d:/tmp/sol_new_shield_insert.sql

Next: bash scripts/deploy_bot.sh sol_new_shield 3000
```

Don't paste full file contents back unless user asks.
