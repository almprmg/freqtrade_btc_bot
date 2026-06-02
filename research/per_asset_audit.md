# Per-Asset Audit

Idea C — scanning all archived backtests to identify the historically best-performing strategy per coin.

Total records scanned: **1266**


## BTC
**Currently live:** `BtcAiShieldV2Strategy / BtcCalendarShieldStrategy`

Top 8 strategies by best_score (roi - 2×dd + 10×sharpe):

| Strategy | Runs | Best ROI | Worst ROI | Median ROI | Median DD | Median Sharpe | Best Score |
|---|---|---|---|---|---|---|---|
| `BtcRotationStrategy` | 13 | 300.9% | -0.7% | 3.2% | 0.2% | 0.132 | 301.2 |
| `BtcAiShieldStrategy` | 17 | 279.7% | 0.0% | 12.3% | 0.0% | 0.059 | 280.5 |
| `BtcRegimeShieldStrategy` | 78 | 229.5% | -13.4% | 9.0% | 0.0% | 0.000 | 229.8 |
| `BtcRotationV3Strategy` | 6 | 124.7% | -3.9% | 0.7% | 0.2% | 0.051 | 129.8 |
| `BtcOnChainStrategy` | 32 | 121.9% | -50.7% | 0.0% | 0.1% | 0.000 | 126.7 |
| `BtcCalendarShieldStrategy` | 21 | 121.6% | 0.0% | 0.0% | 0.0% | 0.000 | 126.2 |
| `BtcAiShieldV2Strategy` | 15 | 118.1% | 0.0% | 13.9% | 0.0% | 0.072 | 122.7 |
| `Btc3LayerStrategy` | 39 | 99.6% | -49.1% | 64.7% | 0.2% | 0.087 | 113.8 |

⚠️ **Potential upgrade**: live `BtcAiShieldV2Strategy / BtcCalendarShieldStrategy` not in top 3 by audit score.

## ETH
**Currently live:** `EthRegimeShieldStrategy (Pure)`

Top 8 strategies by best_score (roi - 2×dd + 10×sharpe):

| Strategy | Runs | Best ROI | Worst ROI | Median ROI | Median DD | Median Sharpe | Best Score |
|---|---|---|---|---|---|---|---|
| `BtcRotationStrategy` | 13 | 1069.1% | -13.8% | 9.2% | 0.2% | 0.132 | 1069.4 |
| `BtcRegimeShieldStrategy` | 6 | 249.6% | -11.7% | 27.9% | 0.0% | 0.047 | 254.3 |
| `MultiCycleShieldStrategy` | 6 | 148.0% | -11.1% | 20.8% | 0.0% | 0.036 | 150.5 |
| `BtcRotationV2Strategy` | 6 | 33.9% | -15.2% | 4.4% | 0.2% | 0.076 | 35.2 |
| `BtcRotationV3Strategy` | 6 | 33.5% | -15.6% | 1.2% | 0.2% | 0.051 | 34.4 |
| `SatsStrategy` | 4 | -99.3% | -99.9% | -99.9% | 1.0% | -1.683 | -109.7 |
| `BtcDynamicRebalanceStrategy` | 7 | 281.5% | -55.1% | 32.3% | 0.0% | -100.000 | -999.0 |

⚠️ **Potential upgrade**: live `EthRegimeShieldStrategy (Pure)` not in top 3 by audit score.

## SOL
**Currently live:** `SolRegimeShieldStrategy (Pure)`

Top 8 strategies by best_score (roi - 2×dd + 10×sharpe):

| Strategy | Runs | Best ROI | Worst ROI | Median ROI | Median DD | Median Sharpe | Best Score |
|---|---|---|---|---|---|---|---|
| `BtcRotationStrategy` | 13 | 1573.6% | -34.3% | 0.0% | 0.2% | 0.132 | 1574.0 |
| `MultiCycleShieldStrategy` | 6 | 646.4% | -31.1% | 9.9% | 0.1% | 0.056 | 648.3 |
| `BtcRotationV2Strategy` | 6 | 512.6% | -46.2% | 2.3% | 0.2% | 0.076 | 516.2 |
| `BtcRotationV3Strategy` | 6 | 387.6% | -37.2% | 1.9% | 0.2% | 0.051 | 392.7 |
| `BtcRegimeShieldStrategy` | 6 | 902.6% | -43.1% | 21.9% | 0.1% | -0.111 | 232.2 |
| `SatsStrategy` | 4 | -99.9% | -100.0% | -99.9% | 1.0% | -0.774 | -107.3 |
| `BtcDynamicRebalanceStrategy` | 7 | 756.7% | -87.2% | 57.7% | 0.0% | -100.000 | -999.0 |

⚠️ **Potential upgrade**: live `SolRegimeShieldStrategy (Pure)` not in top 3 by audit score.

## BNB
**Currently live:** `BnbShieldSlowStrategy`

Top 8 strategies by best_score (roi - 2×dd + 10×sharpe):

