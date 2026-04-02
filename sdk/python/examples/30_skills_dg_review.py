# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Skills — Load /dg skill as a durable agent.

Demonstrates:
    - Loading an agentskills.io skill directory as an Agent
    - Sub-agents (gilfoyle, dinesh) running as real Conductor SUB_WORKFLOW tasks
    - Resource files read on demand via read_skill_file worker
    - Full execution DAG visibility with per-sub-agent tracking
    - Composing skills with regular agents in a pipeline

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - /dg skill installed (https://github.com/v1r3n/dinesh-gilfoyle)

Install /dg:
    curl -sSL https://conductor-oss.github.io/conductor-skills/install.sh | bash -s -- --all
    # Or: git clone https://github.com/v1r3n/dinesh-gilfoyle ~/.claude/skills/dg
"""

from agentspan.agents import Agent, AgentRuntime, EventType, agent_tool, skill
from settings import settings

# ── Load /dg skill as an Agent ─────────────────────────────────────
# Convention-based discovery:
#   - SKILL.md → orchestrator instructions
#   - gilfoyle-agent.md → sub-agent (own Conductor sub-workflow)
#   - dinesh-agent.md → sub-agent (own Conductor sub-workflow)
#   - comic-template.html → resource (read on demand)

dg = skill(
    "~/.claude/skills/dg",
    model=settings.llm_model,
    agent_models={
        "gilfoyle": settings.secondary_llm_model,  # Gilfoyle gets the bigger model
        "dinesh": settings.llm_model,
    },
)

# ── Example 1: Run standalone ──────────────────────────────────────

def run_standalone():
    """Run /dg as a standalone agent and show execution details."""
    with AgentRuntime() as rt:
        print("=== /dg Standalone Review ===\n")

        stream = rt.stream(dg, "Review this code:\n\n```python\n"
            "import sqlite3\n"
            "def get_user(name):\n"
            "    conn = sqlite3.connect('users.db')\n"
            "    result = conn.execute(f'SELECT * FROM users WHERE name = \"{name}\"')\n"
            "    return result.fetchone()\n"
            "```")

        print(f"Execution ID: {stream.workflow_id}\n")

        for event in stream:
            if event.type == EventType.TOOL_CALL:
                print(f"  [{event.tool_name}] dispatched")
            elif event.type == EventType.TOOL_RESULT:
                # Sub-agent results show as tool results
                preview = str(event.result)[:100]
                print(f"  [{event.tool_name}] returned: {preview}...")
            elif event.type == EventType.DONE:
                print(f"\n--- Review Complete ---")
                out = event.output.get("result", "") if isinstance(event.output, dict) else str(event.output)
                print(str(out)[:500])

        result = stream.get_result()
        print(f"\nExecution ID: {result.workflow_id}")
        print(f"Status: {result.status}")
        print(f"Tokens: {result.token_usage}")

        # Sub-agent results are individually visible
        if result.sub_results:
            print(f"\nSub-agent executions:")
            for sub in result.sub_results:
                print(f"  - {sub.agent_name}: {sub.status} ({sub.token_usage})")


# ── Example 2: Compose with regular agent in pipeline ──────────────

fixer = Agent(
    name="fixer",
    model=settings.secondary_llm_model,
    instructions=(
        "You receive a code review with findings. For each critical or important "
        "finding, write the fixed code. Output the corrected code with explanations."
    ),
)

review_and_fix = dg >> fixer  # Review first, then fix


def run_pipeline():
    """Run /dg in a pipeline: review → fix."""
    with AgentRuntime() as rt:
        print("=== Review → Fix Pipeline ===\n")

        result = rt.run(
            review_and_fix,
            "Review and fix this code:\n\n```python\n"
            "import os\n"
            "API_KEY = 'sk-1234567890abcdef'\n"
            "def fetch(url):\n"
            "    return os.popen(f'curl {url}').read()\n"
            "```",
        )

        print(f"Execution ID: {result.workflow_id}")
        print(f"Status: {result.status}")
        result.print_result()


# ── Example 3: Use /dg as a tool on another agent ──────────────────

tech_lead = Agent(
    name="tech_lead",
    model=settings.secondary_llm_model,
    instructions=(
        "You are a tech lead. When asked to review code, use the dg code review tool. "
        "After getting the review results, summarize the key findings and prioritize them."
    ),
    tools=[agent_tool(dg, description="Run adversarial Dinesh vs Gilfoyle code review")],
)


def run_as_tool():
    """Use /dg as a tool invoked by a tech lead agent."""
    with AgentRuntime() as rt:
        print("=== Tech Lead using /dg as Tool ===\n")

        result = rt.run(
            tech_lead,
            "Please review the authentication module in our latest PR. "
            "The code adds JWT token validation."
        )

        print(f"Execution ID: {result.workflow_id}")
        print(f"Status: {result.status}")
        result.print_result()


if __name__ == "__main__":
    import sys

    examples = {
        "standalone": run_standalone,
        "pipeline": run_pipeline,
        "tool": run_as_tool,
    }

    choice = sys.argv[1] if len(sys.argv) > 1 else "standalone"
    if choice in examples:
        examples[choice]()
    else:
        print(f"Usage: python {sys.argv[0]} [{'/'.join(examples)}]")
