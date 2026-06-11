---
name: ai-batches-complete
description: "Multi-batch AI integration session — 8 deploys / 11 rejections / fleet 29 bots / 57 containers"
metadata: 
  node_type: memory
  type: project
  originSessionId: f5b8d411-6772-4bab-83da-8fb16976dbd5
---

11 ideas + 4 extensions tested as of 2026-06-03. Fleet grew from 21 to **29 bots / 57 containers**.

**Deployed (8 new bots, $23K total new wallet):**
- sub #98 — `BtcAiShieldV2Strategy` (BTC) — backtest +36.5%/yr
- sub #99 — `BtcTripleRegimeStrategy` (BTC defensive) — +10.5%/yr
- sub #100 — `BtcCalendarShieldStrategy` (BTC) — +38.2%/yr
- sub #101 — `BtcRegimeShieldStrategy` (ETH Pure Shield) — +47%/yr vs +21% DynRebal
- sub #102 — `SolVolShieldStrategy` (SOL chop-aware) — +45%/yr WARN
- sub #103 — `BtcTripleRegimeStrategy` (BNB defensive) — +17.7%/yr WARN
- sub #104 — `BtcTripleRegimeStrategy` (ADA defensive) — +14.4%/yr PASS
- sub #105 — `BtcCalendarShieldStrategy` (ETH) — **+55%/yr PASS** (strongest deploy)

**Rejected (11 honest):**
Cooldown V3, Per-asset Cycles, AVAX 3Layer, SOL Pure/AIShV2/Triple,
Sentiment Shield, BNB Rotation, DOGE Adaptive, ADA AIShV2, DOGE Triple.

**Why:** user requested all 18 ideas tested in batches with adversarial validation, honest failure reporting, and archival of every backtest. User explicitly said "اعمل ما تبقى كامل مره واحده" → completed extensions in single batch. Subscriptions deployed alongside existing bots (not replacing).

**How to apply:**
- Read `research/ALL_BATCHES_FINAL.md` for full scoreboard before suggesting new bots
- ETH Calendar Shield (#105) is the session's strongest deployment (+55%/yr, PASS)
- SOL VolShield v3 cracked SOL after 3 failed attempts — chop-aware filters (ret_30d AND ret_60d, ATR%, 5-day confirmation)
- DOGE still has no working bear protection (all 4 candidates failed adversarial); future work
- AVAX MetaAdaptive stays (all alternatives worse)
- `meta_allocator.py` weekly cron on trad-server; needs ~30d live data before first apply
- Adversarial Validator is the deployment gate — 11 candidates rejected on it this session

**Per-coin live map:**
- BTC: V2 (#98) + Triple (#99) + Calendar (#100) — 3 bots
- ETH: DynRebal (existing) + Pure Shield (#101) + **Calendar (#105)** — 3 bots
- SOL: DynRebal (existing) + **VolShield v3 (#102)** — 2 bots
- BNB: Pure Shield (existing) + Triple (#103) — 2 bots
- ADA: MetaAdaptive (existing) + Triple (#104) — 2 bots
- DOGE: Pure Shield Defensive (existing) — no upgrade found
- AVAX: MetaReliable (existing) — no upgrade found

**Patterns that worked:**
- Calendar Shield (BTC tilts) → portable to ETH with even better results
- Triple Regime → universal defensive sleeve, useful as 2nd bot per coin
- Volatility-aware shields (custom thresholds) for high-vol coins like SOL

Linked: [[strategy-registration]], [[remote-server-deployment]]
