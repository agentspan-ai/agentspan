import json
from types import SimpleNamespace

from oncall_agent import digest


def test_digest_lists_open_incidents_chronic_clusters_and_waiting_approvals(tmp_path, monkeypatch):
    from oncall_agent import release_index, alert_history
    monkeypatch.setattr(release_index, "DB", tmp_path / "ops.db")
    now = 1_800_000_000.0
    conn = alert_history.db()
    for d in range(1, 9):
        alert_history.record(conn, now - d * 86400, "C", "noisy", "CPU usage is at 99%", None)
    wf = {"W1": {"tasks": [{"referenceTaskName": "triage", "outputData": {"answer": "*Cause*: workers leak DB connections\n*Action*: x"}},
                           {"referenceTaskName": "await_event__1", "outputData": {"kind": "firing"}}],
                 "variables": {"pending": "AG1"}}}
    monkeypatch.setattr(digest.requests, "get", lambda url, params=None, timeout=None:
                        SimpleNamespace(json=lambda: wf.get(url.rsplit("/", 1)[-1], {})))
    (tmp_path / "triages.jsonl").write_text(json.dumps({"at": now - 60, "answer": "*Cause*: x"}) + "\n")
    (tmp_path / "feedback.jsonl").write_text(json.dumps({"at": now - 60, "verdict": "correct"}) + "\n")
    state = {"incidents_open": {"k": {"workflow_id": "W1", "cluster": "orkes-devops", "after": now - 7200}}}
    text = digest.build(state, "http://x/api", tmp_path, now=now)
    assert "`orkes-devops` (2h, fired 2x) — workers leak DB connections" in text
    assert "`noisy` — 8 of 30 days" in text
    assert "Waiting for approval" in text and "1 investigations" in text and "1 correct / 0 wrong" in text


def test_digest_is_due_once_a_day_after_its_hour(monkeypatch):
    monkeypatch.setenv("ONCALL_DIGEST_HOUR_UTC", "03:30")
    morning, early = 1_800_000_000 - (1_800_000_000 % 86400) + 4 * 3600, 1_800_000_000 - (1_800_000_000 % 86400) + 3600
    assert digest.due({}, now=morning) and not digest.due({}, now=early)
    import time
    assert not digest.due({"digest_posted": time.strftime("%Y-%m-%d", time.gmtime(morning))}, now=morning)
