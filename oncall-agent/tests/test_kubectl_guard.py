"""Deterministic guard: only read-only kubectl commands may reach the cluster.

Mirrors sql_guard: the model proposes, the guard disposes. KUBECTL_UNRESTRICTED
can run anything, so every command must pass this allowlist first.
"""
import pytest

from oncall_agent.kubectl_guard import NotReadOnlyKubectlError, ensure_readonly_kubectl

ALLOWED = [
    "get pods -n orkes",
    "kubectl get pods -A",  # leading 'kubectl' tolerated and stripped
    "describe pod orkes-agent-deployment-abc -n orkes",
    "logs orkes-agent-deployment-abc -n orkes --tail=200",
    "top pods -n orkes",
    "get events -n ingress-nginx --sort-by=.lastTimestamp",
    "rollout history deployment/orkes-agent-deployment -n orkes",
    "version",
    "api-resources",
]

REJECTED = [
    "delete pod orkes-agent-deployment-abc -n orkes",
    "apply -f evil.yaml",
    "edit deployment/orkes-conductor",
    "scale deployment/orkes-conductor --replicas=0",
    "exec -it pod -- /bin/sh",
    "port-forward pod 8080:8080",
    "patch deployment x -p '{}'",
    "rollout restart deployment/x",   # rollout is allowed ONLY for history/status
    "drain node-1",
    "cordon node-1",
    "label pod x a=b",
    "annotate pod x a=b",
    "cp pod:/etc/passwd /tmp/x",
    "create -f x.yaml",
    "replace -f x.yaml",
    "set image deployment/x c=i",
    "get pods; kubectl delete pod x",   # shell chaining
    "get pods && rm -rf /",
    "get pods | tee /tmp/x",
    "get pods $(rm -rf /)",
    "get pods `id`",
    "",
]


@pytest.mark.parametrize("cmd", ALLOWED)
def test_readonly_commands_pass(cmd):
    assert ensure_readonly_kubectl(cmd)


@pytest.mark.parametrize("cmd", REJECTED)
def test_mutating_or_shelly_commands_rejected(cmd):
    with pytest.raises(NotReadOnlyKubectlError):
        ensure_readonly_kubectl(cmd)


def test_rollout_status_allowed_restart_rejected():
    assert ensure_readonly_kubectl("rollout status deployment/x -n orkes")
    with pytest.raises(NotReadOnlyKubectlError):
        ensure_readonly_kubectl("rollout undo deployment/x")
