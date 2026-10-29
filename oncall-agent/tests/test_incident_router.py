from types import SimpleNamespace

from oncall_agent import incident, router as router_mod
from oncall_agent.incident import IncidentWorkers, classify

BOT = "UBOT"


def test_classify_replies():
    assert classify("approve", BOT) == {"kind": "approve"}
    assert classify("Rejected - wrong pod", BOT) == {"kind": "reject"}
    assert classify("resolved", BOT) == {"kind": "close"}
    assert classify("correct", BOT)["kind"] == "feedback"
    assert classify("cause: cold image pull", BOT) == {"kind": "feedback", "meaning": {"cause": "cold image pull"}}
    assert classify("did you check the deciderQueue size?", BOT) == {"kind": "question"}
    assert classify("ok thanks", BOT) is None


def test_workflow_definition_shape():
    names = [t["taskReferenceName"] for t in incident.WORKFLOW_DEF["tasks"]]
    assert names == ["triage", "set_pending_after_triage", "events"]
    loop = incident.WORKFLOW_DEF["tasks"][2]["loopOver"]
    assert [t["type"] for t in loop] == ["WAIT", "SIMPLE", "SET_VARIABLE"]
    assert loop[0]["inputParameters"]["duration"] == incident.QUIET_CLOSE


class Slack:
    def __init__(self, replies=()):
        self.replies, self.posts = list(replies), []

    def read_replies(self, channel, ts):
        return self.replies

    def post_reply(self, channel, ts, text):
        self.posts.append(text)

    def bot_user_id(self):
        return BOT


class Server:
    """Fake agentspan server: workflows with an optional waiting WAIT task."""

    def __init__(self):
        self.workflows, self.completed, self.started = {}, [], []

    def get(self, url, params=None, timeout=None):
        wid = url.rsplit("/", 1)[-1]
        return SimpleNamespace(ok=True, json=lambda: self.workflows.get(wid, {}))

    def post(self, url, json=None, timeout=None):
        if url.endswith("/workflow"):
            self.started.append(json)
            wid = f"wf{len(self.started)}"
            self.workflows[wid] = {"status": "RUNNING", "tasks": []}
            return SimpleNamespace(status_code=200, text=f'"{wid}"')
        self.completed.append(json)
        return SimpleNamespace(status_code=200, text="")


def _router(monkeypatch, slack, server, state):
    monkeypatch.setattr(router_mod.requests, "get", server.get)
    monkeypatch.setattr(router_mod.requests, "post", server.post)
    cfg = SimpleNamespace(agentspan_server_url="http://x/api", slack_bot_token="t")
    r = router_mod.Router(cfg, slack, state, lambda: None)
    monkeypatch.setattr(r, "_permalink", lambda c, t: "<link>")
    return r


def test_new_alert_starts_a_workflow_and_a_second_one_joins_it(monkeypatch):
    server, slack, state = Server(), Slack(), {}
    r = _router(monkeypatch, slack, server, state)
    a = SimpleNamespace(execution_id="E1", cluster="c1")
    wid = r.on_alert("C", {"ts": "100.0", "text": "alert"}, a)
    assert server.started[0]["correlationId"] == "C:100.0" and server.started[0]["input"]["cluster"] == "c1"
    again = r.on_alert("C", {"ts": "200.0", "text": "alert again"}, SimpleNamespace(execution_id="E2", cluster="c1"))
    assert again == wid and len(server.started) == 1
    assert state["outbox"]["C:100.0"][0]["kind"] == "firing" and slack.posts == []  # repeats are silent


def test_replies_wait_in_the_outbox_until_the_workflow_is_waiting(monkeypatch):
    server = Server()
    slack = Slack([{"ts": "150.0", "user": "U1", "text": "why workers?"},
                   {"ts": "151.0", "bot_id": "B", "text": "*Answer*: ..."},
                   {"ts": "152.0", "user": "U1", "text": "correct"}])
    state = {}
    r = _router(monkeypatch, slack, server, state)
    r.on_alert("C", {"ts": "100.0", "text": "alert"}, SimpleNamespace(execution_id="E1", cluster="c1"))
    r.poll_threads()  # still triaging: nothing delivered
    assert server.completed == [] and [e["kind"] for e in state["outbox"]["C:100.0"]] == ["question", "feedback"]
    server.workflows["wf1"]["tasks"] = [{"taskType": "WAIT", "status": "IN_PROGRESS", "taskId": "T1"}]
    r.deliver()  # one event per waiting WAIT, in order
    assert server.completed[0]["taskId"] == "T1" and server.completed[0]["outputData"]["kind"] == "question"
    assert [e["kind"] for e in state["outbox"]["C:100.0"]] == ["feedback"]
    r.poll_threads()  # replies already seen are not queued twice
    assert len(state["outbox"]["C:100.0"]) <= 1


