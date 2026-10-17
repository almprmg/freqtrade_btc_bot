"""fleet_watchdog.sh writes its actions to trad_pg system_events.

The script runs against a fake `docker` on PATH. For the DB insert the fake
runs the script's real `sh -c 'psql ...'` command, so with a scratch Postgres
(WATCHDOG_TEST_PG="port:db", table system_events present) the quoting is
exercised for real — including a message full of quotes and SQL.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fleet_watchdog.sh"
BASH = shutil.which("bash", path=r"C:\Program Files\Git\usr\bin") or shutil.which("bash")
PG = os.environ.get("WATCHDOG_TEST_PG")  # e.g. "55433:t3"
PSQL_DIR = os.environ.get("WATCHDOG_TEST_PSQL_DIR", "/c/Program Files/PostgreSQL/18/bin")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")

FAKE_DOCKER = r"""#!/usr/bin/env bash
# Fake docker for watchdog tests. Behaviour comes from env:
#   BOT (container name), MODE=hung|unreadable, INSERT=ok|fail|real
calls="$FAKE_DIR/calls"
case "$1" in
  ps)
    if [[ "$*" == *"-a"* ]]; then echo "$BOT"; else echo "$BOT"; fi ;;
  exec)
    if [[ "$2" == "-i" ]]; then
      shift 2; pg="$1"; shift 3   # exec -i <container> sh -c
      script="$1"; shift          # then: _ level type subject message metadata
      printf 'EVENT %s\n' "$*" >>"$calls"
      sql=$(cat); printf 'SQL %s\n' "$sql" >>"$calls"
      case "$INSERT" in
        fail) exit 1 ;;
        real) printf '%s' "$sql" | PATH="$PSQL_DIR:$PATH" POSTGRES_USER=trading POSTGRES_DB="$PG_DB" PGPORT="$PG_PORT" sh -c "$script" "$@" ;;
        *) exit 0 ;;
      esac
    else
      [[ "$MODE" == unreadable ]] && exit 1
      echo $(( $(date +%s) - 5000 ))   # log 5000s old -> hung
    fi ;;
  restart) echo "RESTART ${*:2}" >>"$calls" ;;
  inspect) echo "running 0" ;;
esac
"""


def _run(tmp: Path, **env: str) -> tuple[str, str]:
    fake = tmp / "bin"
    fake.mkdir(exist_ok=True)
    (fake / "docker").write_text(FAKE_DOCKER, newline="\n")
    (fake / "flock").write_text("#!/usr/bin/env bash\nexit 0\n", newline="\n")
    for f in ("docker", "flock"):
        (fake / f).chmod(0o755)
    state = tmp / "state"
    base = {
        **os.environ,
        "PATH": f"{fake.as_posix()}{os.pathsep}{os.environ['PATH']}",
        "FAKE_DIR": tmp.as_posix(),
        "STATE_DIR": state.as_posix(),
        "LOG": (tmp / "wd.log").as_posix(),
        "LOCK": (tmp / "wd.lock").as_posix(),
        "STAGGER_SECS": "0",
        "STALE_SECS": "600",
        "BOT": "freqtrade_hung",
        "MODE": "hung",
        "INSERT": "ok",
        "PSQL_DIR": PSQL_DIR,
        **env,
    }
    # Git Bash wants a POSIX PATH; prepend the fake bin in POSIX form.
    base["PATH"] = f"{_posix(fake)}:{os.environ.get('PATH', '')}"
    subprocess.run([BASH, SCRIPT.as_posix()], env=base, check=True, timeout=60)
    calls = (tmp / "calls").read_text() if (tmp / "calls").exists() else ""
    log = (tmp / "wd.log").read_text() if (tmp / "wd.log").exists() else ""
    return calls, log


def _posix(p: Path) -> str:
    s = p.as_posix()
    return f"/{s[0].lower()}{s[2:]}" if len(s) > 1 and s[1] == ":" else s


def test_restart_of_a_hung_bot_is_recorded(tmp_path: Path) -> None:
    calls, log = _run(tmp_path)
    assert "RESTART -t 20 freqtrade_hung" in calls
    assert "EVENT _ warning bot_restarted freqtrade_hung" in calls
    assert '{"log_age_seconds": 50' in calls  # ~5000s, rendered by the script
    assert "INSERT INTO system_events" in calls and ":'msg'" in calls
    assert "RESTART freqtrade_hung" in log


def test_unreadable_bot_warns_at_most_hourly(tmp_path: Path) -> None:
    calls, _ = _run(tmp_path, MODE="unreadable")
    calls2, log2 = _run(tmp_path, MODE="unreadable")
    assert calls2.count("bot_unreadable") == 1  # second run deduped
    assert log2.count("cannot read logfile mtime") == 2  # file log still every run


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    calls, log = _run(tmp_path, DRY="1")
    assert "EVENT" not in calls and "RESTART" not in calls
    assert "DRY  freqtrade_hung" in log


def test_db_failure_never_stops_the_watchdog(tmp_path: Path) -> None:
    calls, log = _run(tmp_path, INSERT="fail")
    assert "RESTART -t 20 freqtrade_hung" in calls
    assert "WARN system_events insert failed (bot_restarted freqtrade_hung)" in log


@pytest.mark.skipif(not PG, reason="WATCHDOG_TEST_PG not set")
def test_real_insert_survives_hostile_text(tmp_path: Path) -> None:
    port, db = PG.split(":")  # type: ignore[union-attr]
    # Container names come from `docker ps` and are split on whitespace by the
    # script, so the hostile text has no spaces (real names can't hold quotes either).
    bot = "freqtrade_it's\";DROP_TABLE_system_events;--"
    marker = f"wd-test-{time.time_ns()}"
    _run(tmp_path, INSERT="real", BOT=bot, PG_PORT=port, PG_DB=db, MARKER=marker)
    psql = Path(PSQL_DIR.replace("/c/", "C:/")) / "psql.exe"
    out = subprocess.run(
        [str(psql), "-p", port, "-U", "trading", "-d", db, "-X", "-At", "-c",
         "select subject, level, metadata->>'log_age_seconds' from system_events "
         "where event_type='bot_restarted' order by id desc limit 1"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    subject, level, age = out.split("|")
    assert subject == bot  # stored verbatim, table intact
    assert level == "warning"
    assert int(age) >= 4999
