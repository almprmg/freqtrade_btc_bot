#!/usr/bin/env bash
set -euo pipefail
export PATH="$PWD/.venv/Scripts:$PATH"
CFG="config.adaptive.json"; TRANGE="20210101-20260101"; OUT="./adaptive_results"
mkdir -p "$OUT"

MODES=(
  ADAPT_AGGR_BASELINE ADAPT_AGGR_TIGHT ADAPT_AGGR_LOOSE ADAPT_AGGR_NOSTOP
  ADAPT_BAL_BASELINE  ADAPT_BAL_TIGHT  ADAPT_BAL_LOOSE  ADAPT_BAL_NOSTOP
  ADAPT_DEF_BASELINE  ADAPT_DEF_TIGHT  ADAPT_DEF_LOOSE  ADAPT_DEF_NOSTOP
)

for mode in "${MODES[@]}"; do
  echo; echo "================================================================"
  echo ">>> $mode"
  echo "================================================================"
  AD_MODE="$mode" freqtrade backtesting \
      --userdir ./user_data --config "$CFG" \
      --strategy BtcAdaptiveStrategy --timerange "$TRANGE" \
      --cache none --export trades \
      2>&1 | tee "$OUT/${mode}.log" | tail -20 || true
done
echo
echo "DONE — run adaptive_report.py"
