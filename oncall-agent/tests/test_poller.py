"""Deterministic tests for the Slack poll loop — fakes for Slack + the agent runtime,
no network and no LLM."""
import json
import threading
import time
from pathlib import Path

from oncall_agent import slack_app
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
    def run(self, agent, prompt, **kwargs):
        return DictOutputResult()


class FakeRuntime:
    def __init__(self):
        self.calls = []

    def run(self, agent, prompt, **kwargs):
        self.calls.append(prompt)
        return FakeResult()


class FailingRuntime:
    def run(self, agent, prompt, **kwargs):
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


# ── multi-channel polling ────────────────────────────────────────────────
# Production watches BOTH the raw alert channel and the aggregator digest
# channel. SLACK_ALERT_CHANNEL accepts a comma-separated list; dedup state is
# kept per channel.


class MultiChannelSlack:
    def __init__(self, by_channel):
        self._by_channel = by_channel
        self.posts = []  # (channel, thread_ts, text)

    def read_messages(self, channel, oldest="0", limit=20):
        return list(self._by_channel.get(channel, []))

    def post_reply(self, channel, thread_ts, text):
        self.posts.append((channel, thread_ts, text))


def _cfg_multi(tmp_path) -> Config:
    return Config(
        conductor_server_url="x", conductor_key_id="x", conductor_key_secret="x",
        slack_bot_token="xoxb", slack_alert_channel="C1,C2", poll_interval=300,
        state_file=str(tmp_path / "state.json"),
        agentspan_server_url="x", model="m", dry_run=True,
    )


def test_channels_property_splits_and_strips():
    c = Config(
        conductor_server_url="x", conductor_key_id="x", conductor_key_secret="x",
        slack_bot_token="x", slack_alert_channel=" C1, C2 ", poll_interval=1,
        state_file="s", agentspan_server_url="x", model="m", dry_run=True,
    )
    assert c.slack_alert_channels == ["C1", "C2"]


def test_both_channels_polled_and_replies_stay_in_their_channel(tmp_path):
    # Distinct incidents per channel — identical ones are signature-suppressed.
    slack = MultiChannelSlack({
        "C1": [{"type": "message", "ts": "1.0", "text": ALERT}],
        "C2": [{"type": "message", "ts": "2.0", "text": OTHER_ALERT}],
    })
    runtime = FakeRuntime()
    handled = run_once(_cfg_multi(tmp_path), slack, runtime, agent=object())

    assert handled == 2
    channels_posted = {p[0] for p in slack.posts}
    assert channels_posted == {"C1", "C2"}


def test_same_ts_in_different_channels_is_not_cross_deduped(tmp_path):
    # ts values are per-channel in Slack; identical ts in two channels must both
    # run (distinct incidents — identical ones are signature-suppressed instead).
    slack = MultiChannelSlack({
        "C1": [{"type": "message", "ts": "5.0", "text": ALERT}],
        "C2": [{"type": "message", "ts": "5.0", "text": OTHER_ALERT}],
    })
    runtime = FakeRuntime()
    handled = run_once(_cfg_multi(tmp_path), slack, runtime, agent=object())
    assert handled == 2


def test_same_incident_across_channels_is_triaged_once(tmp_path):
    # The digest and raw channel carry the SAME incident — one triage total.
    slack = MultiChannelSlack({
        "C1": [{"type": "message", "ts": "1.0", "text": ALERT}],
        "C2": [{"type": "message", "ts": "2.0", "text": ALERT_B}],
    })
    runtime = FakeRuntime()
    handled = run_once(_cfg_multi(tmp_path), slack, runtime, agent=object())
    assert handled == 1
    assert len(runtime.calls) == 1


# ── signature cooldown (flapper re-triage guard) ────────────────────────
# Live 2026-07-22: the raw channel fired the same shailesh-test-gcp TIMED_OUT
# alert 4x in <1h (fresh exec id each time) and each got a full LLM triage.
# Within the cooldown window, a repeated signature is marked processed but NOT
# re-triaged and nothing is posted for it.

ALERT_B = ALERT.replace("364b459a-689f-11f1-94b6-de01f12a4ed9",
                        "aaaaaaaa-689f-11f1-94b6-de01f12a4ed9")
OTHER_ALERT = (
    "[CRITICAL] The health-checking has FAILED for the Acme's prod acme-prod cluster:\n"
    "https://ah5r-prod.orkesconductor.com/execution/bbbbbbbb-689f-11f1-94b6-de01f12a4ed9"
)


