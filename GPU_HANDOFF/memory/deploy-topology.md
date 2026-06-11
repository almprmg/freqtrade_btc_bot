---
name: deploy-topology
description: How the live trading stack runs in Docker (testnet compose) and the launch gotchas
metadata: 
  node_type: memory
  type: project
  originSessionId: c6b7981a-ab09-43a6-8c01-9158e654c95d
---

The **live** running stack is the `trad_*` containers from `D:\pythone\trad_system\docker-compose.testnet.yml`, launched with `--env-file .env.testnet`:
- `trad_backend` (host :3010) — builds from `../../node/trading_backend`, `NODE_ENV=production`
- `trad_admin` (host :3001) — builds from `../../node/trading_admin`, BFF reaches backend via internal `http://backend:3000/api/v1`
- `trad_engine`, `trad_pg` (:5433), `trad_redis` (:6380)

Do NOT use `D:\node\trading_backend\docker-compose.yml` — it produces a separate `trading_backend` container that collides on port 3010.

Gotchas (each cost debugging time):
- Always pass `--env-file .env.testnet`. Without it, `${POSTGRES_PASSWORD:-trading}` defaults to `trading` and the backend fails DB auth (`password authentication failed for user "trading"`) against the existing pgdata volume. There is no `.env` in the dir for substitution.
- Because containers run `NODE_ENV=production`, the env validator ([env.ts](D:/node/trading_backend/src/config/env.ts)) refuses to boot on dev-default secrets or `CORS_ORIGIN="*"`. New required secrets must be added to `.env.testnet`.
- `D:\node\trading_backend\.env` has a typo `CORS_ORIGINS` (plural); the schema reads `CORS_ORIGIN` (singular).
- Rebuild after source edits: `docker compose -f docker-compose.testnet.yml --env-file .env.testnet up -d --build <service>` (the source is baked into the image — no bind mount / hot reload).

Related: [[dashboard-live-websocket]]
