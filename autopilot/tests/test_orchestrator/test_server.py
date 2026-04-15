"""E2E tests for the server API client — hits the real server at localhost:6767.

All tests are marked ``@pytest.mark.network`` so they can be excluded from
fast local runs with ``-m "not network"``.
"""

from __future__ import annotations

import pytest

from autopilot.config import AutopilotConfig
from autopilot.orchestrator.server import (
    get_execution,
    get_running_agents,
    query_executions,
)

# All tests in this module require a running server.
pytestmark = pytest.mark.network

# Use default config (localhost:6767).
_CONFIG = AutopilotConfig()


class TestQueryExecutions:
    """Tests for query_executions against the real server."""

    def test_query_executions_returns_list(self):
        results = query_executions(config=_CONFIG)
        assert isinstance(results, list)
        # The server should have at least some executions recorded.
        # Even if zero, the shape must be a list.
        for item in results:
            assert isinstance(item, dict)
            assert "executionId" in item
            assert "agentName" in item
            assert "status" in item

    def test_query_executions_status_filter(self):
        results = query_executions(status="RUNNING", config=_CONFIG)
        assert isinstance(results, list)
        for item in results:
            assert item["status"] == "RUNNING", (
                f"Expected status RUNNING, got {item['status']} for {item['executionId']}"
            )

    def test_query_executions_agent_name_filter(self):
        # First, get any execution to find a valid agent name.
        all_results = query_executions(config=_CONFIG)
        if not all_results:
            pytest.skip("No executions found on server to test agent name filter")

        target_name = all_results[0]["agentName"]
        filtered = query_executions(agent_name=target_name, config=_CONFIG)
        assert isinstance(filtered, list)
        assert len(filtered) >= 1
        for item in filtered:
            assert item["agentName"] == target_name, (
                f"Expected agentName {target_name}, got {item['agentName']}"
            )

    def test_query_executions_invalid_status_returns_empty(self):
        """A status value that doesn't match any execution returns an empty list."""
        results = query_executions(status="NONEXISTENT_STATUS_XYZ", config=_CONFIG)
        assert isinstance(results, list)
        assert len(results) == 0


class TestGetRunningAgents:
    """Tests for the get_running_agents convenience wrapper."""

    def test_get_running_agents_returns_list(self):
        results = get_running_agents(config=_CONFIG)
        assert isinstance(results, list)
        for item in results:
            assert isinstance(item, dict)
            assert item["status"] == "RUNNING"

    def test_running_agents_have_required_fields(self):
        results = get_running_agents(config=_CONFIG)
        for item in results:
            assert "executionId" in item
            assert "agentName" in item
            assert "startTime" in item


class TestGetExecution:
    """Tests for get_execution — fetching a single execution by ID."""

    def test_get_execution_returns_details(self):
        all_results = query_executions(config=_CONFIG)
        if not all_results:
            pytest.skip("No executions found on server to test get_execution")

        eid = all_results[0]["executionId"]
        details = get_execution(eid, config=_CONFIG)
        assert isinstance(details, dict)
        assert details.get("executionId") == eid or "executionId" in details or "status" in details

    def test_get_execution_nonexistent_raises(self):
        """Requesting a nonexistent execution ID should raise an HTTP error."""
        import httpx
        with pytest.raises(httpx.HTTPStatusError):
            get_execution("00000000-0000-0000-0000-000000000000", config=_CONFIG)
