# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credentials — CLI tools with automatic credential mapping.

Demonstrates:
    - cli_allowed_commands auto-maps to credentials (gh → GITHUB_TOKEN, aws → AWS_*)
    - No need to declare credentials manually when using CLI tools
    - Multi-credential tools (aws needs 3 env vars)
    - terraform guard: raises ConfigurationError (not supported — use isolated tools)

CLI credential auto-mapping (built-in):
    gh          → GITHUB_TOKEN
    aws         → AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN
    gcloud      → GOOGLE_APPLICATION_CREDENTIALS (CredentialFile)
    docker      → DOCKER_USERNAME, DOCKER_PASSWORD
    kubectl     → KUBECONFIG (CredentialFile)
    az          → AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID
    npm         → NPM_TOKEN
    pip         → PIP_INDEX_URL
    databricks  → DATABRICKS_TOKEN, DATABRICKS_HOST
    snowflake   → SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD
    terraform   → ConfigurationError (use @tool with explicit credentials instead)

Setup (one-time, via CLI):
    agentspan login
    agentspan credentials set --name GITHUB_TOKEN
    agentspan credentials set --name AWS_ACCESS_KEY_ID
    agentspan credentials set --name AWS_SECRET_ACCESS_KEY

Requirements:
    - Agentspan server running at AGENTSPAN_SERVER_URL
    - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-5.4)
    - gh and aws CLIs installed
"""

import os
import subprocess

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


# gh is in cli_allowed_commands → GITHUB_TOKEN auto-injected in subprocess
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


# aws is in cli_allowed_commands → AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
# AWS_SESSION_TOKEN all auto-injected in subprocess
@tool(credentials=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])
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


@tool(credentials=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])
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


# Agent with cli_allowed_commands — credentials auto-mapped from CLI tool names
# gh → GITHUB_TOKEN, aws → AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY
github_aws_agent = Agent(
    name="devops_agent",
    model=settings.llm_model,
    tools=[gh_list_prs, gh_create_pr, aws_list_s3_buckets, aws_get_caller_identity],
    cli_allowed_commands=["gh", "aws"],  # auto-maps to credentials; no need to list them
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

