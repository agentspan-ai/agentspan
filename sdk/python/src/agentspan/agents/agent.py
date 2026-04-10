# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Agent — the single orchestration primitive for Conductor Agents.

Everything is an Agent. A single agent wraps an LLM + tools.
An agent with sub-agents IS a multi-agent system. The Agent class
handles both simple and complex orchestration patterns.
"""

from __future__ import annotations

import functools
import re
import warnings
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from agentspan.agents.claude_code import ClaudeCode

_VALID_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]*$")


class ConfigurationError(ValueError):
    """Raised at agent definition time for invalid configuration.

    Example: using ``terraform`` in ``cli_allowed_commands`` without providing
    an explicit ``credentials=[...]`` list.
    """


class Strategy(str, Enum):
    """How sub-agents are orchestrated."""

    HANDOFF = "handoff"
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    ROUTER = "router"
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    SWARM = "swarm"
    MANUAL = "manual"


@dataclass(frozen=True)
class PromptTemplate:
    """Reference to a named prompt template stored on the Conductor server.

    The SDK does not create templates — they are managed via the Conductor UI,
    API, or ``prompt_client.save_prompt()`` outside of agent code.  This class
    simply says *"use this named template"*.

    Args:
        name: Name of an existing prompt template on the server.
        variables: Substitution variables for ``${var}`` placeholders.
            Values may include Conductor expressions like
            ``"${workflow.input.user_tier}"`` for runtime dynamism.
        version: Template version to use.  ``None`` means latest.
    """

    name: str
    variables: Dict[str, Any] = field(default_factory=dict)
    version: Optional[int] = None


# ── AgentDef (attached by @agent decorator) ─────────────────────────────


@dataclass
class AgentDef:
    """Resolved agent definition (parallel to ToolDef, GuardrailDef).

    Attached to ``@agent``-decorated functions as ``_agent_def``.

    Attributes:
        name: Agent name (becomes the Conductor workflow name).
        model: LLM model in ``"provider/model"`` format.  Empty string
            means "inherit from parent agent at resolution time".
        instructions: System prompt — a string or the decorated callable.
        tools: List of tools for the agent.
        guardrails: List of guardrails for the agent.
        agents: Sub-agents for multi-agent orchestration.
        strategy: Multi-agent strategy.
        max_turns: Maximum agent loop iterations.
        max_tokens: Maximum tokens for LLM generation.
        temperature: Sampling temperature.
        metadata: Arbitrary metadata.
        func: The original decorated function.
    """

    name: str
    model: Union[str, Any] = ""
    instructions: Any = ""
    tools: List[Any] = field(default_factory=list)
    guardrails: List[Any] = field(default_factory=list)
    agents: List[Any] = field(default_factory=list)
    strategy: Union[str, Strategy] = Strategy.HANDOFF
    max_turns: int = 25
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    func: Optional[Callable[..., Any]] = field(default=None, repr=False)
    local_code_execution: bool = False
    allowed_languages: List[str] = field(default_factory=list)
    allowed_commands: List[str] = field(default_factory=list)
    code_execution: Optional[Any] = None
    cli_commands: bool = False
    cli_config: Optional[Any] = None
    cli_allowed_commands: List[str] = field(default_factory=list)
    credentials: List[Any] = field(default_factory=list)


# ── @agent decorator ────────────────────────────────────────────────────


def agent(
    func: Optional[Callable[..., Any]] = None,
    *,
    name: Optional[str] = None,
    model: Union[str, Any] = "",
    tools: Optional[List[Any]] = None,
    guardrails: Optional[List[Any]] = None,
    agents: Optional[List[Any]] = None,
    strategy: Union[str, Strategy] = Strategy.HANDOFF,
    max_turns: int = 25,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
    local_code_execution: bool = False,
    allowed_languages: Optional[List[str]] = None,
    allowed_commands: Optional[List[str]] = None,
    code_execution: Optional[Any] = None,
    cli_commands: bool = False,
    cli_config: Optional[Any] = None,
    cli_allowed_commands: Optional[List[str]] = None,
    credentials: Optional[List[Any]] = None,
) -> Any:
    """Register a Python function as an agent definition.

    Can be used bare (``@agent``) or with arguments
    (``@agent(model="openai/gpt-4o", tools=[search])``).

    The decorated function retains its original signature and can still be
    called directly.  A ``_agent_def`` attribute is attached containing the
    resolved :class:`AgentDef`.

    The function's **docstring** becomes the agent's instructions.  If the
    function body **returns a string**, it acts as callable instructions
    (dynamic instructions evaluated at compile time).

    When ``model`` is omitted (empty string), the agent inherits the
    parent's model at resolution time via :func:`_resolve_agent`.

    Examples::

        @agent(model="openai/gpt-4o", tools=[get_weather])
        def weatherbot():
            \"\"\"You are a weather assistant.\"\"\"

        @agent  # inherits model from parent
        def summarizer():
            \"\"\"Summarize the research findings.\"\"\"
    """

    def _wrap(fn: Callable[..., Any]) -> Any:
        agent_name = name or fn.__name__

        ad = AgentDef(
            name=agent_name,
            model=model,
            instructions=fn,
            tools=list(tools) if tools else [],
            guardrails=list(guardrails) if guardrails else [],
            agents=list(agents) if agents else [],
            strategy=strategy,
            max_turns=max_turns,
            max_tokens=max_tokens,
            temperature=temperature,
            metadata=dict(metadata) if metadata else {},
            func=fn,
            local_code_execution=local_code_execution,
            allowed_languages=list(allowed_languages) if allowed_languages else [],
            allowed_commands=list(allowed_commands) if allowed_commands else [],
            code_execution=code_execution,
            cli_commands=cli_commands,
            cli_config=cli_config,
            cli_allowed_commands=list(cli_allowed_commands) if cli_allowed_commands else [],
            credentials=list(credentials) if credentials else [],
        )

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        wrapper._agent_def = ad  # type: ignore[attr-defined]
        return wrapper

    if func is not None:
        return _wrap(func)
    return _wrap


# ── Resolution helper ───────────────────────────────────────────────────


def _resolve_agent(obj: Any, parent_model: str = "") -> "Agent":
    """Convert an ``@agent``-decorated function into an :class:`Agent` instance.

    If *obj* is already an :class:`Agent`, it is returned as-is.

    When the decorated function has no explicit model (``model=""``) and
    *parent_model* is provided, the parent's model is inherited.

    Raises:
        TypeError: If *obj* is not an Agent or ``@agent``-decorated function.
    """
    if isinstance(obj, Agent):
        return obj
    if callable(obj) and hasattr(obj, "_agent_def"):
        ad: AgentDef = obj._agent_def
        # Handle ClaudeCode: don't inherit parent model for claude-code agents
        if isinstance(ad.model, ClaudeCode):
            resolved_model = ad.model
        else:
            resolved_model = ad.model or parent_model
        return Agent(
            name=ad.name,
            model=resolved_model,
            instructions=ad.func,
            tools=ad.tools,
            guardrails=ad.guardrails,
            agents=ad.agents,
            strategy=ad.strategy,
            max_turns=ad.max_turns,
            max_tokens=ad.max_tokens,
            temperature=ad.temperature,
            metadata=ad.metadata,
            local_code_execution=ad.local_code_execution,
            allowed_languages=ad.allowed_languages or None,
            allowed_commands=ad.allowed_commands or None,
            code_execution=ad.code_execution,
            cli_commands=ad.cli_commands,
            cli_config=ad.cli_config,
            cli_allowed_commands=ad.cli_allowed_commands or None,
            credentials=ad.credentials or None,
        )
    raise TypeError(f"Expected an Agent or @agent-decorated function, got {type(obj).__name__}")


class Agent:
    """An AI agent backed by a durable Conductor workflow.

    Args:
        name: Unique agent name (used as workflow name).
        model: LLM model in ``"provider/model"`` format (e.g. ``"openai/gpt-4o"``).
            If empty, the agent is treated as an **external** reference to a
            workflow deployed elsewhere — the server produces a
            ``SubWorkflowTask`` instead of compiling the agent inline.
        instructions: System prompt — a string, a callable that returns one,
            or a :class:`PromptTemplate` referencing a server-side template.
        tools: List of ``@tool``-decorated functions or :class:`ToolDef` instances.
        agents: Sub-agents for multi-agent orchestration.  Accepts
            :class:`Agent` instances and ``@agent``-decorated functions
            (which are resolved into Agent instances automatically).
        strategy: How sub-agents are orchestrated.  Use :class:`Strategy` enum
            values (e.g. ``Strategy.HANDOFF``) or plain strings (e.g.
            ``"handoff"``).  Valid values: ``handoff``, ``sequential``,
            ``parallel``, ``router``, ``round_robin``, ``random``, ``swarm``,
            ``manual``.
        router: For ``strategy="router"``, an :class:`Agent` or callable that
            selects which sub-agent runs each turn.
        output_type: A Pydantic model or dataclass for structured output.
        guardrails: List of :class:`Guardrail` instances for input/output validation.
        memory: Optional :class:`ConversationMemory` for session management.
        dependencies: Optional dict of dependencies to inject into tool context.
        max_turns: Maximum agent loop iterations (default 25).
        max_tokens: Maximum tokens for LLM generation.
        temperature: Sampling temperature for the LLM.
        stop_when: Optional callable ``(context) -> bool`` to end the loop early.
        termination: Optional :class:`TerminationCondition` for composable
            termination logic.  Can be combined with ``&`` and ``|``.
        handoffs: List of :class:`HandoffCondition` for ``strategy="swarm"``.
            Defines post-tool and post-work transitions to other agents.
        allowed_transitions: Optional mapping of ``agent_name -> [allowed_next_agents]``
            to constrain which agents can follow which in multi-agent strategies.
        introduction: Optional text this agent uses to introduce itself in
            group conversations.
        metadata: Arbitrary metadata attached to the agent / workflow.
        local_code_execution: When ``True``, automatically attaches an
            ``execute_code`` tool backed by :class:`LocalCodeExecutor`.
        allowed_languages: Interpreter languages the LLM may use when
            ``local_code_execution`` is enabled (default ``["python"]``).
        allowed_commands: Shell commands the code may invoke (e.g.
            ``["pip", "ls"]``).  Empty list means no restrictions.
        code_execution: A :class:`CodeExecutionConfig` for full control
            over the executor, languages, commands, and timeout.
            Mutually exclusive with ``local_code_execution``.
        planner: When ``True``, the server enhances the system prompt with
            planning instructions so the agent plans before executing.
        callbacks: List of :class:`CallbackHandler` instances for lifecycle
            hooks.  Multiple handlers chain per-position in list order;
            first non-empty dict return short-circuits remaining handlers.
            Supports 6 positions: ``on_agent_start``, ``on_agent_end``,
            ``on_model_start``, ``on_model_end``, ``on_tool_start``,
            ``on_tool_end``.
        before_agent_callback: *Deprecated* — use ``callbacks`` instead.
            A callable invoked before the agent starts processing.
        after_agent_callback: *Deprecated* — use ``callbacks`` instead.
            A callable invoked after the agent finishes processing.
        before_model_callback: *Deprecated* — use ``callbacks`` instead.
            A callable invoked before each LLM call.
        after_model_callback: *Deprecated* — use ``callbacks`` instead.
            A callable invoked after each LLM call.
        include_contents: Controls parent conversation context for sub-agents.
            ``"default"`` passes full context, ``"none"`` gives fresh context.
        thinking_budget_tokens: Token budget for extended reasoning/thinking
            mode. When set, the LLM spends extra tokens on internal reasoning
            before responding.
    """

    def __init__(
        self,
        name: str,
        model: Union[str, "ClaudeCode", Any] = "",
        instructions: Union[str, Callable[..., str], PromptTemplate] = "",
        tools: Optional[List[Any]] = None,
        agents: Optional[List[Any]] = None,
        strategy: Union[str, Strategy] = Strategy.HANDOFF,
        router: Optional[Union["Agent", Callable[..., Any]]] = None,
        output_type: Optional[type] = None,
        guardrails: Optional[List[Any]] = None,
        memory: Optional[Any] = None,
        dependencies: Optional[Dict[str, Any]] = None,
        max_turns: int = 25,
        max_tokens: Optional[int] = None,
        timeout_seconds: int = 0,
        temperature: Optional[float] = None,
        stop_when: Optional[Callable[..., bool]] = None,
        termination: Optional[Any] = None,
        handoffs: Optional[List[Any]] = None,
        allowed_transitions: Optional[Dict[str, List[str]]] = None,
        introduction: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        local_code_execution: bool = False,
        allowed_languages: Optional[List[str]] = None,
        allowed_commands: Optional[List[str]] = None,
        code_execution: Optional[Any] = None,
        cli_commands: bool = False,
        cli_allowed_commands: Optional[List[str]] = None,
        cli_config: Optional[Any] = None,
        planner: bool = False,
        callbacks: Optional[List[Any]] = None,
        before_agent_callback: Optional[Callable[..., Any]] = None,
        after_agent_callback: Optional[Callable[..., Any]] = None,
        before_model_callback: Optional[Callable[..., Any]] = None,
        after_model_callback: Optional[Callable[..., Any]] = None,
        include_contents: Optional[str] = None,
        thinking_budget_tokens: Optional[int] = None,
        required_tools: Optional[List[str]] = None,
        gate: Optional[Any] = None,
        credentials: Optional[List[Any]] = None,
        stateful: bool = False,
    ) -> None:
        if not name or not isinstance(name, str):
            raise ValueError("Agent name must be a non-empty string")
        if not _VALID_NAME_RE.match(name):
            raise ValueError(
                f"Invalid agent name {name!r}. "
                "Must start with a letter or underscore and contain only "
                "letters, digits, underscores, or hyphens."
            )
        try:
            strategy = Strategy(strategy)
        except ValueError:
            valid = ", ".join(s.value for s in Strategy)
            raise ValueError(f"Invalid strategy {strategy!r}. Must be one of: {valid}")
        if strategy == "router" and router is None:
            raise ValueError("strategy='router' requires a router argument")
        if max_turns is not None and max_turns < 1:
            raise ValueError(f"max_turns must be >= 1, got {max_turns}")

        self.name = name

        # Handle ClaudeCode config object
        self._claude_code_config: Optional[Any] = None
        if isinstance(model, ClaudeCode):
            self._claude_code_config = model
            self.model = model.to_model_string()
        else:
            self.model = model

        self.instructions = instructions
        self.tools: List[Any] = list(tools) if tools else []

        # Validate claude-code tools are all strings
        if self.is_claude_code and self.tools:
            for t in self.tools:
                if not isinstance(t, str):
                    raise ValueError(
                        "Claude Code agents only support built-in string tools like "
                        "'Read', 'Edit', 'Bash'. Custom @tool functions are not "
                        "supported yet (Phase 2)."
                    )

        self.agents: List[Agent] = [_resolve_agent(a, self.model) for a in agents] if agents else []
        # Validate sub-agent name uniqueness
        if self.agents:
            seen: Dict[str, int] = {}
            for a in self.agents:
                seen[a.name] = seen.get(a.name, 0) + 1
            duplicates = [n for n, count in seen.items() if count > 1]
            if duplicates:
                raise ValueError(
                    f"Duplicate sub-agent names in '{name}': {duplicates}. "
                    "Each sub-agent must have a unique name. "
                    "If reusing the same agent, create separate instances with distinct names."
                )
        self.strategy = strategy
        self.router = router
        self.output_type = output_type
        self.guardrails: List[Any] = list(guardrails) if guardrails else []
        self.memory = memory
        self.dependencies: Dict[str, Any] = dict(dependencies) if dependencies else {}
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.stop_when = stop_when
        self.termination = termination
        self.handoffs: List[Any] = list(handoffs) if handoffs else []
        self.allowed_transitions: Optional[Dict[str, List[str]]] = (
            dict(allowed_transitions) if allowed_transitions else None
        )
        self.introduction = introduction
        self.metadata: Dict[str, Any] = dict(metadata) if metadata else {}
        self.stateful = stateful
        self.planner = planner
        self.callbacks: List[Any] = list(callbacks) if callbacks else []
        self.before_agent_callback = before_agent_callback
        self.after_agent_callback = after_agent_callback
        self.before_model_callback = before_model_callback
        self.after_model_callback = after_model_callback
        for _attr in (
            "before_agent_callback",
            "after_agent_callback",
            "before_model_callback",
            "after_model_callback",
        ):
            if getattr(self, _attr) is not None:
                warnings.warn(
                    f"{_attr} is deprecated, use callbacks=[CallbackHandler()] instead",
                    DeprecationWarning,
                    stacklevel=2,
                )
        self.include_contents = include_contents
        self.thinking_budget_tokens = thinking_budget_tokens
        self.required_tools: List[str] = list(required_tools) if required_tools else []
        self.gate = gate
        # ── Code execution setup ─────────────────────────────────────
        self.code_execution_config: Optional[Any] = None
        if code_execution is not None:
            self.code_execution_config = code_execution
        elif local_code_execution:
            from agentspan.agents.code_execution_config import CodeExecutionConfig

            self.code_execution_config = CodeExecutionConfig(
                enabled=True,
                allowed_languages=(list(allowed_languages) if allowed_languages else ["python"]),
                allowed_commands=(list(allowed_commands) if allowed_commands else []),
            )
        if self.code_execution_config and self.code_execution_config.enabled:
            self._attach_code_execution_tool()

        # ── CLI command execution setup ───────────────────────────────
        self.cli_config: Optional[Any] = None
        if cli_config is not None:
            self.cli_config = cli_config
        elif cli_commands or cli_allowed_commands:
            from agentspan.agents.cli_config import CliConfig

            self.cli_config = CliConfig(
                allowed_commands=(
                    list(cli_allowed_commands)
                    if cli_allowed_commands
                    else list(allowed_commands)
                    if allowed_commands
                    else []
                ),
            )
        if self.cli_config and self.cli_config.enabled:
            self._attach_cli_tool()

        # ── Credential setup ─────────────────────────────────────────────
        # Credentials must be explicitly declared — no auto-mapping.
        if credentials is not None:
            self.credentials: List[Any] = list(credentials)
        else:
            self.credentials = []

        # Propagate agent-level credentials to CLI/code tools so the
        # dispatch layer can resolve them per-tool (the dispatch only
        # looks at tool_def.credentials, not agent-level credentials).
        if self.credentials:
            from agentspan.agents.tool import get_tool_def

            for t in self.tools:
                td = getattr(t, "_tool_def", None)
                if td is not None and not td.credentials and td.tool_type in ("cli", "code"):
                    td.credentials = list(self.credentials)
                    # Also update _tool_def on raw func for pickle survival
                    if td.func and hasattr(td.func, "_tool_def"):
                        td.func._tool_def.credentials = list(self.credentials)

    def _attach_code_execution_tool(self) -> None:
        """Auto-create and attach a code execution tool from config."""
        from agentspan.agents.code_execution_config import (
            _make_code_execution_tool,
        )
        from agentspan.agents.code_executor import LocalCodeExecutor

        cfg = self.code_execution_config
        executor = cfg.executor
        if executor is None:
            executor = LocalCodeExecutor(
                language="python",
                timeout=cfg.timeout,
                working_dir=cfg.working_dir,
            )
        code_tool = _make_code_execution_tool(
            executor=executor,
            allowed_languages=cfg.allowed_languages,
            allowed_commands=cfg.allowed_commands,
            timeout=cfg.timeout,
            agent_name=self.name,
        )
        self.tools.append(code_tool)

    def _attach_cli_tool(self) -> None:
        """Auto-create and attach a CLI command execution tool from config."""
        from agentspan.agents.cli_config import _make_cli_tool

        cfg = self.cli_config
        self.tools.append(
            _make_cli_tool(
                allowed_commands=cfg.allowed_commands,
                timeout=cfg.timeout,
                working_dir=cfg.working_dir,
                allow_shell=cfg.allow_shell,
                agent_name=self.name,
            )
        )

    # ── Claude Code detection ──────────────────────────────────────────

    @property
    def is_claude_code(self) -> bool:
        """True if this agent uses the Claude Agent SDK runtime."""
        return isinstance(self.model, str) and self.model.startswith("claude-code")

    # ── External detection ────────────────────────────────────────────

    @property
    def external(self) -> bool:
        """``True`` if this agent references an external workflow (no local definition).

        An agent with no ``model`` is treated as external — the server
        produces a ``SubWorkflowTask`` referencing the workflow by name
        instead of compiling the agent inline.
        """
        return not self.model

    # ── Chaining shorthand ──────────────────────────────────────────────

    def __rshift__(self, other: "Agent") -> "Agent":
        """Create a sequential pipeline: ``agent_a >> agent_b >> agent_c``.

        Returns a new Agent with ``strategy="sequential"`` combining both sides.
        """
        left_agents = self.agents if self.strategy == "sequential" else [self]
        right_agents = other.agents if other.strategy == "sequential" else [other]
        all_agents = list(left_agents) + list(right_agents)
        combined_name = "_".join(a.name for a in all_agents)
        return Agent(
            name=combined_name,
            model=self.model,
            agents=all_agents,
            strategy=Strategy.SEQUENTIAL,
        )

    # ── Representation ──────────────────────────────────────────────────

    def __repr__(self) -> str:
        if self.external:
            return f"Agent(name={self.name!r}, external=True)"
        parts = [f"Agent(name={self.name!r}, model={self.model!r}"]
        if self.tools:
            parts.append(f", tools={len(self.tools)}")
        if self.agents:
            parts.append(f", agents={len(self.agents)}, strategy={self.strategy!r}")
        parts.append(")")
        return "".join(parts)


# ── Scatter-Gather convenience helper ─────────────────────────────────


_SCATTER_GATHER_PREFIX = """\
You are a coordinator that decomposes problems into independent sub-tasks.

