"""Unit tests for liveness config fields."""

import os

from agentspan.agents.runtime.config import AgentConfig


def test_liveness_defaults_present():
    cfg = AgentConfig()
    assert cfg.liveness_enabled is True
    assert cfg.liveness_startup_timeout_seconds == 2.0
    assert cfg.liveness_stall_seconds == 30.0
    assert cfg.liveness_check_interval_seconds == 10.0
    assert cfg.liveness_stall_policy == "restart_worker"
    assert cfg.liveness_stall_max_restarts == 1


def test_liveness_from_env_overrides(monkeypatch):
    monkeypatch.setenv("AGENTSPAN_LIVENESS_ENABLED", "false")
    monkeypatch.setenv("AGENTSPAN_LIVENESS_STARTUP_TIMEOUT", "0.5")
    monkeypatch.setenv("AGENTSPAN_LIVENESS_STALL_SECONDS", "5")
    monkeypatch.setenv("AGENTSPAN_LIVENESS_CHECK_INTERVAL", "2")
    monkeypatch.setenv("AGENTSPAN_LIVENESS_STALL_POLICY", "raise")
    monkeypatch.setenv("AGENTSPAN_LIVENESS_STALL_MAX_RESTARTS", "3")
    cfg = AgentConfig.from_env()
    assert cfg.liveness_enabled is False
    assert cfg.liveness_startup_timeout_seconds == 0.5
    assert cfg.liveness_stall_seconds == 5.0
    assert cfg.liveness_check_interval_seconds == 2.0
    assert cfg.liveness_stall_policy == "raise"
    assert cfg.liveness_stall_max_restarts == 3


def test_liveness_invalid_policy_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("AGENTSPAN_LIVENESS_STALL_POLICY", "wat")
    cfg = AgentConfig.from_env()
    assert cfg.liveness_stall_policy == "restart_worker"
