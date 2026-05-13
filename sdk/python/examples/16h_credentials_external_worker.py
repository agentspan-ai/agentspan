# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credentials — External worker credential resolution.

Demonstrates:
    - @tool(external=True, credentials=["GITHUB_TOKEN"]) declares
      credentials for an external worker
    - The external worker uses resolve_credentials() to fetch
      credential values from the server at runtime
    - Works for workers running in separate processes, containers,
      or machines

This example shows two sides:
    1. Agent definition (declares the external tool with credentials)
    2. External worker (resolves credentials using the helper)

The external worker typically runs in a separate process. Here we
simulate both in one file for demonstration.

Setup (one-time):
    agentspan credentials set GITHUB_TOKEN <your-github-token>
Requirements:
    - Agentspan server running at AGENTSPAN_SERVER_URL
    - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-5.4)
    - GITHUB_TOKEN stored via `agentspan credentials set`
"""

from agentspan.agents import Agent, AgentRuntime, tool, resolve_credentials
from settings import settings


# ── Agent side: declare external tool with credentials ──────────

@tool(external=True, credentials=["GITHUB_TOKEN"])
def github_lookup(username: str) -> dict:
    """Look up a GitHub user's profile. Runs on an external worker."""
    ...  # stub — actual implementation is in the external worker below


agent = Agent(
    name="external_cred_agent",
    model=settings.llm_model,
    tools=[github_lookup],
    instructions="You can look up GitHub users. Use the github_lookup tool.",
)


# ── External worker side: resolve credentials at runtime ────────
# In production, this would run in a separate process.

def run_external_worker():
    """Simulate an external worker that resolves credentials."""
    from conductor.client.worker.worker_task import worker_task
    from conductor.client.http.models.task import Task
    from conductor.client.http.models.task_result import TaskResult
    from conductor.client.http.models.task_result_status import TaskResultStatus
    import requests

    @worker_task(task_definition_name="github_lookup")
    def github_lookup_worker(task: Task) -> TaskResult:
        username = task.input_data.get("username", "")

        # resolve_credentials reads __agentspan_ctx__ from task input
        # and calls the server to get the credential values
        creds = resolve_credentials(task.input_data, ["GITHUB_TOKEN"])
        token = creds.get("GITHUB_TOKEN", "")

        headers = {"Authorization": f"Bearer {token}"} if token else {}
        resp = requests.get(
            f"https://api.github.com/users/{username}",
            headers=headers, timeout=10,
        )

        if resp.ok:
            user = resp.json()
            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=task.workflow_instance_id,
                status=TaskResultStatus.COMPLETED,
                output_data={
                    "name": user.get("name"),
                    "login": user.get("login"),
                    "public_repos": user.get("public_repos"),
                    "followers": user.get("followers"),
                },
            )
        else:
            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=task.workflow_instance_id,
                status=TaskResultStatus.FAILED,
                reason_for_incompletion=f"GitHub API error: {resp.status_code}",
            )


if __name__ == "__main__":
    print("Note: This example demonstrates the pattern for external workers.")
    print("The external worker (run_external_worker) would run in a separate process.")
    print()
    print("To run end-to-end:")
    print("  1. Start the external worker in one terminal")
    print("  2. Run the agent in another terminal")
    print()
    print("Agent definition:")
    print(f"  tools: {[t._tool_def.name for t in agent.tools]}")
    print(f"  credentials: {agent.tools[0]._tool_def.credentials}")
    print()
    print("External worker pattern:")
    print("  creds = resolve_credentials(task.input_data, ['GITHUB_TOKEN'])")
    print("  token = creds['GITHUB_TOKEN']")
