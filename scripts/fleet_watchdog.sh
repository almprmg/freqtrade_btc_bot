#!/usr/bin/env bash
# fleet_watchdog.sh — restart freqtrade bots whose process is alive but hung.
#
# Why: on 2026-06-25 every bot failed load_markets, hit a cleanup exception and
# hung with PID 1 still alive, so Docker kept reporting "Up" for 108 days while
# nothing traded. Container status can't detect that; log freshness can —
# freqtrade writes a heartbeat line every ~60s to its --logfile.
#
# Install (host cron, every 5 min):
#   */5 * * * * /srv/trad/pythone/freqtrade_btc_bot/scripts/fleet_watchdog.sh
#
# Env overrides: STALE_SECS (default 600), COOLDOWN_SECS (1800), MAX_RESTARTS (5),
#                STAGGER_SECS (10), DRY=1 to only report, EVENTS=0 to skip the DB,
#                PG_CONTAINER (trad_pg).
#
# Every action (restart, recreate, failure, new warning) is also written to
# trad_pg system_events so it shows on the admin Events page. Routine runs and
# cooldown HOLDs are not written.
set -euo pipefail

STALE_SECS="${STALE_SECS:-600}"
COOLDOWN_SECS="${COOLDOWN_SECS:-1800}"
MAX_RESTARTS="${MAX_RESTARTS:-5}"
STATE_DIR="${STATE_DIR:-/var/lib/fleet-watchdog}"
LOG="${LOG:-/var/log/fleet-watchdog.log}"
LOCK="${LOCK:-/run/fleet-watchdog.lock}"
STAGGER_SECS="${STAGGER_SECS:-10}"
PG_CONTAINER="${PG_CONTAINER:-trad_pg}"

mkdir -p "$STATE_DIR"
exec 9>"$LOCK"
flock -n 9 || exit 0  # previous run still going

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" >>"$LOG"; }

# event LEVEL TYPE SUBJECT MESSAGE [METADATA_JSON]
# Values reach psql as variables (:'v' quoting), never spliced into SQL. A DB
# failure is logged and never stops the watchdog from acting.
event() {
  [[ "${DRY:-0}" == 1 || "${EVENTS:-1}" == 0 ]] && return 0
  local meta="${5:-}"
  [[ -n "$meta" ]] || meta='{}'
  if ! docker exec -i "$PG_CONTAINER" sh -c \
       'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -q -v ON_ERROR_STOP=1 -v lvl="$1" -v typ="$2" -v subj="$3" -v msg="$4" -v meta="$5"' \
       _ "$1" "$2" "$3" "$4" "$meta" >/dev/null 2>&1 <<'SQL'
INSERT INTO system_events (source, level, event_type, subject, message, metadata)
VALUES ('watchdog', :'lvl'::log_level, :'typ', :'subj', :'msg', :'meta'::jsonb);
SQL
  then
    log "WARN system_events insert failed ($2 $3)"
  fi
}

# due KEY SECONDS — true at most once per SECONDS for KEY (repeating warnings).
due() {
  local f="$STATE_DIR/evt_$1"
  if [[ -f "$f" ]] && (( $(date +%s) - $(stat -c %Y "$f") < $2 )); then return 1; fi
  touch "$f"
}

now=$(date +%s)
restarts=0

for c in $(docker ps --format '{{.Names}}' | grep '^freqtrade_' | grep -v '_bridge$' || true); do
  # Logfile path comes from the bot's own command line (PID 1 is freqtrade).
  mtime=$(docker exec "$c" sh -c '
    f=$(tr "\0" "\n" </proc/1/cmdline | grep -A1 -- --logfile | tail -1)
    [ -n "$f" ] && [ -f "$f" ] && stat -c %Y "$f"' 2>/dev/null) || {
    log "WARN $c: cannot read logfile mtime"
    if due "unreadable_$c" 3600; then
      event warning bot_unreadable "$c" "Cannot read the bot's log file (crash-looping or its process is gone)"
    fi
    continue
  }
  age=$(( now - mtime ))
  (( age <= STALE_SECS )) && continue

  last=0
  [[ -f "$STATE_DIR/$c" ]] && last=$(stat -c %Y "$STATE_DIR/$c")
  if (( now - last < COOLDOWN_SECS )); then
    log "HOLD $c: log stale ${age}s, restarted $(( now - last ))s ago (cooldown)"
    continue
  fi
  if (( restarts >= MAX_RESTARTS )); then
    log "HOLD $c: log stale ${age}s, restart budget for this run used"
    continue
  fi

  if [[ "${DRY:-0}" == 1 ]]; then
    log "DRY  $c: would restart (log stale ${age}s)"
    continue
  fi
  log "RESTART $c: log stale ${age}s"
  if docker restart -t 20 "$c" >/dev/null; then
    touch "$STATE_DIR/$c"
    event warning bot_restarted "$c" "Bot was hung (no log for ${age}s); restarted" "{\"log_age_seconds\": ${age}}"
  else
    log "ERROR $c: restart failed"
    event error bot_restart_failed "$c" "Bot is hung (no log for ${age}s) and the restart failed" "{\"log_age_seconds\": ${age}}"
  fi
  restarts=$(( restarts + 1 ))
  sleep "$STAGGER_SECS"  # stagger: avoid every bot hitting Binance load_markets at once
