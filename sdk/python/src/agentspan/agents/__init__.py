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
from agentspan.agents.agent import (
    Agent,
    AgentDef,
    ConfigurationError,
    PromptTemplate,
    Strategy,
    agent,
    scatter_gather,
)

# Claude Code configuration
from agentspan.agents.claude_code import ClaudeCode

# Callback handlers
from agentspan.agents.callback import CallbackHandler
from agentspan.agents.cli_config import CliConfig

# Code execution
from agentspan.agents.code_execution_config import CodeExecutionConfig
from agentspan.agents.code_executor import (
    CodeExecutor,
    DockerCodeExecutor,
    ExecutionResult,
    JupyterCodeExecutor,
    LocalCodeExecutor,
    ServerlessCodeExecutor,
)

# Exceptions
from agentspan.agents.exceptions import AgentAPIError, AgentNotFoundError, AgentspanError

# Extended agent types
from agentspan.agents.ext import GPTAssistantAgent, UserProxyAgent

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

# Handoff conditions (for swarm strategy)
from agentspan.agents.handoff import HandoffCondition, OnCondition, OnTextMention, OnToolResult

# Memory
from agentspan.agents.memory import ConversationMemory

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

# Credential management
from agentspan.agents.runtime.credentials.accessor import get_credential
from agentspan.agents.runtime.credentials.types import (
    CredentialAuthError,
    CredentialFile,
    CredentialNotFoundError,
    CredentialRateLimitError,
    CredentialServiceError,
)


def resolve_credentials(input_data: dict, names: list) -> dict:
    """Resolve credentials from Conductor task input data.

    For external workers that need to resolve credentials from the
    agentspan credential store. Extracts the execution token from
    ``__agentspan_ctx__`` in the task input and calls the server.

    Args:
        input_data: The Conductor task's ``input_data`` dict.
        names: Credential names to resolve.

    Returns:
        Dict mapping credential name to resolved plaintext value.
    """
    from agentspan.agents.runtime.credentials.fetcher import WorkerCredentialFetcher
    from agentspan.agents.runtime.config import AgentConfig

    token = None
    ctx = input_data.get("__agentspan_ctx__")
    if isinstance(ctx, dict):
        token = ctx.get("execution_token")
    elif isinstance(ctx, str):
        token = ctx

    config = AgentConfig.from_env()
    fetcher = WorkerCredentialFetcher(server_url=config.server_url)
    return fetcher.fetch(token, names)


# Agent discovery
from agentspan.agents.runtime.discovery import discover_agents

# MCP discovery utilities
from agentspan.agents.runtime.mcp_discovery import clear_discovery_cache
from agentspan.agents.runtime.runtime import AgentRuntime
from agentspan.agents.semantic_memory import MemoryEntry, MemoryStore, SemanticMemory

# Termination conditions
from agentspan.agents.termination import (
    MaxMessageTermination,
    StopMessageTermination,
    TerminationCondition,
    TerminationResult,
    TextMentionTermination,
    TokenUsageTermination,
)

# Tool decorator and constructors
from agentspan.agents.tool import (
    ToolContext,
    ToolDef,
    agent_tool,
    api_tool,
    audio_tool,
    http_tool,
    human_tool,
    image_tool,
    index_tool,
    mcp_tool,
    pdf_tool,
    search_tool,
    tool,
    video_tool,
)

# Tracing (optional — only activates if opentelemetry is installed)
from agentspan.agents.tracing import is_tracing_enabled

__all__ = [
    # Core
    "Agent",
    "AgentDef",
    "ClaudeCode",
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
    "api_tool",
    "http_tool",
    "human_tool",
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
    # Credentials
    "get_credential",
    "resolve_credentials",
    "CredentialFile",
    "CredentialNotFoundError",
    "CredentialAuthError",
    "CredentialRateLimitError",
    "CredentialServiceError",
    # Configuration errors
    "ConfigurationError",
]
