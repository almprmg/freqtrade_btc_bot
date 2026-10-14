# Strategy critic log

## 2026-10-11 — BtcDynamicRebalanceStrategy DR_PROFIT_20, C14 anchor fix
- Change: profit trigger measured vs per-trade portfolio anchor (re-set on each fill) + open-order/60-min cooldown.
- Full run 2020-01-01→2026-06-03 (MTM): BTC +584%→+706%, DD -64.6%→-54.0%, orders 1522→27; ETH +1006%→+1039%, orders 1242→50; SOL +496%→+477%, orders 1031→58. Fees cut ~60%.
- Adversarial windows (both versions, ~identical): BEAR_2022 BTC -53% / ETH -54% / SOL -86%; SIDEWAYS_2025 SOL -22%; BEAR_2026Q12 -12/-25/-27%. Verdict: CATASTROPHIC (75% static long, no shield) — unchanged by the fix.
- Verdict: fix APPROVED as a bug fix for the existing dry-run bots; strategy VETOED for live capital / new wallets.
- Open follow-ups: partial-exit sizing uses cost-basis stake (oversells when in profit); minimal_roi 10.0 sentinel is now reachable (SOL 2021 roi exit).
- 30/60/90d follow-up: confirm live order count per bot drops to a few per month.

## 2026-10-11 — Anomaly circuit breaker, C12 in-sample IsolationForest (BtcCalendarShield / BtcAiShieldV2 / SolVolShield)
- Change: `research/ai/anomaly_detector.py --walk-forward` refits per calendar year on rows < Y-01-01 (min 200 rows, same features/params) -> `anomaly_flags_wf.feather` (+`train_end`). Strategies read `ANOMALY_FLAGS_FILE` (default `anomaly_flags.feather` = live unchanged). Leakage pinned by `tests/test_anomaly_walk_forward.py`.
- Full run 2020-01-01→2026-06-03, $10K, MTM equity rebuilt from orders (matches freqtrade ROI exactly; freqtrade DD is closed-trade only):
  - CalendarShield BTC: LIVE flags +923% (CAGR 43.6%, MTM DD -32.3%, 26 tr) → WF +605% (35.5%, -40.2%, 18 tr). In-sample regen on current data +694%. No breaker at all +785% (40.4%, -40.1%, 8 tr).
  - AiShieldV2 BTC: LIVE +844% (41.9%, -31.0%) → WF +579% (34.8%, -40.1%). Regen +635%. No breaker +765%.
  - SolVolShield SOL: LIVE +598% → WF +603% → no breaker +613% (DD -33% all). No material effect.
- Whole BTC delta sits in 2021 (+131% LIVE vs +69% WF): the live in-sample model flagged 2021-04-18 and exited near the April top, dodging May; no out-of-sample model (and not even an in-sample refit on today's data) reproduces it. The live file is a one-off vintage (BTC history then began 2020).
- Adversarial windows (2022 / 2025 / 2026Q12) identical LIVE vs WF: Calendar PASS, AiV2 PASS, SolVol WARN (2025 -12.8%). Verdicts unchanged.
- Red flags: "single-window darling" (2021) + leaked feature. Redundancy check: out-of-sample, the breaker LOWERS BTC return by ~180pp vs no breaker and does not reduce MTM DD (-40% both) -> the feature has no demonstrated OOS value.
- Verdict: fix APPROVED (research-integrity bug fix). Restate BTC shield expectations to WF numbers (~+600%, CAGR ~35%, MTM DD ~-40%), not +923%/-18%. No new capital decisions on archive results that used anomaly_flags.feather for 2019-2023. Switching live bots to WF flags: low risk (2024+ flags are OOS in both files) but recommended for consistency; removing the breaker is a separate experiment, not approved here.
- 30/60/90d follow-up: compare live anomaly exits vs WF file; re-run C12 grid when 2026 closes.

## 2026-10-13 — C14b BtcDynamicRebalanceStrategy partial-sell sizing + unreachable ROI (DR_PROFIT_20, BTC $10K / ETH $1K / SOL $500)
- Root cause (confirmed in freqtrade 2026.4 source): a negative `adjust_trade_position` return is converted to amount as `|stake| * trade.amount / trade.stake_amount` (freqtradebot.py process_open_trade_positions; optimize/backtesting.py _get_adjust_trade_entry_for_candle) = fraction of COST BASIS. The strategy returned the market-value overweight -> over-sold in profit (BTC 2021-02-12 left 48.95% BTC), under-sold at a loss (SOL 2023 trims left 78-84%).
- Fix: `partial_exit_stake()` returns (sell_value/current_rate/trade.amount) * trade.stake_amount; `minimal_roi = {}` (no ROI entry ever matches; old {"0": 10.0} closed SOL via ROI in 2021). Tests `tests/test_dynrebal_sizing.py` (9 fail on origin/main, all 63 pass after).
- Full run 2020-01-01 -> 2026-10-12 (data extended), MTM equity rebuilt from orders (matches freqtrade final balance exactly):
  - BTC: +840.9% / CAGR 39.2% / MTM DD -54.0% / 27 orders / fees $188 / trim alloc 49-75% -> +737.6% / 36.8% / -64.4% / 33 / $141 / 75.0-75.1%
  - ETH: +1367.7% / 48.7% / -64.9% / 52 / $52.6 / 47-76% -> +1330.8% / 48.1% / -67.8% / 51 / $35.5 / 75.0-75.1%
  - SOL: +693.5% / 45.1% / -89.8% / 60 / $17.8 / 47-84%, 1 ROI exit -> +729.7% / 46.3% / -90.2% / 60 / $11.6 / 75.0-75.2%, 0 ROI exits
- BTC/ETH "lost" return is the bug's accidental de-risking (cash raised near the 2021 tops), not edge; the fixed version does what the strategy says (75% exposure) and its DD is the honest 75%-of-coin drawdown.
- Adversarial (before -> after): BTC 2022 -53.1/-53.1, 2025 -3.9/-4.3, 2026Q12 -11.7/-11.7; ETH -53.9/-53.2, -1.8/-2.7, -25.4/-25.4; SOL -86.2/-85.6, -22.1/-22.9, -27.0/-27.0. CATASTROPHIC both before and after (75% long-only by design).
- Verdict: fix APPROVED as a correctness fix for the 3 existing dry-run bots. Strategy remains VETOED for real money / new wallets (unchanged).
- 30/60/90d follow-up: after next live trim, check post-trim coin share ~75% in bot DB.
