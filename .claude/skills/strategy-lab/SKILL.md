---
name: strategy-lab
description: Top-level orchestrator for the 12 specialized crypto trading skills covering research, development, validation, deployment, operations, monitoring, risk, and reporting. Use as the entry point when a task spans multiple skills or when unsure which specialized skill to invoke. Routes to the right sub-skill at each phase.
---

# Strategy Lab — Orchestrator (12 specialized skills)

The umbrella skill. Routes work between the 12 specialized skills based on intent.

## DEVELOPMENT (5 skills) — building strategies

| Skill | Role | Invoke when |
|---|---|---|
| `strategy-architect` | Market expert / reference knowledge | "Is X a fit for Y?", "Tell me about Z" |
| `strategy-researcher` | Archive miner / factor discoverer | "Mine the data", "What works historically?" |
| `strategy-explorer` | Hypothesis generator | "Give me new ideas", "What should we try?" |
| `bot-builder` | Code generator + deployer | "Build me a bot", "Deploy this" |
| `strategy-critic` | Adversarial reviewer / deploy gate | "Is this safe?", "Review before deploy" |

## OPERATIONS (4 skills) — running the fleet

| Skill | Role | Invoke when |
|---|---|---|
| `fleet-monitor` | Daily health watcher | "Bot status", "Any alerts", "How's the fleet" |
| `data-engineer` | Data pipeline maintainer | "Refresh data", "Update OHLCV", "Stale data" |
| `strategy-debugger` | Diagnose unexpected behavior | "Why didn't it enter?", "Trace this trade" |
| `portfolio-risk-manager` | Capital allocation + risk | "Total exposure", "Concentration", "Kill switches" |

## ADVANCED (3 skills) — going live, reporting, macro

| Skill | Role | Invoke when |
|---|---|---|
| `live-trading-ops` | Dryrun → live transition (HIGH RISK) | "Go live", "Real money", "Production exchange" |
| `performance-reporter` | Weekly/monthly reports | "Generate report", "Weekly summary" |
| `market-analyst` | Macro / sector context | "BTC dominance", "Sector rotation", "Macro" |

## When to invoke `strategy-lab` directly

Only when:
- Task spans multiple skills (full pipeline)
- User is unsure which to invoke
- Need orchestration logic ("do A, then B based on result")

For specific asks, INVOKE THE SUB-SKILL DIRECTLY. Don't always route through strategy-lab.

## The end-to-end pipeline (when full lab orchestration is needed)

```
1. EXPLORER → generates 3-5 hypotheses
        ↓
2. ARCHITECT → confirms hypothesis is sound (market context)
        ↓
3. RESEARCHER → checks if archive supports/contradicts
        ↓
4. BUILDER → generates code + config + compose + SQL
        ↓
5. (User runs 6-window backtest)
        ↓
6. CRITIC → runs adversarial + checks overfit signals
        ↓
7. BUILDER → deploys (only if CRITIC approves)
        ↓
8. RESEARCHER → tracks live vs backtest divergence over time
```

Each step can be invoked individually. The orchestrator chains them when the user wants "the full workflow."

## Mapping user intent → which skill(s)

### Development asks
| User says | Primary skill | Secondary |
|---|---|---|
| "Build a new bot" | bot-builder | architect, critic |
| "Port X to coin Y" | bot-builder | architect (vol-check), critic |
| "What should I try?" | strategy-explorer | researcher, architect |
| "Mine the archive" | strategy-researcher | — |
| "Find common factors" | strategy-researcher | — |
| "Review this candidate" | strategy-critic | — |
| "Tell me about SOL strategies" | strategy-architect | — |
| "Give me 5 ideas" | strategy-explorer | researcher |

### Operations asks
| User says | Primary skill | Secondary |
|---|---|---|
| "How are the bots?" | fleet-monitor | — |
| "Any alerts?" | fleet-monitor | strategy-debugger (if alerts) |
| "Refresh data" | data-engineer | — |
| "Update OHLCV" | data-engineer | — |
| "Why didn't bot X enter?" | strategy-debugger | architect (if root cause is design) |
| "Trace this trade" | strategy-debugger | — |
| "Total exposure?" | portfolio-risk-manager | — |
| "Should I deactivate Y?" | portfolio-risk-manager | — |
| "Rebalance" | portfolio-risk-manager | — |

### Advanced asks
| User says | Primary skill | Secondary |
|---|---|---|
| "Go live" | live-trading-ops | risk-manager, critic |
| "Generate weekly report" | performance-reporter | — |
| "Monthly summary" | performance-reporter | — |
| "BTC dominance?" | market-analyst | — |
| "Macro context" | market-analyst | — |
| "Should we onboard ARB?" | market-analyst | architect, explorer |

### Full pipeline
"Develop end-to-end" → invoke this orchestrator, it chains the 5 development skills.

## State of the production system (as of session end)

This block is auto-updated by the lab. Reflects what's actually live.

