# Strategy Lab

Distilled methodology from a major AI integration session (15 hypotheses, 8 deploys, 11 rejections, fleet 21→29 bots).

This skill exists so future sessions don't repeat the 11 mistakes that were already paid for in time.

## Activation

```
/strategy-lab
```

Or invoke automatically when user asks to:
- Build a new bot
- Port a strategy to another coin
- Add an AI feature (calendar, sentiment, regime)
- Audit existing bots
- Evaluate any "what if X" hypothesis

## Structure

```
strategy-lab/
├── SKILL.md                  # Entry point — Claude reads this first
├── README.md                 # This file
├── docs/
│   ├── METHODOLOGY.md        # The 5-phase pipeline deep-dive
│   ├── PATTERNS.md           # 8 proven patterns with code
│   ├── ANTI_PATTERNS.md      # 10 ways to fail (with real examples)
│   └── CASE_STUDIES.md       # All 19 candidates from this session
├── templates/
│   ├── strategy_pure_shield.py.tmpl     # baseline regime
│   ├── strategy_sigmoid_v2.py.tmpl      # + halving + sigmoid
│   ├── strategy_calendar.py.tmpl        # + calendar tilts (STRONGEST)
│   ├── strategy_triple_regime.py.tmpl   # defensive sleeve
│   ├── strategy_vol_shield.py.tmpl      # high-vol coins
│   ├── config.json.tmpl
│   ├── docker-compose.yml.tmpl
│   └── insert_sub.sql.tmpl
├── scripts/
│   ├── run_pipeline.py       # End-to-end orchestrator
│   ├── deploy_bot.sh         # 4-artifact server deploy
│   └── analyze_archive.py    # Per-asset audit + portfolio sim
└── examples/
    ├── win_eth_calendar_shield.md       # strongest deploy of session
    ├── win_sol_volshield_v3.md          # 3-iteration discipline
    ├── loss_avax_3layer_overfit.md      # why we validate fresh
    ├── loss_sentiment_redundant.md      # redundancy detection
    └── loss_sol_pure_shield_transfer.md # vol-profile mismatch
```

## The 5-Phase Pipeline

| Phase | Action | Skip = | Tool |
|---|---|---|---|
| 1 | State hypothesis (1 sentence + pre-mortem) | Build the wrong thing | (human) |
| 2 | Build from template | Code from scratch | `templates/` |
| 3 | 6-window yearly backtest | Trust archive numbers | `research/ai/logged_backtest.py` |
| 4 | 3-window adversarial validation | Deploy overfit | `research/ai/adversarial_validator.py` |
| 5 | Deploy IF PASS or WARN | Lose money | `scripts/deploy_bot.sh` |

**Skipping any phase = recipe for one of the 11 failures documented in CASE_STUDIES.md.**

## The 7 Most Important Rules

(Full list in docs/METHODOLOGY.md)

1. **Single-window backtests are overfit by default** — always 6 yearly windows
2. **BTC indicators don't transfer to high-vol coins** — SOL/AVAX need vol_shield template
3. **Defensive sleeves are valid deployments** — Triple Regime alongside, even at lower return
4. **Test cheap signal before expensive pipeline** — FGI before FinBERT
5. **RL is overkill when heuristic gap < 5pp/yr** — use meta_allocator cron
6. **Calendar effects transfer; cycle phases don't** — port calendar tilts freely; not halving phases
7. **Honest rejection > silent overfit** — document every rejection with hypothesis + failure mode

## Quick-Start (5 minutes)

```bash
cd d:/pythone/freqtrade_btc_bot

# 1. Pick template + customize
# Example: port Calendar Shield to BNB
cp user_data/strategies/btc_calendar_shield_strategy.py \
   user_data/strategies/bnb_calendar_strategy.py
# Edit COIN constant, class name, anomaly filter

# 2. Config (copy + edit pair_whitelist + bot_name + db_url)
cp config.calendar.json config.calendar-BNB.json
# Edit pair_whitelist to ["BNB/USDT"]

# 3. 6 yearly backtests
for tr in 20210101-20220101 20220101-20230101 20230101-20240101 \
          20240101-20250101 20250101-20260101 20260101-20260601; do
  ./.venv/Scripts/python.exe -m research.ai.logged_backtest \
    --config config.calendar-BNB.json \
    --strategy BnbCalendarStrategy \
    --timerange "$tr" \
    --mode "Y_$(echo $tr | cut -c1-4)" \
    --notes "Port Calendar Shield to BNB — market-wide calendar effects hypothesis"
done

# 4. Adversarial gate
./.venv/Scripts/python.exe -m research.ai.adversarial_validator \
  --strategy BnbCalendarStrategy --config config.calendar-BNB.json \
  --name BnbCalendar --skip-baselines

# 5. If PASS/WARN: deploy. If FAIL/CATASTROPHIC: document in examples/loss_*.md and stop.
bash C:/Users/user/.claude/skills/strategy-lab/scripts/deploy_bot.sh \
  calendar-bnb 3000
```

## What Lives Where (the freqtrade_btc_bot repo)

| Asset | Location |
|---|---|
| Strategy code | `user_data/strategies/<name>_strategy.py` |
| Configs | `config.<name>.json` |
| Docker compose | `docker-compose.<name>.yml` |
| Backtest archive | `research/experiments/<timestamp>__...` |
| Archive index | `research/experiments/INDEX.csv` |
| Tools | `research/ai/*.py` |
| Reports | `research/ALL_BATCHES_FINAL.md` |

## What the skill does NOT replace

- The actual tools (logged_backtest, adversarial_validator, etc.) — they live in the repo
- Your judgment about portfolio allocation
- Real money exposure decisions (always require explicit user approval for live trading)

## When you're stuck

Read in order:
1. `docs/METHODOLOGY.md` — phase you're stuck at
2. `docs/ANTI_PATTERNS.md` — make sure you're not making a known mistake
3. `examples/` — concrete cases that match your situation
4. `docs/PATTERNS.md` — copy a code skeleton

## Live deployment state (as of session end)

Fleet: 29 bots / 57 containers on trad-server.

| Coin | Live bots | Sub IDs |
|---|---|---|
| BTC | AI Shield V2, Triple, Calendar | #98, #99, #100 |
| ETH | DynRebal (existing), Pure Shield, **Calendar Shield** | #101, **#105** |
| SOL | DynRebal (existing), **VolShield v3** | #102 |
| BNB | Pure Shield (existing), Triple | #103 |
| ADA | MetaAdaptive (existing), Triple | #104 |
| DOGE | Pure Shield Defensive (existing) | — open challenge |
| AVAX | MetaReliable (existing) | — no upgrade found |

**Strongest deploy:** ETH Calendar Shield (#105), +55%/yr backtest, PASS adversarial.

## Methodology origin

Built from one session (2026-06-02 → 2026-06-03). The session tested:
- 18 ideas from a master plan
- 4 additional extensions in a final batch
- = 22 total candidates
- → 8 deploys + 11 rejections + 3 research-only

Each phase rule in this skill came from at least one real failure. The Adversarial Validator concept came from being burned by archive cherry-picking on AVAX 3Layer. The volatility-aware template came from 3 SOL failures.

**This is paid-for wisdom. Don't pay for it twice.**
