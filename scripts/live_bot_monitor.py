#!/usr/bin/env python3
"""Host-side monitor for the isolated live bot (live_btc_rebalance).

The bot has no network path to trad_pg on purpose, so the admin panel cannot
see it. This runs on the HOST (cron, every 10 min), reads the bot's SQLite
file directly and writes rows into system_events (source='live_bot'):

  live_bot_order      every newly filled order                    info
  live_bot_daily      once a day: value, BTC share, target        info
  live_bot_down       container not running (hourly at most)      error
  live_bot_restarted  unhealthy (no heartbeat) for 15 min ->      warning
                      restarted, at most once per hour

Read-only towards the bot; never touches its keys (secrets.json is never
opened). DRY=1 prints instead of writing/restarting.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CONTAINER = "live_btc_rebalance"
BASE = Path("/srv/trad/pythone/freqtrade_btc_bot/live/btc_rebalance")
DB = BASE / "data" / "live_btc_rebalance.sqlite"
CONFIG = BASE / "config.json"
STATE = Path(os.environ.get("STATE", "/var/lib/live-bot-monitor/state.json"))
PG = os.environ.get("PG_CONTAINER", "trad_pg")
DRY = os.environ.get("DRY") == "1"
FEE = 0.001
UNHEALTHY_RESTART_S = 15 * 60
RESTART_COOLDOWN_S = 60 * 60
DOWN_ALERT_EVERY_S = 60 * 60

SQL = """INSERT INTO system_events (source, level, event_type, subject, message, metadata)
VALUES ('live_bot', :'lvl'::log_level, :'typ', :'subj', :'msg', :'meta'::jsonb);"""


def event(level: str, typ: str, msg: str, meta: dict) -> None:
    if DRY:
        print(f"[DRY] {level} {typ}: {msg} {meta}")
        return
    cmd = ["docker", "exec", "-i", PG, "sh", "-c",
           'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -q -v ON_ERROR_STOP=1 '
           '-v lvl="$1" -v typ="$2" -v subj="$3" -v msg="$4" -v meta="$5"',
           "_", level, typ, CONTAINER, msg, json.dumps(meta)]
    r = subprocess.run(cmd, input=SQL, text=True, capture_output=True)
    if r.returncode != 0:
        print(f"WARN system_events insert failed ({typ}): {r.stderr.strip()}", file=sys.stderr)


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def save_state(st: dict) -> None:
    if DRY:
        return
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st))


def container_state() -> tuple[bool, str]:
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}} {{.State.Health.Status}}", CONTAINER],
                       text=True, capture_output=True)
    if r.returncode != 0:
        return False, "missing"
    running, health = (r.stdout.split() + ["unknown"])[:2]
    return running == "true", health


def btc_price() -> float | None:
    try:
        with urllib.request.urlopen("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=10) as f:
            return float(json.load(f)["price"])
    except Exception:
        return None


def check_health(st: dict, now: float) -> None:
    running, health = container_state()
    if not running:
        if now - st.get("last_down_alert", 0) >= DOWN_ALERT_EVERY_S:
            event("error", "live_bot_down", f"{CONTAINER} is not running ({health})", {"health": health})
            st["last_down_alert"] = now
        return
    if health != "unhealthy":
        st.pop("unhealthy_since", None)
        return
    since = st.setdefault("unhealthy_since", now)
    if now - since >= UNHEALTHY_RESTART_S and now - st.get("last_restart", 0) >= RESTART_COOLDOWN_S:
        if not DRY:
            subprocess.run(["docker", "restart", "-t", "30", CONTAINER], capture_output=True)
        event("warning", "live_bot_restarted",
              f"{CONTAINER} had no heartbeat for {int((now - since) / 60)} min; restarted",
              {"unhealthy_minutes": int((now - since) / 60)})
        st["last_restart"] = now
        st.pop("unhealthy_since", None)


def report_orders(con: sqlite3.Connection, st: dict, mode: str) -> None:
    last = int(st.get("last_order_id", 0))
    rows = con.execute(
        "SELECT id, ft_order_side, filled, average, cost, order_filled_date FROM orders "
        "WHERE id > ? AND status = 'closed' AND filled > 0 ORDER BY id", (last,)).fetchall()
    for oid, side, filled, avg, cost, at in rows:
        msg = f"[{mode}] {side.upper()} {filled:.6f} BTC @ {avg:,.2f} = {cost:,.2f} USDT"
        event("info", "live_bot_order", msg,
              {"order_id": oid, "side": side, "qty": filled, "price": avg, "cost": cost, "filled_at": at, "mode": mode})
        st["last_order_id"] = oid


def report_daily(con: sqlite3.Connection, st: dict, mode: str, wallet: float) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    if st.get("last_daily") == today:
        return
    price = btc_price()
    if price is None:
        return  # try again next run
    cash = wallet
    for side, cost in con.execute("SELECT ft_order_side, cost FROM orders WHERE status='closed' AND filled > 0"):
        cash += -cost * (1 + FEE) if side == "buy" else cost * (1 - FEE)
    qty = con.execute("SELECT COALESCE(SUM(amount), 0) FROM trades WHERE is_open = 1").fetchone()[0]
    target = con.execute(
        "SELECT cd_value FROM trade_custom_data WHERE cd_key='dr_applied_target' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    value = cash + qty * price
    share = qty * price / value if value else 0.0
    tgt = float(target[0]) if target else None
    msg = (f"[{mode}] value {value:,.2f} USDT ({value / wallet - 1:+.2%} since start), "
           f"BTC {share:.0%}" + (f" (target {tgt:.0%})" if tgt is not None else "") + f", BTC price {price:,.0f}")
    event("info", "live_bot_daily", msg,
          {"value": round(value, 2), "start": wallet, "btc_qty": qty, "btc_share": round(share, 4),
           "target": tgt, "cash": round(cash, 2), "btc_price": price, "mode": mode})
    st["last_daily"] = today


def main() -> None:
    st = load_state()
    now = time.time()
    check_health(st, now)
    cfg = json.loads(CONFIG.read_text())
    mode = "dry-run" if cfg.get("dry_run", True) else "LIVE"
    wallet = float(cfg.get("dry_run_wallet", 0)) if mode == "dry-run" else float(os.environ.get("LIVE_START_USDT", "0"))
    if DB.exists():
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
        try:
            report_orders(con, st, mode)
            if wallet > 0:
                report_daily(con, st, mode, wallet)
        finally:
            con.close()
    save_state(st)


if __name__ == "__main__":
    main()
