---
name: postgres-zombie-txns
description: "When trad_pg shows \"idle in transaction\" for hours/days, server load skyrockets and disk locks block DELETEs"
metadata: 
  node_type: memory
  type: reference
  originSessionId: f5b8d411-6772-4bab-83da-8fb16976dbd5
---

When server load on trad-server is unexpectedly high (e.g. 300+) and RAM is exhausted, check for stale postgres transactions before touching docker containers:

```sql
SELECT pid, state, query_start, LEFT(query, 80)
FROM pg_stat_activity
WHERE state = 'idle in transaction' AND query_start < NOW() - INTERVAL '1 hour';
```

If many rows return, kill them:
```sql
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle in transaction' AND query_start < NOW() - INTERVAL '1 hour';
```

**Real incident (2026-06-09):** trad-server load avg was 309/236/163, RAM at 99%. Investigation found 74 zombie transactions dating back ~6 days holding row locks across `trades`, `orders`, `strategies`. Killing them dropped load to 0.68 in under a minute and freed enough RAM that no bots needed stopping. The zombies were also blocking a 799K-row cascade DELETE that appeared "hung."

**Why:** Most likely a Node/Python service crashed without closing transactions, or a TCP connection was severed mid-BEGIN. PostgreSQL keeps the transaction "open" indefinitely until either COMMIT, ROLLBACK, or the connection is force-closed.

**Prevention:** Set `idle_in_transaction_session_timeout` in trad_pg config (e.g. 300s = 5min). Default is 0 (unlimited).
