# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Skills — Load conductor skill for workflow management.

Demonstrates:
    - Loading a skill with scripts (conductor_api.py) as auto-wrapped tools
    - Progressive disclosure: reference docs loaded on demand via read_skill_file
    - Each conductor_api call is a visible SIMPLE task in the Conductor DAG
    - Composing the conductor skill with /dg in a multi-agent team

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - conductor-skills installed (https://github.com/conductor-oss/conductor-skills)

Install conductor-skills:
    git clone https://github.com/conductor-oss/conductor-skills ~/.claude/skills/conductor-skills
    # The skill is at ~/.claude/skills/conductor/
"""

from agentspan.agents import Agent, AgentRuntime, agent_tool, load_skills, skill
from settings import settings

# ── Load conductor skill ───────────────────────────────────────────
# Convention-based discovery:
#   - SKILL.md → orchestrator instructions (workflow management commands)
#   - scripts/conductor_api.py → auto-wrapped as "conductor_api" worker tool
#   - references/*.md → available via read_skill_file (progressive disclosure)
#   - examples/*.md → available via read_skill_file

conductor_skill = skill(
    "~/.claude/skills/conductor",
    model=settings.llm_model,
)

# ── Example 1: Run conductor skill standalone ──────────────────────

def run_standalone():
    """Use conductor skill to create and manage a workflow."""
    with AgentRuntime() as rt:
        print("=== Conductor Skill — Workflow Management ===\n")

        result = rt.run(
            conductor_skill,
            "Create a simple HTTP workflow that fetches https://httpbin.org/get, "
            "then transforms the response with a JSON_JQ_TRANSFORM to extract the origin IP. "
            "Start the workflow and show me the result.",
        )

        print(f"Execution ID: {result.workflow_id}")
        print(f"Status: {result.status}")
        print(f"Tokens: {result.token_usage}")
        result.print_result()


# ── Example 2: Load all skills from a directory ────────────────────

def run_with_load_skills():
    """Load all skills at once and use them."""
    skills = load_skills(
        "~/.claude/skills/",
        model=settings.llm_model,
    )

    print(f"Loaded {len(skills)} skills: {list(skills.keys())}\n")

    # Use the conductor skill
    if "conductor" in skills:
        with AgentRuntime() as rt:
            result = rt.run(skills["conductor"], "List all workflow definitions")
            print(f"Execution ID: {result.workflow_id}")
            print(f"Status: {result.status}")
            result.print_result()


# ── Example 3: Multi-skill team — /dg + conductor ─────────────────

def run_multi_skill_team():
    """Combine /dg and conductor skills in a router-based team."""

    dg = skill("~/.claude/skills/dg", model=settings.secondary_llm_model)

    team = Agent(
        name="devops_team",
        model=settings.llm_model,
        instructions=(
            "You are a DevOps team lead. Route tasks to the right specialist:\n"
            "- Code review requests → use the dg agent (adversarial code review)\n"
            "- Workflow/orchestration tasks → use the conductor agent\n"
            "- For tasks that need both, run review first then deploy"
        ),
        tools=[
            agent_tool(dg, description="Run adversarial code review with Dinesh vs Gilfoyle"),
            agent_tool(conductor_skill, description="Create, run, and manage Conductor workflows"),
        ],
    )

    with AgentRuntime() as rt:
        print("=== DevOps Team — /dg + Conductor ===\n")

        result = rt.run(
            team,
            "Review this workflow worker code, then create a Conductor workflow "
            "that uses it:\n\n```python\n"
            "def process_order(task):\n"
            "    order = task.input_data.get('order')\n"
            "    total = sum(item['price'] for item in order['items'])\n"
            "    if total > 10000:\n"
            "        return {'status': 'REQUIRES_APPROVAL', 'total': total}\n"
            "    return {'status': 'APPROVED', 'total': total}\n"
            "```",
        )

        print(f"Execution ID: {result.workflow_id}")
        print(f"Status: {result.status}")

        # Show sub-agent executions
        if result.sub_results:
            print(f"\nSub-agent executions:")
            for sub in result.sub_results:
                print(f"  - {sub.agent_name}: {sub.status} "
                      f"(tokens: {sub.token_usage})")

        result.print_result()


if __name__ == "__main__":
    import sys

    examples = {
        "standalone": run_standalone,
        "load_skills": run_with_load_skills,
        "team": run_multi_skill_team,
    }

    choice = sys.argv[1] if len(sys.argv) > 1 else "standalone"
    if choice in examples:
        examples[choice]()
    else:
        print(f"Usage: python {sys.argv[0]} [{'/'.join(examples)}]")