def test_closed_workflows_are_forgotten(monkeypatch):
    server, slack, state = Server(), Slack(), {}
    r = _router(monkeypatch, slack, server, state)
    r.on_alert("C", {"ts": "100.0", "text": "a"}, SimpleNamespace(execution_id="E1", cluster="c1"))
    server.workflows["wf1"]["status"] = "COMPLETED"
    r.poll_threads()
    assert state["incidents_open"] == {}


class Runtime:
    def __init__(self):
        self.responses = []

    def respond(self, eid, out):
        self.responses.append((eid, out))

    def get_status(self, eid):
        return SimpleNamespace(is_complete=True, status="COMPLETED", output={"result": "*Cause*: done"})


def _workers(slack, tmp_path, monkeypatch):
    from oncall_agent import slack_app
    monkeypatch.setattr(slack_app, "_store", lambda cfg: tmp_path)
    cfg = SimpleNamespace(approvers=("U_ME",), agentspan_server_url="http://x/api", model="m")
    return IncidentWorkers(cfg, slack, Runtime(), agent=None, parallel=1)


INC = {"channel": "C", "thread_ts": "100.0", "alert_execution": "E1", "cluster": "c1"}


def test_handle_approval_only_from_approvers_and_only_with_a_pending_change(tmp_path, monkeypatch):
    slack = Slack()
    w = _workers(slack, tmp_path, monkeypatch)
    assert w.handle({"incident": INC, "event": {"kind": "approve", "user": "U_OTHER"}, "pending": "AG1"}) == \
        {"open": True, "pending": "AG1"} and w.runtime.responses == []
    out = w.handle({"incident": INC, "event": {"kind": "approve", "user": "U_ME"}, "pending": "AG1"})
    assert out == {"open": True, "pending": ""} and w.runtime.responses[0][1]["approved"] is True
    assert slack.posts[-1] == "*Cause*: done"
    w.handle({"incident": INC, "event": {"kind": "approve", "user": "U_ME"}, "pending": ""})
    assert "no change waiting" in slack.posts[-1]


def test_handle_quiet_timeout_closes_and_rejects_a_pending_change(tmp_path, monkeypatch):
    w = _workers(Slack(), tmp_path, monkeypatch)
    assert w.handle({"incident": INC, "event": {}, "pending": "AG1"}) == {"open": False, "pending": ""}
    assert w.runtime.responses == [("AG1", {"approved": False, "reason": "expired"})]


def test_handle_feedback_is_recorded(tmp_path, monkeypatch):
    slack = Slack()
    w = _workers(slack, tmp_path, monkeypatch)
    w.handle({"incident": INC, "event": {"kind": "feedback", "user": "U1", "ts": "1",
                                         "meaning": {"verdict": "correct"}}, "pending": ""})
    assert '"verdict": "correct"' in (tmp_path / "feedback.jsonl").read_text()
    assert "Noted" in slack.posts[-1]


def test_tasks_left_running_by_a_dead_listener_are_retried(monkeypatch):
    calls = []

    class R:
        def __init__(self, data): self.ok, self._d = True, data
        def json(self): return self._d

    def get(url, params=None, timeout=None):
        if url.endswith("/workflow/search"):
            return R({"results": [{"workflowId": "W1"}]})
        return R({"workflowId": "W1", "tasks": [
            {"taskDefName": incident.TRIAGE_TASK, "status": "IN_PROGRESS", "taskId": "T1"},
            {"taskDefName": "await_event", "status": "IN_PROGRESS", "taskId": "T2"}]})

    monkeypatch.setattr(incident.requests, "get", get)
    monkeypatch.setattr(incident.requests, "post", lambda url, json=None, timeout=None: calls.append(json))
    w = IncidentWorkers(SimpleNamespace(agentspan_server_url="http://x/api"), None, None, None, parallel=1)
    assert w.requeue_orphans() == 1
    assert calls == [{"workflowInstanceId": "W1", "taskId": "T1", "status": "FAILED",
                      "reasonForIncompletion": "listener restarted while this task ran; retrying"}]
    assert all(t["retryCount"] == 1 for t in incident.TASK_DEFS)
