#!/usr/bin/env bash
# Daily macro signals refresh — fetches Yahoo data + recomputes signals.
# Used by BtcMacroV2Strategy (sub #108).
set -euo pipefail

LOG=/srv/trad/logs/macro_refresh_$(date +%Y%m%d).log
mkdir -p /srv/trad/logs
cd /srv/trad/pythone/freqtrade_btc_bot

# Build dedicated image (idempotent — cached after first build)
if ! docker image inspect macro-fetcher:latest >/dev/null 2>&1; then
  cat > scripts/Dockerfile.macro-fetcher <<EOF
FROM python:3.12-slim
RUN pip install --no-cache-dir numpy>=1.26 pandas>=2.0 pyarrow yfinance>=1.4 scipy
WORKDIR /work
ENTRYPOINT ["python3"]
EOF
  docker build -t macro-fetcher:latest -f scripts/Dockerfile.macro-fetcher scripts/ 2>&1 | tail -3
fi

docker run --rm \
  -e PYTHONIOENCODING=utf-8 \
  -v "$PWD:/work" \
  macro-fetcher:latest \
  research/ai/macro_data.py all >> "$LOG" 2>&1

echo "[$(date)] macro refresh completed, log: $LOG"
tail -10 "$LOG"
