# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""GitHub Coding Agent (Chained) — conditional sequential pipeline.

Demonstrates:
    - Sequential pipeline with gate (conditional execution)
    - SWARM orchestration nested inside a pipeline stage
    - Clean separation of concerns: fetch -> code -> push
    - ``cli_commands`` for stages that only run CLI tools (stages 1 & 3)
    - ``local_code_execution`` for stages that write/run code (stage 2)

Architecture:
    pipeline = git_fetch_issues >> coding_qa >> git_push_pr

    git_fetch_issues --gate--> coding_qa (coder <-> qa_tester) --> git_push_pr

    Gate: if no open issues, pipeline stops after stage 1.
    Each stage receives the previous stage's output as its prompt.

Requirements:
    - Conductor server running
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - gh CLI authenticated (gh auth status)
    - GITHUB_TOKEN or GH_TOKEN set for API access
"""

import uuid

from agentspan.agents import Agent, AgentRuntime, Strategy
from agentspan.agents.gate import TextGate
from agentspan.agents.handoff import OnTextMention

REPO = "agentspan/codingexamples"
WORK_DIR = f"/tmp/codingexamples-{uuid.uuid4().hex[:8]}"
MODEL = "anthropic/claude-sonnet-4-20250514"

# -- Stage 1: Fetch issues -------------------------------------------------

git_fetch_issues = Agent(
    name="git_fetch_issues",
    model=MODEL,
    instructions=f"""\
You are a GitHub issue fetcher.  You fetch issues and if the issue is already fetched you respond with STOP.

1. List the 5 most recent open issues on {REPO} (include number, title, body).
2. If there are NO open issues, output exactly: NO_OPEN_ISSUES
3. Otherwise pick the most suitable issue, then:
   - Clone {REPO} into {WORK_DIR}
   - Create a branch named fix/issue-<NUMBER>
   - Output the issue summary, working directory, and branch name for the next stage.
""",
    cli_commands=True,
    cli_allowed_commands=["gh", "git", "mkdir", "ls"],
    max_turns=5,
    gate=TextGate("NO_OPEN_ISSUES"),
)

# -- Stage 2: Coding + QA (SWARM) ------------------------------------------

coder = Agent(
    name="coder",
    model=MODEL,
    max_tokens=60000,
    instructions=f"""\
You are a senior developer. You receive a task description with a working
directory and branch. Implement the fix/feature in {WORK_DIR}.
Note: For a new feature development, create a new folder - pick a name that resonates with the requirements
After making changes, say HANDOFF_TO_QA to request review.
""",
    local_code_execution=True,
)

qa_tester = Agent(
    name="qa_tester",
    model=MODEL,
    instructions=f"""\
You are a QA engineer. Review the code changes in {WORK_DIR}.

1. Read the modified files and check for correctness.
2. Run any existing tests: `cd {WORK_DIR} && python -m pytest` (if applicable).
3. If you find bugs, say HANDOFF_TO_CODER with a description of what to fix.
4. If everything looks good, say QA_APPROVED with a summary of what was tested.
""",
    local_code_execution=True,
    max_tokens=60000,
    max_turns=5
)

coding_qa = Agent(
    name="coding_qa",
    model=MODEL,
    instructions="Delegate to coder to start implementing the task. "
                 "Once the coder has completed the task, get QA to validate the changes. "
                 "If QA does not pass, then send it back to coder to fix"
                 "Note: For a new feature development, create a new folder - pick a name that resonates with the "
                 "requirements",
    agents=[coder, qa_tester],
    strategy=Strategy.SWARM,
    handoffs=[
        OnTextMention(text="HANDOFF_TO_QA", target="qa_tester"),
        OnTextMention(text="HANDOFF_TO_CODER", target="coder"),
    ],
    max_turns=200,
    max_tokens=60000,
    timeout_seconds=6000,
)

# -- Stage 3: Push + PR ----------------------------------------------------

git_push_pr = Agent(
    name="git_push_pr",
    model=MODEL,
    instructions=f"""\
You are a github worker who can commit and push code to github.  Nothing more.    
When commiting the changes, based on the current project, you know which files to be ignored.
1. Stage and commit all changes in {WORK_DIR} with a descriptive commit message.
2. Push the branch to origin.
3. Create a PR on {REPO} with a clear title and body summarising the changes.
4. Output the PR URL.
""",
    cli_commands=True,
    max_tokens=60000,
    cli_allowed_commands=["git", "gh", "ls"],
)

# -- Pipeline ---------------------------------------------------------------

pipeline = git_fetch_issues >> coding_qa >> git_push_pr

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(pipeline, "Pick an open issue and create a PR.", timeout=240000)
        result.print_result()
