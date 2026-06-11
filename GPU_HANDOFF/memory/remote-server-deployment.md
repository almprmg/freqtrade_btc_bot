---
name: remote-server-deployment
description: "Production-ish testnet deploy on 72.62.179.86 (srv1246762, Ubuntu 22.04) — layout, ports, gotchas"
metadata: 
  node_type: memory
  type: project
  originSessionId: c6b7981a-ab09-43a6-8c01-9158e654c95d
---

The trad_* stack is mirrored to **root@72.62.179.86** (Hostinger VPS, Ubuntu 22.04.5, 4 vCPU/15 GB/194 GB). Initial deploy: 2026-06-01.

**Why:** user requested a publicly-reachable testnet so they (and others) can hit the dashboard from outside; local Docker stack was already healthy with real data — moved everything as-is.

**How to apply:** when iterating on backend/engine/admin, edit local repos as usual; redeploy by re-running `tar | ssh` push then `docker compose ... up -d --build <service>`. SSH key auth via `~/.ssh/id_ed25519_trad` (alias `trad-server` in `~/.ssh/config`). DO NOT push secrets to git — `.env.testnet` is `scp`'d separately and `chmod 600`.

## Layout (mirrors `D:/` paths so compose build contexts resolve)
```
/srv/trad/
├── pythone/{trad_system, trading_engine}    # compose lives in trad_system
└── node/{trading_backend, trading_admin}
```

## Ports (no conflict with the unrelated `traveler-*` stack also on this server)
- 3001 admin / 3010 backend / 5433 pg / 6380 redis / 9090 engine metrics / 9091 prometheus / 3004 grafana
- mailpit web 8026 + SMTP 1026 (compose already remapped because traveler-mailpit holds 8025/1025)

## Gotchas baked in already
1. **`.env.testnet` URL keys patched to public IP** on remote: `FRONTEND_URL`, `CORS_ORIGIN`, `REALTIME_WS_URL` all use `http(s)://72.62.179.86:<port>`. If you re-scp the local file, re-apply the sed.
2. **Admin CSP `connect-src` was hard-coded `ws://localhost:3010`**. Fixed by adding `ARG NEXT_PUBLIC_REALTIME_WS_ORIGIN` + `ENV …=$ARG` after `ENV NEXT_TELEMETRY_DISABLED=1` in [node/trading_admin/Dockerfile], wiring `build.args` in the admin block of `docker-compose.testnet.yml`, and adding `NEXT_PUBLIC_REALTIME_WS_ORIGIN=ws://72.62.179.86:3010 wss://72.62.179.86:3010` to `.env.testnet`. **These edits live only on the remote** — port them to local repos and commit when convenient (otherwise the next `tar | ssh` push will clobber them).
3. **Auth cookies had `Secure` flag forced by `NODE_ENV=production`** — browser silently dropped them on plain HTTP, so login looked broken (returned 200, browser stored nothing, redirected back to /login). Fixed by patching `node/trading_admin/src/lib/server/cookies.ts` to honor `COOKIES_SECURE=false` (`secure: process.env.COOKIES_SECURE === "false" ? false : isProd`), wiring `COOKIES_SECURE: ${COOKIES_SECURE:-true}` into the admin block of the compose file, and setting `COOKIES_SECURE=false` in `.env.testnet`. **Flip back to `true` the moment HTTPS is in front of admin** — otherwise cookies are network-readable. Same caveat as item 2: edits live only on remote until ported back.
4. **Seed admin password was unrecoverable** after restoring the dump (bcrypt is one-way; the local `SEED_ADMIN_PASSWORD` was set inline and not stored anywhere). Reset both `admin` and `support1` to `TempAdmin#2026` via `docker exec trad_backend node -e 'bcrypt.hash(...)'` → `UPDATE admin_auth SET password_hash = ...`. **This is a TEMP credential** — anyone with conversation/log access can read it. Rotate from the admin UI ASAP.
3. **Postgres dump restore failed first time** with `--clean --if-exists` because tables have circular FK constraints (users → user_auth/portfolios/orders/etc.). Workaround: `DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL …` then re-pipe the gzipped dump into `psql`.
4. **SSH password auth for root is broken** on this VPS even though it was working on 2026-05-01. Use the installed ed25519 key (see [[ssh-credentials]] if you ever write it down).

## Quick commands
```bash
ssh trad-server                                                  # alias
ssh trad-server 'cd /srv/trad/pythone/trad_system && docker compose -f docker-compose.testnet.yml --env-file .env.testnet ps'
ssh trad-server 'docker logs trad_engine --tail 50'
```

Related: [[deploy-topology]] (local stack), [[dashboard-live-websocket]] (the WS that needs CSP), [[user-data-stream-gap]] (engine quirk).
