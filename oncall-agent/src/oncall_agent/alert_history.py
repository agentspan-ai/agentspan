"""How often has this cluster alerted before? A month of alert history, from the alert channels.

ah5r's search keeps only ~3-4 days of health checks, too short to tell a chronic pattern from a
new one. Slack keeps the alerts themselves, and the listener reads every one: each is recorded
here (time, cluster, issue kinds), and ``scripts/backfill_alert_history.py`` loads the past
30 days once. Lives in the same private SQLite file as the release index.
"""
from __future__ import annotations

import re
import sqlite3
import time
from datetime import datetime, timezone

from .release_index import connect

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (ts REAL, channel TEXT, cluster TEXT, kinds TEXT, execution_id TEXT,
                                   PRIMARY KEY (channel, ts));
CREATE INDEX IF NOT EXISTS alerts_cluster ON alerts (cluster, ts);
"""

# Coarse issue kinds: stable across wording changes in the notifier, readable in an answer.
_KINDS = [("cpu", r"cpu"), ("memory", r"heap|memory|oom"), ("redis", r"redis"), ("postgres", r"postgres|database|db "),
          ("timed_out", r"timed.?out|poll timeout"), ("domain", r"domain|certificate|dns|ingress"),
          ("pod_down", r"has failed|not running|failed to connect|unreachable|restart"),
          ("queue", r"queue|backlog|decider"), ("prometheus", r"prometheus|grafana|metrics")]


def kinds_of(text: str) -> list[str]:
    t = (text or "").lower()
    return sorted({k for k, rx in _KINDS if re.search(rx, t)}) or ["other"]


def db() -> sqlite3.Connection:
    c = connect()
    c.executescript(SCHEMA)
    return c


def record(conn: sqlite3.Connection, ts: float, channel: str, cluster: str | None, text: str,
           execution_id: str | None) -> None:
    if not cluster:
        return
    conn.execute("INSERT OR IGNORE INTO alerts VALUES (?,?,?,?,?)",
                 (float(ts), channel, cluster, ",".join(kinds_of(text)), execution_id))
    conn.commit()


def history(conn: sqlite3.Connection, cluster: str | None, text: str, days: int = 30,
            now: float | None = None) -> dict:
    """Days with alerts in the last ``days`` (all kinds and this alert's kinds) and a verdict."""
    if not cluster:
        return {"verdict": "unknown cluster"}
    now = now or time.time()
    rows = conn.execute("SELECT ts, kinds FROM alerts WHERE cluster = ? AND ts > ? AND ts < ?",
                        (cluster, now - days * 86400, now - 60)).fetchall()
    mine = set(kinds_of(text))
    day = lambda ts: datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    all_days = {day(r[0]) for r in rows}
    same = [r for r in rows if mine & set((r[1] or "").split(","))]
    same_days = sorted({day(r[0]) for r in same})
    if not rows:
        verdict = f"NEW: no alerts from this cluster in the last {days} days."
    elif len(same_days) >= max(3, days // 5):
        verdict = (f"CHRONIC: this kind of alert ({', '.join(sorted(mine))}) fired on {min(len(same_days), days)} of the "
                   f"last {days} days ({len(same)} alerts), first {same_days[0]}. It is a standing condition: "
                   "never call it transient or one-off — say it recurs and name the lasting fix.")
    elif same_days:
        verdict = (f"RECURRING: same kind of alert on {len(same_days)} day(s) in the last {days} "
                   f"({', '.join(same_days[-5:])}).")
    else:
        verdict = f"Alerted on {len(all_days)} day(s) in the last {days}, but never with this kind of alert."
    return {"days": days, "daysWithAlerts": len(all_days), "daysWithThisKind": len(same_days),
            "alertsOfThisKind": len(same), "kinds": sorted(mine), "verdict": verdict}
