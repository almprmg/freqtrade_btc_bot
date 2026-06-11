---
name: strategy-skills-cloud
description: 13 specialized skills for crypto bot fleet — DEV (5) + OPS (4) + ADVANCED (3) + ORCHESTRATOR
metadata: 
  node_type: memory
  type: reference
  originSessionId: f5b8d411-6772-4bab-83da-8fb16976dbd5
---

User installed 13 specialized skills at `C:\Users\user\.claude\skills\` covering the entire crypto bot fleet lifecycle.

## 5 DEVELOPMENT skills (build new bots)
| Skill | Role |
|---|---|
| `strategy-architect` | Market expert / reference knowledge — coin profiles, regime taxonomy, calendar effects, architecture patterns |
| `strategy-researcher` | Archive miner — finds common factors across PASS strategies, mines 3500+ backtests + live trades |
| `strategy-explorer` | Hypothesis generator — 5 recipes (cross-coin transfer, failed-with-fix, combinations, capital alloc, external signals) |
| `bot-builder` | Code generator — 5 strategy templates + config/compose/SQL templates + deploy_bot.sh + run_pipeline.py |
| `strategy-critic` | Adversarial gate — runs the 3-window validator, checks 15 overfit signs, vetoes deployments |

## 4 OPERATIONS skills (run the fleet)
| Skill | Role |
|---|---|
| `fleet-monitor` | Daily health — container uptime, bridge sync, live PnL vs backtest, drawdown alerts (8 checks) |
| `data-engineer` | Data pipeline maintainer — OHLCV / anomaly_flags / halving_cycle / FGI refresh schedules + new-coin onboarding |
| `strategy-debugger` | Diagnose unexpected behavior — 7 playbooks (no-entry, early-exit, live-vs-backtest, dataframe inspect, 0-trades, PnL mismatch, container crash) + 5 known bugs catalogue |
| `portfolio-risk-manager` | Capital + concentration — wallet limits ($500-$5K), per-coin caps (30%/40% BTC), drawdown triggers, kill switches |

## 3 ADVANCED skills
| Skill | Role |
|---|---|
| `live-trading-ops` | Dryrun → live transition — API key provisioning, canary rollout ($200→$3K), security checklist. REFUSES without explicit user authorization |
| `performance-reporter` | Weekly/monthly/quarterly reports — markdown templates, vs-backtest comparison, scheduled crons |
| `market-analyst` | Macro/sector context — BTC.D, sector rotation, FGI, ETF flows, sector onboarding decisions |

## 1 ORCHESTRATOR
| Skill | Role |
|---|---|
| `strategy-lab` | Top-level router — when task spans multiple skills, this routes; lists all 12 + intent mapping |

## Total: 13 skills in cloud

**Why:** user asked "ناقص اي سكل اخرى" after the initial 6-skill split, then chose "السبعة الكاملة" — added operations + advanced layer to cover full fleet lifecycle, not just development.

## How they hand off

```
EXPLORER → generates hypothesis (recipes)
   ↓
ARCHITECT → confirms design sound (coin profiles)
   ↓
RESEARCHER → checks if archive supports
   ↓
BUILDER → generates code
   ↓ backtest
CRITIC → adversarial gate (VETO or PASS)
   ↓
RISK-MANAGER → checks concentration/wallet
   ↓
BUILDER → deploys
   ↓
FLEET-MONITOR → daily health
   ↓ (if anomaly)
DEBUGGER → investigates
   ↓
RESEARCHER → live-vs-backtest divergence

PARALLEL (always running):
DATA-ENGINEER (data fresh)
PERFORMANCE-REPORTER (periodic)
MARKET-ANALYST (macro context)
LIVE-TRADING-OPS (only when going live)
```

## Skill files
All under `C:\Users\user\.claude\skills\<name>\`:
- Each has SKILL.md as entry point
- Most have subdirectories: knowledge/ (architect), templates/ (builder), scripts/ (researcher, fleet-monitor, data-engineer, debugger), checklists/ (critic, live-trading-ops), playbooks/ (explorer, debugger), policies/ (risk-manager), schedules/ (data-engineer)
- Tools that exist in the repo (`d:/pythone/freqtrade_btc_bot/research/ai/*.py`) are REFERENCED by skills but not duplicated

Linked: [[ai-batches-complete]]