**Fleet:** 29 bots / 57 containers on trad-server (72.62.179.86)

**Live deploys from major session:**

| Sub | Bot | Coin | Strategy | Wallet | Adv Verdict | Backtest |
|---|---|---|---|---|---|---|
| #98 | freqtrade_ai_shield_v2 | BTC | BtcAiShieldV2 | $5K | PASS | +36.5%/yr |
| #99 | freqtrade_triple | BTC | BtcTripleRegime | $2K | PASS | +10.5%/yr |
| #100 | freqtrade_calendar | BTC | BtcCalendarShield | $3K | PASS | +38.2%/yr |
| #101 | freqtrade_eth_shield | ETH | BtcRegimeShield | $3K | WARN | +47%/yr |
| #102 | freqtrade_sol_vol_shield | SOL | SolVolShield | $3K | WARN | +45%/yr |
| #103 | freqtrade_bnb_triple | BNB | BtcTripleRegime | $2K | WARN | +17.7%/yr |
| #104 | freqtrade_ada_triple | ADA | BtcTripleRegime | $2K | PASS | +14.4%/yr |
| #105 | freqtrade_eth_calendar | ETH | BtcCalendarShield | $3K | PASS | +55%/yr 🏆 |

**Open challenges:**
- DOGE bear protection (4 candidates failed adversarial)
- meta_allocator activation (cron running dry, needs 30+ days)

## File layout (where things live)

```
.claude/skills/
├── strategy-lab/         ← orchestrator (this skill)
│   ├── SKILL.md
│   ├── README.md
│   ├── docs/             ← legacy methodology docs (use sub-skill docs first)
│   └── examples/         ← case studies (8 wins + 11 rejections)
│
├── strategy-architect/   ← market expert
│   ├── SKILL.md
│   └── knowledge/        ← coin profiles, regime taxonomy, patterns
│
├── bot-builder/          ← code generator
│   ├── SKILL.md
│   ├── templates/        ← 5 strategy + config + compose + SQL templates
│   └── scripts/          ← deploy_bot.sh, run_pipeline.py
│
├── strategy-researcher/  ← data miner
│   ├── SKILL.md
│   ├── scripts/          ← find_common_factors.py, live_vs_backtest.py
│   └── playbooks/        ← hypothesis_from_data.md
│
├── strategy-critic/      ← deploy gate
│   ├── SKILL.md
│   └── checklists/       ← adversarial_thresholds.md, overfit_signs.md
│
└── strategy-explorer/    ← hypothesis generator
    ├── SKILL.md
    └── playbooks/        ← (TBD)
```

## In the freqtrade_btc_bot repo

The actual TOOLS live in the repo, NOT in skills:

```
d:/pythone/freqtrade_btc_bot/
├── research/ai/
│   ├── experiment_logger.py          ← archives every backtest
│   ├── logged_backtest.py            ← wrapper for freqtrade backtest
│   ├── adversarial_validator.py      ← the gate
│   ├── calendar_analyzer.py          ← DOW/Month stats
│   ├── per_asset_audit.py            ← archive ranking
│   ├── backfill_per_coin.py          ← yearly + adversarial sweep
│   ├── sentiment_test.py             ← FGI feasibility
│   ├── portfolio_simulator.py        ← allocator comparison
│   ├── meta_allocator.py             ← heuristic weekly reallocation
│   └── ...
├── research/experiments/INDEX.csv    ← master archive of all backtests
├── research/adversarial/             ← all adversarial verdicts
├── research/ALL_BATCHES_FINAL.md     ← session report
└── user_data/strategies/*.py         ← all strategy code
```

Skills REFERENCE these tools but don't duplicate them.

## Quick decision tree

```
START
  ↓
Does user want a specific action?
  ├── BUILD code → bot-builder
  ├── ANALYZE data → strategy-researcher
  ├── DESIGN context → strategy-architect
  ├── REVIEW safety → strategy-critic
  ├── BRAINSTORM ideas → strategy-explorer
  └── FULL WORKFLOW → strategy-lab (this skill orchestrates)
```

## Anti-pattern: don't always orchestrate

Bad: invoke strategy-lab for "build me an ETH calendar bot" → routes through all 5 sub-skills.

Good: invoke bot-builder directly. It already knows to consult architect for vol-check and critic for adversarial validation.

The orchestrator is for tasks the user explicitly says "do the full thing" — not for every interaction.

## Legacy docs (kept for reference)

The old strategy-lab structure had everything in one skill. Some content was migrated to sub-skills:

- `docs/METHODOLOGY.md` → split into architect/PATTERNS + critic/checklists + this orchestrator
- `docs/PATTERNS.md` → architect/knowledge/architecture_patterns.md (with code skeletons)
- `docs/ANTI_PATTERNS.md` → critic/checklists/overfit_signs.md
- `docs/CASE_STUDIES.md` → strategy-lab/examples/ (8 wins + 11 rejections)
- `templates/` → bot-builder/templates/

Old paths still work — content is preserved.
