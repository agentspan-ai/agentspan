"""Coverage guard: every health-check alert type must stay in the triage playbook.

The agent matches alerts by their message text (the `issues` field of get_incident_details),
so the playbook in agent.py anchors on phrases from each `HealthIssue` description. This test
pins all 17 types to a distinctive phrase and fails if any is dropped from the instructions —
a deterministic, no-LLM guard so a refactor can't silently lose an alert type.

Source of truth: the `HealthIssue` enum in
orkes-saas/.../worker/HealthCheckIssuesWorker.java. If that enum changes, update this map.
"""
from oncall_agent.agent import INSTRUCTIONS

# HealthIssue enum constant -> a phrase from its description that the playbook anchors on.
# (The two Redis tiers share one playbook line, hence one shared anchor.)
ALERT_ANCHORS = {
    "REDIS_CRITICAL_USAGE": "Redis instance is at",
    "REDIS_HIGH_USAGE": "Redis instance is at",
    "CONDUCTOR_HIGH_HEAP_USAGE": "Heap usage is at",
    "CONDUCTOR_HIGH_CPU_USAGE": "CPU usage is at",
    "CONDUCTOR_ERROR_LOGS_COUNT_EXCEEDED_THRESHOLD": "Error Logs Count",
    "CONDUCTOR_WARN_LOGS_COUNT_EXCEEDED_THRESHOLD": "Warn Logs Count",
    "CONDUCTOR_HEALTHY": "Conductor has failed",
    "WORKERS_HEALTHY": "Workers have failed",
    "PROMETHEUS_NOT_RUNNING": "Prometheus is down",
    "POD_NOT_RUNNING": "not Running",
    "POD_RESTARTED": "has been restarted",
    "DNS_HEALTHY": "DNS resolution has failed",
    "DOMAIN_RESOLUTION": "has not been resolved",
    "DOMAIN_REACHABILITY": "domain X is down",
    "AUTH_STALE": "stale API key",
    "DOMAIN_CERTIFICATE_WILL_EXPIRE": "certificate expires in less than",
    "RESPONSE_TIME": "taking too long to respond",
}


def test_all_17_alert_types_are_covered():
    assert len(ALERT_ANCHORS) == 17, "HealthIssue has 17 alert types; keep this map in sync"
    missing = [name for name, anchor in ALERT_ANCHORS.items() if anchor.lower() not in INSTRUCTIONS.lower()]
    assert not missing, f"alert types missing from the triage playbook: {missing}"
