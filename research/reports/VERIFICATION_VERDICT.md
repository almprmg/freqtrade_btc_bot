# AI Strategy — Overfit Verification Verdict

**Date:** 2026-06-11 · GPU machine · branch `gpu/lstm-v1-btc`

The user asked: *are these results overfit?* Answer below, after escalating rigor.

## The escalation (each level killed optimism from the previous)

| Test | Portfolio result | Honest? |
|---|---|---|
| Single 80/20 split | corr +0.47, BTC +37% | ❌ landed on a lucky window (misled 3×) |
| Naive "improvement" (k tuned on OOS, no costs) | CAGR +82%, OOS +42% | ❌ **OVERFIT** — k selected on the reported window |
| Nested split + real costs + bootstrap | CAGR −24.5%, Sharpe −1.33, CI∋0 | ✅ clean, but short test slice |
| **Purged walk-forward** (model+k fit on past only, fixed k, real costs) | **CAGR +40%, Sharpe 1.19, CI [0.40, 1.85]** | ✅✅ **gold standard** |

Costs in the rigorous tests: 0.075% fee + 0.05% slippage per side, next-bar execution.

## Final verdict (purged walk-forward, every prediction out-of-sample)

| Coin | WF CAGR | Buy&Hold | Sharpe | Sharpe CI (5–95%) | Significant? |
|---|---|---|---|---|---|
| DOGE | +109% | +92% | 1.29 | [0.58, 1.84] | ✅ yes |
| BNB | +34% | +56% | 0.80 | [0.09, 1.42] | ✅ yes |
| ETH | +19% | +46% | 0.62 | [−0.02, 1.26] | borderline |
| ADA | +21% | +34% | 0.62 | [−0.17, 1.35] | no |
| XRP | +12% | +34% | 0.47 | [−0.15, 1.15] | no |
| BTC | +10% | +46% | 0.45 | [−0.25, 1.04] | no |
| SOL | +7% | −16% | 0.38 | [−0.47, 1.25] | no |
| **Portfolio** | **+40%** | — | **1.19** | **[0.40, 1.85]** | ✅ **yes** |

## What this means (honest)

1. **The spectacular numbers were overfit.** +0.47 corr / +82% CAGR did NOT survive clean testing. The user's instinct was correct.
2. **A real but MODEST edge survives** the gold-standard test — but only clearly at the **portfolio level** (Sharpe 1.19, bootstrap CI clears 0). Diversifying 7 coins is what makes it statistically significant; most single coins are not.
3. **It mostly underperforms buy&hold on raw CAGR** (BTC 10% vs 46%) — the strategy is defensive (sits in cash often). Its value is **risk-adjusted** (positive Sharpe) and **drawdown timing**, not beating HODL in a bull run.
4. **Drawdowns are large** (−47% portfolio, −60–80% some coins). Not deployable as-is.

## Bottom line

> The AI signal has a **genuine but modest risk-adjusted edge at the portfolio level** (Sharpe ~1.2, CI > 0), NOT the headline returns seen earlier — those were overfit. It is **not yet better than buy&hold in absolute terms** and carries heavy drawdowns. Verdict: *promising research signal, not a deployable strategy yet.*

## Risk control added (vol-targeting + 0.8 position cap)

Scaling exposure down when realized vol is high (target 0.025 daily, causal) +
hard cap 0.8. Same purged walk-forward, fixed params (not tuned on data):

| | No control | **Vol-targeted** |
|---|---|---|
| Portfolio CAGR | +40% | +21% |
| Portfolio Sharpe | 1.19 | 1.12 |
| Portfolio Sharpe CI | [0.40, 1.85] | [0.43, 1.84] |
| Portfolio maxDD | −47% | **−23.5%** |
| Significant coins | 2/7 | **3/7** (BNB, XRP, DOGE) |

Per-coin maxDD: BTC −63→−42, ETH −59→−39, SOL −81→−60, ADA −79→−48,
XRP −57→−33, DOGE −60→**−19.5**. Drawdown ~halved, Sharpe preserved, edge still
significant → a real risk-adjusted improvement (lower CAGR is the expected cost
of de-risking). WF signals cached in `trading_results/wf_signal_*.feather`.

## Next levers (honest, to actually improve risk-adjusted return)
- Position cap / vol-targeting to cut the −60% drawdowns.
- Walk-forward signals for ALL reports (stop trusting single-split numbers).
- Test as a **risk overlay** on the existing AnalogV2 rather than standalone.
- The official call still needs the freqtrade 9-year engine on the CPU machine.

Artifacts: `GPU_HANDOFF/ai_verify.py`, `ai_walkforward_backtest.py`;
results in `research/dl_models/trading_results/` (`verify_summary.json`, `walkforward_verdict.json`).
