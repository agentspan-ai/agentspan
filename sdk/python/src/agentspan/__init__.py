# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

# OpenAI Agents SDK compatibility — ``from agentspan import Runner``
from agentspan.agents.openai_compat import RunResult, Runner
from agentspan.agents.tool import tool as function_tool

__all__ = ["Runner", "RunResult", "function_tool"]

