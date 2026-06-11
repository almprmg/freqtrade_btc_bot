---
name: user-data-stream-gap
description: "Binance user-data push is 410 Gone; runtime LIMIT/grid-TP fills are now caught by the OrderPoller (REST fallback), not the WS"
metadata: 
  node_type: memory
  type: project
  originSessionId: c6b7981a-ab09-43a6-8c01-9158e654c95d
---

Binance deprecated the SPOT listen-key user-data stream (`POST /api/v3/userDataStream` → **410 Gone**), so the engine's private push stream never opens. The 410 is handled gracefully (one warning, no traceback).

**Impact (historical):** MARKET fills were always fine (synchronous in the REST place_order response → `open_trade`/`close_trade` called directly). The gap was **resting LIMIT fills — the grid take-profit exits** ([[strategy-registration]]): their only observer was the `executionReport` push, and the startup `Reconciler` only resolves `status='pending'` (a resting LIMIT is `OPEN`).

**Fixed (2026-05-26):** an always-on `OrderPoller` (`engine/order_poller.py`, interval `ORDER_POLL_INTERVAL_SECONDS`, default 5s) polls non-terminal orders via `GET /api/v3/order` and, on a terminal transition, runs the SAME persist + open/close-trade dispatch as the WS through the shared `engine/order_sync.py` helper (`apply_order_update` + `map_binance_status` — now single-sourced across WS handler, poller, order manager, reconciler). Commission is fetched via `get_my_trades` for fee-accurate PnL. `open_trade`/`close_trade` are idempotent (entry/exit-order guards), so WS+poller overlap is a no-op.

**Option B (real-time WS-API push) — BUILT, feature-flagged OFF (2026-05-26):** `BinanceWsApiUserDataStream` (`exchanges/binance/ws_user_data_api.py`) does `session.logon` (Ed25519, `ws_api_auth.py`) → `userDataStream.subscribe`, routing events through the shared `user_data_events.UserDataEventRouter` (also used by the listen-key WS). Schema: `exchange_connections.ws_api_key` + `ws_api_private_key_enc` (alembic `ws_api_ed25519_keys`, private key AES-encrypted). `ws_manager` uses it only when `ENABLE_WS_API_USER_DATA=true` AND the connection has an Ed25519 key; else listen-key→poller. **Not yet enabled** — needs an Ed25519 key registered on the Binance account (enablement steps + envelope-verification caveat in `docs/user_data_stream_migration.md`).
