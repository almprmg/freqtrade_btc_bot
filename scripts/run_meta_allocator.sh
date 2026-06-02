#!/usr/bin/env bash
# Weekly meta-allocator runner — invoked by cron Sundays 00:00.
# Reallocates capital across the fleet based on rolling 90-day Sharpe.
# Runs inside trad_pg container (has psycopg pre-installed).
set -euo pipefail

LOG=/srv/trad/logs/meta_allocator_$(date +%Y%m%d).log
mkdir -p /srv/trad/logs

cd /srv/trad/pythone/freqtrade_btc_bot

# Use the bridge image which has python + psycopg
docker run --rm \
  --network trad_system_trad \
  -e TRAD_PG_DSN="postgresql://trading:e763ad7f2c4924e949913f58@trad_pg:5432/trading" \
  -e LOOKBACK_DAYS=90 \
  -v "$PWD:/work:ro" \
  -w /work \
  freqtrade-bridge:latest \
  python3 research/ai/meta_allocator.py --dry-run >> "$LOG" 2>&1

echo "[$(date)] meta-allocator dry-run completed, log: $LOG"
tail -20 "$LOG"
