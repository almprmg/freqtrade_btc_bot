#!/usr/bin/env bash
# End-to-end backtest pipeline for BtcRegimeStrategy.
#
# Order matters:
#   1. download-data        — fetch BTC/USDT for 4h + 1h + 1d across 2022-2025
#   2. lookahead-analysis   — proves the strategy doesn't peek into the future
#   3. recursive-analysis   — proves indicators converge with more history
#   4. backtesting          — actual P&L over the full period, exported trades
#
# The downloader is idempotent — re-running fetches only missing candles, so
# it's safe to call this script repeatedly during tuning.
#
# Usage:
#   chmod +x backtest.sh
#   ./backtest.sh                 # all 4 phases, default config.dryrun.json
#   CONFIG=./my.json ./backtest.sh  # use a different config file
#
# Acceptance criteria (from spec):
#   Win Rate     > 58%
#   Profit Factor > 1.5
#   Sharpe        > 0.8
#   Max Drawdown  < 20%
#   Trade count   > 150
# Manually inspect user_data/backtest_results/ after the run.

set -euo pipefail

CONFIG="${CONFIG:-./config.dryrun.json}"
USERDIR="${USERDIR:-./user_data}"
STRATEGY="${STRATEGY:-BtcRegimeStrategy}"
PAIRS="${PAIRS:-BTC/USDT}"
TIMEFRAMES="${TIMEFRAMES:-4h 1h 1d}"
TIMERANGE="${TIMERANGE:-20220101-20260101}"

echo "================================================================"
echo "BtcRegimeStrategy backtest pipeline"
echo "  config:     $CONFIG"
echo "  user_data:  $USERDIR"
echo "  pair(s):    $PAIRS"
echo "  timeframes: $TIMEFRAMES"
echo "  timerange:  $TIMERANGE"
echo "================================================================"

if ! command -v freqtrade >/dev/null 2>&1; then
  echo "ERROR: freqtrade not on PATH. Activate your venv first (see README)." >&2
  exit 1
fi

mkdir -p "$USERDIR/logs" "$USERDIR/data" "$USERDIR/backtest_results"

# ---- 1. Download data ----------------------------------------------------
echo
echo "[1/4] Downloading OHLCV..."
freqtrade download-data \
    --userdir "$USERDIR" \
    --config "$CONFIG" \
    --pairs $PAIRS \
    --timeframes $TIMEFRAMES \
    --timerange "$TIMERANGE" \
    --exchange binance

# ---- 2. Lookahead analysis ----------------------------------------------
echo
echo "[2/4] Lookahead analysis (no future leakage)..."
freqtrade lookahead-analysis \
    --userdir "$USERDIR" \
    --config "$CONFIG" \
    --strategy "$STRATEGY" \
    --timerange "$TIMERANGE"

# ---- 3. Recursive analysis ----------------------------------------------
echo
echo "[3/4] Recursive analysis (indicator stability)..."
freqtrade recursive-analysis \
    --userdir "$USERDIR" \
    --config "$CONFIG" \
    --strategy "$STRATEGY" \
    --timerange "$TIMERANGE"

# ---- 4. Backtest --------------------------------------------------------
echo
echo "[4/4] Running backtest..."
freqtrade backtesting \
    --userdir "$USERDIR" \
    --config "$CONFIG" \
    --strategy "$STRATEGY" \
    --timerange "$TIMERANGE" \
    --export trades \
    --export-filename "$USERDIR/backtest_results/btc_regime_$(date +%Y%m%d_%H%M%S).json"

echo
echo "================================================================"
echo "DONE — review:"
echo "  $USERDIR/backtest_results/   (trades export + summary)"
echo "Run \`freqtrade plot-dataframe\` or \`freqtrade backtesting-show\` for"
echo "deeper analysis."
echo "================================================================"
