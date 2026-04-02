# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Skills — Multi-agent workflows with skills as sub-agents.

Demonstrates:
    - Skills as sub-agents in router, sequential, and parallel teams
    - Mixing skill-based agents with regular @tool agents
    - Skills composed via agent_tool() on an orchestrator
    - Skills in a pipeline with >> operator
    - Full visibility: each skill sub-agent is a real Conductor SUB_WORKFLOW

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - /dg skill installed (https://github.com/v1r3n/dinesh-gilfoyle)
    - conductor skill installed (https://github.com/conductor-oss/conductor-skills)
"""

from agentspan.agents import (
    Agent,
    AgentRuntime,
    Strategy,
    agent_tool,
    skill,
    tool,
)
from settings import settings


# ── Load skills ────────────────────────────────────────────────────

dg = skill("~/.claude/skills/dg", model=settings.llm_model)
conductor_skill = skill(
    "~/.claude/skills/conductor",
    model=settings.secondary_llm_model,  # larger model for conductor (tool output can be big)
)


# ── Shared tools ───────────────────────────────────────────────────

@tool
def read_file(path: str) -> str:
    """Read a file from the filesystem."""
    try:
        with open(path) as f:
            return f.read()
    except Exception as e:
        return f"Error: {e}"


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    try:
        with open(path, "w") as f:
            f.write(content)
        return f"Written {len(content)} chars to {path}"
    except Exception as e:
        return f"Error: {e}"


# ══════════════════════════════════════════════════════════════════
# Example 1: Router — DevOps team routes to the right specialist
# ══════════════════════════════════════════════════════════════════

coder = Agent(
    name="coder",
    model=settings.llm_model,
    instructions=(
        "You are a senior developer. Write clean, production-ready code. "
        "Always include error handling and type hints."
    ),
    tools=[read_file, write_file],
)

devops_team = Agent(
    name="devops_team",
    model=settings.llm_model,
    agents=[dg, coder, conductor_skill],
    strategy=Strategy.ROUTER,
    router=Agent(
        name="router",
        model=settings.llm_model,
        instructions=(
            "Route tasks to the right specialist:\n"
            "- Code review, PR review, quality checks → dg (adversarial code review)\n"
            "- Writing code, fixing bugs, implementing features → coder\n"
            "- Workflow orchestration, Conductor management → conductor\n"
            "If a task needs multiple specialists, explain your routing plan."
        ),
    ),
)


def example_router():
    """Router dispatches to the right skill/agent based on the task."""
    with AgentRuntime() as rt:
        print("=== Example 1: Router Team ===\n")
        result = rt.run(
            devops_team,
            "Review this function for security issues:\n\n"
            "def login(username, password):\n"
            "    query = f\"SELECT * FROM users WHERE user='{username}' AND pass='{password}'\"\n"
            "    return db.execute(query)\n",
        )
        print(f"Workflow ID: {result.workflow_id}")
        print(f"Status:      {result.status}")
        print(f"Tokens:      {result.token_usage}")
        result.print_result()


# ══════════════════════════════════════════════════════════════════
# Example 2: Sequential Pipeline — Review → Fix → Deploy
# ══════════════════════════════════════════════════════════════════

fixer = Agent(
    name="fixer",
    model=settings.secondary_llm_model,
    instructions=(
        "You receive a code review with findings. For each critical and important "
        "finding, rewrite the code with the fix applied. Output the complete "
        "corrected code with inline comments explaining each fix."
    ),
)

deployer = Agent(
    name="deployer",
    model=settings.llm_model,
    instructions=(
        "You receive fixed code. Create a Conductor workflow definition that "
        "uses a SIMPLE task to run this code as a worker. Output the workflow "
        "JSON definition ready to be registered."
    ),
)

# Review → Fix → Deploy as workflow
review_fix_deploy = dg >> fixer >> deployer


def example_pipeline():
    """Sequential pipeline: skill → regular agent → regular agent."""
    with AgentRuntime() as rt:
        print("=== Example 2: Review → Fix → Deploy Pipeline ===\n")
        result = rt.run(
            review_fix_deploy,
            "Review, fix, and create a workflow for:\n\n"
            "def process_payment(amount, card_number):\n"
            "    log.info(f'Processing {card_number} for ${amount}')\n"
            "    if amount > 0:\n"
            "        return charge_card(card_number, amount)\n"
            "    return {'error': 'invalid amount'}\n",
        )
        print(f"Workflow ID: {result.workflow_id}")
        print(f"Status:      {result.status}")
        print(f"Tokens:      {result.token_usage}")
        if result.sub_results:
            print("\nSub-agent executions:")
            for sub in result.sub_results:
                print(f"  - {getattr(sub, 'workflow_id', '?')}: {sub.status}")
        result.print_result()


# ══════════════════════════════════════════════════════════════════
# Example 3: Parallel — Multiple reviewers simultaneously
# ══════════════════════════════════════════════════════════════════

security_reviewer = Agent(
    name="security_reviewer",
    model=settings.llm_model,
    instructions=(
        "You are a security specialist. Review code ONLY for security issues: "
        "injection attacks, credential exposure, auth gaps, OWASP Top 10. "
        "Ignore style, performance, and design concerns."
    ),
)

performance_reviewer = Agent(
    name="performance_reviewer",
    model=settings.llm_model,
    instructions=(
        "You are a performance specialist. Review code ONLY for performance: "
        "O(n²) algorithms, missing caching, N+1 queries, blocking calls, "
        "memory leaks. Ignore security, style, and design concerns."
    ),
)

parallel_review = Agent(
    name="parallel_review",
    model=settings.llm_model,
    agents=[dg, security_reviewer, performance_reviewer],
    strategy=Strategy.PARALLEL,
    instructions=(
        "Run all three reviewers in parallel on the same code. "
        "Aggregate their findings into a unified report, deduplicating "
        "any issues found by multiple reviewers."
    ),
)


def example_parallel():
    """Parallel: skill + regular agents review simultaneously."""
    with AgentRuntime() as rt:
        print("=== Example 3: Parallel Review ===\n")
        result = rt.run(
            parallel_review,
            "Review this API endpoint:\n\n"
            "from flask import request\n"
            "import subprocess\n\n"
            "@app.route('/run')\n"
            "def execute():\n"
            "    cmd = request.args.get('cmd')\n"
            "    output = subprocess.check_output(cmd, shell=True)\n"
            "    return output.decode()\n",
        )
        print(f"Workflow ID: {result.workflow_id}")
        print(f"Status:      {result.status}")
        print(f"Tokens:      {result.token_usage}")
        if result.sub_results:
            print("\nParallel sub-agent executions:")
            for sub in result.sub_results:
                print(f"  - {getattr(sub, 'workflow_id', '?')}: {sub.status}")
        result.print_result()


# ══════════════════════════════════════════════════════════════════
# Example 4: Skills as tools on an orchestrator
# ══════════════════════════════════════════════════════════════════

@tool
def run_tests(code: str) -> str:
    """Run unit tests on the provided code (simulated)."""
    if not code:
        return "ERROR: no code provided to test"
    if "SELECT *" in code and "f'" in code:
        return "FAIL: test_sql_injection detected SQL injection vulnerability"
    if "subprocess" in code and "shell=True" in code:
        return "FAIL: test_command_injection detected command injection"
    return "PASS: all tests passed"


tech_lead = Agent(
    name="tech_lead",
    model=settings.llm_model,
    instructions=(
        "You are a tech lead managing a code review and deployment pipeline.\n\n"
        "Your workflow:\n"
        "1. Run the code review using the dg tool (adversarial review)\n"
        "2. If critical issues found, stop and report them\n"
        "3. If code passes review, run tests using run_tests\n"
        "4. If tests pass, use conductor tool to create a deployment workflow\n"
        "5. Summarize the full pipeline result\n\n"
        "Always explain your decisions."
    ),
    tools=[
        agent_tool(dg, description="Run adversarial Dinesh vs Gilfoyle code review"),
        agent_tool(conductor_skill, description="Create and manage Conductor workflows"),
        run_tests,
    ],
)


def example_orchestrator():
    """Orchestrator uses skills as tools alongside regular tools."""
    with AgentRuntime() as rt:
        print("=== Example 4: Tech Lead Orchestrator ===\n")
        result = rt.run(
            tech_lead,
            "Review and deploy this worker function:\n\n"
            "def enrich_customer(task):\n"
            "    customer_id = task.input_data['customer_id']\n"
            "    profile = fetch_profile(customer_id)\n"
            "    enriched = {\n"
            "        'name': profile['name'],\n"
            "        'segment': classify_segment(profile),\n"
            "        'ltv': calculate_ltv(profile['orders']),\n"
            "    }\n"
            "    return {'status': 'COMPLETED', 'output': enriched}\n",
        )
        print(f"Workflow ID: {result.workflow_id}")
        print(f"Status:      {result.status}")
        print(f"Tokens:      {result.token_usage}")
        result.print_result()


# ══════════════════════════════════════════════════════════════════
# Example 5: Swarm — Agents hand off to each other
# ══════════════════════════════════════════════════════════════════

from agentspan.agents.handoff import OnTextMention

architect = Agent(
    name="architect",
    model=settings.secondary_llm_model,
    instructions=(
        "You are a software architect. Design the system architecture for "
        "the given requirements. When the design is ready, say HANDOFF_TO_DG "
        "for code review. If the review comes back with issues, redesign "
        "and say HANDOFF_TO_DG again."
    ),
)

swarm_team = Agent(
    name="design_review_loop",
    model=settings.llm_model,
    agents=[architect, dg],
    strategy=Strategy.SWARM,
    handoffs=[
        OnTextMention(text="HANDOFF_TO_DG", target="dg"),
        OnTextMention(text="HANDOFF_TO_ARCHITECT", target="architect"),
    ],
)


def example_swarm():
    """Swarm: architect and /dg skill hand off to each other."""
    with AgentRuntime() as rt:
        print("=== Example 5: Architect ↔ /dg Swarm ===\n")
        result = rt.run(
            swarm_team,
            "Design a rate limiter service that supports:\n"
            "- Fixed window and sliding window algorithms\n"
            "- Redis backend for distributed state\n"
            "- REST API for configuration\n"
            "- Middleware integration for Express.js",
        )
        print(f"Workflow ID: {result.workflow_id}")
        print(f"Status:      {result.status}")
        print(f"Tokens:      {result.token_usage}")
        result.print_result()


# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    examples = {
        "router": example_router,
        "pipeline": example_pipeline,
        "parallel": example_parallel,
        "orchestrator": example_orchestrator,
        "swarm": example_swarm,
    }

    choice = sys.argv[1] if len(sys.argv) > 1 else "router"
    if choice == "all":
        for name, fn in examples.items():
            print(f"\n{'='*60}")
            fn()
    elif choice in examples:
        examples[choice]()
    else:
        print(f"Usage: python {sys.argv[0]} [{'/'.join(examples)}/all]")
