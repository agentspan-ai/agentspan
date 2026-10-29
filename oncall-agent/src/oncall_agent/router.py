"""The thin Slack router for incident workflows (ONCALL_MODE=workflow).

Each poll:
  * new alert in a watched channel -> if its cluster already has an open incident, that
    incident's workflow gets a "firing" event (and the new alert's thread points to it);
    otherwise a new ``oncall_incident`` workflow starts (correlationId = channel:thread_ts).
  * new human reply in an open incident's thread -> classified (question / approve / reject /
    feedback / close) and delivered to that workflow by completing its waiting WAIT task.
    A reply that arrives while the workflow is still busy stays in the outbox and is delivered
    on a later poll, in order — nothing is dropped.

The router keeps only routing state (which thread belongs to which workflow, what was read);
everything about the incident itself lives in the workflow.
"""
from __future__ import annotations

import logging
import time

import requests

from . import incident
from .alert import message_text

log = logging.getLogger(__name__)

THREADS_PER_POLL = 20  # Slack conversations.replies budget per minute


class Router:
    def __init__(self, cfg, slack, state: dict, save):
        self.cfg, self.slack, self.state, self.save = cfg, slack, state, save
        self.base = cfg.agentspan_server_url.rstrip("/")
        self.bot = slack.bot_user_id() if hasattr(slack, "bot_user_id") else None
        state.setdefault("incidents_open", {})   # thread key -> {workflow_id, channel, thread_ts, cluster, after, checked}
        state.setdefault("outbox", {})           # thread key -> [events not yet delivered]

    # ---- alerts ---------------------------------------------------------------------------
    def open_for_cluster(self, cluster: str | None) -> tuple[str, dict] | None:
        if not cluster:
            return None
        for key, inc in self.state["incidents_open"].items():
            if inc.get("cluster") == cluster and self._running(inc["workflow_id"]):
                return key, inc
        return None

    def on_alert(self, channel: str, msg: dict, alert) -> str:
        """Start an incident for this alert, or attach it to the cluster's open one."""
        ts = msg["ts"]
        existing = self.open_for_cluster(alert.cluster)
        if existing:
            key, inc = existing
            self._queue(key, {"kind": "firing", "at": time.strftime("%H:%M UTC", time.gmtime(float(ts))),
                              "alert_execution": alert.execution_id})
            link = self._permalink(inc["channel"], inc["thread_ts"])
            self.slack.post_reply(channel, ts, f":link: Same open incident on `{alert.cluster}` — tracked in "
                                               f"{link or 'the earlier thread'}.")
            return inc["workflow_id"]
        wid = requests.post(f"{self.base}/workflow", timeout=30, json={
            "name": incident.WORKFLOW, "version": 1, "correlationId": f"{channel}:{ts}",
            "input": {"channel": channel, "thread_ts": ts, "alert_execution": alert.execution_id,
                      "cluster": alert.cluster, "alert_text": message_text(msg)}}).text.strip().strip('"')
        self.state["incidents_open"][f"{channel}:{ts}"] = {
            "workflow_id": wid, "channel": channel, "thread_ts": ts, "cluster": alert.cluster,
            "after": float(ts), "checked": 0.0, "seen": []}
        self.save()
        log.info("incident started cluster=%s workflow=%s", alert.cluster, wid)
        return wid

    # ---- replies ----------------------------------------------------------------------------
    def poll_threads(self) -> None:
        open_ = self.state["incidents_open"]
        for key, inc in list(open_.items()):
            if not self._running(inc["workflow_id"]):
                open_.pop(key)
                self.state["outbox"].pop(key, None)
        for key, inc in sorted(open_.items(), key=lambda kv: kv[1]["checked"])[:THREADS_PER_POLL]:
            inc["checked"] = time.time()
            try:
                replies = self.slack.read_replies(inc["channel"], inc["thread_ts"])
            except Exception:
                log.exception("read replies failed for %s", key)
                continue
            for m in sorted(replies, key=lambda m: float(m.get("ts", 0))):
                ts = m.get("ts", "0")
                if float(ts) <= inc["after"] or m.get("bot_id") or ts in inc["seen"]:
                    continue
                inc["seen"].append(ts)
                event = incident.classify(m.get("text", ""), self.bot)
                if event:
                    self._queue(key, {**event, "text": m.get("text", ""), "user": m.get("user"), "ts": ts})
        self.save()
        self.deliver()

    def _queue(self, key: str, event: dict) -> None:
        self.state["outbox"].setdefault(key, []).append(event)
        self.save()

    def deliver(self) -> None:
        """Hand each workflow its next event if it is waiting; otherwise keep it for later."""
        for key, events in list(self.state["outbox"].items()):
            inc = self.state["incidents_open"].get(key)
            if not events or not inc:
                self.state["outbox"].pop(key, None)
                continue
            task = self._waiting_task(inc["workflow_id"])
            if not task:
                continue  # still triaging / handling: deliver on a later poll
            r = requests.post(f"{self.base}/tasks", timeout=30, json={
                "workflowInstanceId": inc["workflow_id"], "taskId": task["taskId"],
                "status": "COMPLETED", "outputData": events[0]})
            if r.status_code < 300:
                events.pop(0)
                log.info("delivered an event to %s (%d still queued)", inc["workflow_id"], len(events))
        self.save()

    # ---- server helpers ---------------------------------------------------------------------
    def _workflow(self, wid: str) -> dict:
        r = requests.get(f"{self.base}/workflow/{wid}", params={"includeTasks": "true"}, timeout=30)
        return r.json() if r.ok else {}

    def _running(self, wid: str) -> bool:
        return self._workflow(wid).get("status") in ("RUNNING", "PAUSED")

    def _waiting_task(self, wid: str) -> dict | None:
        for t in reversed(self._workflow(wid).get("tasks", [])):
            if t.get("taskType") == "WAIT" and t.get("status") == "IN_PROGRESS":
                return t
        return None

    def _permalink(self, channel: str, ts: str) -> str | None:
        try:
            r = requests.get("https://slack.com/api/chat.getPermalink", timeout=30,
                             headers={"Authorization": f"Bearer {self.cfg.slack_bot_token}"},
                             params={"channel": channel, "message_ts": ts}).json()
            return r.get("permalink")
        except Exception:
            return None
