# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credentials — CLI tools with explicit credential declarations.

Demonstrates:
    - Explicit credentials on agents and tools
    - cli_allowed_commands defines which CLI tools the agent can use
    - credentials=[...] declares which secrets the server must inject
    - Multi-credential tools (aws needs multiple env vars)

Setup (one-time, via CLI):
    agentspan login
    agentspan credentials set GITHUB_TOKEN <your-github-token>
    agentspan credentials set AWS_ACCESS_KEY_ID <your-aws-access-key-id>
    agentspan credentials set AWS_SECRET_ACCESS_KEY <your-aws-secret-access-key>
Requirements:
    - Agentspan server running at AGENTSPAN_SERVER_URL
    - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-5.4)
    - gh and aws CLIs installed
"""

import os
import subprocess

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


# gh tool — requires GITHUB_TOKEN
@tool(credentials=["GITHUB_TOKEN"])
def gh_list_prs(repo: str, state: str = "open") -> dict:
    """List pull requests for a GitHub repo using the gh CLI.

    repo format: "owner/repo"
    state: "open", "closed", or "all"
    """
    result = subprocess.run(
        ["gh", "pr", "list", "--repo", repo, "--state", state,
         "--limit", "10", "--json", "number,title,author,createdAt,url"],
        capture_output=True, text=True, timeout=15,
        env={**os.environ, "GH_TOKEN": os.environ.get("GITHUB_TOKEN", "")},
    )
    if result.returncode != 0:
        return {"error": result.stderr.strip()}

    import json
    prs = json.loads(result.stdout)
    return {"repo": repo, "state": state, "pull_requests": prs}


@tool(credentials=["GITHUB_TOKEN"])
def gh_create_pr(repo: str, title: str, body: str, head: str, base: str = "main") -> dict:
    """Create a pull request via the gh CLI.

    head: source branch (e.g. "feature/my-feature")
    base: target branch (default: "main")
    """
    result = subprocess.run(
        ["gh", "pr", "create", "--repo", repo,
         "--title", title, "--body", body,
         "--head", head, "--base", base],
        capture_output=True, text=True, timeout=15,
        env={**os.environ, "GH_TOKEN": os.environ.get("GITHUB_TOKEN", "")},
    )
    if result.returncode != 0:
        return {"error": result.stderr.strip()}
    return {"url": result.stdout.strip()}


# aws tool — requires AWS credentials
@tool(credentials=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"])
def aws_list_s3_buckets() -> dict:
    """List S3 buckets accessible with the user's AWS credentials."""
    result = subprocess.run(
        ["aws", "s3", "ls", "--output", "json"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        return {"error": result.stderr.strip()}

    lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    buckets = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 3:
            buckets.append({"created": f"{parts[0]} {parts[1]}", "name": parts[2]})
    return {"buckets": buckets}


@tool(credentials=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"])
def aws_get_caller_identity() -> dict:
    """Return the AWS identity (account, ARN) for the current credentials."""
    result = subprocess.run(
        ["aws", "sts", "get-caller-identity", "--output", "json"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return {"error": result.stderr.strip()}

    import json
    return json.loads(result.stdout)


# Agent with explicit credentials for CLI tools
github_aws_agent = Agent(
    name="devops_agent",
    model=settings.llm_model,
    tools=[gh_list_prs, gh_create_pr, aws_list_s3_buckets, aws_get_caller_identity],
    cli_allowed_commands=["gh", "aws"],
    credentials=["GITHUB_TOKEN", "GH_TOKEN", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"],
    instructions=(
        "You are a DevOps assistant. You can manage GitHub pull requests and "
        "inspect AWS resources. Always confirm destructive actions before proceeding."
    ),
)


if __name__ == "__main__":
    import sys

    # Allow passing a task on the command line for quick testing
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "Who am I in AWS, and list my S3 buckets?"
    )

    with AgentRuntime() as runtime:
        result = runtime.run(github_aws_agent, task)
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(github_aws_agent)
        # CLI alternative:
        # agentspan deploy --package examples.16c_credentials_cli_tools
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(github_aws_agent)