WORKFLOW:
1. Analyze the input and identify independent sub-problems
2. Call the '{worker_name}' tool MULTIPLE TIMES IN PARALLEL — once per sub-problem, each with a clear, self-contained prompt
3. After all results return, synthesize them into a unified answer

IMPORTANT: Issue all '{worker_name}' tool calls in a SINGLE response to maximize parallelism.
"""


def scatter_gather(
    name: str,
    worker: "Agent",
    *,
    model: str = None,
    instructions: str = "",
    tools: Optional[List[Any]] = None,
    retry_count: Optional[int] = None,
    retry_delay_seconds: Optional[int] = None,
    fail_fast: bool = False,
    **kwargs: Any,
) -> "Agent":
    """Create a coordinator Agent pre-configured for the scatter-gather pattern.

    The coordinator decomposes a problem into N independent sub-tasks,
    dispatches the *worker* agent N times in parallel (via ``agent_tool``),
    and synthesizes the results.  N is determined at runtime by the LLM.

    Each sub-task is a durable Conductor sub-workflow with automatic retries
    on transient failures.  By default, individual sub-task failures are
    tolerated so the coordinator can synthesize partial results.

    Args:
        name: Name for the coordinator agent.
        worker: The worker Agent that handles each sub-task.
        model: LLM model for the coordinator.  Defaults to the worker's model.
        instructions: Additional instructions appended after the auto-generated
            decomposition/synthesis prefix.
        tools: Extra tools for the coordinator (in addition to the worker tool).
        retry_count: Retries per sub-task on failure (default 2, linear backoff).
        retry_delay_seconds: Base delay between retries in seconds (default 2).
        fail_fast: When ``True``, a single sub-task failure fails the entire
            scatter-gather.  Default ``False`` — the coordinator continues with
            partial results.
        **kwargs: Forwarded to the :class:`Agent` constructor (e.g. ``max_turns``,
            ``guardrails``, ``temperature``, ``timeout_seconds``).
            If ``timeout_seconds`` is not specified, defaults to 300 (5 minutes)
            since scatter-gather dispatches multiple sub-agents in parallel.

    Returns:
        An :class:`Agent` configured as a scatter-gather coordinator.

    Example::

        researcher = Agent(name="researcher", model="openai/gpt-4o",
                          tools=[search], instructions="Research a topic.")
        coordinator = scatter_gather("coordinator", researcher,
                                     instructions="Focus on technical depth.")
        result = runtime.run(coordinator, "Compare Python, Rust, and Go for CLIs")
    """
    from agentspan.agents.tool import agent_tool

    # Default to 5 minutes — scatter-gather waits for N parallel sub-agents
    kwargs.setdefault("timeout_seconds", 300)

    worker_tool = agent_tool(
        worker,
        retry_count=retry_count,
        retry_delay_seconds=retry_delay_seconds,
        optional=not fail_fast if fail_fast else None,
    )
    resolved_model = model if model is not None else worker.model

    prefix = _SCATTER_GATHER_PREFIX.format(worker_name=worker.name)
    full_instructions = f"{prefix}\n{instructions}" if instructions else prefix

    all_tools = [worker_tool] + (list(tools) if tools else [])

    return Agent(
        name=name,
        model=resolved_model,
        instructions=full_instructions,
        tools=all_tools,
        **kwargs,
    )
