#!/usr/bin/env python3
"""Run — trigger the deployed agent by name.

Requires: deploy.py has been run AND serve.py is running.

The agent is referenced by name, not by object. This decouples the
trigger from the definition — you can run this from anywhere.

CLI equivalent:
    agentspan run github_pipeline "Pick an open issue and create a PR."
"""

from agentspan.agents import AgentRuntime

AGENT_NAME = "git_fetch_issues_coding_qa_git_push_pr"  # Pipeline auto-name
PROMPT = "Pick an open issue from the repo and create a PR with the fix."

with AgentRuntime() as rt:
    result = rt.run(AGENT_NAME, PROMPT, timeout=240000)
    print(f"Status: {result.status}")
    result.print_result()
