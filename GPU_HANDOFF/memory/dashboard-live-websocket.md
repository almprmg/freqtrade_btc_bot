---
name: dashboard-live-websocket
description: The dashboard-only realtime WebSocket feature — architecture and where it lives
metadata: 
  node_type: memory
  type: project
  originSessionId: c6b7981a-ab09-43a6-8c01-9158e654c95d
---

The admin dashboard ([dashboard.tsx](D:/node/trading_admin/src/pages/dashboard.tsx)) has live WebSocket updates (added 2026-05-23). Other pages stay REST/React-Query only — the WS client is lazy and only connects while dashboard components are mounted.

Backend feature: `D:/node/trading_backend/src/services/admin-service/admin-realtime/`
- Ticket auth: `POST /api/v1/admin/realtime/ticket` mints a single-use 30s JWT (secret `JWT_WS_TICKET_SECRET`, jti stored in Redis). WS upgrade at `/api/v1/realtime/ws?ticket=...` verifies+consumes it. Needed because the admin uses HTTP-only cookies (no client token).
- `market-feed.ts` bridges Binance public WS (`wss://stream.binance.com:9443`) for `ticker:*` / `kline:*` topics (lazy, only when subscribed).
- `snapshot-broadcaster.ts` polls DB every `REALTIME_SNAPSHOT_INTERVAL_MS` (2500) and broadcasts diffs for `trades.recent` + `system.overview`. No Python engine changes — that was a deliberate choice; upgrade path is Redis pub/sub fed by the engine.
- Gateway attached in [server.ts](D:/node/trading_backend/src/server.ts) on the `upgrade` event.

Frontend: singleton [ws-client.ts](D:/node/trading_admin/src/lib/realtime/ws-client.ts) + [useDashboardLive.ts](D:/node/trading_admin/src/lib/hooks/useDashboardLive.ts) hooks that patch React Query caches by `qk.*` keys. `PricePulse` flashes on cache patch.

In production set `REALTIME_WS_URL` to a browser-reachable `wss://` URL — otherwise the URL is derived from the request host, which is the internal `backend:3000` and unreachable from the browser. (In testnet `.env.testnet` it is `ws://localhost:3010/api/v1/realtime/ws`.)

Idempotency rule: `useLiveTrades` is mounted by multiple dashboard components (DashboardKpis + RecentTradesCard), and the ws-client delivers each event to EVERY registered handler — so a handler runs N times per event. Upsert-by-id patches are naturally idempotent; any ACCUMULATOR (e.g. folding realized P&L into a subscription on close) must be guarded (module-level `foldedClosedTradeIds` Set) or it double-counts. The backend snapshot-broadcaster must track ALL open trades (`where status:'open' OR closed_at recent`), not a `take:N` window by opened_at, or closes of older positions are never emitted; and it seeds the first poll silently via a `bootstrapped` flag (don't key the bootstrap off `lastTrades.size===0` — that only suppresses the first row and floods the rest).

Cache rule: live hooks must PATCH React Query caches with `setQueryData`, never `invalidateQueries`. Invalidation triggers a REST refetch per WS event; the backend global limiter is 100 req/15min and invalidating on a busy feed floods it → 429. (As of 2026-05-26 the limiter keys per-admin — `rl:globalLimiter:admin:<sub>` from the Bearer token — not by the shared BFF IP, so it's 100/15min PER admin; rate-limiter.middleware.ts `clientKey`. Login/unauthenticated still keys by IP.) `useLiveTrades` patches trades.recent / trades.today / trades.open and folds realized P&L into the owning subscription on close — zero REST after first mount. To clear a stuck limiter: `docker compose -f docker-compose.testnet.yml exec -T redis redis-cli --scan --pattern '*Limiter*' | xargs redis-cli del`.

CSP gotcha: the browser dials the backend WS on a *different origin*, so the admin's CSP `connect-src` must allow it. [next.config.ts](D:/node/trading_admin/next.config.ts) builds `connect-src 'self' ${NEXT_PUBLIC_REALTIME_WS_ORIGIN}` (defaults to `ws://localhost:3010 wss://localhost:3010`). Set `NEXT_PUBLIC_REALTIME_WS_ORIGIN` to the prod wss origin. Symptom when wrong: badge stuck on "Connecting…" and no `realtime/ws` entry in the Network tab. After changing CSP, hard-refresh the browser (cached old header + bundle).

Deployment/launch: see [[deploy-topology]].
