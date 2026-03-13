# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Shared fixtures for integration tests.

Provides a module-scoped AgentRuntime and a configurable LLM model.

SSE streaming is enabled by default. Disable explicitly with
``AGENTSPAN_STREAMING_ENABLED=false`` if the server does not support SSE.
"""

import os

import pytest

from agentspan.agents import AgentRuntime
from agentspan.agents.runtime.config import AgentConfig

DEFAULT_MODEL = os.environ.get("AGENT_LLM_MODEL", "openai/gpt-4o-mini")


@pytest.fixture(scope="module")
def runtime():
    """Module-scoped AgentRuntime — shared across all tests in a module.

    SSE streaming is enabled by default. Set AGENTSPAN_STREAMING_ENABLED=false
    to disable it explicitly.
    """
    config = AgentConfig()
    with AgentRuntime(config=config) as rt:
        yield rt


@pytest.fixture
def model():
    """LLM model string, overridable via AGENT_LLM_MODEL env var."""
    return DEFAULT_MODEL
