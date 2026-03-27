# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Plan (Dry Run) — compile an agent without executing it.

Demonstrates:
    - runtime.plan() to compile an agent to a Conductor workflow
    - Inspecting the compiled workflow structure (tasks, loops, tool routing)
    - CI/CD validation: verify agents compile correctly before deployment

plan() sends the agent config to the server, which compiles it into a
Conductor WorkflowDef and returns it — without registering, starting
workers, or executing. Useful for debugging and CI validation.

Requirements:
    - Conductor server running
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

import json

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


@tool
def search_web(query: str) -> dict:
    """Search the web for information.

    Args:
        query: Search query string.

    Returns:
        Dictionary with search results.
    """
    return {"query": query, "results": ["result1", "result2"]}


@tool
def write_report(title: str, content: str) -> dict:
    """Write a section of a report.

    Args:
        title: Section title.
        content: Section body text.

    Returns:
        Dictionary with the formatted section.
    """
    return {"section": f"## {title}\n\n{content}"}


# ── Define the agent (same as any other example) ─────────────────────

agent = Agent(
    name="research_writer",
    model=settings.llm_model,
    instructions="You are a research writer. Research topics and write reports.",
    tools=[search_web, write_report],
    max_turns=10,
)

if __name__ == "__main__":
    # ── Plan: compile without executing ──────────────────────────────────

    with AgentRuntime() as runtime:
        workflow_def = runtime.plan(agent)

        # The returned dict shows exactly what Conductor will execute
        print(f"Workflow name: {workflow_def['name']}")
        tasks = workflow_def.get("tasks", [])
        print(f"Total tasks:   {len(tasks)}")
        print()

        # Walk the task tree
        for task in tasks:
            print(f"  [{task['type']}] {task['taskReferenceName']}")
            if task["type"] == "DO_WHILE" and task.get("loopOver"):
                for sub in task["loopOver"]:
                    print(f"    [{sub['type']}] {sub['taskReferenceName']}")

        # Full JSON for CI/CD validation or export
        print("\n--- Full workflow JSON ---")
        print(json.dumps(workflow_def, indent=2, default=str))
