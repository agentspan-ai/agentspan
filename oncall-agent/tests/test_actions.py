"""Safety invariants for the only tools that change anything."""
import pytest

from oncall_agent import actions, tools
from oncall_agent.actions import action_tools


def _boom(*_a, **_k):
    raise AssertionError("dispatched a change")


def test_every_live_action_needs_approval_and_never_retries():
    live = action_tools("approve")
    assert {t._tool_def.name for t in live} == {"restart_deployment", "set_conductor_heap"}
    assert all(t._tool_def.approval_required and t._tool_def.retry_count == 0 for t in live)


def test_read_tools_have_no_approval_gate_and_no_action_names():
    names = {t._tool_def.name for t in tools.ALL_TOOLS}
    assert not names & {"restart_deployment", "set_conductor_heap"}


def test_propose_mode_never_dispatches(monkeypatch):
    monkeypatch.setattr(tools, "_disp", _boom)
    monkeypatch.setattr(tools, "_kubectl_text", _boom)
    proposed = {t._tool_def.name: t for t in action_tools("propose")}
    # dry-run task names differ, so no live worker can ever pick up a proposal
    assert set(proposed) == {"restart_deployment_dryrun", "set_conductor_heap_dryrun"}
    out = proposed["restart_deployment_dryrun"](execution_id="e", deployment="workers", triage_summary="s")
    assert out["executed"] is False and "orkes-workers-deployment" in out["proposed"]
    out = proposed["set_conductor_heap_dryrun"](execution_id="e", xmx_mb=1200, triage_summary="s")
    assert "-Xmx1200M" in out["proposed"]


def test_only_orkes_deployments_can_be_restarted(monkeypatch):
    monkeypatch.setattr(tools, "_disp", _boom)
    with pytest.raises(ValueError):
        actions.restart_deployment("e", "postgres", "s")
    with pytest.raises(ValueError):
        action_tools("propose")[0](execution_id="e", deployment="kube-system/coredns", triage_summary="s")


def test_heap_is_bounded_by_the_container_limit(monkeypatch):
    monkeypatch.setattr(actions, "_heap_and_limit", lambda _e: ("-Xms1500M -Xmx1500M", 2048))
    monkeypatch.setattr(actions, "_dispatch", _boom)
    with pytest.raises(ValueError, match="65%"):
        actions.set_conductor_heap("e", 1500, "s")  # 1500 > 0.65 * 2048
    with pytest.raises(ValueError):
        actions.set_conductor_heap("e", 256, "s")


def test_heap_patch_is_a_strategic_merge_of_one_env_var(monkeypatch):
    sent = {}
    monkeypatch.setattr(actions, "_heap_and_limit", lambda _e: ("-Xms1500M -Xmx1500M", 2048))
    monkeypatch.setattr(actions, "_dispatch", lambda e, c, w, p, l: sent.update(cmd=c, wf=w, **p) or {})
    monkeypatch.setattr(actions, "_wait_rollout", lambda e, d: "successfully rolled out")
    out = actions.set_conductor_heap("e", 1200, "s")
    assert sent["cmd"] == "PATCH_DEPLOYMENT" and sent["patchType"] == "strategic"
    assert sent["resource"] == "orkes-conductor-deployment"
    assert '"name":"JVM_MEMORY_SETTINGS","value":"-Xms1200M -Xmx1200M"' in sent["patchStatement"]
    assert "-Xmx1500M" in out["action"] and "-Xmx1200M" in out["action"]


def test_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        action_tools("yolo")
