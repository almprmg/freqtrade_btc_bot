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
#                DRY=1 to only report.
set -euo pipefail

STALE_SECS="${STALE_SECS:-600}"
COOLDOWN_SECS="${COOLDOWN_SECS:-1800}"
MAX_RESTARTS="${MAX_RESTARTS:-5}"
STATE_DIR="${STATE_DIR:-/var/lib/fleet-watchdog}"
LOG="${LOG:-/var/log/fleet-watchdog.log}"
LOCK="${LOCK:-/run/fleet-watchdog.lock}"

mkdir -p "$STATE_DIR"
exec 9>"$LOCK"
flock -n 9 || exit 0  # previous run still going

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" >>"$LOG"; }

now=$(date +%s)
restarts=0

for c in $(docker ps --format '{{.Names}}' | grep '^freqtrade_' | grep -v '_bridge$' || true); do
  # Logfile path comes from the bot's own command line (PID 1 is freqtrade).
  mtime=$(docker exec "$c" sh -c '
    f=$(tr "\0" "\n" </proc/1/cmdline | grep -A1 -- --logfile | tail -1)
    [ -n "$f" ] && [ -f "$f" ] && stat -c %Y "$f"' 2>/dev/null) || { log "WARN $c: cannot read logfile mtime"; continue; }
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
  docker restart -t 20 "$c" >/dev/null && touch "$STATE_DIR/$c" || log "ERROR $c: restart failed"
  restarts=$(( restarts + 1 ))
  sleep 10  # stagger: avoid every bot hitting Binance load_markets at once
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
  else
    log "ERROR $c: recreate failed"
  fi
  restarts=$(( restarts + 1 ))
  sleep 10
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
    touch "$seen"
  fi
done
