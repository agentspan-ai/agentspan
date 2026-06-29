# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Runtime package — execution lifecycle management."""

from conductor.ai.agents.runtime.config import AgentConfig
from conductor.ai.agents.runtime.runtime import AgentRuntime

__all__ = ["AgentRuntime", "AgentConfig"]
