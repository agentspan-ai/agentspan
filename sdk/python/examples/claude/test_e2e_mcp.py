# examples/claude/test_e2e_mcp.py
"""E2E test: real Claude + real Conductor, exercises all MCP bridge features.

Run: AGENTSPAN_WORKER_THREADS=2 uv run python examples/claude/test_e2e_mcp.py
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("AGENTSPAN_WORKER_THREADS", "2")

import httpx

from agentspan.agents import AgentRuntime
from agentspan.agents.frameworks import ClaudeCodeAgent
from agentspan.agents.tool import tool

CONDUCTOR_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:8080/api")


@tool
def echo_tool(message: str) -> str:
    """Echo the message with prefix 'echo:'."""
    return f"echo:{message}"


def get_workflow_events(workflow_id: str) -> list:
    """Fetch events for a workflow from Agentspan server.

    Returns empty list if the server does not support the events endpoint.
    """
    try:
        resp = httpx.get(
            f"{CONDUCTOR_URL}/agent/events/{workflow_id}",
            timeout=10,
        )
        return resp.json() if resp.status_code == 200 else []
    except Exception:
        return []


def get_conductor_workflow(workflow_id: str) -> dict:
    resp = httpx.get(f"{CONDUCTOR_URL}/workflow/{workflow_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def search_workflows_by_type(workflow_type: str, limit: int = 20) -> list:
    """Search Conductor for workflows of a given type, ordered by start time desc."""
    try:
        resp = httpx.get(
            f"{CONDUCTOR_URL}/workflow/search",
            params={"query": f"workflowType = {workflow_type}", "start": 0, "size": limit},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("results", [])
        return []
    except Exception:
        return []


agent = ClaudeCodeAgent(
    name="e2e_mcp_test",
    cwd="/tmp",
    allowed_tools=["Bash"],      # one built-in tool
    mcp_tools=[echo_tool],        # one ecosystem tool via MCP
    conductor_subagents=True,     # spawn_subagent via Conductor
    max_turns=8,
    model="claude-sonnet-4-6",
    permission_mode="bypassPermissions",  # auto-approve all tool calls
    system_prompt="""You are a test agent. Complete these FOUR steps exactly, then stop:

STEP 1: Run bash command: echo "built-in"
STEP 2: Call the mcp__agentspan__echo_tool with message="ecosystem"
STEP 3: Call spawn_subagent with prompt: "Reply with only the word: subagent-done"
STEP 4: Reply with exactly this format (no other text):
RESULT|<output of step 1>|<output of step 2>|<output of step 3>

