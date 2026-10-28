"""Who holds the Conductor DB's connections, and is any of them leaking?

"remaining connection slots are reserved" means Postgres is at max_connections. The
question is never the DB — it is which client filled it. pg_stat_activity knows the
client IP of every backend; the cluster knows which pod has that IP. Joined, the
answer reads "orkes-workers-... holds 330 of 403, 320 idle for over an hour" — a
leaked pool (a pool that is opened per request and never closed), fixed by
restarting THAT deployment, not the DB or conductor.
"""
from __future__ import annotations

from datetime import datetime, timezone

SQL = """
select client_addr::text ip, count(*) n,
       count(*) filter (where state = 'idle') idle,
       count(*) filter (where state = 'idle' and state_change < now() - interval '10 minutes') stale,
       min(backend_start)::text oldest, max(backend_start)::text newest,
       max(state_change)::text last_used,
       (select setting::int from pg_settings where name = 'max_connections') max_conn,
       (select setting::int from pg_settings where name = 'superuser_reserved_connections') reserved,
       left(max(query) filter (where state = 'idle'), 160) sample_query
from pg_stat_activity where backend_type = 'client backend'
group by 1 order by n desc
"""

# A pod holding more idle connections than this, untouched for 10+ minutes, is not a pool
# doing its job: Conductor's own Hikari pool caps at 32 and recycles its idle connections.
_LEAK_STALE = 40


def _pod_ips(pods_wide: str) -> dict[str, str]:
    """IP -> pod name from ``get pods -o wide`` text."""
    out = {}
    lines = [l.split() for l in (pods_wide or "").splitlines() if l.strip()]
    if not lines:
        return out
    header = [h.upper() for h in lines[0]]
    if "IP" not in header:
        return out
    ip_col = header.index("IP")
    for row in lines[1:]:
        if len(row) > ip_col:
            out[row[ip_col]] = row[0]
    return out


def summarize_connections(rows: list[dict], pods_wide: str) -> dict:
    """Connection holders by pod, saturation, and a leak verdict."""
    if not rows:
        return {"verdict": "UNKNOWN", "detail": "pg_stat_activity returned no client connections"}
    ips = _pod_ips(pods_wide)
    max_conn = int(rows[0].get("max_conn") or 0)
    usable = max_conn - int(rows[0].get("reserved") or 0)
    holders = []
    for r in rows:
        ip = str(r.get("ip") or "local").split("/")[0]
        holders.append({"pod": ips.get(ip, f"{ip} (not a pod in this namespace)"),
                        "connections": int(r["n"]), "idle": int(r["idle"]),
                        "idleOver10Min": int(r["stale"]), "oldest": r.get("oldest"),
                        "newest": r.get("newest"), "lastUsed": r.get("last_used"),
                        "sampleQuery": r.get("sample_query")})
    total = sum(h["connections"] for h in holders)
    leaks = [h for h in holders if h["idleOver10Min"] >= _LEAK_STALE]
    top = holders[0]
    if leaks:
        leak = leaks[0]
        verdict = "LEAK"
        detail = (f"{leak['pod']} holds {leak['connections']} connections, {leak['idleOver10Min']} idle for over "
                  f"10 min — a pool opened per request and never closed (last query: "
                  f"{(leak['sampleQuery'] or '')[:80]}). Restarting that deployment frees them; it fills again "
                  f"until the code is fixed.")
    elif usable and total >= usable * 0.9:
        verdict = "SATURATED"
        detail = f"{total}/{max_conn} in use; biggest holder {top['pod']} with {top['connections']}."
    else:
        verdict = "OK"
        detail = (f"{total}/{max_conn} in use NOW — not saturated. If the alert was about connection slots, "
                  f"they were freed since (a restart?); compare with the alert time.")
    return {"verdict": verdict, "detail": detail, "inUse": total, "maxConnections": max_conn,
            "usableByApps": usable, "holders": holders[:8],
            "readAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
