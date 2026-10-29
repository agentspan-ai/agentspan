"""One durable workflow per incident: triage, then react to every reply in its Slack thread.

    oncall_incident(channel, thread_ts, alert_execution, cluster, alert_text)
      1. triage                      agent investigates, posts the 3-line answer (or a proposed change)
      2. SET_VARIABLE pending        the agent execution waiting for approval, if any
      3. DO_WHILE events (open)
           await_event   WAIT        completed by the router with the next reply; after 72h of
                                     silence it completes on its own (= close)
           handle                    question -> agent answers in the thread
                                     approve/reject -> resumes/ends the paused agent execution
                                     correct/wrong/cause: -> feedback for the learning loop
                                     firing -> the alert fired again (noted in the thread)
           SET_VARIABLE pending      carried to the next reply

Every incident runs in its own workflow, so investigations run in parallel; state lives in
the server, so a restarted listener loses nothing. The two task types are served by
``IncidentWorkers`` (threads in the listener process, sharing one AgentRuntime).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import requests

from . import approvals, feedback

log = logging.getLogger(__name__)

WORKFLOW = "oncall_incident"
TRIAGE_TASK = "oncall_incident_triage"
HANDLE_TASK = "oncall_incident_handle"
QUIET_CLOSE = "72 hours"
MAX_EVENTS = 200

WORKFLOW_DEF = {
    "name": WORKFLOW, "version": 1, "schemaVersion": 2, "ownerEmail": "oncall@orkes.io",
    "description": "On-call incident: triage, then answer questions / apply approved changes / record feedback",
    "timeoutSeconds": 0, "variables": {"pending": ""},
    "tasks": [
        {"name": TRIAGE_TASK, "taskReferenceName": "triage", "type": "SIMPLE",
         "inputParameters": {"incident": "${workflow.input}"}},
        {"name": "set_pending", "taskReferenceName": "set_pending_after_triage", "type": "SET_VARIABLE",
         "inputParameters": {"pending": "${triage.output.pending}"}},
        {"name": "events", "taskReferenceName": "events", "type": "DO_WHILE",
         "loopCondition": f"if ($.handle['open'] == true && $.events['iteration'] < {MAX_EVENTS}) "
                          "{ true; } else { false; }",
         "inputParameters": {"handle": "${handle.output}", "events": "${events.output}"},
         "loopOver": [
             {"name": "await_event", "taskReferenceName": "await_event", "type": "WAIT",
              "inputParameters": {"duration": QUIET_CLOSE}},
             {"name": HANDLE_TASK, "taskReferenceName": "handle", "type": "SIMPLE",
              "inputParameters": {"incident": "${workflow.input}", "event": "${await_event.output}",
                                  "pending": "${workflow.variables.pending}"}},
             {"name": "set_pending", "taskReferenceName": "set_pending", "type": "SET_VARIABLE",
              "inputParameters": {"pending": "${handle.output.pending}"}},
         ]},
    ],
}

TASK_DEFS = [
    {"name": TRIAGE_TASK, "retryCount": 0, "timeoutSeconds": 3600, "responseTimeoutSeconds": 3000,
     "ownerEmail": "oncall@orkes.io", "timeoutPolicy": "TIME_OUT_WF"},
    {"name": HANDLE_TASK, "retryCount": 0, "timeoutSeconds": 3600, "responseTimeoutSeconds": 3000,
     "ownerEmail": "oncall@orkes.io", "timeoutPolicy": "ALERT_ONLY"},
]


def register(server: str) -> None:
    base = server.rstrip("/")
    r = requests.post(f"{base}/metadata/taskdefs", json=TASK_DEFS, timeout=30)
    if r.status_code >= 300 and "exists" not in r.text.lower():
        requests.put(f"{base}/metadata/taskdefs", json=TASK_DEFS[0], timeout=30)
        requests.put(f"{base}/metadata/taskdefs", json=TASK_DEFS[1], timeout=30)
    r = requests.put(f"{base}/metadata/workflow", json=[WORKFLOW_DEF], timeout=30)
    r.raise_for_status()


class IncidentWorkers:
    """Serve the incident task types with a small thread pool (incidents run in parallel)."""

    def __init__(self, cfg, slack, runtime, agent, parallel: int = 4):
        self.cfg, self.slack, self.runtime, self.agent = cfg, slack, runtime, agent
        self.base = cfg.agentspan_server_url.rstrip("/")
        self.pool = ThreadPoolExecutor(parallel, thread_name_prefix="incident")
        self.free = threading.Semaphore(parallel)
        self.stop = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._poll_loop, name="incident-poller", daemon=True).start()

    def _poll_loop(self) -> None:
        handlers = {TRIAGE_TASK: self.triage, HANDLE_TASK: self.handle}
        while not self.stop.is_set():
            got = False
            for task_type, fn in handlers.items():
                if not self.free.acquire(blocking=False):
                    break
                try:
                    r = requests.get(f"{self.base}/tasks/poll/{task_type}",
                                     params={"workerid": "oncall-listener"}, timeout=30)
                    task = r.json() if r.status_code == 200 and r.text.strip() else None
                except Exception:
                    log.exception("poll %s failed", task_type)
                    task = None
                if not task:
                    self.free.release()
                    continue
                got = True
                self.pool.submit(self._run, fn, task)
            if not got:
                self.stop.wait(1.0)

    def _run(self, fn, task: dict) -> None:
        try:
            out, status = fn(task.get("inputData") or {}), "COMPLETED"
        except Exception as exc:  # report into the workflow; never leave a task hanging
            log.exception("%s failed", task.get("taskDefName"))
            out, status = {"error": str(exc)[:500], "open": True, "pending": ""}, "FAILED"
        finally:
            self.free.release()
        try:
            requests.post(f"{self.base}/tasks", timeout=30, json={
                "workflowInstanceId": task["workflowInstanceId"], "taskId": task["taskId"],
                "status": status, "outputData": out})
        except Exception:
            log.exception("could not report task %s", task.get("taskId"))

    # ---- task: triage -------------------------------------------------------------------
    def triage(self, inp: dict) -> dict:
        from .slack_app import (_AwaitingApproval, _FEEDBACK_ASK, _TRIAGE_DEADLINE_S, _header,
                                _start_until_answer, _store, _triage_prompt, _PLAYBOOK_VERSION)
        from .runtime_compat import summary_text
        inc = inp["incident"]
        ch, th = inc["channel"], inc["thread_ts"]
        alert = SimpleNamespace(raw=inc.get("alert_text", ""), execution_id=inc["alert_execution"],
                                cluster=inc.get("cluster"))
        self.slack.post_reply(ch, th, f":mag: On-call triage starting for execution `{alert.execution_id}`…")
        record = {"alert_execution": alert.execution_id, "cluster": alert.cluster, "alert_text": alert.raw,
                  "channel": ch, "thread_ts": th, "model": self.cfg.model, "playbook": _PLAYBOOK_VERSION}
        try:
            result = _start_until_answer(self.runtime, self.agent, _triage_prompt(alert), _TRIAGE_DEADLINE_S)
        except _AwaitingApproval as wait:
            calls = approvals.extract_calls(wait.pending)
            text = approvals.proposal_text(alert.cluster or "?", calls, self.cfg.approvers)
            self.slack.post_reply(ch, th, _header(self.cfg) + text)
            feedback.log_triage(_store(self.cfg), {**record, "answer": text, "agent_execution": wait.execution_id})
            return {"answer": text, "pending": wait.execution_id}
        summary = summary_text(result)
        self.slack.post_reply(ch, th, _header(self.cfg) + summary + _FEEDBACK_ASK)
        feedback.log_triage(_store(self.cfg), {**record, "answer": summary})
        return {"answer": summary, "pending": ""}

    # ---- task: handle one event ---------------------------------------------------------
    def handle(self, inp: dict) -> dict:
        from .slack_app import _store
        inc, ev, pending = inp["incident"], inp.get("event") or {}, inp.get("pending") or ""
        ch, th, kind = inc["channel"], inc["thread_ts"], ev.get("kind")
        store = _store(self.cfg)
        if not kind:  # the WAIT ran out: 72h without a reply
            if pending:
                self.runtime.respond(pending, {"approved": False, "reason": "expired"})
            return {"open": False, "pending": ""}
        if kind == "close":
            return {"open": False, "pending": ""}
        if kind == "firing":  # a repeat of this incident: recorded, never posted (no thread spam)
            feedback.log_triage(store, {"firing": {**inc, "at": ev.get("at"), "alert_execution": ev.get("alert_execution")}})
            return {"open": True, "pending": pending}
        if kind in ("approve", "reject"):
            return self._decide(inc, ev, pending)
        if kind == "feedback":
            feedback._append(store / "feedback.jsonl", {
                "at": time.time(), "alert_execution": inc["alert_execution"], "cluster": inc.get("cluster"),
                "by": ev.get("user"), "msg_ts": ev.get("ts"), **(ev.get("meaning") or {})})
            self.slack.post_reply(ch, th, ":memo: Noted — this incident becomes an eval case for the agent.")
            return {"open": True, "pending": pending}
        if kind == "question":
            return self._answer(inc, ev, pending)
        return {"open": True, "pending": pending}

    def _decide(self, inc: dict, ev: dict, pending: str) -> dict:
        ch, th, user = inc["channel"], inc["thread_ts"], ev.get("user")
        if user not in self.cfg.approvers:
            return {"open": True, "pending": pending}  # only approvers decide
        if not pending:
            self.slack.post_reply(ch, th, f"<@{user}> There is no change waiting for approval here.")
            return {"open": True, "pending": ""}
        approve = ev["kind"] == "approve"
        self.runtime.respond(pending, {"approved": approve, "reason": f"{ev['kind']} by {user} in Slack"})
        if not approve:
            self.slack.post_reply(ch, th, f":no_entry: Rejected by <@{user}> — nothing was changed.")
            return {"open": True, "pending": ""}
        self.slack.post_reply(ch, th, f":white_check_mark: Approved by <@{user}> — applying.")
        text = self._await_agent(pending)
        self.slack.post_reply(ch, th, text)
        return {"open": True, "pending": ""}

    def _await_agent(self, execution_id: str, deadline_s: int = 2400) -> str:
        from .runtime_compat import summary_text
        end = time.time() + deadline_s
        while time.time() < end:
            st = self.runtime.get_status(execution_id)
            if st.is_complete:
                try:
                    return summary_text(st)
                except Exception as exc:
                    return f":warning: The change ran but the agent gave no summary: `{exc}`"
            time.sleep(10)
        return f":warning: The approved change is still running after {deadline_s // 60} min — check `{execution_id}`."

    def _answer(self, inc: dict, ev: dict, pending: str) -> dict:
        from .slack_app import (_AwaitingApproval, _TRIAGE_DEADLINE_S, _followup_prompt,
                                _start_until_answer, _store)
        from .runtime_compat import answer_text
        ch, th = inc["channel"], inc["thread_ts"]
        q = {"alert_execution": inc["alert_execution"], "cluster": inc.get("cluster"), "text": ev.get("text", "")}
        try:
            result = _start_until_answer(self.runtime, self.agent,
                                         _followup_prompt(q, self.slack.read_replies(ch, th)), _TRIAGE_DEADLINE_S)
        except _AwaitingApproval as wait:
            calls = approvals.extract_calls(wait.pending)
            self.slack.post_reply(ch, th, approvals.proposal_text(inc.get("cluster") or "?", calls, self.cfg.approvers))
            return {"open": True, "pending": wait.execution_id}
        text = answer_text(result)
        self.slack.post_reply(ch, th, f"<@{ev.get('user')}> {text}")
        feedback.log_triage(_store(self.cfg), {"followup": {**q, "user": ev.get("user")}, "answer": text})
        return {"open": True, "pending": pending}


def classify(text: str, bot_user_id: str | None) -> dict | None:
    """What a human reply in an incident thread means for the workflow (None = ignore)."""
    t = (text or "").strip()
    word = (t.split() or [""])[0].lower().strip(".,!:")
    if word in ("approve", "approved", "reject", "rejected"):
        return {"kind": "approve" if word.startswith("approve") else "reject"}
    if word in ("close", "closed", "resolved") and len(t.split()) <= 3:
        return {"kind": "close"}
    meaning = feedback.parse(t)
    if meaning:
        return {"kind": "feedback", "meaning": meaning}
    if feedback.is_question(t, bot_user_id):
        return {"kind": "question"}
    return None
