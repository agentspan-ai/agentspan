"""Shared fixtures for autopilot tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from autopilot.registry import reset_default_registry


@pytest.fixture(autouse=True)
def _reset_registry():
    """Reset the global registry before each test for isolation."""
    reset_default_registry()
    yield
    reset_default_registry()


@pytest.fixture
def tmp_agent_dir(tmp_path: Path) -> Path:
    """Create a minimal agent directory with agent.yaml and workers/."""
    agent_dir = tmp_path / "test_agent"
    agent_dir.mkdir()
    workers_dir = agent_dir / "workers"
    workers_dir.mkdir()
    return agent_dir
