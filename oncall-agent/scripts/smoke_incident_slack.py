"""End-to-end check of the incident workflow through the approver's Slack DM (not an alert channel).

Starts one oncall_incident workflow for a real health-check execution, serves its tasks, and routes
replies from the DM thread until the workflow ends (reply `close`, or 40 min pass).
    PYTHONPATH=src .venv/bin/python scripts/smoke_incident_slack.py <health_check execution> <cluster>
"""
import json
import logging
import sys
import tempfile
import time
from types import SimpleNamespace

import requests
from conductor.ai.agents import AgentRuntime

from oncall_agent import incident
from oncall_agent.agent import build_agent
from oncall_agent.config import Config
from oncall_agent.router import Router
from oncall_agent.runtime_compat import use_thread_workers_if_needed
from oncall_agent.slack_app import _SLACK_API, SlackClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
use_thread_workers_if_needed()
cfg = Config.from_env()
exec_id, cluster = sys.argv[1], sys.argv[2]
tok = {"Authorization": f"Bearer {cfg.slack_bot_token}"}
dm = requests.post(f"{_SLACK_API}/conversations.open", headers=tok, json={"users": cfg.approvers[0]}, timeout=30).json()["channel"]["id"]
text = (f":test_tube: Incident-workflow test (not a real alert) — health check `{cluster}`\n"
        f"https://ah5r-prod.orkesconductor.com/execution/{exec_id}")
msg = requests.post(f"{_SLACK_API}/chat.postMessage", headers=tok, timeout=30, json={"channel": dm, "text": text}).json()
slack = SlackClient(cfg.slack_bot_token)
state, path = {}, tempfile.mktemp(suffix=".json")
with AgentRuntime(server_url=cfg.agentspan_server_url) as rt:
    incident.register(cfg.agentspan_server_url)
    incident.IncidentWorkers(cfg, slack, rt, build_agent(cfg.model, cfg.actions)).start()
    router = Router(cfg, slack, state, lambda: open(path, "w").write(json.dumps(state)))
    wid = router.on_alert(dm, {"ts": msg["ts"], "text": text}, SimpleNamespace(execution_id=exec_id, cluster=cluster))
    print("WORKFLOW", wid, flush=True)
    end = time.time() + 2400
    while time.time() < end and router._running(wid):
        router.poll_threads()
        time.sleep(15)
    w = router._workflow(wid)
    print("FINAL", w.get("status"), [(t["referenceTaskName"], t["status"], (t.get("outputData") or {}).get("kind"))
                                     for t in w.get("tasks", []) if t["taskType"] in ("WAIT", "SIMPLE")], flush=True)