| Strategy | Runs | Best ROI | Worst ROI | Median ROI | Median DD | Median Sharpe | Best Score |
|---|---|---|---|---|---|---|---|
| `BtcMetaAdaptiveStrategy` | 24 | 568.4% | -24.4% | -0.2% | 0.1% | -0.009 | 569.5 |
| `BtcRegimeShieldStrategy` | 30 | 942.4% | -26.9% | 13.0% | 0.1% | -100.000 | 380.2 |
| `BtcRotationStrategy` | 13 | 350.3% | -14.6% | 3.2% | 0.2% | 0.132 | 350.6 |
| `MultiCycleShieldStrategy` | 6 | 229.6% | -15.8% | 7.4% | 0.1% | 0.007 | 230.6 |
| `BtcAdaptiveStrategy` | 24 | 176.7% | -31.6% | 15.1% | 0.0% | -100.000 | 181.8 |
| `Btc3LayerStrategy` | 24 | 161.9% | -37.4% | 15.0% | 0.2% | 0.129 | 166.9 |
| `BtcRotationV3Strategy` | 6 | 129.6% | -14.7% | -2.0% | 0.2% | 0.051 | 134.7 |
| `BtcRotationV2Strategy` | 6 | 103.7% | -4.0% | 0.0% | 0.2% | 0.076 | 107.3 |

⚠️ **Potential upgrade**: live `BnbShieldSlowStrategy` not in top 3 by audit score.

## AVAX
**Currently live:** `AvaxMetaReliableStrategy`

Top 8 strategies by best_score (roi - 2×dd + 10×sharpe):

| Strategy | Runs | Best ROI | Worst ROI | Median ROI | Median DD | Median Sharpe | Best Score |
|---|---|---|---|---|---|---|---|
| `Btc3LayerStrategy` | 24 | 284.6% | -63.4% | -13.6% | 0.3% | -0.057 | 297.7 |
| `BtcRegimeShieldStrategy` | 30 | 265.3% | -36.1% | -2.5% | 0.2% | -0.027 | 265.9 |
| `BtcMetaAdaptiveStrategy` | 24 | 164.9% | -19.3% | 0.0% | 0.1% | 0.000 | 166.7 |
| `MultiCycleShieldStrategy` | 6 | 161.5% | -34.6% | 3.3% | 0.2% | -0.067 | 164.4 |
| `BtcAdaptiveStrategy` | 24 | 98.5% | -64.8% | 0.5% | 0.0% | -100.000 | 6.1 |
| `SatsStrategy` | 4 | -99.7% | -100.0% | -99.9% | 1.0% | -0.909 | -107.0 |
| `BtcDcaHoldStrategy` | 12 | 619.1% | -86.7% | -11.9% | 0.1% | -100.000 | -999.0 |
| `BtcDynamicRebalanceStrategy` | 24 | 190.3% | -81.1% | -15.1% | 0.2% | -100.000 | -999.0 |

⚠️ **Potential upgrade**: live `AvaxMetaReliableStrategy` not in top 3 by audit score.

## DOGE
**Currently live:** `DogeShieldDefensiveStrategy`

Top 8 strategies by best_score (roi - 2×dd + 10×sharpe):

| Strategy | Runs | Best ROI | Worst ROI | Median ROI | Median DD | Median Sharpe | Best Score |
|---|---|---|---|---|---|---|---|
| `BtcRebalanceStrategy` | 18 | 3066.2% | -49.7% | 5.8% | 0.0% | -100.000 | 3068.6 |
| `BtcDynamicRebalanceStrategy` | 24 | 3032.8% | -51.4% | 4.1% | 0.0% | -100.000 | 3035.2 |
| `BtcRegimeShieldStrategy` | 30 | 2332.9% | -39.1% | -5.2% | 0.2% | -0.024 | 2333.4 |
| `BtcDcaHoldStrategy` | 12 | 918.7% | -58.7% | 2.6% | 0.1% | -100.000 | 919.4 |
| `MultiCycleShieldStrategy` | 6 | 320.1% | -28.7% | -10.2% | 0.3% | -0.071 | 319.5 |
| `BtcMetaAdaptiveStrategy` | 24 | 177.8% | -34.9% | 0.0% | 0.1% | 0.000 | 178.8 |
| `Btc3LayerStrategy` | 24 | 128.5% | -46.0% | 5.0% | 0.3% | -0.007 | 131.6 |
| `BtcAdaptiveStrategy` | 24 | 177.0% | -27.2% | 9.8% | 0.0% | -100.000 | 101.1 |

⚠️ **Potential upgrade**: live `DogeShieldDefensiveStrategy` not in top 3 by audit score.

## ADA
**Currently live:** `AdaMetaBalancedStrategy`

Top 8 strategies by best_score (roi - 2×dd + 10×sharpe):

| Strategy | Runs | Best ROI | Worst ROI | Median ROI | Median DD | Median Sharpe | Best Score |
|---|---|---|---|---|---|---|---|
| `BtcRegimeShieldStrategy` | 30 | 339.1% | -43.3% | 2.2% | 0.0% | 0.000 | 289.9 |
| `Btc3LayerStrategy` | 24 | 230.7% | -58.5% | 0.5% | 0.3% | 0.024 | 232.6 |
| `BtcMetaAdaptiveStrategy` | 24 | 169.6% | -33.2% | 0.0% | 0.0% | 0.000 | 172.8 |
| `MultiCycleShieldStrategy` | 6 | 123.1% | -29.6% | 5.0% | 0.2% | 0.013 | 123.7 |
| `BtcAdaptiveStrategy` | 24 | 93.7% | -58.0% | 4.8% | 0.0% | -100.000 | 73.6 |
| `SatsStrategy` | 4 | -99.9% | -99.9% | -99.9% | 1.0% | -1.159 | -110.6 |
| `BtcDcaHoldStrategy` | 12 | 134.6% | -78.9% | 12.3% | 0.1% | -100.000 | -999.0 |
| `BtcDynamicRebalanceStrategy` | 24 | 451.9% | -70.8% | 9.0% | 0.1% | -100.000 | -999.0 |

⚠️ **Potential upgrade**: live `AdaMetaBalancedStrategy` not in top 3 by audit score.