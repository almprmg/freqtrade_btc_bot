# Memory Index

- [Deploy topology](deploy-topology.md) — live stack is the `trad_*` testnet compose; launch gotchas (--env-file, CORS, prod secrets)
- [Dashboard live WebSocket](dashboard-live-websocket.md) — dashboard-only realtime feed: backend gateway + Binance bridge + snapshot poller, frontend ws-client/hooks
- [Strategy registration](strategy-registration.md) — a strategy needs both an engine `@register` class AND a `strategies` DB row; not auto-synced
- [User-data stream gap](user-data-stream-gap.md) — Binance listen-key stream is 410 Gone; fills caught by OrderPoller (REST); Option B WS-API push (Ed25519 session.logon) built but feature-flagged OFF until keys provisioned
- [Remote server deployment](remote-server-deployment.md) — `trad_*` stack mirrored to 72.62.179.86 (`/srv/trad/`); ssh alias `trad-server`; admin CSP + .env URL patches live only on remote until ported back
- [AI batches complete](ai-batches-complete.md) — 11/18 ideas tested, 4 deployed (subs #98-#101); SOL has no viable Shield variant; meta_allocator on weekly cron
- [Strategy skills cloud](strategy-skills-cloud.md) — 13 specialized skills: DEV (architect/researcher/explorer/builder/critic) + OPS (fleet-monitor/data-engineer/debugger/risk-manager) + ADVANCED (live-trading-ops/reporter/market-analyst) + orchestrator (strategy-lab)
- [Postgres zombie txns](postgres-zombie-txns.md) — high server load + RAM exhaustion often caused by stale `idle in transaction` connections; kill them before touching docker
