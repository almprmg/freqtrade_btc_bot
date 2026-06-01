#!/usr/bin/env bash
# Run the winning DR_PROFIT_20 dynamic-rebalance strategy on three high-
# liquidity pairs (BTC/ETH/SOL) over the same 5-year window so the user
# can compare ROI per asset before picking which one to deploy.
set -euo pipefail
export PATH="$PWD/.venv/Scripts:$PATH"

TRANGE="20210101-20260101"
OUT="./multipair_results"
mkdir -p "$OUT"

PAIRS=(BTC/USDT ETH/USDT SOL/USDT)

for pair in "${PAIRS[@]}"; do
  short=$(echo "$pair" | cut -d/ -f1)
  cfg_tmp="config.dynrebal-${short}.json"
  # Generate a per-pair config from the base.
  jq --arg p "$pair" --arg bot "btc_dynrebal_${short}" \
     --arg db "sqlite:///user_data/tradesv3_dynrebal_${short}.sqlite" \
     '.exchange.pair_whitelist = [$p] | .bot_name = $bot | .db_url = $db' \
     config.dynrebal.json > "$cfg_tmp"

  echo
  echo "================================================================"
  echo ">>> DR_PROFIT_20 on $pair"
  echo "================================================================"
  DR_MODE=DR_PROFIT_20 freqtrade backtesting \
      --userdir ./user_data --config "$cfg_tmp" \
      --strategy BtcDynamicRebalanceStrategy --timerange "$TRANGE" \
      --cache none --export trades \
      2>&1 | tee "$OUT/dynrebal_${short}.log" | tail -25 || true
  rm -f "$cfg_tmp"
done

echo
echo "ALL DONE — run multipair_report.py"
