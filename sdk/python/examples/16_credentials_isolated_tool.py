# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credentials — per-user secrets injected into isolated tool subprocesses.

Demonstrates:
    - @tool with credentials=["GITHUB_TOKEN"] (default isolated=True)
    - Credentials injected into a fresh subprocess — parent env never touched
    - Tool reads credential from os.environ inside the subprocess
    - Fallback to os.environ when no server credential is set (non-strict mode)

How it works:
    1. Agent starts → server mints a short-lived execution token
    2. Before each tool call, the SDK fetches declared credentials from
       POST /api/credentials/resolve using that token
    3. The tool function runs in a fresh subprocess with credentials
       injected as env vars. The parent process's os.environ is unchanged.

Setup (one-time, via CLI):
    agentspan login                                     # authenticate
    agentspan credentials set GITHUB_TOKEN <your-github-token> # enter token when prompted

Requirements:
    - Agentspan server running at AGENTSPAN_SERVER_URL
    - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-5.4)
    - GITHUB_TOKEN stored via `agentspan credentials set` OR set in os.environ
"""

import os
import subprocess

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


@tool(credentials=["GITHUB_TOKEN"])
def list_github_repos(username: str) -> dict:
    """List public repositories for a GitHub user.

    The GITHUB_TOKEN env var is injected into this subprocess automatically.
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = ["Accept: application/vnd.github+json"]
    if token:
        headers.append(f"Authorization: Bearer {token}")

    result = subprocess.run(
        ["curl", "-sf", "-H", headers[0], "-H", headers[-1],
         f"https://api.github.com/users/{username}/repos?per_page=5&sort=updated"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return {"error": result.stderr.strip()}

    import json
    repos = json.loads(result.stdout)
    return {
        "username": username,
        "repos": [{"name": r["name"], "stars": r["stargazers_count"]} for r in repos],
        "authenticated": bool(token),
    }


@tool(credentials=["GITHUB_TOKEN"])
def create_github_issue(repo: str, title: str, body: str) -> dict:
    """Create a GitHub issue. Requires GITHUB_TOKEN with write access.

    repo format: "owner/repo-name"
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return {"error": "GITHUB_TOKEN not available — cannot create issues without auth"}

    import json
    payload = json.dumps({"title": title, "body": body})
    result = subprocess.run(
        ["curl", "-sf", "-X", "POST",
         "-H", "Accept: application/vnd.github+json",
         "-H", f"Authorization: Bearer {token}",
         "-H", "Content-Type: application/json",
         "-d", payload,
         f"https://api.github.com/repos/{repo}/issues"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return {"error": result.stderr.strip()}

    issue = json.loads(result.stdout)
    return {"issue_number": issue.get("number"), "url": issue.get("html_url")}


agent = Agent(
    name="github_agent",
    model=settings.llm_model,
    tools=[list_github_repos, create_github_issue],
    # Declare credentials at the agent level — SDK auto-fetches for all tools
    credentials=["GITHUB_TOKEN"],
    instructions=(
        "You are a GitHub assistant. You can list repos and create issues. "
        "Always confirm with the user before creating issues."
    ),
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            agent,
            "List the 5 most recently updated repos for the 'agentspan-ai' GitHub org.",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.16_credentials_isolated_tool
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

