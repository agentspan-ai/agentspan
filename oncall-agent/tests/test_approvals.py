import time
from types import SimpleNamespace

from oncall_agent import approvals

ME, OTHER = "U_ME", "U_OTHER"
PENDING = {"taskRefName": "oncall_triage_approval_human",
           "toolCalls": [{"name": "restart_deployment",
                          "args": {"execution_id": "e", "deployment": "workers",
                                        "triage_summary": "*Cause*: workers leak DB connections"}}]}


class Slack:
    def __init__(self, replies=()):
        self.replies, self.posts = list(replies), []

    def read_replies(self, channel, thread):
        return self.replies

    def post_reply(self, channel, thread, text):
        self.posts.append(text)


class Runtime:
    def __init__(self, status=None):
        self.responses, self.status = [], status

    def respond(self, exec_id, output):
        self.responses.append((exec_id, output))

    def get_status(self, exec_id):
        return self.status


def _cfg():
    return SimpleNamespace(approvers=(ME,))


def _state(asked_at, phase="awaiting"):
    return {"pending_actions": {"X1": {"channel": "C", "thread_ts": "1.0", "phase": phase,
                                       "asked_at": asked_at, "decided_at": asked_at}}}


def _msg(user, text, ts, bot=False):
    m = {"user": user, "text": text, "ts": str(ts)}
    if bot:
        m["bot_id"] = "B1"
    return m


def test_proposal_says_exactly_what_changes():
    calls = approvals.extract_calls(PENDING)
    assert calls == [("restart_deployment", PENDING["toolCalls"][0]["args"])]
    text = approvals.proposal_text("orkes-devops", calls, (ME,))
    assert "workers leak DB connections" in text
    assert "orkes-workers-deployment" in text and "orkes-devops" in text and f"<@{ME}>" in text


def test_only_an_approvers_reply_after_the_proposal_counts():
    asked = 100.0
    replies = [_msg(ME, "approve", 99),            # before the proposal
               _msg(OTHER, "approve", 101),        # not an approver
               _msg(ME, "approve", 102, bot=True),  # a bot
               _msg(ME, "Reject - wrong pod", 103)]
    assert approvals.decision(replies, (ME,), asked) == ("reject", ME)
    assert approvals.decision(replies[:3], (ME,), asked) is None


def test_approve_is_saved_before_it_is_sent_then_result_posted():
    now = time.time()
    state = _state(now - 10)
    slack, runtime = Slack([_msg(ME, "approve", now)]), Runtime()
    saved_phases = []

    def save():
        saved_phases.append(state["pending_actions"].get("X1", {}).get("phase"))

    approvals.process_pending(_cfg(), slack, runtime, state, None, save)
    assert saved_phases[0] == "executing" and runtime.responses == [("X1", {"approved": True, "reason": f"approve by {ME} in Slack"})]
    assert "Approved" in slack.posts[0]

    runtime.status = SimpleNamespace(is_complete=True, status="COMPLETED", output={"result": "*Cause*: x"})
    approvals.process_pending(_cfg(), slack, runtime, state, lambda st: st.output["result"], lambda: None)
    assert slack.posts[-1] == "*Cause*: x" and state["pending_actions"] == {}


def test_reject_and_expiry_change_nothing():
    now = time.time()
    state, runtime, slack = _state(now - 10), Runtime(), Slack([_msg(ME, "reject", now)])
    approvals.process_pending(_cfg(), slack, runtime, state, None, lambda: None)
    assert runtime.responses[0][1]["approved"] is False and "nothing was changed" in slack.posts[0]
    assert state["pending_actions"] == {}

    state, runtime, slack = _state(now - approvals.APPROVAL_TTL_S - 1), Runtime(), Slack()
    approvals.process_pending(_cfg(), slack, runtime, state, None, lambda: None)
    assert runtime.responses[0][1]["approved"] is False and "Expired" in slack.posts[0]


def test_no_reply_yet_waits():
    state, runtime, slack = _state(time.time()), Runtime(), Slack()
    approvals.process_pending(_cfg(), slack, runtime, state, None, lambda: None)
    assert runtime.responses == [] and slack.posts == [] and "X1" in state["pending_actions"]
