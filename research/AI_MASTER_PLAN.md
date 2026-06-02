# AI Master Plan — Complete Roadmap

**Goal**: integrate AI/ML across the existing 20-bot trading system to materially improve risk-adjusted returns.
**Constraint**: CPU-only inference (Intel UHD GPU — no CUDA). Local-first.
**Honest expectation**: not every idea will work. We test, deploy winners, document losers.

---

## Answers to standing questions

| Question | Decision |
|---|---|
| Scope | Build all reasonable ideas in batches |
| Sequence | Sequential — easier to debug + each builds on previous |
| Time budget | Multi-session — split into 7 batches |
| Focus | Both ROI improvement AND DD reduction |
| Deployment | Paper-trade first (dry-run), promote winners with small wallets |
| Model size | Start small (Chronos-small, Llama-3 8B Q4); upgrade only if value proven |
| Training | CPU local for inference; Google Colab free-tier for any fine-tune |
| Single vs multi-pair | Multi-pair (BTC/ETH/SOL/BNB) — already proven by Rotation V1 |
| Horizon | 1-day for prediction, but rebalance frequency varies per idea |
| Integration | New strategies + enhance existing (e.g., Meta-Allocator over the 20-bot fleet) |

---

## All 18 Ideas — Status Tracker

| # | Idea | Difficulty | Expected gain | Batch | Status |
|---|---|---|---|---|---|
| 1 | Vol Ensemble (Naive + Chronos + GARCH) | Easy | +0-5% | 2 | pending |
| 2 | Multi-Timeframe Voting (1d/4h/1h) | Easy | +5-10% | 3 | pending |
| 3 | XGBoost Position Sizing | Medium | +5-10% | 3 | pending |
| 4 | FinBERT News Sentiment Filter | Medium | +5-15% | 4 | pending |
| 5 | Hierarchical AI (macro+micro) | Medium | +10-20% | 6 | pending |
| 6 | AI Stop-Loss Optimizer | Medium | DD -5-15% | 4 | pending |
| 7 | Regime Classifier (Random Forest) | Medium | +10-15% | 3 | pending |
| 8 | **Meta-Allocator over 20-bot fleet** | Medium | +15-30% | **1** | **in progress** |
| 9 | LLM Trade Analyst (Llama-3 8B) | Hard | 0-30% | 7 | pending |
| 10 | Multi-Agent Debate System | Hard | +10-25% | 7 | pending |
| 11 | Causal Inference (DoubleML) | Hard | 0-20% | (deferred) | future |
| 12 | RL Agent on top of Chronos | Very Hard | 0-50% var | (deferred) | future |
| 13 | Foundation Model Ensemble | Medium | +5-10% | 5 | pending |
| 14 | Anomaly Detection (Isolation Forest) | Easy | +5-10% | 2 | pending |
| 15 | Adversarial Validator | Medium | DD -10% | 4 | pending |
| 16 | Correlation-Aware Allocation | Medium | +10-15% | 6 | pending |
| 17 | Halving Cycle Predictor | Easy | +5-10% | 6 | pending |
| 18 | Whale Movement Tracker | Hard | 0-15% | (deferred) | future — needs paid data |

---

## The 7 Batches

### Batch 1 — Meta-Allocator (THE BIG ONE) — ~3 days
**Why first**: highest-impact, builds on existing 20 bots. Pure win.
- Read 90d rolling performance per bot from trades table
- Score: Sharpe × win_rate × low_DD
- Dynamic capital allocation: top 5 bots get 80%, rest get 20%
- Re-balance weekly; persist allocations to subscriptions.allocated_capital
- A "master orchestrator" bot/script, NOT a Freqtrade strategy

### Batch 2 — Quick Wins (Vol Ensemble + Anomaly Detection) — ~1 day
**Why second**: easy, low-risk, can pair with existing strategies.
- Vol Ensemble: combine 3 vol forecasts → vol-targeted Shield
- Anomaly Detection: Isolation Forest on price/volume → "exit signal"

### Batch 3 — Predictive AI (XGBoost + Regime Classifier + Multi-TF) — ~3 days
**Why third**: proper ML on engineered features. Foundation for downstream.
- XGBoost regressor: predicts target_pct (0-1) from 50 features
- Random Forest classifier: BULL/BEAR/RANGE/CRASH
- Multi-Timeframe voting: combine 1d + 4h + 1h signals

### Batch 4 — Defensive AI (FinBERT + Adversarial + AI Stop-Loss) — ~3 days
**Why fourth**: reduces false signals, improves DD.
- FinBERT: read crypto news → sentiment score
- Adversarial Validator: 2nd model tries to refute entry → only enter if refuted-fails
- AI Stop-Loss: XGBoost predicts optimal SL/TP for each entry

### Batch 5 — Foundation Model Ensemble — ~2 days
**Why fifth**: combine Chronos + Lag-Llama + TimesFM for triple vote.
- 3 zero-shot foundation models predict in parallel
- Trade only on majority consensus
- High variance, hopefully better than any single

### Batch 6 — Innovative (Hierarchical + Correlation + Halving) — ~3 days
- Hierarchical: macro-AI decides regime, micro-AI decides timing
- Correlation-Aware: live correlation matrix → dynamic diversification
- Halving Cycle: model learns from 3 past BTC halvings

### Batch 7 — LLM Trade Analyst — ~3-5 days
**Most experimental**: Llama-3 8B Q4 (4-bit quantized, runs on CPU).
- LLM reads: technical indicators + price action + news headlines
- Outputs: trade rationale + confidence
- Used as final filter on rule-based signals

---

## Deferred (future work)

- **11. Causal Inference**: deep statistical work, needs proper experiment design
- **12. RL Agent**: high overfit risk on financial data; needs careful reward shaping
- **18. Whale Tracker**: requires paid on-chain API (Whale Alert, Nansen, etc.)

---

## Testing Methodology

Every batch follows the same protocol:
1. **Build** the component
2. **Smoke test** on 1 quarter
3. **Year-by-year** backtest 2021-2026 (6 segments)
4. **Walk-forward** TRAIN 2021-2023 / VAL 2024 / TEST 2025-2026
5. **Reality check** with 2x fees + market orders
6. **Robustness score** (5-factor composite)
7. **Compare** against Pure Shield baseline (+24.3%/yr)
8. **Promote** to deployment if wins by >2pp annual AND DD <50%

## Deployment Strategy

- New strategies deployed in dry-run at $1-2K wallet
- Existing winners (Pure Shield, Rotation V1) keep their wallets
- Meta-Allocator can OVERRIDE allocations across all subs
- All bots' trades flow to trad_pg via bridges → admin UI

---

## Success Criteria (per batch)

A batch is considered "successful" if at least ONE component:
- Beats Pure Shield baseline by >2pp annual compound, OR
- Reduces max DD by >5pp while keeping return within 5pp of Pure Shield

If a batch fully fails: document why, move on.

---

## Honest Risks

- **Overfit**: most ML methods overfit on 5y of crypto data. Walk-forward is essential.
- **CPU-only**: inference on CPU may be slow enough that we can't run all 18 features in production. Will need to pick top 5-7.
- **Foundation models** are pre-trained on diverse data, not crypto. Direct zero-shot already failed for direction prediction. May fail for ensemble too.
- **LLM hallucination**: Llama-3 8B may give plausible-but-wrong trade rationales.
- **Time**: full plan is ~17-20 days of work. We'll split across sessions.
