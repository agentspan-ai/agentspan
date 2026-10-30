"""End-to-end approval through Slack: the proposal is posted to the approver's DM with the bot;
the approver replies `approve` / `reject` there; the change runs only on approve.

    PYTHONPATH=src .venv/bin/python scripts/smoke_approval_slack.py <alert execution id> <cluster>
"""
import sys
import time

import requests
from conductor.ai.agents import AgentRuntime

from oncall_agent import approvals
from oncall_agent.agent import build_agent
from oncall_agent.config import Config
from oncall_agent.runtime_compat import summary_text, use_thread_workers_if_needed
from oncall_agent.slack_app import _SLACK_API, SlackClient

use_thread_workers_if_needed()
cfg = Config.from_env()
exec_id, cluster = sys.argv[1], sys.argv[2]
approver = cfg.approvers[0]
tok = {"Authorization": f"Bearer {cfg.slack_bot_token}"}
dm = requests.post(f"{_SLACK_API}/conversations.open", headers=tok, json={"users": approver}, timeout=30).json()
channel = dm["channel"]["id"]
parent = requests.post(f"{_SLACK_API}/chat.postMessage", headers=tok, timeout=30, json={
    "channel": channel, "text": f":test_tube: Approval-flow test on `{cluster}` (not a real alert)."}).json()["ts"]
slack = SlackClient(cfg.slack_bot_token)
prompt = (f"SMOKE TEST of the approval path for alert execution {exec_id}. Do not investigate. "
          f"Immediately call restart_deployment(execution_id='{exec_id}', deployment='workers', "
          "triage_summary='*Cause*: approval-flow test\\n*Action*: restart workers\\n*Evidence*: test') and nothing else.")
state = {}
with AgentRuntime(server_url=cfg.agentspan_server_url) as rt:
    h = rt.start(build_agent(cfg.model, "approve", isolated=True), prompt)
    for _ in range(60):
        st = rt.get_status(h.execution_id)
        if st.is_waiting or st.is_complete:
            break
        time.sleep(3)
    calls = approvals.extract_calls(st.pending_tool)
    slack.post_reply(channel, parent, approvals.proposal_text(cluster, calls, cfg.approvers))
    state["pending_actions"] = {h.execution_id: {"channel": channel, "thread_ts": parent, "phase": "awaiting",
                                                 "asked_at": time.time(), "calls": calls}}
    print("posted to DM; waiting for your reply...", flush=True)
    while state["pending_actions"]:
        approvals.process_pending(cfg, slack, rt, state, summary_text, lambda: None,
                                  record=lambda r: print("outcome:", r.get("outcome"), flush=True))
        time.sleep(10)
print("done", flush=True)
