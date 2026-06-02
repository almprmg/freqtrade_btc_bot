# Sentiment feasibility — Fear & Greed Index test

Data: FGI 2020-01-01 -> 2026-05-29 (2340 rows merged with BTC)

X-FEAR (FGI<=25) edge on 30d forward returns: **-2.51pp**

X-GREED (FGI>=75) edge on 30d forward returns: **+8.43pp**

Interpretation:
  - X-FEAR positive (e.g. +5pp) means contrarian buy signal works
  - X-GREED negative (e.g. -3pp) means contrarian sell signal works

If both signals are <1pp, sentiment likely won't add much value. In that case, FinBERT (noisier source than FGI) is unlikely to help.
