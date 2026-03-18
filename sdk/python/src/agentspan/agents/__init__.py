# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Conductor Agents SDK — durable, scalable, observable AI agents.

This is the public API surface.  Import everything you need from here::

    from agentspan.agents import Agent, AgentRuntime, tool

Quick start::

    from agentspan.agents import Agent, AgentRuntime, tool

    @tool
    def get_weather(city: str) -> str:
        \"\"\"Get current weather for a city.\"\"\"
        return f"72F and sunny in {city}"

    agent = Agent(name="weatherbot", model="openai/gpt-4o", tools=[get_weather])

    with AgentRuntime() as runtime:
        result = runtime.run(agent, "What's the weather in NYC?")
        print(result.output)
"""

# Core primitive
from agentspan.agents.agent import Agent, AgentDef, PromptTemplate, Strategy, agent, scatter_gather

# Tool decorator and constructors
from agentspan.agents.tool import (
    ToolContext,
    ToolDef,
    agent_tool,
    audio_tool,
    http_tool,
    image_tool,
    index_tool,
    mcp_tool,
    pdf_tool,
    search_tool,
    tool,
    video_tool,
)

# MCP discovery utilities
from agentspan.agents.runtime.mcp_discovery import clear_discovery_cache

# Execution API
from agentspan.agents.run import (
    configure,
    deploy,
    deploy_async,
    plan,
    run,
    run_async,
    serve,
    shutdown,
    start,
    start_async,
    stream,
    stream_async,
)

# Runtime (for context manager and advanced usage)
from agentspan.agents.runtime.config import AgentConfig
from agentspan.agents.runtime.runtime import AgentRuntime

# Result types
from agentspan.agents.result import (
    AgentEvent,
    AgentHandle,
    AgentResult,
    AgentStatus,
    AgentStream,
    AsyncAgentStream,
    DeploymentInfo,
    EventType,
    FinishReason,
    Status,
    TokenUsage,
)

# Agent discovery
from agentspan.agents.runtime.discovery import discover_agents

# Guardrails
from agentspan.agents.guardrail import (
    Guardrail,
    GuardrailDef,
    GuardrailResult,
    LLMGuardrail,
    OnFail,
    Position,
    RegexGuardrail,
    guardrail,
)

# Termination conditions
from agentspan.agents.termination import (
    MaxMessageTermination,
    StopMessageTermination,
    TerminationCondition,
    TerminationResult,
    TextMentionTermination,
    TokenUsageTermination,
)

# Memory
from agentspan.agents.memory import ConversationMemory
from agentspan.agents.semantic_memory import MemoryEntry, MemoryStore, SemanticMemory

# Code execution
from agentspan.agents.code_execution_config import CodeExecutionConfig
from agentspan.agents.cli_config import CliConfig
from agentspan.agents.code_executor import (
    CodeExecutor,
    DockerCodeExecutor,
    ExecutionResult,
    JupyterCodeExecutor,
    LocalCodeExecutor,
    ServerlessCodeExecutor,
)

# Callback handlers
from agentspan.agents.callback import CallbackHandler

# Handoff conditions (for swarm strategy)
from agentspan.agents.handoff import HandoffCondition, OnCondition, OnTextMention, OnToolResult

# Extended agent types
from agentspan.agents.ext import GPTAssistantAgent, UserProxyAgent

# Exceptions
from agentspan.agents.exceptions import AgentAPIError, AgentNotFoundError, AgentspanError

# Tracing (optional — only activates if opentelemetry is installed)
from agentspan.agents.tracing import is_tracing_enabled

__all__ = [
    # Core
    "Agent",
    "AgentDef",
    "PromptTemplate",
    "Strategy",
    "agent",
    "scatter_gather",
    "AgentRuntime",
    "AgentConfig",
    # Extended agent types
    "UserProxyAgent",
    "GPTAssistantAgent",
    # Tools
    "tool",
    "ToolDef",
    "ToolContext",
    "agent_tool",
    "http_tool",
    "mcp_tool",
    "image_tool",
    "audio_tool",
    "video_tool",
    "pdf_tool",
    "index_tool",
    "search_tool",
    "clear_discovery_cache",
    # Convenience execution (uses a singleton AgentRuntime)
    "configure",
    "deploy",
    "deploy_async",
    "plan",
    "run",
    "run_async",
    "serve",
    "shutdown",
    "start",
    "start_async",
    "stream",
    "stream_async",
    # Results
    "AgentResult",
    "DeploymentInfo",
    "AgentHandle",
    "AgentStatus",
    "AgentStream",
    "AsyncAgentStream",
    "AgentEvent",
    "EventType",
    "FinishReason",
    "Status",
    "TokenUsage",
    # Guardrails
    "guardrail",
    "Guardrail",
    "GuardrailDef",
    "GuardrailResult",
    "OnFail",
    "Position",
    "RegexGuardrail",
    "LLMGuardrail",
    # Termination conditions
    "TerminationCondition",
    "TerminationResult",
    "TextMentionTermination",
    "StopMessageTermination",
    "MaxMessageTermination",
    "TokenUsageTermination",
    # Memory
    "ConversationMemory",
    "SemanticMemory",
    "MemoryStore",
    "MemoryEntry",
    # Code execution
    "CodeExecutionConfig",
    "CliConfig",
    "CodeExecutor",
    "LocalCodeExecutor",
    "DockerCodeExecutor",
    "JupyterCodeExecutor",
    "ServerlessCodeExecutor",
    "ExecutionResult",
    # Callback handlers
    "CallbackHandler",
    # Handoff conditions
    "HandoffCondition",
    "OnToolResult",
    "OnTextMention",
    "OnCondition",
    # Exceptions
    "AgentspanError",
    "AgentAPIError",
    "AgentNotFoundError",
    # Agent discovery
    "discover_agents",
    # Tracing
    "is_tracing_enabled",
]
