# WIN: ETH Calendar Shield (sub #105) — the strongest deploy

**Date deployed:** 2026-06-03
**Backtest:** +55%/yr 5y
**Adversarial:** PASS

## Hypothesis (1 sentence)

> "Calendar tilts (October, Wednesday, Monday, EoM) that worked on BTC should also work on ETH because day-of-week effects are market-wide, not coin-specific."

## Pre-mortem

"Would fail if calendar effects are BTC-only — i.e., if October's strength came from BTC narratives (halving, ETF launches), not market-wide momentum."

## Build

```bash
# Use BtcCalendarShieldStrategy directly with ETH config — no code changes needed.
cat > config.calendar-ETH.json <<'JSON'
{
  "pair_whitelist": ["ETH/USDT"],
  "strategy": "BtcCalendarShieldStrategy",
  "bot_name": "eth_calendar",
  "db_url": "sqlite:///user_data/tradesv3_calendar_eth.sqlite",
  ...
}
JSON
```

Critical: didn't fork BtcCalendarShieldStrategy. Just changed config. Calendar tilts are market-wide → same code works.

## Backtest

| Year | ROI | vs DynRebal (live) | vs ETH Shield #101 |
|---|---|---|---|
| 2021 | +296% | +25pp | +46pp |
| 2022 | 0% | +55pp | +12pp |
| 2023 | +30% | -35pp | -9pp |
| 2024 | +24% | -8pp | 0pp |
| 2025 | +43% | +46pp | +12pp |
| 2026 Q12 | 0% | +25pp | 0pp |

Compound: $10K → $91,300 over 5y = **+55%/yr**

## Adversarial

- BEAR 2022: 0% ✅
- SIDEWAYS 2025: +43% ✅
- BEAR 2026 Q12: 0% ✅

**Verdict: PASS** (cleanest of any ETH variant tested)

## Deploy

```bash
# 3 artifacts:
- SQL insert: sub #105, $3K wallet
- docker-compose.calendar-ETH.yml
- .env.eth-calendar with chmod 600
```

## Lessons

1. **Calendar effects port across coins.** They're market-wide signals (everyone trades Mon-Fri).
2. **No-code-change ports are the cheapest experiments.** Strategy file unchanged, just config differs.
3. **Best deploys are often re-applications of proven patterns, not new inventions.**
