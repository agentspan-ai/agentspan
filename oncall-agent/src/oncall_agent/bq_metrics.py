"""Load questions answered from the fleet metrics already ingested into BigQuery.

Every cluster ships its Conductor metrics to BigQuery about once a minute, so these
read history around the failure onset without touching the cluster:

* poll load — how many poll requests the server is answering, across how many task
  types, versus how many tasks it actually hands out. A server busy answering empty
  polls (hundreds of task types polled in tight loops) burns CPU on nothing.
* daily pattern — whether CPU is high in the same hours every day, which makes an
  alert a recurring scheduled load rather than a one-off incident.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

_TABLE = "data-bi-474617.conductor_staging.stg_conductor__metrics"


def _bq(sql: str, params: dict[str, str]) -> list[dict]:
    args = ["bq", "--project_id=data-bi-474617", "query", "--use_legacy_sql=false", "--format=json",
            "--max_rows=500"] + [f"--parameter={k}:{v}" for k, v in params.items()] + [sql]
    p = subprocess.run(args, capture_output=True, text=True, timeout=180)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout).strip()[:300])
    return json.loads(p.stdout or "[]")


def _ts(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def poll_load(cluster: str, onset_ms: int, window_min: int = 30) -> dict:
    """Poll requests/s, task types polled and tasks handed out/s in the window before onset."""
    sql = f"""
    WITH c AS (
      SELECT metric_name_base m, label_pod_name pod, label_task_type tt,
             MAX(metric_value) - MIN(metric_value) d,
             TIMESTAMP_DIFF(MAX(metric_timestamp), MIN(metric_timestamp), SECOND) secs
      FROM `{_TABLE}`
      WHERE metric_timestamp BETWEEN TIMESTAMP_SUB(TIMESTAMP(@onset), INTERVAL {int(window_min)} MINUTE)
                                 AND TIMESTAMP(@onset)
        AND metric_category_tag = 'queue_health' AND cluster_name = @cluster
        AND metric_name_base IN ('task_poll_request_seconds', 'task_queue_wait_time_seconds')
        AND metric_type_tag = 'timer_count'
      GROUP BY 1, 2, 3)
    SELECT m, tt, SUM(d / NULLIF(secs, 0)) per_s, COUNT(DISTINCT pod) pods
    FROM c WHERE d >= 0 GROUP BY 1, 2"""
    rows = _bq(sql, {"cluster": f"STRING:{cluster}", "onset": f"STRING:{_ts(onset_ms)}"})
    polls = {r["tt"]: float(r["per_s"] or 0) for r in rows if r["m"] == "task_poll_request_seconds"}
    handed = {r["tt"]: float(r["per_s"] or 0) for r in rows if r["m"] == "task_queue_wait_time_seconds"}
    if not polls:
        return {"error": "no_poll_metrics", "detail": f"no task_poll metrics for {cluster} before the onset"}
    total_polls, total_handed = sum(polls.values()), sum(handed.values())
    empty_types = [t for t, r in polls.items() if r > 0 and handed.get(t, 0) == 0]
    top = sorted(polls.items(), key=lambda kv: -kv[1])[:5]
    empty_share = 1 - min(total_handed / total_polls, 1) if total_polls else None
    verdict = (f"{total_polls:.0f} poll requests/s across {len(polls)} task types, but only "
               f"{total_handed:.1f} tasks/s handed out — {len(empty_types)} task types are polled and "
               f"never have work. ")
    verdict += ("The server is spending its CPU answering EMPTY polls: reduce polled task types / "
                "poll frequency (or batch them), not CPU limits."
                if empty_share is not None and empty_share > 0.9 and total_polls > 200
                else "Poll load is proportionate to the work handed out.")
    return {"window": f"{window_min} min before {_ts(onset_ms)} UTC",
            "pollRequestsPerSec": round(total_polls, 1), "taskTypesPolled": len(polls),
            "tasksHandedOutPerSec": round(total_handed, 2),
            "emptyPollShare": None if empty_share is None else round(empty_share, 3),
            "taskTypesNeverWithWork": len(empty_types),
            "topPolledTaskTypes": [{"taskType": t, "pollsPerSec": round(r, 1)} for t, r in top],
            "verdict": verdict}


def daily_cpu_pattern(cluster: str, onset_ms: int, days: int = 14) -> dict:
    """Is conductor CPU high in the same UTC hours every day? (hour-of-day profile over days)"""
    sql = f"""
    WITH h AS (
      SELECT DATE(metric_timestamp) d, EXTRACT(HOUR FROM metric_timestamp) hr, AVG(metric_value) cpu
      FROM `{_TABLE}`
      WHERE metric_timestamp BETWEEN TIMESTAMP_SUB(TIMESTAMP(@onset), INTERVAL {int(days)} DAY) AND TIMESTAMP(@onset)
        AND metric_category_tag = 'infrastructure' AND cluster_name = @cluster
        AND metric_name_base = 'process_cpu_usage' AND label_pod_name LIKE 'orkes-conductor-deployment%'
      GROUP BY 1, 2)
    SELECT hr, COUNT(*) days_seen, APPROX_QUANTILES(cpu, 2)[OFFSET(1)] median_cpu,
           COUNTIF(cpu >= 0.75) days_hot
    FROM h GROUP BY hr ORDER BY hr"""
    rows = _bq(sql, {"cluster": f"STRING:{cluster}", "onset": f"STRING:{_ts(onset_ms)}"})
    if not rows:
        return {"error": "no_cpu_metrics", "detail": f"no process_cpu_usage for {cluster}"}
    prof = [{"hourUtc": int(r["hr"]), "medianCpu": round(float(r["median_cpu"]), 2),
             "daysHot": int(r["days_hot"]), "daysSeen": int(r["days_seen"])} for r in rows]
    # Hot = clearly above this cluster's OWN baseline in the same hours across days (a 0.50 →
    # 0.65 daily window is the signal on a cluster that never reaches an absolute threshold).
    base = sorted(p["medianCpu"] for p in prof)[len(prof) // 2]
    hot = [p["hourUtc"] for p in prof if p["daysSeen"] >= 3 and base > 0 and p["medianCpu"] >= 1.15 * base]
    alert_hour = datetime.fromtimestamp(onset_ms / 1000, tz=timezone.utc).hour
    if hot:
        verdict = (f"DAILY PATTERN: conductor CPU rises every day in UTC hours {_ranges(hot)} "
                   f"(median {max(p['medianCpu'] for p in prof if p['hourUtc'] in hot):.2f} vs baseline {base:.2f}) "
                   f"over the last {days} days. " + ("The alert falls inside this recurring daily window — a scheduled/"
                                       "batch load that repeats every day, not a one-off incident."
                                       if alert_hour in hot else
                                       f"The alert hour ({alert_hour:02d}:00) is outside it."))
    else:
        verdict = f"No recurring daily CPU window over the last {days} days."
    return {"dailyHotHoursUtc": hot, "alertHourUtc": alert_hour, "verdict": verdict, "hourProfile": prof}


def _ranges(hours: list[int]) -> str:
    out, start, prev = [], hours[0], hours[0]
    for h in hours[1:] + [None]:
        if h is not None and h == prev + 1:
            prev = h
            continue
        out.append(f"{start:02d}:00–{prev + 1:02d}:00")
        if h is not None:
            start = prev = h
    return ", ".join(out)


def restart_timeline(cluster: str, onset_ms: int, days: int = 30) -> dict:
    """Daily restarts per container over the last ``days`` (survives pod moves, unlike restartCount)."""
    sql = f"""
    SELECT DATE(metric_timestamp) d, JSON_VALUE(labels, '$.resource') container,
           MAX(metric_value) - MIN(metric_value) restarts
    FROM `{_TABLE}`
    WHERE metric_timestamp BETWEEN TIMESTAMP_SUB(TIMESTAMP(@onset), INTERVAL {int(days)} DAY)
                               AND TIMESTAMP_ADD(TIMESTAMP(@onset), INTERVAL 1 HOUR)
      AND cluster_name = @cluster AND metric_name_base = 'infra_k8s_restartCount'
    GROUP BY 1, 2 HAVING restarts > 0 ORDER BY 1"""
    rows = _bq(sql, {"cluster": f"STRING:{cluster}", "onset": f"STRING:{_ts(onset_ms)}"})
    days_out: dict[str, dict[str, int]] = {}
    for r in rows:
        days_out.setdefault(r["d"], {})[r["container"]] = int(float(r["restarts"]))
    total = sum(sum(v.values()) for v in days_out.values())
    worst = max(days_out.items(), key=lambda kv: sum(kv[1].values()), default=(None, {}))
    return {"days": days, "totalRestarts": total, "daysWithRestarts": len(days_out),
            "worstDay": {"date": worst[0], "restarts": worst[1]} if worst[0] else None,
            "byDay": days_out}
