# Strategy critic log

## 2026-10-11 — BtcDynamicRebalanceStrategy DR_PROFIT_20, C14 anchor fix
- Change: profit trigger measured vs per-trade portfolio anchor (re-set on each fill) + open-order/60-min cooldown.
- Full run 2020-01-01→2026-06-03 (MTM): BTC +584%→+706%, DD -64.6%→-54.0%, orders 1522→27; ETH +1006%→+1039%, orders 1242→50; SOL +496%→+477%, orders 1031→58. Fees cut ~60%.
- Adversarial windows (both versions, ~identical): BEAR_2022 BTC -53% / ETH -54% / SOL -86%; SIDEWAYS_2025 SOL -22%; BEAR_2026Q12 -12/-25/-27%. Verdict: CATASTROPHIC (75% static long, no shield) — unchanged by the fix.
- Verdict: fix APPROVED as a bug fix for the existing dry-run bots; strategy VETOED for live capital / new wallets.
- Open follow-ups: partial-exit sizing uses cost-basis stake (oversells when in profit); minimal_roi 10.0 sentinel is now reachable (SOL 2021 roi exit).
- 30/60/90d follow-up: confirm live order count per bot drops to a few per month.
