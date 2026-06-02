# Meta-Analysis Report — what we built, what worked, what's next

Auto-generated from `research/` archive. Re-run `meta_analyzer.py` after any new experiment.

## 1. Scope of work
- Aggregated rows: **3263** across 22 sweep files.
- Distinct strategy variants tested: **61**
- Distinct coins tested: **7**
- Per-run archived experiments: **2**

## 2. Market context per coin/year

Return % year-by-year:
```
year   2019   2020    2021  2022   2023   2024  2025  2026
coin                                                      
ADA   -21.7  441.6   647.0 -82.2  137.7   35.6 -63.8 -35.2
BNB   128.9  172.3  1253.8 -53.3   27.6  124.0  22.1 -19.8
DOGE  -48.0  130.7  2898.2 -59.4   27.5  243.5 -63.9 -20.3
LINK  261.0  520.4    64.7 -73.1  165.5   28.7 -43.8 -28.1
```

Max DD % year-by-year:
```
year  2019  2020  2021  2022  2023  2024  2025  2026
coin                                                
ADA   67.7  67.1  59.2  84.8  46.5  59.8  70.6  45.2
BNB   68.0  65.0  61.4  62.9  41.0  34.7  36.8  38.5
DOGE  48.9  50.9  77.2  71.3  39.8  57.9  71.7  41.7
LINK  58.3  62.2  73.7  80.4  40.2  56.3  59.0  43.9
```

## 3. Winners per coin × year (from all sweeps)

```
coin    year                variant  roi_%
 ADA    2021                Dyn_REG  451.9
 ADA    2022                Sh_FAST    0.0
 ADA    2023                Dyn_P10  101.9
 ADA    2024               Meta_BAL   68.0
 ADA    2025             Ad_AGGR_LO   45.7
 ADA 2026Q12                Sh_FAST    0.0
AVAX    2021                 DCA_V1  619.2
AVAX    2022               Meta_VST    0.0
AVAX    2023                Dyn_P30  188.5
AVAX    2024               Meta_REL   32.6
AVAX    2025             Ad_AGGR_LO   30.9
AVAX 2026Q12                Sh_FAST    0.0
 BNB    2021                Sh_SLOW  942.4
 BNB    2022               Meta_STR   -5.3
 BNB    2023             Ad_AGGR_LO   38.0
 BNB    2024                Sh_AGGR  105.1
 BNB    2025               Meta_BAL   42.8
 BNB 2026Q12                 DCA_V1    1.8
DOGE    2021               Rebal_R5 3066.2
DOGE    2022             Ad_AGGR_LO    5.5
DOGE    2023             L3_AGGR_TG   63.0
DOGE    2024                 DCA_V5  205.8
DOGE    2025             Ad_AGGR_LO   18.3
DOGE 2026Q12                Sh_FAST    0.0
 NaN    2021  13 SOL_Shield_RS_AGGR  902.6
 NaN    2022                    NaN   -9.8
 NaN    2023    12 SOL_DynRebal_P20  509.6
 NaN    2024            01 Rebal_R5   79.7
 NaN    2025            Rotation_V2   38.4
 NaN 2026Q12 09 PURE_Shield_RS_AGGR    0.0
```

## 4. Strategy correlation (low = diversification opportunity)

Lowest-correlation pairs (potential complementary strategies):

  - **11 ETH_Shield_RS_AGGR** vs **MA_BAL**: corr = -0.79
  - **MA_BAL** vs **Sh_DEF**: corr = -0.79
  - **MA_BAL** vs **Sh_FAST**: corr = -0.79
  - **MA_BAL** vs **Sh_MED**: corr = -0.79
  - **MA_BAL** vs **Sh_AGGR**: corr = -0.78
  - **MA_BAL** vs **Sh_SLOW**: corr = -0.78
  - **Dyn_REG** vs **MA_BAL**: corr = -0.76
  - **Dyn_P10** vs **MA_BAL**: corr = -0.75
  - **Dyn_P20** vs **MA_BAL**: corr = -0.75
  - **MA_BAL** vs **Rebal_R5**: corr = -0.75