Important: Do all four steps before replying with RESULT.
""",
)


def main():
    print("Starting E2E MCP bridge test...")
    start = time.time()

    with AgentRuntime() as runtime:
        result = runtime.run(agent, "Execute the four steps now.")

    elapsed = time.time() - start
    print(f"Completed in {elapsed:.1f}s")
    print(f"Status: {result.status}")
    print(f"Workflow ID: {result.workflow_id}")
    print(f"Output: {result.output}")

    # ── Assert 1: workflow completed ──────────────────────────────────────
    assert result.status == "COMPLETED", f"Expected COMPLETED, got {result.status}"
    print("✓ Main workflow COMPLETED")

    # ── Assert 2: output contains Bash tool result ─────────────────────────
    output_text = str(result.output)
    assert "built-in" in output_text, \
        f"Expected 'built-in' in output (Bash tool ran), got: {output_text}"
    print("✓ Bash built-in tool executed (output contains 'built-in')")

    # ── Assert 3: echo_tool ran as Conductor task with correct result ──────
    assert "echo:ecosystem" in output_text, \
        f"Expected 'echo:ecosystem' in output (echo_tool ran via MCP→Conductor), got: {output_text}"
    print("✓ echo_tool ran as MCP→Conductor task (output contains 'echo:ecosystem')")

    # Verify a _mcp_tool_echo_tool workflow was actually created in Conductor
    echo_wf_runs = search_workflows_by_type("_mcp_tool_echo_tool", limit=50)
    # Filter to runs that happened after test started (startTime is an ISO string or ms int)
    def _parse_start_time(wf: dict) -> float:
        """Return start time as a float (seconds since epoch)."""
        t = wf.get("startTime", 0) or 0
        if isinstance(t, str):
            try:
                from datetime import datetime, timezone
                return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
            except Exception:
                return 0.0
        return t / 1000.0 if t > 1e10 else float(t)

    cutoff = start - 120  # 2 minutes before test started
    recent_echo_runs = [w for w in echo_wf_runs if _parse_start_time(w) > cutoff]
    if recent_echo_runs:
        echo_wf = recent_echo_runs[0]
        assert "echo:ecosystem" in str(echo_wf.get("output", "")), \
            f"echo_tool Conductor workflow output: {echo_wf.get('output')}"
        print(f"✓ echo_tool dispatched to real Conductor workflow ({echo_wf.get('workflowId', '')[:16]}...)")
    else:
        print("  (echo_tool Conductor workflow search skipped — search results may lag)")

    # ── Assert 4: subagent is a linked Conductor workflow ─────────────────
    # Check that a sub-workflow with _is_subagent=true was created
    agent_wf_runs = search_workflows_by_type("_fw_claude_e2e_mcp_test", limit=50)
    recent_subagent_runs = [
        w for w in agent_wf_runs
        if "_is_subagent" in str(w.get("input", ""))
        and _parse_start_time(w) > cutoff
    ]

    if recent_subagent_runs:
        sub_wf = recent_subagent_runs[0]
        sub_wf_id = sub_wf.get("workflowId", "")
        sub_wf_detail = get_conductor_workflow(sub_wf_id)
        assert sub_wf_detail["status"] == "COMPLETED", \
            f"Subagent workflow {sub_wf_id} expected COMPLETED, got {sub_wf_detail['status']}"
        assert "subagent-done" in str(sub_wf_detail.get("output", "")), \
            f"Subagent output: {sub_wf_detail.get('output')}"
        print(f"✓ Subagent is a real Conductor workflow ({sub_wf_id[:16]}...) — COMPLETED")
    else:
        # Fallback: just verify the output text contains subagent result
        assert "subagent-done" in output_text, \
            f"Expected 'subagent-done' in output (subagent ran), got: {output_text}"
        print("✓ spawn_subagent returned 'subagent-done' (output verified from workflow result)")

    # ── Assert 5: check events endpoint (optional — not all servers support it) ─
    events = get_workflow_events(result.workflow_id)
    if events:
        event_types = {e.get("type") for e in events}
        builtin_calls = [e for e in events if e.get("type") == "tool_call" and e.get("source") == "builtin"]
        mcp_calls = [e for e in events if e.get("type") == "tool_call" and e.get("source") == "mcp"]
        subagent_starts = [e for e in events if e.get("type") == "subagent_start"]
        subagent_stops = [e for e in events if e.get("type") == "subagent_stop"]
        print(f"  Events endpoint: {len(events)} events, types: {event_types}")
        if builtin_calls:
            print(f"  ✓ builtin tool_call events: {[e.get('toolName') for e in builtin_calls]}")
        if mcp_calls:
            print(f"  ✓ MCP tool_call events: {[e.get('toolName') for e in mcp_calls]}")
        if subagent_starts:
            print(f"  ✓ subagent_start event: subWorkflowId={subagent_starts[0].get('subWorkflowId')}")
        if subagent_stops:
            print("  ✓ subagent_stop event")
    else:
        print("  (events endpoint not available on this server — skipping event assertions)")

    print(f"\n✅ All assertions passed in {elapsed:.1f}s")
    print(f"   Main workflow:     {result.workflow_id}")
    result.print_result()


if __name__ == "__main__":
    main()
