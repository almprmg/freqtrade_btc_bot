---
name: strategy-registration
description: How engine strategies become usable — registry (code) + strategies DB table are NOT auto-synced
metadata: 
  node_type: memory
  type: project
  originSessionId: c6b7981a-ab09-43a6-8c01-9158e654c95d
---

A trading strategy is usable only when it exists in BOTH places, which are not auto-synced:

1. **Engine code registry** — a class in `d:/pythone/trading_engine/src/trading_engine/strategies/<name>.py` decorated with `@register` and a `name: ClassVar[str]`. Loaded into `STRATEGY_REGISTRY` at engine boot. Adding a file requires **rebuilding the engine container** (`trad_engine` is a baked image, no source mount) for it to load.
2. **DB `strategies` table** — a row whose `name` matches the registry key. The admin UI, dashboard reports, and subscriptions all read from here. Required cols: `name`, `display_name` (others default: `default_symbol`=BTCUSDT, `default_timeframe`=1h, `min_capital`=0, `is_active`=true).

The engine only **validates** the two at boot (`validate_registry_against_db` in registry.py): logs `engine.strategies_in_db_not_in_code` for `db_only` (aborts boot only when `environment==prod`), and does nothing to create missing DB rows for `registry_only`. So a new code strategy is invisible/unsubscribable until you manually INSERT its DB row.

To dump a strategy's default params for seeding: `docker compose -f docker-compose.testnet.yml exec -T engine python -c "from trading_engine.strategies.registry import STRATEGY_REGISTRY; ..."`.

History: on 2026-05-24 the 7 `ofi_*` (Order Flow Imbalance variants) were in code but missing from the DB — seeded as ids 29–35 (`strategy_type='order_flow'`). `ma_crossover` (DB id 2) is the inverse: a DB row with no code class.

Deploy/rebuild commands: see [[deploy-topology]]. Dashboard per-strategy live P&L: [[dashboard-live-websocket]] (auto-shows any strategy once it has subscriptions + trades).
