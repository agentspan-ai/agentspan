# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for agentspan.cli.deploy — the CLI entry point for agent deployment."""

import json
import sys
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agentspan.cli.deploy import main


def _make_agent(name):
    """Create a minimal agent-like object with a .name attribute."""
    return SimpleNamespace(name=name)


def _make_deployment_info(agent_name, workflow_name):
    """Create a minimal DeploymentInfo-like object."""
    return SimpleNamespace(agent_name=agent_name, workflow_name=workflow_name)


class TestDeployMain:
    """Tests for the deploy CLI main() function."""

    @patch("agentspan.cli.deploy.deploy")
    @patch("agentspan.agents.runtime.discovery.discover_agents")
    def test_all_agents_deploy_successfully(self, mock_discover, mock_deploy):
        """All discovered agents deploy successfully."""
        agents = [_make_agent("alpha"), _make_agent("beta")]
        mock_discover.return_value = agents
        mock_deploy.side_effect = [
            [_make_deployment_info("alpha", "wf_alpha")],
            [_make_deployment_info("beta", "wf_beta")],
        ]

        captured = StringIO()
        with patch("sys.argv", ["deploy", "--package", "myapp"]), \
             patch("sys.stdout", captured):
            main()

        result = json.loads(captured.getvalue())
        assert result == [
            {"agent_name": "alpha", "workflow_name": "wf_alpha", "success": True, "error": None},
            {"agent_name": "beta", "workflow_name": "wf_beta", "success": True, "error": None},
        ]
        mock_discover.assert_called_once_with(["myapp"])

    @patch("agentspan.cli.deploy.deploy")
    @patch("agentspan.agents.runtime.discovery.discover_agents")
    def test_agents_flag_filters_correctly(self, mock_discover, mock_deploy):
        """--agents flag filters to only the named agents."""
        agents = [_make_agent("alpha"), _make_agent("beta"), _make_agent("gamma")]
        mock_discover.return_value = agents
        mock_deploy.return_value = [_make_deployment_info("beta", "wf_beta")]

        captured = StringIO()
        with patch("sys.argv", ["deploy", "--package", "myapp", "--agents", "beta"]), \
             patch("sys.stdout", captured):
            main()

        result = json.loads(captured.getvalue())
        assert len(result) == 1
        assert result[0]["agent_name"] == "beta"
        assert result[0]["success"] is True

        # deploy should have been called only once (for beta)
        assert mock_deploy.call_count == 1

    @patch("agentspan.cli.deploy.deploy")
    @patch("agentspan.agents.runtime.discovery.discover_agents")
    def test_per_agent_failure_produces_mixed_results(self, mock_discover, mock_deploy):
        """One agent fails, others succeed: mixed results JSON."""
        agents = [_make_agent("ok_agent"), _make_agent("bad_agent"), _make_agent("ok2_agent")]
        mock_discover.return_value = agents

        mock_deploy.side_effect = [
            [_make_deployment_info("ok_agent", "wf_ok")],
            RuntimeError("server connection refused"),
            [_make_deployment_info("ok2_agent", "wf_ok2")],
        ]

        captured = StringIO()
        stderr_captured = StringIO()
        with patch("sys.argv", ["deploy", "--package", "myapp"]), \
             patch("sys.stdout", captured), \
             patch("sys.stderr", stderr_captured):
            main()

        result = json.loads(captured.getvalue())
        assert len(result) == 3

        assert result[0] == {
            "agent_name": "ok_agent",
            "workflow_name": "wf_ok",
            "success": True,
            "error": None,
        }
        assert result[1] == {
            "agent_name": "bad_agent",
            "workflow_name": None,
            "success": False,
            "error": "server connection refused",
        }
        assert result[2] == {
            "agent_name": "ok2_agent",
            "workflow_name": "wf_ok2",
            "success": True,
            "error": None,
        }

        # Error message should appear on stderr
        assert "bad_agent" in stderr_captured.getvalue()

    @patch("agentspan.agents.runtime.discovery.discover_agents")
    def test_discovery_failure_exits_with_code_1(self, mock_discover):
        """Discovery failure prints to stderr and exits with code 1."""
        mock_discover.side_effect = ImportError("no module 'bad_pkg'")

        stderr_captured = StringIO()
        with patch("sys.argv", ["deploy", "--package", "bad_pkg"]), \
             patch("sys.stderr", stderr_captured), \
             pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        assert "Discovery failed" in stderr_captured.getvalue()