def test_same_signature_within_cooldown_is_not_retriaged(tmp_path):
    cfg = _cfg(tmp_path)
    runtime = FakeRuntime()
    first = run_once(cfg, FakeSlack([{"type": "message", "ts": "1.0", "text": ALERT}]),
                     runtime, agent=object())
    slack2 = FakeSlack([{"type": "message", "ts": "2.0", "text": ALERT_B}])
    second = run_once(cfg, slack2, runtime, agent=object())

    assert first == 1
    assert second == 0          # same incident, new exec id -> suppressed
    assert len(runtime.calls) == 1
    assert slack2.posts == []   # no thread spam for the duplicate


def test_different_signature_is_triaged(tmp_path):
    cfg = _cfg(tmp_path)
    runtime = FakeRuntime()
    run_once(cfg, FakeSlack([{"type": "message", "ts": "1.0", "text": ALERT}]), runtime, agent=object())
    handled = run_once(cfg, FakeSlack([{"type": "message", "ts": "2.0", "text": OTHER_ALERT}]),
                       runtime, agent=object())
    assert handled == 1
    assert len(runtime.calls) == 2


def test_signature_handled_after_cooldown_expires(tmp_path, monkeypatch):
    # After cooldown expiry the firing is handled again — via incident memory
    # (deterministic update, no second LLM run); the full re-triage cadence is
    # covered by test_full_retriage_after_interval_includes_prior_diagnosis.
    import oncall_agent.slack_app as app

    cfg = _cfg(tmp_path)
    runtime = FakeRuntime()
    clock = {"now": 1000.0}
    monkeypatch.setattr(app.time, "time", lambda: clock["now"])
    run_once(cfg, FakeSlack([{"type": "message", "ts": "1.0", "text": ALERT}]), runtime, agent=object())
    clock["now"] += app._SIGNATURE_COOLDOWN_S + 1
    slack2 = FakeSlack([{"type": "message", "ts": "2.0", "text": ALERT_B}])
    handled = run_once(cfg, slack2, runtime, agent=object())
    assert handled == 1
    assert len(runtime.calls) == 1          # memory answered; no second LLM run
    assert slack2.posts                      # the thread still got an update


def test_same_execution_id_across_channels_is_triaged_once(tmp_path):
    # Live 2026-07-22: the raw channel's TIMED_OUT message and the digest
    # channel's aggregated message reference the SAME execution — but their
    # texts tokenize differently, so signature suppression missed the pair.
    # An execution id, once triaged, must never be triaged again.
    raw_fmt = (
        ":x: The health-checking for the cluster *Elementor - elementor-poc* has failed \n"
        "Failure Status: `TIMED_OUT` \n"
        "<https://ah5r-prod.orkesconductor.com/execution/ec7eba38-689f-11f1-94b6-de01f12a4ed9>"
    )
    digest_fmt = (
        ":warning: *[WARNING]* *Elementor* · `elementor-poc` — `TIMED_OUT`\n"
        "&gt;:x: The health-checking for the cluster *Elementor - elementor-poc* has failed\n"
        "<https://ah5r-prod.orkesconductor.com/execution/ec7eba38-689f-11f1-94b6-de01f12a4ed9|View source>\n"
        ":repeat: *1* occurrences · Last seen: <!date^1784733716^{time}|x>"
    )
    from oncall_agent.alert import alert_signature
    assert alert_signature(raw_fmt) != alert_signature(digest_fmt)  # precondition of the bug

    slack = MultiChannelSlack({
        "C1": [{"type": "message", "ts": "1.0", "text": raw_fmt}],
        "C2": [{"type": "message", "ts": "2.0", "text": digest_fmt}],
    })
    runtime = FakeRuntime()
    handled = run_once(_cfg_multi(tmp_path), slack, runtime, agent=object())
    assert handled == 1
    assert len(runtime.calls) == 1


def test_signature_arm_is_persisted_before_the_triage_runs(tmp_path):
    """Live 2026-07-23: an exception escaping mid-triage (e.g. a failed Slack
    post) was absorbed by the per-channel guard AFTER the in-memory signature/
    execution arm but BEFORE the save — the arm was lost and later firings of
    the same incident re-triaged. The arm must hit disk before the LLM runs."""
    import json

    cfg = _cfg(tmp_path)

    class CrashingSlack(FakeSlack):
        def post_reply(self, channel, thread_ts, text):
            raise RuntimeError("slack hiccup")  # crashes on the ':mag:' post

    runtime = FakeRuntime()
    handled = run_once(cfg, CrashingSlack([{"type": "message", "ts": "2.0", "text": ALERT}]),
                       runtime, agent=object())

    assert handled == 0            # the triage never completed
    state = json.loads(open(cfg.state_file).read())
    assert state.get("signatures"), "signature arm must be persisted pre-triage"
    assert "364b459a-689f-11f1-94b6-de01f12a4ed9" in state.get("executions", {})


