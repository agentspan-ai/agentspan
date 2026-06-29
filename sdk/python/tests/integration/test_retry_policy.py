# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""E2E test: verify retry_policy on @tool flows through to Conductor TaskDef.

Registers tools with different retry policies, then queries the Conductor
metadata API to confirm each TaskDef has the correct retryLogic, retryCount,
and retryDelaySeconds.

Requirements:
    - Agentspan server running
    - export AGENTSPAN_SERVER_URL=http://localhost:6767/api (or via env)
"""

import os

import pytest
import requests

from conductor.ai.agents import Agent, tool

pytestmark = pytest.mark.integration


_MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini")


@tool(retry_policy="fixed", retry_count=4, retry_delay_seconds=7)
def _retry_fixed_tool(x: str) -> str:
    """Tool with FIXED retry policy."""
    return x


@tool(retry_policy="exponential_backoff", retry_count=6, retry_delay_seconds=2)
def _retry_exponential_tool(x: str) -> str:
    """Tool with EXPONENTIAL_BACKOFF retry policy."""
    return x


@tool(retry_policy="linear_backoff", retry_count=1, retry_delay_seconds=10)
def _retry_linear_tool(x: str) -> str:
    """Tool with LINEAR_BACKOFF retry policy."""
    return x


@tool(retry_count=3, retry_delay_seconds=5)
def _retry_default_tool(x: str) -> str:
    """Tool with default retry policy (FIXED)."""
    return x


_AGENT = Agent(
    name="e2e_retry_policy_test",
    model=_MODEL,
    tools=[_retry_fixed_tool, _retry_exponential_tool, _retry_linear_tool, _retry_default_tool],
    instructions="Test agent for retry policy verification.",
)

_EXPECTED = {
    "_retry_fixed_tool": {"retryLogic": "FIXED", "retryCount": 4, "retryDelaySeconds": 7},
    "_retry_exponential_tool": {"retryLogic": "EXPONENTIAL_BACKOFF", "retryCount": 6, "retryDelaySeconds": 2},
    "_retry_linear_tool": {"retryLogic": "LINEAR_BACKOFF", "retryCount": 1, "retryDelaySeconds": 10},
    "_retry_default_tool": {"retryLogic": "LINEAR_BACKOFF", "retryCount": 3, "retryDelaySeconds": 5},
}


def _conductor_base() -> str:
    url = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
    return url.rstrip("/").replace("/api", "")


class TestRetryPolicyTaskDef:
    """Verify that @tool retry_policy propagates to the Conductor TaskDef."""

    @pytest.fixture(scope="class", autouse=True)
    def register_tools(self, runtime):
        """Register tool workers so TaskDefs are created on the server."""
        runtime._prepare_workers(_AGENT)
        import time
        time.sleep(2)

    @pytest.mark.parametrize("task_name,expected", list(_EXPECTED.items()))
    def test_taskdef_retry_config(self, task_name, expected):
        """TaskDef on server has the correct retryLogic, retryCount, retryDelaySeconds."""
        base = _conductor_base()
        resp = requests.get(f"{base}/api/metadata/taskdefs/{task_name}", timeout=10)
        assert resp.status_code == 200, f"TaskDef {task_name} not found on server"

        td = resp.json()
        for key, want in expected.items():
            got = td.get(key)
            assert got == want, (
                f"{task_name}.{key}: expected {want!r}, got {got!r}"
            )
