from oncall_agent.db_connections import summarize_connections
from oncall_agent.restarts import summarize_restarts

# orkes-devops, CCOR-13661: the workers pod held the pool leak, conductor pods their 32 each.
PODS = """NAME                                         READY   STATUS    RESTARTS   AGE   IP              NODE
orkes-conductor-deployment-7f4688d8bf-rqhzn  1/1     Running   258        33d   10.210.3.123    ip-1
orkes-workers-deployment-5b765d8654-znsss    1/1     Running   0          5h    10.210.0.176    ip-2
"""


def _row(ip, n, idle, stale, q="SET application_name = 'PostgreSQL JDBC Driver'"):
    return {"ip": f"{ip}/32", "n": n, "idle": idle, "stale": stale, "oldest": "2026-10-21 19:00",
            "newest": "2026-10-27 21:00", "last_used": "2026-10-27 21:00", "max_conn": 403,
            "reserved": 3, "sample_query": q}


def test_leaking_pod_is_named_with_its_last_query():
    rows = [_row("10.210.0.176", 330, 328, 320, "SELECT id FROM orkesdocs ORDER BY embedding <=> $1"),
            _row("10.210.3.123", 32, 30, 0)]
    out = summarize_connections(rows, PODS)
    assert out["verdict"] == "LEAK"
    assert "orkes-workers-deployment-5b765d8654-znsss" in out["detail"]
    assert "orkesdocs" in out["detail"]
    assert out["inUse"] == 362 and out["maxConnections"] == 403


def test_saturated_without_a_leak():
    rows = [_row("10.210.3.123", 200, 10, 0), _row("10.210.0.176", 180, 10, 0)]
    assert summarize_connections(rows, PODS)["verdict"] == "SATURATED"


def test_healthy_now_says_it_is_a_now_reading():
    out = summarize_connections([_row("10.210.3.123", 32, 30, 0)], PODS)
    assert out["verdict"] == "OK" and "NOW" in out["detail"]


def test_unknown_ip_is_labelled_not_guessed():
    out = summarize_connections([_row("10.9.9.9", 5, 0, 0)], PODS)
    assert "not a pod in this namespace" in out["holders"][0]["pod"]


RESTARTS = """POD                                          STARTED                C                    R      READY        REASON      EXIT   FINISHED
orkes-conductor-deployment-7f4688d8bf-rqhzn  2026-09-25T22:42:03Z   conductor            258    true         OOMKilled   137    2026-10-27T21:20:13Z
orkes-conductor-deployment-7f4688d8bf-rw9p7  2026-09-25T22:42:03Z   conductor            281    false        Error       1      2026-10-27T21:44:25Z
orkes-agent-deployment-d47bb69d8-6cl7q       2026-10-27T05:54:38Z   agent                2      true         Error       137    2026-10-27T06:00:00Z
orkes-workers-deployment-5b765d8654-znsss    2026-10-27T23:36:21Z   workers              0      true         <none>      <none> <none>
"""


def test_restart_reasons_explain_each_exit():
    out = {r["pod"][-5:]: r for r in summarize_restarts(RESTARTS)["restartingContainers"]}
    assert set(out) == {"rqhzn", "rw9p7", "6cl7q"}  # never-restarted workers left out
    assert "MEMORY LIMIT" in out["rqhzn"]["meaning"]
    assert "previous container's logs" in out["rw9p7"]["meaning"]
    assert "liveness" in out["6cl7q"]["meaning"]
    assert out["rw9p7"]["lastFinishedAt"] == "2026-10-27T21:44:25Z"


def test_poll_load_without_task_type_labels_does_not_invent_one(monkeypatch):
    from oncall_agent import bq_metrics
    monkeypatch.setattr(bq_metrics, "_bq", lambda sql, p: [
        {"m": "task_poll_request_seconds", "tt": None, "per_s": 3232.0},
        {"m": "task_queue_wait_time_seconds", "tt": None, "per_s": 0.0}])
    out = bq_metrics.poll_load("auditboard-preprod", 1793160000000)
    assert out["taskTypesPolled"].startswith("unknown") and out["pollRequestsPerSec"] == 3232.0
    assert "1 task type" not in out["verdict"]


def test_window_streak_finds_the_start_date():
    from oncall_agent.bq_metrics import _streak
    days = [{"date": f"2026-09-{d:02d}", "win": 480.0, "rest": 478.0} for d in range(18, 24)] + \
           [{"date": f"2026-09-{d:02d}", "win": 3200.0, "rest": 478.0} for d in range(24, 31)]
    s = _streak(days)
    assert s["currentStreakStartedOn"] == "2026-09-24" and not s["streakIsAsOldAsTheData"]
    assert s["daysWithWindow"] == 7
    assert _streak(days[-3:])["streakIsAsOldAsTheData"]
