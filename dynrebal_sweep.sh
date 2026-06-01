#!/usr/bin/env bash
set -euo pipefail
export PATH="$PWD/.venv/Scripts:$PATH"

CFG="config.dynrebal.json"
TRANGE="20210101-20260101"
OUT="./dynrebal_results"
mkdir -p "$OUT"

MODES=(
  DR_PROFIT_10 DR_PROFIT_20 DR_PROFIT_30
  DR_RSI_70_30 DR_RSI_75_25
  DR_BB
  DR_VOL_HIGH
  DR_DD_20
  DR_EMA50
  DR_RSI_AND_PROFIT
  DR_RSI_OR_BB
  DR_REGIME
)

for mode in "${MODES[@]}"; do
  echo
  echo "================================================================"
  echo ">>> $mode"
  echo "================================================================"
  DR_MODE="$mode" freqtrade backtesting \
      --userdir ./user_data --config "$CFG" \
      --strategy BtcDynamicRebalanceStrategy --timerange "$TRANGE" \
      --cache none --export trades \
      2>&1 | tee "$OUT/${mode}.log" | tail -25 || true
done

echo
echo "ALL DONE — run dynrebal_report.py"
