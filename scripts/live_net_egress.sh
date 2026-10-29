#!/usr/bin/env bash
# Egress policy for the isolated live bot network (live_net / br-live).
#
#   allowed : TCP 443 to public IPs (Binance REST/WS)
#   dropped : everything else leaving br-live, any private/link-local range
#             (other containers, trad_pg, cloud metadata), and the host itself
#
# DNS still works: containers on a user-defined network resolve through
# Docker's embedded resolver (127.0.0.11 inside the container), which dockerd
# forwards from the host namespace — no packet to the host leaves br-live.
#
# Scope: every rule matches -i br-live, so nothing else on the server is
# affected. Idempotent (-C before -I). Run after docker.service (it owns the
# DOCKER-USER chain) by live-net-egress.service; `--remove` undoes it.
set -euo pipefail
IF=br-live
PRIVATE="10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 100.64.0.0/10 127.0.0.0/8"

rule() {  # rule CHAIN POS ARGS...
  local chain=$1 pos=$2; shift 2
  if [[ "${MODE:-add}" == remove ]]; then
    while iptables -C "$chain" "$@" 2>/dev/null; do iptables -D "$chain" "$@"; done
  elif ! iptables -C "$chain" "$@" 2>/dev/null; then
    iptables -I "$chain" "$pos" "$@"
  fi
}

[[ "${1:-}" == --remove ]] && MODE=remove
iptables -N DOCKER-USER 2>/dev/null || true

# Inserted at fixed positions so the final order is: private drop, 443 allow, drop.
pos=1
for net in $PRIVATE; do rule DOCKER-USER $pos -i $IF -d "$net" -j DROP; pos=$((pos + 1)); done
rule DOCKER-USER $pos -i $IF -p tcp --dport 443 -j RETURN; pos=$((pos + 1))
rule DOCKER-USER $pos -i $IF -j DROP
# Nothing from the live network may reach the host (sshd, nginx, docker-proxy...).
rule INPUT 1 -i $IF -j DROP

echo "live_net egress policy ${MODE:-add}ed"
