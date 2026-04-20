# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Crash & Resume — restart workers after a process crash.

Demonstrates the production pattern for durable LangGraph execution:
    - deploy() registers the workflow definition on the server (one-time)
    - start() triggers an execution via the server API
    - serve() registers Python workers and keeps them polling
    - After a crash, just restart serve() — the server dispatches stalled
      tasks to the new workers and the execution resumes automatically

How this works:
    Phase 1: Deploy the agent definition, start an execution, and serve
    workers briefly.  Close the runtime to simulate a crash — workers die
    but the workflow is durable on the server.

    Phase 2: Create a fresh AgentRuntime and call serve(graph).  This
    re-serializes the graph, re-registers the same workers, and starts
    polling.  The server sees workers available again and dispatches any
    stalled tasks.  The execution picks up where it left off — no special
    resume logic, no execution_id needed.

Why this matters:
    LangGraph graphs running through Agentspan are compiled into durable
    Conductor workflows.  If your process crashes (OOM, deploy, exception),
    no work is lost — the server holds the workflow state.  You just need
    to restart serve() and the workers pick up from where they left off.

Production pattern:
    # CI/CD (once):
    runtime.deploy(graph)

    # Long-running worker process (restart on crash):
    runtime.serve(graph)

    # Trigger executions from anywhere:
    runtime.start("sales_analyst", "prompt")  # or via server API / UI

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import os
import time

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from agentspan.agents import AgentRuntime

SESSION_FILE = "/tmp/agentspan_langgraph_resume.session"
SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
UI_BASE = SERVER_URL.replace("/api", "")


# -- Tools that simulate real work (each takes several seconds) ------------


@tool
def fetch_sales_data(quarter: str) -> str:
    """Fetch raw sales data for a given quarter from the data warehouse."""
    print(f"  [fetch_sales_data] Querying data warehouse for {quarter}...")
    time.sleep(3)  # simulate DB query
    return (
        f"Sales data for {quarter}: "
        "revenue=$12.4M, units=45200, regions=NA/EMEA/APAC, "
        "top_product=Widget Pro, growth=+8.3%"
    )


@tool
def analyze_trends(data: str) -> str:
    """Run trend analysis on sales data to identify patterns and anomalies."""
    print("  [analyze_trends] Running statistical analysis...")
    time.sleep(3)  # simulate compute
    return (
        "Trend analysis: Q-over-Q growth accelerating in APAC (+14%), "
        "EMEA flat, NA slight decline (-2%). "
        "Anomaly: Widget Pro spike in APAC correlates with marketing campaign. "
        "Seasonality detected in unit volumes."
    )


@tool
def generate_report(analysis: str) -> str:
    """Generate an executive summary report from the analysis."""
    print("  [generate_report] Formatting executive report...")
    time.sleep(3)  # simulate report generation
    return (
        "EXECUTIVE SUMMARY\n"
        "Revenue: $12.4M (+8.3% YoY)\n"
        "Key insight: APAC driving growth, recommend increasing investment.\n"
        "Risk: NA declining — needs attention.\n"
        "Recommendation: Double APAC marketing budget, investigate NA churn."
    )


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

graph = create_agent(
    llm,
    tools=[fetch_sales_data, analyze_trends, generate_report],
    name="sales_analyst",
)


# -- Phase 1: Deploy, start, serve briefly, then crash --------------------

print("=" * 60)
print("Phase 1: Deploy + start, then simulate crash")
print("=" * 60)

with AgentRuntime() as runtime:
    # Deploy the workflow definition (in production, do this once in CI/CD)
    runtime.deploy(graph)
    print("Agent deployed to server.")

    # Start an execution by name — the agent is already deployed on the server,
    # so we only need to send the name and prompt (not the full graph object).
    handle = runtime.start(
        "sales_analyst",
        "Fetch the Q4 2025 sales data, run a full trend analysis on it, "
        "then generate an executive summary report. "
        "Call each tool in sequence — do not skip any step.",
    )
    print(f"Execution started: {handle.execution_id}")

    # Save execution_id so we can check status later
    with open(SESSION_FILE, "w") as f:
        f.write(handle.execution_id)

    # Serve workers just long enough for the first tool to start
    print("\nServing workers briefly...")
    runtime.serve(graph, blocking=False)
    time.sleep(8)

print("\nRuntime closed — workers are dead, workflow persists on server.")
print()

with open(SESSION_FILE) as f:
    saved_execution_id = f.read().strip()

# -- Pause: let the user see the stalled execution in the UI --------------

ui_link = f"{UI_BASE}/execution/{saved_execution_id}"
print("-" * 60)
print("Open the Agentspan UI to see the execution in RUNNING state:")
print(f"  {ui_link}")
print()
print("The workflow is alive on the server but stalled — no workers are")
print("polling to pick up the next task.  The completed steps are")
print("preserved; only the remaining steps need to run.")
print("-" * 60)
input("\nPress Enter to resume (restart workers)...")
print()


# -- Phase 2: Restart serve — workers pick up stalled tasks ----------------

print("=" * 60)
print("Phase 2: Restart serve() — workers reconnect automatically")
print("=" * 60)

with AgentRuntime() as runtime:
    # serve() re-registers the same workers.  The server dispatches
    # stalled tasks to them — no resume() call needed.
    print("\nServing workers (non-blocking for demo)...")
    runtime.serve(graph, blocking=False)

    # Poll until the execution completes
    print(f"Polling execution: {saved_execution_id}")
    status = runtime.get_status(saved_execution_id)
    while not status.is_complete:
        time.sleep(2)
        status = runtime.get_status(saved_execution_id)
        print(f"  status: {status.status}")

    print(f"\nStatus: {status.status}")
    print(f"Output: {status.output}")
    print("\nCheck the completed execution in the UI:")
    print(f"  {ui_link}")

print("\nDone — same workflow, seamless resume after simulated crash.")
