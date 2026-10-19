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
PG_CONTAINER="${PG_CONTAINER:-trad_pg}"

# event LEVEL TYPE MESSAGE [METADATA_JSON] — a row in system_events (admin
# "System events"), same mechanism as fleet_watchdog.sh. Values reach psql as
# variables, never spliced into SQL; a DB failure only logs.
event() {
  [[ "${EVENTS:-1}" == 0 ]] && return 0
  local meta="${4:-}"
  [[ -n "$meta" ]] || meta='{}'
  if ! docker exec -i "$PG_CONTAINER" sh -c        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -q -v ON_ERROR_STOP=1 -v lvl="$1" -v typ="$2" -v msg="$3" -v meta="$4"'        _ "$1" "$2" "$3" "$meta" >/dev/null 2>&1 <<'SQL'
INSERT INTO system_events (source, level, event_type, subject, message, metadata)
VALUES ('anomaly_refresh', :'lvl'::log_level, :'typ', 'anomaly_flags_wf', :'msg', :'meta'::jsonb);
SQL
  then
    echo "WARN system_events insert failed ($2)"
  fi
}

# json_list a b c -> ["a","b","c"] (container names: [A-Za-z0-9_.-] only)
json_list() {
  local out="" x
  for x in "$@"; do out+="${out:+,}\"$x\""; done
  printf '[%s]' "$out"
}

mkdir -p /srv/trad/logs
exec 9>"$LOCK"
flock -n 9 || exit 0
exec >>"$LOG" 2>&1
cd "$REPO"
echo "[$(date -u +%FT%TZ)] start"

# set -e stops the script on the first failing step; say so in the feed.
trap 'event error anomaly_refresh_failed "Anomaly refresh failed (line $LINENO); flags not updated" "{\"line\":$LINENO}"' ERR

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
  event info anomaly_refresh_unchanged "Anomaly flags refreshed; unchanged, no bot restarted" "{\"md5\":\"$after\"}"
  exit 0
fi

# Restart only bots configured to read the walk-forward file, staggered so they
# don't all hit Binance load_markets at once.
restarted=() failed=()
for c in $(docker ps --format '{{.Names}}' | grep '^freqtrade_' | grep -v '_bridge$'); do
  if docker exec "$c" printenv ANOMALY_FLAGS_FILE 2>/dev/null | grep -qx 'anomaly_flags_wf.feather'; then
    echo "restart $c"
    if docker restart -t 20 "$c" >/dev/null; then restarted+=("$c"); else echo "ERROR restarting $c"; failed+=("$c"); fi
    sleep 10
  fi
done
meta="{\"md5_before\":\"$before\",\"md5_after\":\"$after\",\"restarted\":$(json_list "${restarted[@]}"),\"failed\":$(json_list "${failed[@]}")}"
if (( ${#failed[@]} )); then
  event warning anomaly_refresh_applied "Anomaly flags changed; restarted ${#restarted[@]} bot(s), ${#failed[@]} restart(s) failed" "$meta"
else
  event info anomaly_refresh_applied "Anomaly flags changed; restarted ${#restarted[@]} bot(s)" "$meta"
fi
echo "[$(date -u +%FT%TZ)] done"
