"""One daily message for on-call instead of hundreds of alerts: what is open, what keeps coming back,
what waits for a decision, and how the agent itself is doing.

Posted once a day by the listener (``ONCALL_DIGEST_HOUR_UTC``, default 03:30 UTC = 09:00 IST) to
``ONCALL_DIGEST_CHANNEL`` — the first approver's DM when unset, so it is reviewed before it goes
anywhere public.
"""
from __future__ import annotations

import json
import os
import time
from collections import Counter
from pathlib import Path

import requests

from . import alert_history


def _first_line(text: str) -> str:
    line = next((l for l in (text or "").splitlines() if l.strip()), "")
    return line.replace("*Cause*:", "").strip()[:140]


def build(state: dict, server: str, store: Path, now: float | None = None) -> str:
    now = now or time.time()
    lines = [f"*On-call digest — {time.strftime('%a %d %b', time.gmtime(now))}*"]

    # 1. Open incidents, oldest first, with the agent's one-line cause.
    open_ = sorted(state.get("incidents_open", {}).values(), key=lambda v: v.get("after", 0))
    lines.append(f"\n*Open incidents ({len(open_)})*")
    pending = []
    for inc in open_[:15]:
        try:
            wf = requests.get(f"{server.rstrip('/')}/workflow/{inc['workflow_id']}",
                              params={"includeTasks": "true"}, timeout=30).json()
        except Exception:
            wf = {}
        tasks = wf.get("tasks", [])
        triage = next((t for t in tasks if t.get("referenceTaskName") == "triage"), {})
        answer = (triage.get("outputData") or {}).get("answer") or "investigating…"
        firings = sum(1 for t in tasks if (t.get("outputData") or {}).get("kind") == "firing")
        if (wf.get("variables") or {}).get("pending"):
            pending.append(inc["cluster"])
        age_h = (now - inc.get("after", now)) / 3600
        lines.append(f"• `{inc['cluster']}` ({age_h:.0f}h{f', fired {firings + 1}x' if firings else ''}) — {_first_line(answer)}")
    if len(open_) > 15:
        lines.append(f"• …and {len(open_) - 15} more")

    # 2. What keeps coming back (last 30 days of alerts).
    conn = alert_history.db()
    since = now - 30 * 86400
    chronic = conn.execute("""SELECT cluster, count(*) n, count(DISTINCT date(ts, 'unixepoch')) d
                              FROM alerts WHERE ts > ? GROUP BY cluster HAVING d >= 6
                              ORDER BY d DESC, n DESC LIMIT 6""", (since,)).fetchall()
    if chronic:
        lines.append("\n*Chronic (alerting on many of the last 30 days)*")
        lines += [f"• `{r['cluster']}` — {min(r['d'], 30)} of 30 days, {r['n']} alerts" for r in chronic]

    # 3. Waiting for a human.
    if pending:
        lines.append("\n*Waiting for approval*")
        lines += [f"• `{c}` — a proposed change waits for `approve` / `reject` in its thread" for c in pending]

    # 4. The agent itself, last 24h.
    tri = [json.loads(l) for l in (store / "triages.jsonl").read_text().splitlines()
           if l.strip()] if (store / "triages.jsonl").exists() else []
    tri = [t for t in tri if t.get("at", 0) > now - 86400]
    fb = [json.loads(l) for l in (store / "feedback.jsonl").read_text().splitlines()
          if l.strip()] if (store / "feedback.jsonl").exists() else []
    verdicts = Counter(f.get("verdict") for f in fb if f.get("at", 0) > now - 86400 and f.get("verdict"))
    answers = sum(1 for t in tri if t.get("answer") and not t.get("followup"))
    questions = sum(1 for t in tri if t.get("followup"))
    lines.append(f"\n*Agent, last 24h* — {answers} investigations, {questions} follow-up answers, "
                 f"judged: {verdicts['correct']} correct / {verdicts['wrong']} wrong")
    lines.append("_Reply `correct` / `wrong` in incident threads — that is how the agent is measured._")
    return "\n".join(lines)


def due(state: dict, now: float | None = None) -> bool:
    """Once a day, after the configured hour (UTC)."""
    now = now or time.time()
    hour, minute = (os.environ.get("ONCALL_DIGEST_HOUR_UTC", "03:30").split(":") + ["0"])[:2]
    today = time.strftime("%Y-%m-%d", time.gmtime(now))
    t = time.gmtime(now)
    after = (t.tm_hour, t.tm_min) >= (int(hour), int(minute))
    return after and state.get("digest_posted") != today


def post(cfg, state: dict, save) -> None:
    target = os.environ.get("ONCALL_DIGEST_CHANNEL")
    h = {"Authorization": f"Bearer {cfg.slack_bot_token}"}
    if not target:
        if not cfg.approvers:
            return
        target = requests.post("https://slack.com/api/conversations.open", headers=h,
                               json={"users": cfg.approvers[0]}, timeout=30).json()["channel"]["id"]
    text = build(state, cfg.agentspan_server_url, Path(cfg.state_file).parent)
    r = requests.post("https://slack.com/api/chat.postMessage", headers=h,
                      json={"channel": target, "text": text}, timeout=30).json()
    if r.get("ok"):
        state["digest_posted"] = time.strftime("%Y-%m-%d", time.gmtime())
        save()