done

# Crash loops: a bot that dies on startup never writes a fresh heartbeat and
# can't be exec'd into, so the loop above only warns. `docker restart` keeps
# the same network namespace, so a container whose DNS broke (2026-10-13:
# freqtrade_dca, "Could not contact DNS servers") loops forever. Recreate it
# with the compose file + env file recorded in its own labels.
for c in $(docker ps -a --format '{{.Names}}' | grep '^freqtrade_' | grep -v '_bridge$' || true); do
  read -r status count < <(docker inspect -f '{{.State.Status}} {{.RestartCount}}' "$c" 2>/dev/null) || continue
  prev=$(cat "$STATE_DIR/count_$c" 2>/dev/null || echo "$count")
  echo "$count" >"$STATE_DIR/count_$c"
  # 3+ automatic restarts since the previous run (≤5 min) = crash loop.
  [[ "$status" == restarting ]] || (( count - prev >= 3 )) || continue

  last=0
  [[ -f "$STATE_DIR/recreate_$c" ]] && last=$(stat -c %Y "$STATE_DIR/recreate_$c")
  if (( now - last < COOLDOWN_SECS )); then
    log "HOLD $c: crash loop ($status, restarts $prev→$count), recreated $(( now - last ))s ago (cooldown)"
    continue
  fi
  if (( restarts >= MAX_RESTARTS )); then
    log "HOLD $c: crash loop, restart budget for this run used"
    continue
  fi
  cf=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$c")
  ef=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.environment_file"}}' "$c")
  svc=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$c")
  proj=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$c")
  if [[ -z "$cf" || -z "$svc" || -z "$proj" || ! -f "${cf%%,*}" ]]; then
    log "ERROR $c: crash loop but compose labels missing — recreate by hand"
    if due "labels_$c" 3600; then
      event error bot_recreate_failed "$c" "Bot is crash-looping but its compose labels are missing; recreate it by hand"
    fi
    continue
  fi
  if [[ "${DRY:-0}" == 1 ]]; then
    log "DRY  $c: would recreate (crash loop: $status, restarts $prev→$count) via $(basename "${cf%%,*}")"
    continue
  fi
  log "RECREATE $c: crash loop ($status, restarts $prev→$count)"
  # Only the first config file (bots here use one); env file only if recorded.
  if docker compose -p "$proj" -f "${cf%%,*}" ${ef:+--env-file "${ef%%,*}"} \
       up -d --no-deps --force-recreate "$svc" >/dev/null 2>&1; then
    touch "$STATE_DIR/recreate_$c"
    event warning bot_recreated "$c" "Bot was crash-looping ($status, restarts $prev→$count); recreated from its compose labels" \
      "{\"status\": \"$status\", \"restarts_before\": $prev, \"restarts_after\": $count}"
  else
    log "ERROR $c: recreate failed"
    event error bot_recreate_failed "$c" "Bot is crash-looping ($status) and the recreate failed"
  fi
  restarts=$(( restarts + 1 ))
  sleep "$STAGGER_SECS"
done

# Bridges whose bot is gone keep publishing a frozen position — report, don't act
# (some bots are intentionally stopped).
for b in $(docker ps --format '{{.Names}}' | grep '^freqtrade_.*_bridge$' || true); do
  bot=${b%_bridge}
  state=$(docker inspect -f '{{.State.Status}}' "$bot" 2>/dev/null || echo missing)
  [[ "$state" == running ]] && continue
  seen="$STATE_DIR/orphan_$b"
  # once a day per bridge, not every run
  if [[ ! -f "$seen" ]] || (( now - $(stat -c %Y "$seen") > 86400 )); then
    log "WARN $b running but bot $bot is $state"
    event warning bridge_without_bot "$b" "Bridge is running but its bot $bot is $state (the platform shows a frozen position)"
    touch "$seen"
  fi
done
