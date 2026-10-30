"""Load the last N days of alerts from the alert channels into the alert history (run once).

    PYTHONPATH=src .venv/bin/python scripts/backfill_alert_history.py [--days 30]
Reads Slack history only. Cluster names come from the alert text ("cluster *Org - name*") or the
parsed alert; messages without a cluster are skipped.
"""
from __future__ import annotations

import argparse
import re
import time

import requests

from oncall_agent import alert_history
from oncall_agent.alert import message_text, parse_alert
from oncall_agent.config import Config

_CLUSTER = re.compile(r"cluster \*(?:[^*]* - )?([\w.-]+)\*|·\s*`([\w.-]+)`")


def cluster_of(text: str) -> str | None:
    m = _CLUSTER.search(text or "")
    return (m[1] or m[2]) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    cfg = Config.from_env()
    h = {"Authorization": f"Bearer {cfg.slack_bot_token}"}
    conn = alert_history.db()
    oldest = f"{time.time() - a.days * 86400:.0f}"
    for ch in cfg.slack_alert_channels:
        n, cursor = 0, None
        while True:
            p = {"channel": ch, "oldest": oldest, "limit": 200}
            if cursor:
                p["cursor"] = cursor
            d = requests.get("https://slack.com/api/conversations.history", headers=h, params=p, timeout=30).json()
            if not d.get("ok"):
                if d.get("error") == "ratelimited":
                    time.sleep(20)
                    continue
                print(ch, "error", d.get("error"))
                break
            for m in d.get("messages", []):
                if not (m.get("bot_id") or m.get("subtype") == "bot_message"):
                    continue
                text = message_text(m)
                a_ = parse_alert(text)
                cluster = (a_.cluster if a_ else None) or cluster_of(text)
                alert_history.record(conn, float(m["ts"]), ch, cluster, text, a_.execution_id if a_ else None)
                n += 1
            cursor = (d.get("response_metadata") or {}).get("next_cursor")
            if not d.get("has_more") or not cursor:
                break
            time.sleep(1.2)  # Slack tier-3 rate limit
        print(f"{ch}: {n} alert messages read")
    print("clusters with history:", conn.execute("SELECT count(DISTINCT cluster) FROM alerts").fetchone()[0],
          "| alerts:", conn.execute("SELECT count(*) FROM alerts").fetchone()[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
