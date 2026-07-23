"""Regression tests for the two bugs found in the first live run against ah5r-prod:
  1. cloudEnvironmentTag is absent from the workflow input -> must be derived.
  2. customer-cluster tasks must be routed to the cluster's agent domain via
     task_to_domain, or the in-cluster agent never polls them.

Uses a fake workflow client — deterministic, no network.
"""
from oncall_agent.conductor_client import ConductorDispatcher


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeWF:
    def __init__(self, input_data):
        self._input = input_data
        self.started = []

    def get_workflow(self, workflow_id, include_tasks=False):
        return _Obj(
            input=self._input, status="COMPLETED", tasks=[], output={"ok": True},
            workflow_id=workflow_id,
        )

    def start_workflow(self, request):
        self.started.append(request)
        return "wf-started-id"


def _dispatcher(input_data) -> ConductorDispatcher:
    # Skip __init__ so we don't construct a real Conductor client / hit the network.
    d = ConductorDispatcher.__new__(ConductorDispatcher)
    d._wf = FakeWF(input_data)
    return d


def test_cloud_env_tag_derived_when_absent():
    d = _dispatcher({"organizationId": "3f0c549d-d50e-416c", "clusterName": "viz-stage"})
    assert d.get_context("exec")["cloudEnvironmentTag"] == "c3f0c5-viz-stage"


def test_cloud_env_tag_used_when_present():
    d = _dispatcher(
        {"organizationId": "3f0c549d", "clusterName": "viz-stage", "cloudEnvironmentTag": "explicit"}
    )
    assert d.get_context("exec")["cloudEnvironmentTag"] == "explicit"


def test_dispatch_routes_customer_tasks_to_cluster_domain():
    d = _dispatcher({"organizationId": "org123", "clusterName": "viz-stage"})
    ctx = d.get_context("exec")
    d.dispatch("GET_PODS_DATA", "get_pods_data", ctx, timeout_s=1, poll_s=0)

    req = d._wf.started[-1]
    assert req.task_to_domain["*"] == "org123#-#viz-stage"
    assert req.task_to_domain["prepare_agent_handler"] == "NO_DOMAIN"
    assert req.correlation_id == "org123#-#viz-stage"
    # command + params land in agentHandlerRequest
    assert req.input["agentHandlerRequest"]["command"] == "GET_PODS_DATA"
    assert req.input["cloudEnvironmentTag"] == "corg12-viz-stage"


# ── transport recovery (live failure 2026-07-23) ────────────────────────
# A transient network blip left conductor-python's client with a dead socket
# ("Bad file descriptor") and a poisoned auth token; every retry reused the
# broken client and the poll loop wedged for hours. The dispatcher must
# rebuild its client and retry once on a failed call.


class _BrokenWF:
    def get_workflow(self, *a, **k):
        raise OSError(9, "Bad file descriptor")

    def start_workflow(self, *a, **k):
        raise OSError(9, "Bad file descriptor")

    def search(self, *a, **k):
        raise OSError(9, "Bad file descriptor")


class _FlakyFactory:
    """First build returns a dead client; later builds return a healthy fake."""

    def __init__(self, good):
        self.builds = 0
        self._good = good

    def __call__(self):
        self.builds += 1
        return _BrokenWF() if self.builds == 1 else self._good


def test_dispatcher_rebuilds_client_after_transport_failure():
    good = FakeWF({"organizationId": "0123456789", "clusterName": "c1"})
    factory = _FlakyFactory(good)
    d = ConductorDispatcher("url", "k", "s", client_factory=factory)

    ctx = d.get_context("exec-1")

    assert ctx["organizationId"] == "0123456789"
    assert factory.builds == 2  # broken client replaced exactly once


def test_dispatcher_raises_when_rebuild_also_fails():
    import pytest

    class _AlwaysBroken:
        builds = 0

        def __call__(self):
            self.builds += 1
            return _BrokenWF()

    d = ConductorDispatcher("url", "k", "s", client_factory=_AlwaysBroken())
    with pytest.raises(OSError):
        d.get_context("exec-1")