# ── incident memory (token burn on repeat firings) ──────────────────────
# Manan's review (2026-07-24): every repeat firing of a known incident burned
# a full LLM triage. Now: the first firing runs the full triage and its root
# cause is remembered per signature; repeat firings within
# ONCALL_FULL_TRIAGE_INTERVAL get a deterministic in-thread update built from
# memory (no LLM); a full re-triage runs only after the interval expires, with
# the prior diagnosis included in the prompt.

MEMORY_RESULT = (
    "*Issue*: CPU pinned\n*Findings*:\n- stuff\n"
    "*Likely root cause*: sweeper timeout storm against stale peer IPs\n"
    "*Suggested next step*: rolling restart"
)


class MemoryRuntime:
    def __init__(self):
        self.calls = []

    def run(self, agent, prompt, **kwargs):
        self.calls.append(prompt)
        class _R:
            output = {"result": MEMORY_RESULT, "finishReason": "COMPLETED",
                      "context": {}, "rejectionReason": None}
        return _R()


def test_repeat_firing_within_interval_replies_from_memory_without_llm(tmp_path, monkeypatch):
    import oncall_agent.slack_app as app

    cfg = _cfg(tmp_path)
    clock = {"now": 1000.0}
    monkeypatch.setattr(app.time, "time", lambda: clock["now"])
    runtime = MemoryRuntime()

    first = run_once(cfg, FakeSlack([{"type": "message", "ts": "1.0", "text": ALERT}]),
                     runtime, agent=object())
    assert first == 1 and len(runtime.calls) == 1

    clock["now"] += app._SIGNATURE_COOLDOWN_S + 1  # cooldown expired, interval not
    slack2 = FakeSlack([{"type": "message", "ts": "2.0", "text": ALERT_B}])
    second = run_once(cfg, slack2, runtime, agent=object())

    assert len(runtime.calls) == 1          # NO new LLM run
    assert second == 1                       # but the firing was handled
    update = slack2.posts[-1][2]
    assert "sweeper timeout storm against stale peer IPs" in update  # prior diagnosis
    assert "no new investigation" in update.lower()


def test_full_retriage_after_interval_includes_prior_diagnosis(tmp_path, monkeypatch):
    import oncall_agent.slack_app as app

    cfg = _cfg(tmp_path)
    clock = {"now": 1000.0}
    monkeypatch.setattr(app.time, "time", lambda: clock["now"])
    runtime = MemoryRuntime()

    run_once(cfg, FakeSlack([{"type": "message", "ts": "1.0", "text": ALERT}]),
             runtime, agent=object())
    clock["now"] += app._FULL_TRIAGE_INTERVAL_S + 1
    run_once(cfg, FakeSlack([{"type": "message", "ts": "2.0", "text": ALERT_B}]),
             runtime, agent=object())

    assert len(runtime.calls) == 2           # full re-triage ran
    assert "sweeper timeout storm" in runtime.calls[1]  # prompt carries prior diagnosis


# ── triage deadline ──────────────────────────────────────────────────────
# runtime.run() blocks. A triage that never returns wedges the whole poll
# loop: no channel is read again until the process is restarted. Seen live —
# a tool task hit its responseTimeout, was re-queued with nobody polling it,
# and the loop sat on one incident for 59h (Sat 01:25 -> Mon 12:48) having
# triaged nothing. The deadline exists so the loop walks away instead.


class HangingRuntime:
    """Blocks in run() until released — stands in for a wedged execution."""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def run(self, agent, prompt, **kwargs):
        self.entered.set()
        self.release.wait(30)  # bounded so a failing test cannot hang the suite
        return FakeResult()


def test_hung_triage_does_not_wedge_the_loop(tmp_path, monkeypatch):
    monkeypatch.setattr(slack_app, "_TRIAGE_DEADLINE_S", 1)
    slack = FakeSlack([{"type": "message", "ts": "2.0", "text": ALERT}])
    runtime = HangingRuntime()
    try:
        started = time.monotonic()
        handled = run_once(_cfg(tmp_path), slack, runtime, agent=object())
        elapsed = time.monotonic() - started

        assert runtime.entered.is_set()          # we really did call into run()
        assert elapsed < 10                      # returned on the deadline, not on release
        assert handled == 1                      # counted, so the loop moves on
        assert any("gave up after" in p[2] for p in slack.posts)
        assert not any("Likely root cause" in p[2] for p in slack.posts)
    finally:
        runtime.release.set()


