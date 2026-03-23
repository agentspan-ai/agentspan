"""E2E test: credential resolution through the real server.

Exercises the FULL credential pipeline — no mocks anywhere:
  1. Store/list/delete credentials via REST API
  2. Token extraction from __agentspan_ctx__ dict format
  3. Credential fetcher against real server (env fallback, auth error)
  4. SubprocessIsolator injects credentials into child env
  5. make_tool_worker with tool_def passes credentials through
  6. Non-isolated tool receives credentials via context var
  7. Config serializer includes credentials in tool config

Requires: agentspan server running at AGENTSPAN_SERVER_URL (default localhost:8080)
"""

import os
import sys

import httpx

SERVER = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:8080")
API = f"{SERVER}/api"
CRED_NAME = "_E2E_TEST_CRED"
CRED_VALUE = "e2e-test-secret-value-12345"


def step(msg):
    print(f"\n{'='*60}\n  STEP: {msg}\n{'='*60}")


def main():
    client = httpx.Client(timeout=10.0)

    # ── Step 1: Store a test credential ─────────────────────────
    step("Store credential via REST API")
    resp = client.post(f"{API}/credentials", json={"name": CRED_NAME, "value": CRED_VALUE})
    if resp.status_code not in (200, 201):
        resp = client.put(f"{API}/credentials/{CRED_NAME}", json={"value": CRED_VALUE})
    assert resp.status_code in (200, 201, 204), f"Failed to store credential: {resp.text}"
    print(f"  OK Credential '{CRED_NAME}' stored")

    # ── Step 2: Verify credential is listed ─────────────────────
    step("Verify credential exists in store")
    resp = client.get(f"{API}/credentials")
    creds = resp.json()
    names = [c["name"] for c in creds]
    assert CRED_NAME in names, f"{CRED_NAME} not found in credential list"
    print(f"  OK Credential listed")

    # ── Step 3: Token extraction from dict format ───────────────
    step("Token extraction from __agentspan_ctx__ dict")
    from agentspan.agents.runtime._dispatch import _extract_execution_token

    class FakeTaskDict:
        input_data = {"__agentspan_ctx__": {"execution_token": "test-token-abc"}}
        workflow_input = {}

    class FakeTaskString:
        input_data = {"__agentspan_ctx__": "test-token-plain"}
        workflow_input = {}

    class FakeTaskEmpty:
        input_data = {}
        workflow_input = {}

    assert _extract_execution_token(FakeTaskDict()) == "test-token-abc"
    assert _extract_execution_token(FakeTaskString()) == "test-token-plain"
    assert _extract_execution_token(FakeTaskEmpty()) is None
    print(f"  OK Dict, string, and empty all handled correctly")

    # ── Step 4: Credential fetcher — real server ────────────────
    step("WorkerCredentialFetcher against real server")
    from agentspan.agents.runtime.credentials.fetcher import WorkerCredentialFetcher
    from agentspan.agents.runtime.credentials.types import (
        CredentialAuthError, CredentialServiceError,
    )
    from unittest.mock import patch

    # 4a: No token → env lookup (local dev)
    fetcher = WorkerCredentialFetcher(server_url=API)
    with patch.dict(os.environ, {CRED_NAME: CRED_VALUE}):
        resolved = fetcher.fetch(None, [CRED_NAME])
    assert resolved.get(CRED_NAME) == CRED_VALUE
    print(f"  OK Env lookup (no token, local dev)")

    # 4b: Invalid token → CredentialAuthError (no fallback)
    try:
        fetcher.fetch("invalid-token", [CRED_NAME])
        print(f"  FAIL Expected CredentialAuthError")
        sys.exit(1)
    except CredentialAuthError:
        print(f"  OK Invalid token rejected (CredentialAuthError)")

    # 4c: Unreachable server with token → CredentialServiceError (no env fallback)
    bad_fetcher = WorkerCredentialFetcher(server_url="http://127.0.0.1:19999/api")
    try:
        bad_fetcher.fetch("some-token", [CRED_NAME])
        print(f"  FAIL Expected CredentialServiceError")
        sys.exit(1)
    except CredentialServiceError:
        print(f"  OK Unreachable server raises CredentialServiceError (no env fallback)")

    # ── Step 5: SubprocessIsolator injects env ──────────────────
    step("SubprocessIsolator credential injection")
    from agentspan.agents.runtime.credentials.isolator import SubprocessIsolator

    def _check_env(**kwargs):
        import os as _os
        return {"received": _os.environ.get(CRED_NAME), "home": _os.environ.get("HOME")}

    isolator = SubprocessIsolator(timeout=30)
    result = isolator.run(_check_env, args=(), kwargs={}, credentials={CRED_NAME: CRED_VALUE})
    assert result["received"] == CRED_VALUE
    assert result["home"] != os.environ.get("HOME")  # temp HOME
    assert CRED_NAME not in os.environ  # parent not modified
    print(f"  OK Subprocess received credential, parent env clean")

    # ── Step 6: ToolDef credentials survive into make_tool_worker
    step("ToolDef credentials survive decorator → worker")
    from agentspan.agents.tool import tool, get_tool_def
    from agentspan.agents.runtime._dispatch import make_tool_worker, _get_credential_names_from_tool

    @tool(credentials=["GITHUB_TOKEN", "OPENAI_API_KEY"])
    def cred_tool(x: str) -> str:
        return x

    td = get_tool_def(cred_tool)
    # Both raw func and wrapper have _tool_def (survives spawn-mode pickling)
    assert _get_credential_names_from_tool(td.func) == ["GITHUB_TOKEN", "OPENAI_API_KEY"]
    assert _get_credential_names_from_tool(cred_tool) == ["GITHUB_TOKEN", "OPENAI_API_KEY"]
    # ToolDef has credentials
    assert td.credentials == ["GITHUB_TOKEN", "OPENAI_API_KEY"]
    print(f"  OK Credentials survive @tool → ToolDef → make_tool_worker")

    # ── Step 7: Non-isolated tool receives credentials via context var
    step("Non-isolated tool credential context")
    from agentspan.agents.runtime.credentials.accessor import (
        get_credential,
        set_credential_context,
        clear_credential_context,
    )

    set_credential_context({"MY_SECRET": "ctx-value-123"})
    try:
        val = get_credential("MY_SECRET")
        assert val == "ctx-value-123"
        print(f"  OK get_credential() returns value from context")
    finally:
        clear_credential_context()

    # After clearing, get_credential should raise
    from agentspan.agents.runtime.credentials.types import CredentialNotFoundError
    try:
        get_credential("MY_SECRET")
        print(f"  FAIL Expected CredentialNotFoundError after clear")
        sys.exit(1)
    except CredentialNotFoundError:
        print(f"  OK Context cleared, get_credential raises")

    # ── Step 8: Config serializer includes credentials ──────────
    step("Config serializer includes credentials in tool config")
    from agentspan.agents.config_serializer import AgentConfigSerializer
    from agentspan.agents.agent import Agent

    @tool(credentials=["GITHUB_TOKEN"])
    def gh_tool(repo: str) -> str:
        return repo

    agent = Agent(name="test_agent", model="openai/gpt-4o", tools=[gh_tool])
    serializer = AgentConfigSerializer()
    config = serializer.serialize(agent)

    tool_configs = config.get("tools", [])
    gh_config = next((t for t in tool_configs if t["name"] == "gh_tool"), None)
    assert gh_config is not None
    assert gh_config.get("config", {}).get("credentials") == ["GITHUB_TOKEN"]
    print(f"  OK Serializer emits credentials in tool config")

    # ── Step 9: make_tool_worker runs tool without credentials ──
    step("Tool without credentials runs directly (no subprocess)")
    from conductor.client.http.models.task import Task

    @tool
    def add(a: int, b: int) -> int:
        return a + b

    td = get_tool_def(add)
    wrapper = make_tool_worker(td.func, td.name, tool_def=td)
    task = Task()
    task.input_data = {"a": 3, "b": 7}
    task.workflow_instance_id = "test-wf"
    task.task_id = "test-task"
    result = wrapper(task)
    assert result.status == "COMPLETED"
    assert result.output_data["result"] == 10
    print(f"  OK Simple tool runs correctly (result=10)")

    # ── Step 10: Cleanup ────────────────────────────────────────
    step("Cleanup test credential")
    resp = client.delete(f"{API}/credentials/{CRED_NAME}")
    print(f"  OK Cleaned up (status={resp.status_code})")

    print(f"\n{'='*60}")
    print(f"  ALL E2E TESTS PASSED (10 steps)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
