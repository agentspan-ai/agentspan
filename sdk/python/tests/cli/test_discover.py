# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for agentspan.cli.discover — the CLI entry point for agent discovery."""

import json
import sys
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agentspan.cli.discover import main


def _make_agent(name):
    """Create a minimal agent-like object with a .name attribute."""
    return SimpleNamespace(name=name)


class TestDiscoverMain:
    """Tests for the discover CLI main() function."""

    @patch("agentspan.cli.discover.detect_framework")
    @patch("agentspan.agents.runtime.discovery.discover_agents")
    def test_normal_discovery_two_agents(self, mock_discover, mock_detect):
        """Two agents discovered, correct JSON output."""
        agents = [_make_agent("agent_a"), _make_agent("agent_b")]
        mock_discover.return_value = agents
        mock_detect.side_effect = [None, "langgraph"]

        captured = StringIO()
        with patch("sys.argv", ["discover", "--package", "myapp"]), \
             patch("sys.stdout", captured):
            main()

        result = json.loads(captured.getvalue())
        assert result == [
            {"name": "agent_a", "framework": "native"},
            {"name": "agent_b", "framework": "langgraph"},
        ]
        mock_discover.assert_called_once_with(["myapp"])

    @patch("agentspan.cli.discover.detect_framework")
    @patch("agentspan.agents.runtime.discovery.discover_agents")
    def test_none_framework_normalized_to_native(self, mock_discover, mock_detect):
        """detect_framework returning None is normalized to 'native'."""
        mock_discover.return_value = [_make_agent("bot")]
        mock_detect.return_value = None

        captured = StringIO()
        with patch("sys.argv", ["discover", "--package", "pkg"]), \
             patch("sys.stdout", captured):
            main()

        result = json.loads(captured.getvalue())
        assert result == [{"name": "bot", "framework": "native"}]

    @patch("agentspan.cli.discover.detect_framework")
    @patch("agentspan.agents.runtime.discovery.discover_agents")
    def test_framework_agent_shows_framework_string(self, mock_discover, mock_detect):
        """Framework agents show their framework string (e.g., 'langgraph')."""
        mock_discover.return_value = [_make_agent("lg_agent")]
        mock_detect.return_value = "langgraph"

        captured = StringIO()
        with patch("sys.argv", ["discover", "--package", "pkg"]), \
             patch("sys.stdout", captured):
            main()

        result = json.loads(captured.getvalue())
        assert result == [{"name": "lg_agent", "framework": "langgraph"}]

    @patch("agentspan.agents.runtime.discovery.discover_agents")
    def test_discovery_error_exits_with_code_1(self, mock_discover):
        """Discovery failure prints to stderr and exits with code 1."""
        mock_discover.side_effect = ImportError("no module named 'bad_pkg'")

        stderr_captured = StringIO()
        with patch("sys.argv", ["discover", "--package", "bad_pkg"]), \
             patch("sys.stderr", stderr_captured), \
             pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        assert "Discovery failed" in stderr_captured.getvalue()
