#!/usr/bin/env bash
# Runs all 16 3-layer modes back-to-back over 5 years at $10k portfolio.
set -euo pipefail
export PATH="$PWD/.venv/Scripts:$PATH"

CFG="config.3layer.json"
TRANGE="20210101-20260101"
OUT="./3layer_results"
mkdir -p "$OUT"

MODES=(
  L3_AGGR_BASELINE
  L3_AGGR_TIGHT_GRID
  L3_AGGR_WIDE_GRID
  L3_AGGR_WEEKLY
  L3_BAL_BASELINE
  L3_BAL_TIGHT_GRID
  L3_BAL_WIDE_GRID
  L3_BAL_WEEKLY
  L3_BAL_QUARTERLY
  L3_BAL_CRASH_SOFT
  L3_BAL_CRASH_HARD
  L3_DEF_BASELINE
  L3_DEF_TIGHT_GRID
  L3_DEF_WIDE_GRID
  L3_DEF_CRASH_SOFT
  L3_DEF_PARTIAL_DEPLOY
)

for mode in "${MODES[@]}"; do
  echo
  echo "================================================================"
  echo ">>> $mode"
  echo "================================================================"
  L3_MODE="$mode" freqtrade backtesting \
      --userdir ./user_data --config "$CFG" \
      --strategy Btc3LayerStrategy --timerange "$TRANGE" \
      --cache none --export trades \
      2>&1 | tee "$OUT/${mode}.log" | tail -30 || true
done

echo
echo "ALL DONE — run 3layer_report.py for analysis"
