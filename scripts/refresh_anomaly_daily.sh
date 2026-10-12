#!/usr/bin/env bash
# refresh_anomaly_daily.sh — keep the walk-forward anomaly flags current.
#
# Why: nothing refreshed the 1d OHLCV or the anomaly flags after 2026-06-01,
# so every shield bot's anomaly exit was silently inert for four months, and
# the server had no BTC/ETH/SOL 1d data at all (audit C12 follow-up).
#
# Steps: incremental 1d download (public data, no keys) → walk-forward flags
# (never touches the in-sample anomaly_flags.feather) → if the flags changed,
# restart the bots that read them (strategies load the file at import).
#
# Install (host cron, after the 00:00 UTC daily close and the 00:30 macro job):
#   45 0 * * * /srv/trad/pythone/freqtrade_btc_bot/scripts/refresh_anomaly_daily.sh
set -euo pipefail

REPO=/srv/trad/pythone/freqtrade_btc_bot
IMAGE=freqtradeorg/freqtrade:2026.4
PAIRS="BTC/USDT ETH/USDT SOL/USDT ADA/USDT AVAX/USDT BNB/USDT DOGE/USDT"
FLAGS=user_data/data/anomaly_flags_wf.feather
LOG=/srv/trad/logs/anomaly_refresh_$(date -u +%Y%m%d).log
LOCK=/run/anomaly-refresh.lock

mkdir -p /srv/trad/logs
exec 9>"$LOCK"
flock -n 9 || exit 0
exec >>"$LOG" 2>&1
cd "$REPO"
echo "[$(date -u +%FT%TZ)] start"

before=$(md5sum "$FLAGS" 2>/dev/null | cut -c1-32 || echo none)

# shellcheck disable=SC2086
docker run --rm -v "$REPO/user_data":/freqtrade/user_data "$IMAGE" \
  download-data --exchange binance --pairs $PAIRS --timeframes 1d \
  --data-format-ohlcv feather --datadir /freqtrade/user_data/data/binance \
  | grep -E "Downloaded|ERROR" || true

docker run --rm --entrypoint python -v "$REPO":/repo -w /repo "$IMAGE" \
  research/ai/anomaly_detector.py --walk-forward

after=$(md5sum "$FLAGS" | cut -c1-32)
if [[ "$before" == "$after" ]]; then
  echo "flags unchanged; no restart"
  exit 0
fi

# Restart only bots configured to read the walk-forward file, staggered so they
# don't all hit Binance load_markets at once.
for c in $(docker ps --format '{{.Names}}' | grep '^freqtrade_' | grep -v '_bridge$'); do
  if docker exec "$c" printenv ANOMALY_FLAGS_FILE 2>/dev/null | grep -qx 'anomaly_flags_wf.feather'; then
    echo "restart $c"
    docker restart -t 20 "$c" >/dev/null || echo "ERROR restarting $c"
    sleep 10
  fi
done
echo "[$(date -u +%FT%TZ)] done"
