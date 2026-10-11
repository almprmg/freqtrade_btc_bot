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
