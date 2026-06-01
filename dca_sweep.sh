#!/usr/bin/env bash
# Runs all 6 DCA modes over the same 5-year window and dumps each run's
# backtest-result JSON for later year-by-year analysis.
set -euo pipefail
export PATH="$PWD/.venv/Scripts:$PATH"

CFG="config.dca.json"
TRANGE="20210101-20260101"
OUT="./dca_results"
mkdir -p "$OUT"

MODES=(V1_BLIND V2_BLIND_TP V3_RSI V4_BELOW_EMA V5_TIERED V6_TIERED_TP)

for mode in "${MODES[@]}"; do
  echo
  echo "================================================================"
  echo ">>> $mode"
  echo "================================================================"
  DCA_MODE="$mode" freqtrade backtesting \
      --userdir ./user_data --config "$CFG" \
      --strategy BtcDcaHoldStrategy --timerange "$TRANGE" \
      --cache none --export trades \
      --export-filename "user_data/backtest_results/${mode}.json" \
      2>&1 | tee "$OUT/${mode}.log" | tail -50 || true
done

echo
echo "================================================================"
echo "ALL MODES DONE — run yearly_report.py for the breakdown"
echo "================================================================"
