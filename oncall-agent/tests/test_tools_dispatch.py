"""Each read-only tool must dispatch the right agent-handler command.

Deterministic — a fake dispatcher records (command, workflow_name, params) instead
of hitting Conductor; no network, no LLM. Guards against a tool being wired to the
wrong command (e.g. a mutating one) or silently changing its dispatch contract.
"""
import oncall_agent.tools as tools


class _FakeDispatcher:
    def __init__(self):
        self.calls = []

    def dispatch(self, command, workflow_name, context, parameters=None, **kw):
        self.calls.append((command, workflow_name, context, parameters or {}))
        return {"ok": True}

    def get_context(self, execution_id):  # pragma: no cover - cache is pre-seeded
        return {"organizationId": "org", "clusterName": "c"}


def _install(monkeypatch):
    fake = _FakeDispatcher()
    monkeypatch.setattr(tools, "_dispatcher", fake)
    # Pre-seed the per-execution context cache so the tool never calls get_context.
    monkeypatch.setattr(tools, "_ctx_cache", {"exec": {"organizationId": "org", "clusterName": "c"}})
    return fake


# (tool callable, expected command, expected workflow name)
_DISPATCH_MAP = [
    (lambda: tools.get_cluster_metrics("exec"), "GET_CLUSTER_METRICS", "get_cluster_metrics"),
    (lambda: tools.get_infrastructure_metrics("exec"), "GET_INFRASTRUCTURE_METRICS", "get_infrastructure_metrics"),
    (lambda: tools.get_pods_data("exec"), "GET_PODS_DATA", "get_pods_data"),
    (lambda: tools.get_deployments_info("exec"), "GET_DEPLOYMENTS_INFO", "get_deployments_info"),
    (lambda: tools.get_ingress_info("exec"), "GET_INGRESS_INFO", "get_ingress_info"),
]


def test_tools_dispatch_expected_commands(monkeypatch):
    for call, command, workflow_name in _DISPATCH_MAP:
        fake = _install(monkeypatch)
        call()
        assert fake.calls, f"{command} tool dispatched nothing"
        got_command, got_wf, _, _ = fake.calls[-1]
        assert got_command == command, f"expected {command}, dispatched {got_command}"
        assert got_wf == workflow_name, f"expected workflow {workflow_name}, got {got_wf}"


def test_get_ingress_info_is_in_the_toolset():
    names = {getattr(t, "__name__", None) for t in tools.ALL_TOOLS}
    assert "get_ingress_info" in names


def test_download_heap_dump_dispatches_expected_command(monkeypatch):
    # Team decision (2026-07-22): the agent captures heap dumps itself via the
    # ah5r-prod DOWNLOAD_HEAP_DUMP command instead of telling the engineer to.
    fake = _install(monkeypatch)
    tools.download_heap_dump("exec", "orkes-conductor-deployment-abc-xyz")
    command, wf, _, params = fake.calls[-1]
    assert command == "DOWNLOAD_HEAP_DUMP"
    assert wf == "download_heap_dump"
    assert params["podName"] == "orkes-conductor-deployment-abc-xyz"


def test_download_heap_dump_is_in_the_toolset():
    names = {getattr(t, "__name__", None) for t in tools.ALL_TOOLS}
    assert "download_heap_dump" in names


def test_download_thread_dump_dispatches_expected_command(monkeypatch):
    fake = _install(monkeypatch)
    tools.download_thread_dump("exec", "orkes-conductor-deployment-abc-xyz")
    command, wf, _, params = fake.calls[-1]
    assert command == "DOWNLOAD_THREAD_DUMP"
    assert wf == "download_thread_dump"
    assert params["podName"] == "orkes-conductor-deployment-abc-xyz"


def test_download_thread_dump_is_in_the_toolset():
    names = {getattr(t, "__name__", None) for t in tools.ALL_TOOLS}
    assert "download_thread_dump" in names


def test_run_kubectl_read_dispatches_guarded_command(monkeypatch):
    fake = _install(monkeypatch)
    tools.run_kubectl_read("exec", "kubectl get pods -n orkes")
    command, wf, _, params = fake.calls[-1]
    assert command == "KUBECTL_UNRESTRICTED"
    assert wf == "kubectl_unrestricted"
    assert params["unrestrictedCommand"] == "get pods -n orkes"  # 'kubectl' stripped


def test_run_kubectl_read_rejects_mutations_before_dispatch(monkeypatch):
    fake = _install(monkeypatch)
    out = tools.run_kubectl_read("exec", "delete pod x -n orkes")
    assert out.get("error") == "rejected_non_readonly_kubectl"
    assert fake.calls == []  # never reached the cluster