Highest-correlation pairs (redundant — pick one):

  - Sh_AGGR vs Sh_FAST: corr = +1.00
  - Sh_AGGR vs Sh_MED: corr = +1.00
  - Sh_AGGR vs Sh_SLOW: corr = +1.00
  - Sh_DEF vs Sh_FAST: corr = +1.00
  - Sh_DEF vs Sh_MED: corr = +1.00
  - Sh_DEF vs Sh_SLOW: corr = +1.00
  - Sh_FAST vs Sh_MED: corr = +1.00
  - Sh_FAST vs Sh_SLOW: corr = +1.00
  - Sh_MED vs Sh_SLOW: corr = +1.00
  - VS_CLASSIC vs VS_LOOSE: corr = +1.00

## 5. Repeating failure modes (ROI < -30%)

187 catastrophic-loss results identified.

Per year:
  - 2021: 2 variants lost >30%
  - 2022: 101 variants lost >30%
  - 2024: 1 variants lost >30%
  - 2025: 51 variants lost >30%


Most frequent big-losers:
```
variant
DCA_V5        9
Rebal_R5      9
DCA_V1        8
Dyn_P30       8
Dyn_P20       8
Dyn_P10       8
Dyn_REG       8
L3_AGGR_BL    8
L3_AGGR_WG    8
L3_BAL_WG     8
```

## 6. Per-run archive index

```
      timestamp                strategy    mode     pair  roi_pct  n_trades  max_dd_pct  sharpe
20260602_172321 BtcRegimeShieldStrategy RS_AGGR BTC/USDT  229.497         8      10.860   0.052
20260602_172800     BtcAiShieldStrategy default BTC/USDT  279.706        22      11.794   0.101
```

## 7. New ideas — based on the data

### A. Combine high-return + low-correlation pairs
The correlation matrix above suggests a few pairs that are uncorrelated
(or even negative). A portfolio that runs BOTH could deliver more
stable returns. Example: pair the most aggressive momentum strategy
with the most defensive regime-shielded one — when one fails, the
other often wins.

### B. Use 2022/2024/2026 as adversarial validators
Three years where most long-only spot strategies failed. ANY new
strategy candidate must survive these three windows BEFORE testing
on bull years.

### C. Asset-specific strategy mapping (not one-size-fits-all)
The mega_sweep already proved each coin needs a different winner:
  - BTC favours Shield + AI overlay
  - ETH favours Pure Shield
  - SOL favours Pure Shield (high vol)
  - BNB favours Sh_SLOW (slow confirms)
  - DOGE favours Sh_DEF (defensive)
  - ADA favours Meta_BAL
Don't deploy a "BTC strategy" on alts. Re-run mega_sweep per coin.

### D. Halving-cycle-conditional sizing
AI Shield uses cycle_bias linearly. Try a non-linear sigmoid that
boosts heavy in ACCUMULATION+EARLY_BULL (post-halving), shrinks fast
in DISTRIBUTION (the late-cycle window where corrections start). Run
2025-2026 data through this filter — expected to flag pre-correction.

### E. Anomaly cooldown
Currently anomaly flag = force exit. But after an anomaly clears, we
re-enter on next signal. Try a 7-day cooldown after each anomaly — the
post-flash-crash bounce is often followed by another drop. Test
this against the 40 BTC anomalies in history.

### F. Cross-asset cycle desync
BTC halving cycle drives BTC. But ETH/SOL/BNB have their own cycles
(ETH merge, SOL FTX recovery, etc.). Build a per-asset cycle model
that doesn't assume BTC-cycle homogeneity. Use ETH staking-yield as
ETH-specific cycle indicator.

### G. Ensemble of regime detectors
Currently Shield uses 1 regime rule (EMA200 + 30d-return + ADX). Build
3 separate regime detectors (e.g., 30d/60d/90d momentum) and trade
only when ALL THREE agree. Lower entry frequency, higher quality.

### H. Sentiment-volatility coupling
When sentiment AND volatility both spike together = real news event,
trade. When only volatility spikes = noise, skip. Needs FinBERT
integration (Batch 4, still pending).

### I. RL on the meta-allocator (not on price)
RL agents fail on direct price prediction. But RL on the meta-allocator
(which bot to give capital to next) is a much simpler problem — the
"actions" are 20-dimensional weights, rewards are realized PnL. Far
less overfit risk than RL on candlesticks.

### J. Time-of-week / calendar effects
The archive has dates on every trade. Group by day-of-week, end-of-
month, etc. If there's a calendar bias (e.g., Mondays are net-down),
exit before the weekend.
