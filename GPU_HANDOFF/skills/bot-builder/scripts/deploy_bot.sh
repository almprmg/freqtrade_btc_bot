#!/usr/bin/env bash
# deploy_bot.sh — Deploy a new bot to trad-server.
#
# Usage:
#   bash deploy_bot.sh <slug> <wallet_usd>
#
# Assumes you've already:
#   1. Created strategy file (user_data/strategies/<slug>_strategy.py)
#   2. Created config (config.<slug>.json)
#   3. Created docker-compose (docker-compose.<slug>.yml)
#   4. Created SQL insert (d:/tmp/<slug>_insert.sql)
#   5. PASSED Adversarial Validator (PASS or WARN verdict)
#
# This script:
#   1. Syncs artifacts to trad-server
#   2. Runs SQL on trad_pg
#   3. Captures sub_id
#   4. Writes env file (chmod 600)
#   5. Brings up containers
#   6. Verifies running

set -euo pipefail

SLUG="${1:-}"
WALLET="${2:-3000}"
REPO="${REPO:-d:/pythone/freqtrade_btc_bot}"
SSH_HOST="${SSH_HOST:-trad-server}"

if [ -z "$SLUG" ]; then
  echo "Usage: bash deploy_bot.sh <slug> [wallet_usd]"
  echo "Example: bash deploy_bot.sh eth_calendar 3000"
  exit 1
fi

CONFIG="$REPO/config.${SLUG}.json"
STRATEGY="$REPO/user_data/strategies/${SLUG}_strategy.py"
COMPOSE="$REPO/docker-compose.${SLUG}.yml"
SQL="d:/tmp/${SLUG}_insert.sql"

for f in "$CONFIG" "$STRATEGY" "$COMPOSE" "$SQL"; do
  if [ ! -f "$f" ]; then
    echo "ERROR: missing $f"
    exit 1
  fi
done

echo "=== 1. Sync artifacts to $SSH_HOST ==="
tar -cf - -C "$REPO" \
  "user_data/strategies/${SLUG}_strategy.py" \
  "config.${SLUG}.json" \
  "docker-compose.${SLUG}.yml" \
  | ssh "$SSH_HOST" "tar -xf - -C /srv/trad/pythone/freqtrade_btc_bot"

scp "$SQL" "$SSH_HOST:/tmp/" > /dev/null

echo "=== 2. Insert DB rows ==="
ssh "$SSH_HOST" "
  docker cp /tmp/${SLUG}_insert.sql trad_pg:/tmp/
  docker exec trad_pg psql -U trading -d trading -f /tmp/${SLUG}_insert.sql 2>&1 | tail -5
"

echo "=== 3. Capture sub_id and write env file ==="
SUB_ID=$(ssh "$SSH_HOST" "docker exec trad_pg psql -U trading -d trading -tAc \"SELECT id FROM user_strategy_subscriptions WHERE custom_parameters->>'source'='freqtrade_${SLUG}';\"")
if [ -z "$SUB_ID" ]; then
  echo "ERROR: could not find sub_id after insert"
  exit 1
fi
echo "  sub_id = $SUB_ID"

SLUG_UPPER=$(echo "$SLUG" | tr '[:lower:]' '[:upper:]')
ssh "$SSH_HOST" "
  cd /srv/trad/pythone/freqtrade_btc_bot
  cat > .env.${SLUG} <<ENV
FREQTRADE__EXCHANGE__KEY=
FREQTRADE__EXCHANGE__SECRET=
BRIDGE_USER_ID=10
TRAD_PG_DSN=postgresql://trading:e763ad7f2c4924e949913f58@trad_pg:5432/trading
BRIDGE_${SLUG_UPPER}_SUB=$SUB_ID
BRIDGE_POLL_INTERVAL=30
ENV
  chmod 600 .env.${SLUG}
"

echo "=== 4. docker compose up ==="
ssh "$SSH_HOST" "
  cd /srv/trad/pythone/freqtrade_btc_bot
  docker compose -f docker-compose.${SLUG}.yml --env-file .env.${SLUG} up -d 2>&1 | tail -6
"

echo "=== 5. Verify (sleeping 20s for startup) ==="
ssh "$SSH_HOST" "
  sleep 20
  docker ps --filter 'name=freqtrade_${SLUG}' --format 'table {{.Names}}\t{{.Status}}'
  echo ''
  echo 'Fleet total: '\$(docker ps --filter name=freqtrade_ --format '{{.Names}}' | wc -l)' containers'
"

echo ""
echo "=== Deployed: sub #$SUB_ID, wallet \$${WALLET} ==="
echo "Next: monitor for 24h via 'docker logs freqtrade_${SLUG}' before considering it stable."
