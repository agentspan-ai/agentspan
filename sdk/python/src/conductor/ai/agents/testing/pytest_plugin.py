# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Pytest plugin — fixtures and markers for agent correctness testing.

Registered automatically via the ``pytest11`` entry point when
``agentspan`` is installed.
"""

from __future__ import annotations

import pytest

from conductor.ai.agents.testing.mock import MockEvent, mock_run


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "agent_correctness: marks tests as agent correctness tests",
    )
    config.addinivalue_line(
        "markers",
        "semantic: marks tests that use LLM judge for semantic assertions "
        "(requires litellm and API key)",
    )


@pytest.fixture
def mock_agent_run():
    """Fixture that returns the :func:`mock_run` callable."""
    return mock_run


@pytest.fixture
def event():
    """Fixture that returns the :class:`MockEvent` factory class."""
    return MockEvent
