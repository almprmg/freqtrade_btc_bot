#!/usr/bin/env bash
# Runs all 6 rebalance modes back-to-back over 5 years at $500 portfolio,
# then re-runs the chosen winner at $100 to compare scale sensitivity.
set -euo pipefail
export PATH="$PWD/.venv/Scripts:$PATH"

CFG="config.rebalance.json"
TRANGE="20210101-20260101"
OUT="./rebalance_results"
mkdir -p "$OUT"

MODES=(R1_DAILY_FULL R2_DAILY_5PCT R3_DAILY_10PCT R4_25_BTC R5_75_BTC R6_HALFWAY)

# --- Phase 1: all 6 modes at $500 -----------------------------------------
for mode in "${MODES[@]}"; do
  echo
  echo "================================================================"
  echo ">>> $mode  (wallet=\$500)"
  echo "================================================================"
  REBALANCE_MODE="$mode" freqtrade backtesting \
      --userdir ./user_data --config "$CFG" \
      --strategy BtcRebalanceStrategy --timerange "$TRANGE" \
      --dry-run-wallet 500 \
      --cache none --export trades \
      2>&1 | tee "$OUT/${mode}__500.log" | tail -40 || true
done

# --- Phase 2: best mode also at $100 (decided by yearly_rebalance_report.py) #
# Pass winner mode via env or default to R1.
WINNER="${REBALANCE_WINNER:-R1_DAILY_FULL}"
echo
echo "================================================================"
echo ">>> $WINNER  (wallet=\$100)"
echo "================================================================"
REBALANCE_MODE="$WINNER" freqtrade backtesting \
    --userdir ./user_data --config "$CFG" \
    --strategy BtcRebalanceStrategy --timerange "$TRANGE" \
    --dry-run-wallet 100 \
    --cache none --export trades \
    2>&1 | tee "$OUT/${WINNER}__100.log" | tail -40 || true

echo
echo "ALL DONE — run rebalance_report.py for analysis"
