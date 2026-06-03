#!/usr/bin/env bash
# Weekly meta-allocator runner — invoked by cron Sundays 00:00.
# Uses a purpose-built image (meta-allocator:latest) that has numpy + pandas + psycopg.
# Build once: docker build -t meta-allocator:latest -f scripts/Dockerfile.meta-allocator scripts/
set -euo pipefail

LOG=/srv/trad/logs/meta_allocator_$(date +%Y%m%d).log
mkdir -p /srv/trad/logs

cd /srv/trad/pythone/freqtrade_btc_bot

# Build the image if missing (idempotent — Docker caches layers)
if ! docker image inspect meta-allocator:latest >/dev/null 2>&1; then
  echo "[$(date)] building meta-allocator image..." >> "$LOG"
  docker build -t meta-allocator:latest -f scripts/Dockerfile.meta-allocator scripts/ >> "$LOG" 2>&1
fi

docker run --rm \
  --network trad_system_trad \
  -e TRAD_PG_DSN="postgresql://trading:e763ad7f2c4924e949913f58@trad_pg:5432/trading" \
  -e LOOKBACK_DAYS=90 \
  -v "$PWD:/work:ro" \
  -w /work \
  meta-allocator:latest \
  research/ai/meta_allocator.py >> "$LOG" 2>&1
# (dry-run is the default; add --apply to actually write changes to DB)

echo "[$(date)] meta-allocator dry-run completed, log: $LOG"
tail -25 "$LOG"
