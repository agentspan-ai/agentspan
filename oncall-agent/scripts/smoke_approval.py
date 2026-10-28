"""Exercise the approval path end to end against the Agentspan server, then REJECT.

Nothing is changed: the proposed action is rejected, so its tool never runs.
    PYTHONPATH=src .venv/bin/python scripts/smoke_approval.py <alert execution id>
"""
import sys
import time

from conductor.ai.agents import AgentRuntime

from oncall_agent import approvals
from oncall_agent.agent import build_agent
from oncall_agent.config import Config
from oncall_agent.runtime_compat import use_thread_workers_if_needed

use_thread_workers_if_needed()
cfg = Config.from_env()
exec_id = sys.argv[1]
prompt = (f"SMOKE TEST of the approval path for alert execution {exec_id}. Do not investigate. "
          f"Immediately call restart_deployment(execution_id='{exec_id}', deployment='workers', "
          "triage_summary='*Cause*: smoke test\\n*Action*: restart workers\\n*Evidence*: 0') and nothing else.")
with AgentRuntime(server_url=cfg.agentspan_server_url) as rt:
    h = rt.start(build_agent(cfg.model, "approve"), prompt)
    print("execution", h.execution_id, flush=True)
    for _ in range(60):
        st = rt.get_status(h.execution_id)
        if st.is_waiting or st.is_complete:
            break
        time.sleep(3)
    print("waiting:", st.is_waiting, "status:", st.status, flush=True)
    calls = approvals.extract_calls(st.pending_tool)
    print("pending:", calls, flush=True)
    print(approvals.proposal_text("smoke", calls, ("U_TEST",)), flush=True)
    rt.respond(h.execution_id, {"approved": False, "reason": "smoke test reject"})
    for _ in range(40):
        st = rt.get_status(h.execution_id)
        if st.is_complete:
            break
        time.sleep(3)
    print("after reject:", st.status, str(st.output)[:200], flush=True)
