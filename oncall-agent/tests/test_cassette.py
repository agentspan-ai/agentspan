import pytest

from oncall_agent import cassette


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("ONCALL_RECORD_DIR", raising=False)
    monkeypatch.delenv("ONCALL_REPLAY_DIR", raising=False)
    cassette._replay.clear()
    cassette._served.clear()


def _tool(calls):
    def get_pods(execution_id: str, ns: str = "default") -> dict:
        calls.append(ns)
        if ns == "boom":
            raise ValueError("kubectl failed")
        return {"pods": len(calls), "ns": ns}
    return get_pods


def test_record_then_replay_without_live_calls(tmp_path, monkeypatch):
    live = []
    monkeypatch.setenv("ONCALL_RECORD_DIR", str(tmp_path))
    rec = cassette.wrap("get_pods", _tool(live))
    assert rec("ex1", ns="a") == {"pods": 1, "ns": "a"}
    assert rec(execution_id="ex1", ns="a") == {"pods": 2, "ns": "a"}
    with pytest.raises(ValueError):
        rec("ex1", ns="boom")

    monkeypatch.delenv("ONCALL_RECORD_DIR")
    monkeypatch.setenv("ONCALL_REPLAY_DIR", str(tmp_path))
    replayed = []
    rep = cassette.wrap("get_pods", _tool(replayed))
    # same answers, in order, then the last one repeats
    assert rep(execution_id="ex1", ns="a") == {"pods": 1, "ns": "a"}
    assert rep("ex1", "a") == {"pods": 2, "ns": "a"}
    assert rep("ex1", "a") == {"pods": 2, "ns": "a"}
    with pytest.raises(RuntimeError, match="kubectl failed"):
        rep("ex1", ns="boom")
    assert replayed == []  # nothing ran live


def test_unrecorded_call_lists_recorded_alternatives(tmp_path, monkeypatch):
    monkeypatch.setenv("ONCALL_RECORD_DIR", str(tmp_path))
    cassette.wrap("get_pods", _tool([]))("ex1", ns="a")
    monkeypatch.delenv("ONCALL_RECORD_DIR")
    monkeypatch.setenv("ONCALL_REPLAY_DIR", str(tmp_path))
    out = cassette.wrap("get_pods", _tool([]))("ex1", ns="other")
    assert out["error"] == "not_recorded"
    assert "'ns': 'a'" in out["detail"]


def test_pass_through_when_not_recording_or_replaying(tmp_path):
    live = []
    assert cassette.wrap("get_pods", _tool(live))("ex1") == {"pods": 1, "ns": "default"}
    assert list(tmp_path.iterdir()) == []


def test_every_registered_tool_is_wrapped():
    from oncall_agent.tools import ALL_TOOLS
    assert all(t._tool_def.func.__wrapped__ for t in ALL_TOOLS)
