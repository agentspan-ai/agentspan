# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""GitHub Coding Agent (simplified) — pick an issue, code the fix, create a PR.

Uses built-in code execution (local_code_execution=True) so the LLM
composes shell commands naturally — zero custom tool definitions.

Demonstrates:
    - Swarm orchestration with 3 specialist agents + team coordinator
    - Built-in code execution for git/gh CLI operations
    - End-to-end autonomous workflow: issue → code → test → PR

Architecture:
    coding_team (swarm coordinator)
        ├── github_agent — picks issues, clones repo, commits, pushes, creates PRs
        ├── coder — implements the fix in the cloned repo
        └── qa_tester — reviews code, runs tests, reports bugs or approval

    Flow:
        1. coding_team triages → transfers to github_agent
        2. github_agent picks issue, clones repo → transfers to coder
        3. coder implements → transfers to qa_tester
        4. qa_tester tests → if bugs: transfers to coder (loop)
                            → if pass: transfers to github_agent
        5. github_agent commits, pushes, creates PR → done

Requirements:
    - Conductor server running
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api in .env or environment
    - gh CLI authenticated (gh auth status)
    - Git configured with push access to the repo
"""

import uuid

from agentspan.agents import Agent, AgentRuntime, Strategy
from agentspan.agents.handoff import OnTextMention

REPO = "agentspan/codingexamples"
WORK_DIR = f"/tmp/codingexamples-{uuid.uuid4().hex[:8]}"

# ── GitHub Agent: handles all git/gh operations ──────────────────────

github_agent = Agent(
    name="github_agent",
    model="anthropic/claude-sonnet-4-20250514",
    instructions=(
        "You are a GitHub operations specialist. You handle all git and "
        "GitHub CLI interactions.\n\n"
        f"Repo: {REPO}\n"
        f"Work dir: {WORK_DIR}\n\n"
        "IMPORTANT: Read the conversation history carefully. If the "
        "conversation already contains messages from [coder] and "
        "[qa_tester] (especially 'ALL TESTS PASSED' or similar), then "
        "the code is already implemented and tested — you are in PHASE 2. "
        "Skip directly to step 6 below.\n\n"
        "PHASE 1 — SETUP (only if no [coder]/[qa_tester] messages exist):\n"
        f"1. List issues: gh issue list --repo {REPO} --state open "
        "--json number,title,body\n"
        "2. Pick the most suitable issue\n"
        f"3. Clone: gh repo clone {REPO} {WORK_DIR}\n"
        f"4. Branch: cd {WORK_DIR} && git checkout -b feature/issue-N-desc\n"
        "5. Call transfer_to_coder with the issue details.\n\n"
        "PHASE 2 — PR CREATION (conversation contains QA approval):\n"
        "6. Commit and push:\n"
        f"   cd {WORK_DIR} && git add -A && "
        "git commit -m 'Fix #N: description' && git push -u origin HEAD\n"
        f"7. Create PR: gh pr create --repo {REPO} --title 'Fix #N: title' "
        "--body 'Description of changes.\\n\\nCloses #N'\n"
        "8. Output the PR URL as your final response. Do NOT call any "
        "transfer tool — the workflow ends automatically."
    ),
    local_code_execution=True,
    thinking_budget_tokens=4096,
    max_tokens=16384,
)

# ── Coder: implements the fix ────────────────────────────────────────

coder = Agent(
    name="coder",
    model="anthropic/claude-sonnet-4-20250514",
    instructions=(
        "You are an expert developer. You write clean, well-structured code.\n\n"
        f"The repo is cloned at {WORK_DIR}.\n\n"
        "WHEN YOU RECEIVE A TASK:\n"
        f"1. Explore: find {WORK_DIR} -type f -not -path '*/.git/*'\n"
        "2. Write ALL files in a SINGLE bash execution using heredocs:\n"
        f"   cat > {WORK_DIR}/src/main.py << 'PYEOF'\n"
        "   ...code...\n"
        "   PYEOF\n"
        "3. Test your code to verify it works\n"
        "4. Call transfer_to_qa_tester for review\n\n"
        "IF QA REPORTS BUGS:\n"
        "5. Fix the issues\n"
        "6. Re-test\n"
        "7. Call transfer_to_qa_tester again\n\n"
        "IMPORTANT: You can ONLY use transfer_to_qa_tester. Do NOT call "
        "transfer_to_coding_team or transfer_to_github_agent.\n\n"
        "CRITICAL: Each tool call uses one turn. Minimize turns by "
        "combining multiple bash commands into a single execute_code call.\n\n"
        "Always include ALL necessary code in each execution — "
        "every code block runs in an isolated environment."
    ),
    local_code_execution=True,
    thinking_budget_tokens=4096,
    max_tokens=16384,
)

# ── QA Tester: reviews code and runs tests ───────────────────────────

qa_tester = Agent(
    name="qa_tester",
    model="anthropic/claude-sonnet-4-20250514",
    instructions=(
        "You are a meticulous QA engineer. Review the code written by the "
        "coder for correctness, edge cases, and bugs.\n\n"
        f"The repo is at {WORK_DIR}. You can read files with:\n"
        f"  cat {WORK_DIR}/src/main.py\n\n"
        "You can run any language to execute tests. Always include ALL "
        "necessary code (imports, function definitions) in each execution "
        "— every code block runs in an isolated environment.\n\n"
        "Test coverage should include: normal inputs, edge cases (empty "
        "input, zero, negative numbers, None), and boundary conditions.\n\n"
        "TRANSFER RULES (you MUST follow these exactly):\n"
        "  If you find bugs → call transfer_to_coder\n"
        "  If all tests pass → call transfer_to_github_agent\n"
        "  NEVER call transfer_to_coding_team (it will be rejected)\n"
    ),
    local_code_execution=True,
    thinking_budget_tokens=4096,
    max_tokens=16384,
)

# ── Coding Team: swarm coordinator ───────────────────────────────────

coding_team = Agent(
    name="coding_team",
    model="anthropic/claude-sonnet-4-20250514",
    instructions=(
        "You are a coding team coordinator. Delegate the incoming request "
        "to github_agent to get started — it will pick an issue and set "
        "up the repo. Call transfer_to_github_agent now."
    ),
    agents=[github_agent, coder, qa_tester],
    strategy=Strategy.SWARM,
    handoffs=[
        OnTextMention(text="transfer_to_github_agent", target="github_agent"),
        OnTextMention(text="transfer_to_coder", target="coder"),
        OnTextMention(text="transfer_to_qa_tester", target="qa_tester"),
    ],
    allowed_transitions={
        "coding_team": ["github_agent"],
        "github_agent": ["coder"],
        "coder": ["qa_tester"],
        "qa_tester": ["coder", "github_agent"],
    },
    max_turns=30,
    timeout_seconds=900,
)

# ── Run ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    prompt = (
        "Pick an open issue from the GitHub repository, implement the "
        "feature or fix the bug, get it reviewed by QA, and create a PR."
    )

    print("=" * 60)
    print("  GitHub Coding Agent (Simplified)")
    print(f"  Repo: {REPO}")
    print(f"  Work dir: {WORK_DIR}")
    print("  coding_team → github_agent ↔ coder ↔ qa_tester (swarm)")
    print("  Tools: built-in code execution (any language)")
    print("=" * 60)
    print(f"\nPrompt: {prompt}\n")


    with AgentRuntime() as runtime:
        result = runtime.run(coding_team, prompt)

        # Display output
        output = result.output
        skip_keys = {"finishReason", "rejectionReason", "is_transfer", "transfer_to"}
        if isinstance(output, dict):
            for key, text in output.items():
                if key in skip_keys or not text:
                    continue
                print(f"\n{'─' * 60}")
                print(f"  [{key}]")
                print(f"{'─' * 60}")
                print(text)
        else:
            print(output)

        print(f"\nFinish reason: {result.finish_reason}")
        print(f"Workflow ID: {result.execution_id}")

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(coding_team)
        # CLI alternative:
        # agentspan deploy --package examples.60a_github_coding_agent_simple
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(coding_team)

