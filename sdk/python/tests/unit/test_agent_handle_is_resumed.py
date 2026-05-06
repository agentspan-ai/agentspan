# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.
"""Unit tests for AgentHandle.is_resumed flag."""

from agentspan.agents.result import AgentHandle


def test_is_resumed_default_false():
    h = AgentHandle(execution_id="exec-1", runtime=None)
    assert h.is_resumed is False


def test_is_resumed_can_be_set():
    h = AgentHandle(execution_id="exec-1", runtime=None, is_resumed=True)
    assert h.is_resumed is True


def test_stall_error_default_none():
    h = AgentHandle(execution_id="exec-1", runtime=None)
    assert h._stall_error is None
    assert h._liveness_monitor is None