def test_loop_keeps_triaging_after_a_timeout(tmp_path, monkeypatch):
    """The wedged incident must not poison the next one."""
    monkeypatch.setattr(slack_app, "_TRIAGE_DEADLINE_S", 1)
    cfg = _cfg_multi(tmp_path)
    hung = HangingRuntime()

    class OneHangThenWork:
        def __init__(self):
            self.calls = []

        def run(self, agent, prompt, **kwargs):
            self.calls.append(prompt)
            if len(self.calls) == 1:
                return hung.run(agent, prompt)
            return FakeResult()

    slack = MultiChannelSlack({
        "C1": [{"type": "message", "ts": "1.0", "text": ALERT}],
        "C2": [{"type": "message", "ts": "2.0", "text": OTHER_ALERT}],
    })
    runtime = OneHangThenWork()
    try:
        handled = run_once(cfg, slack, runtime, agent=object())
        assert handled == 2
        assert len(runtime.calls) == 2
        assert any("gave up after" in p[2] for p in slack.posts)      # C1 abandoned
        assert any("Likely root cause" in p[2] for p in slack.posts)  # C2 still triaged
    finally:
        hung.release.set()


def test_deadline_passed_through_to_the_runtime(tmp_path, monkeypatch):
    """The SDK gets the bound too — so the abandoned thread eventually exits."""
    monkeypatch.setattr(slack_app, "_TRIAGE_DEADLINE_S", 77)
    seen = {}

    class RecordingRuntime:
        def run(self, agent, prompt, **kwargs):
            seen.update(kwargs)
            return FakeResult()

    slack = FakeSlack([{"type": "message", "ts": "2.0", "text": ALERT}])
    run_once(_cfg(tmp_path), slack, RecordingRuntime(), agent=object())
    assert seen.get("timeout") == 77


# ── non-COMPLETED executions ─────────────────────────────────────────────
# runtime.run() returns normally when the execution FAILED or was TERMINATED;
# only the .status says so. summary_text() then falls through to str(output).
# Seen live: terminating the 59h-wedged execution by hand made the loop post
# "{'result': None, 'finishReason': 'TOOL_CALLS', ...}" into a prod thread and
# store it in incident memory as that incident's diagnosis.


class TerminatedResult:
    output = {
        "result": None,
        "finishReason": "TOOL_CALLS",
        "context": {},
        "rejectionReason": None,
    }
    status = "TERMINATED"
    error = "stuck 59h - tool tasks stranded in queue"


class TerminatedRuntime:
    def run(self, agent, prompt, **kwargs):
        return TerminatedResult()


def test_terminated_execution_is_not_posted_as_a_diagnosis(tmp_path):
    slack = FakeSlack([{"type": "message", "ts": "2.0", "text": ALERT}])
    cfg = _cfg(tmp_path)
    handled = run_once(cfg, slack, TerminatedRuntime(), agent=object())

    assert handled == 1
    posted = " ".join(p[2] for p in slack.posts)
    assert "Triage failed" in posted
    assert "TERMINATED" in posted
    # The raw result dict must never reach the thread.
    assert "finishReason" not in posted
    assert "TOOL_CALLS" not in posted


def test_terminated_execution_is_not_written_to_incident_memory(tmp_path):
    """A poisoned memory entry outlives the incident — it is replayed as the
    'PRIOR DIAGNOSIS' on every later firing of the same signature."""
    cfg = _cfg(tmp_path)
    run_once(cfg, FakeSlack([{"type": "message", "ts": "2.0", "text": ALERT}]),
             TerminatedRuntime(), agent=object())

    state = json.loads(Path(cfg.state_file).read_text())
    assert state.get("incidents", {}) == {}


# ── worker-health preflight ──────────────────────────────────────────────
# The process stayed alive while SDK worker threads died. Every triage forked
# tool tasks onto unpolled queues and burned the 30-minute deadline producing
# nothing — 26+ dead triages over 2.1 days. Skip fast and say why instead.


def test_triage_is_skipped_when_tool_workers_are_dead(tmp_path, monkeypatch):
    monkeypatch.setattr(slack_app, "_poll_ages",
                        lambda url, tts: {t: 3071 * 60 for t in tts})
    slack = FakeSlack([{"type": "message", "ts": "2.0", "text": ALERT}])
    runtime = FakeRuntime()
    handled = run_once(_cfg(tmp_path), slack, runtime, agent=object())

    assert handled == 1
    assert runtime.calls == [], "must NOT invoke the LLM when tools cannot run"
    posted = " ".join(p[2] for p in slack.posts)
    assert "tool workers are not polling" in posted
    assert "min ago" in posted, "must say how stale, not just that it failed"


def test_triage_proceeds_normally_when_workers_are_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr(slack_app, "_poll_ages", lambda url, tts: {t: 0.1 for t in tts})
    slack = FakeSlack([{"type": "message", "ts": "2.0", "text": ALERT}])
    runtime = FakeRuntime()
    handled = run_once(_cfg(tmp_path), slack, runtime, agent=object())

    assert handled == 1
    assert len(runtime.calls) == 1, "healthy workers must not block triage"
    assert any("Likely root cause" in p[2] for p in slack.posts)
