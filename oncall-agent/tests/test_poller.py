"""Deterministic tests for the Slack poll loop — fakes for Slack + the agent runtime,
no network and no LLM."""
from oncall_agent.config import Config
from oncall_agent.slack_app import run_once

CHANNEL = "C123"
ALERT = (
    "[CRITICAL] The health-checking has FAILED for the Vizient's prod viz-stage cluster:\n"
    "https://ah5r-prod.orkesconductor.com/execution/364b459a-689f-11f1-94b6-de01f12a4ed9"
)


class FakeSlack:
    def __init__(self, messages):
        self._messages = messages
        self.posts = []  # (channel, thread_ts, text)

    def read_messages(self, channel, oldest="0", limit=20):
        return list(self._messages)

    def post_reply(self, channel, thread_ts, text):
        self.posts.append((channel, thread_ts, text))


class FakeResult:
    output = "*Issue*: redis high\n*Likely root cause*: queue backlog"


class DictOutputResult:
    """Mirrors the real AgentRuntime result: ``.output`` is a dict with the
    agent's text under ``result`` (seen live against the server, 2026-07-22).
    The text often leads with narration despite instructions — the posted
    reply must start at *Issue*:."""

    output = {
        "result": (
            "I have all the data I need. Let me compile the summary.\n\n---\n\n"
            "*Issue*: pod failed\n*Likely root cause*: stale pod from rollout"
        ),
        "finishReason": "COMPLETED",
        "context": {},
        "rejectionReason": None,
    }


class DictOutputRuntime:
    def run(self, agent, prompt):
        return DictOutputResult()


class FakeRuntime:
    def __init__(self):
        self.calls = []

    def run(self, agent, prompt):
        self.calls.append(prompt)
        return FakeResult()


class FailingRuntime:
    def run(self, agent, prompt):
        raise RuntimeError("dispatch boom")


def _cfg(tmp_path) -> Config:
    return Config(
        conductor_server_url="x", conductor_key_id="x", conductor_key_secret="x",
        slack_bot_token="xoxb", slack_alert_channel=CHANNEL, poll_interval=300,
        state_file=str(tmp_path / "state.json"),
        agentspan_server_url="x", model="m", dry_run=True,
    )


def test_only_alert_messages_are_triaged(tmp_path):
    slack = FakeSlack([
        {"type": "message", "ts": "1.0", "text": "morning all"},
        {"type": "message", "ts": "2.0", "text": ALERT},
        {"type": "message", "ts": "3.0", "text": "lunch?"},
    ])
    runtime = FakeRuntime()
    handled = run_once(_cfg(tmp_path), slack, runtime, agent=object())

    assert handled == 1
    # Exactly one execution was triaged, and the prompt carried its id.
    assert len(runtime.calls) == 1
    assert "364b459a-689f-11f1-94b6-de01f12a4ed9" in runtime.calls[0]
    # Two replies (starting + summary), both threaded under the alert message ts "2.0".
    assert [p[1] for p in slack.posts] == ["2.0", "2.0"]
    assert any("Likely root cause" in p[2] for p in slack.posts)


def test_dedup_across_polls(tmp_path):
    cfg = _cfg(tmp_path)
    msgs = [{"type": "message", "ts": "2.0", "text": ALERT}]
    runtime = FakeRuntime()

    first = run_once(cfg, FakeSlack(msgs), runtime, agent=object())
    second = run_once(cfg, FakeSlack(msgs), runtime, agent=object())

    assert first == 1
    assert second == 0  # already processed -> not triaged again
    assert len(runtime.calls) == 1


def test_dict_output_result_posts_summary_text(tmp_path):
    """The runtime's result.output is a dict — the thread reply must carry the
    agent's text, not a stringified dict or a 'Triage failed' error."""
    slack = FakeSlack([{"type": "message", "ts": "2.0", "text": ALERT}])
    handled = run_once(_cfg(tmp_path), slack, DictOutputRuntime(), agent=object())

    assert handled == 1
    assert not any("Triage failed" in p[2] for p in slack.posts)
    summary = slack.posts[-1][2]
    assert "Likely root cause" in summary
    assert "finishReason" not in summary  # not a dumped dict
    # LLM preamble before *Issue*: is stripped deterministically (seen twice live).
    assert "all the data I need" not in summary
    assert summary.splitlines()[1].startswith("*Issue*:")  # line 0 is the dry-run header


def test_triage_failure_is_reported_not_raised(tmp_path):
    slack = FakeSlack([{"type": "message", "ts": "2.0", "text": ALERT}])
    handled = run_once(_cfg(tmp_path), slack, FailingRuntime(), agent=object())

    assert handled == 1
    assert any("Triage failed" in p[2] for p in slack.posts)
