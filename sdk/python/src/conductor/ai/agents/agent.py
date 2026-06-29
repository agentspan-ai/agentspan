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

from conductor.ai.agents.claude_code import ClaudeCode

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
    PLAN_EXECUTE = "plan_execute"


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
    context_window_budget: Optional[int] = None
    prefill_tools: List[Any] = field(default_factory=list)


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
    context_window_budget: Optional[int] = None,
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
            context_window_budget=context_window_budget,
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
            context_window_budget=ad.context_window_budget,
            prefill_tools=ad.prefill_tools or None,
        )
    raise TypeError(f"Expected an Agent or @agent-decorated function, got {type(obj).__name__}")


# ── from_instance resolution helpers ────────────────────────────────────


def _discover_agent_methods(instance: Any) -> Dict[str, Callable[..., Any]]:
    """Discover ``@agent``-decorated methods on *instance*, keyed by agent name.

    Walks the instance's attributes (which includes inherited methods) and
    collects bound methods whose underlying function carries an
    ``_agent_def``.  The key is the resolved agent name (``AgentDef.name``,
    i.e. the decorator's ``name=`` or the method name).

    Raises:
        ValueError: On duplicate resolved agent names.
    """
    import inspect as _inspect

    methods: Dict[str, Callable[..., Any]] = {}
    seen_funcs: set = set()
    for attr_name in dir(instance):
        if attr_name.startswith("__"):
            continue
        try:
            member = getattr(instance, attr_name)
        except Exception:
            continue
        if not callable(member):
            continue
        ad = getattr(member, "_agent_def", None)
        if ad is None:
            continue
        # Deduplicate: dir() can surface the same callable under aliases.
        underlying = getattr(member, "__func__", member)
        if id(underlying) in seen_funcs:
            continue
        seen_funcs.add(id(underlying))
        if not _inspect.ismethod(member):
            # A class attribute that is a plain @agent function (unbound) —
            # skip; from_instance operates on bound methods of the instance.
            continue
        agent_name = ad.name
        if agent_name in methods:
            raise ValueError(
                f"Duplicate @agent name {agent_name!r} on {type(instance).__name__!r}. "
                "Each @agent method must resolve to a unique name."
            )
        methods[agent_name] = member
    return methods


def _discover_instance_tools(instance: Any) -> List[Any]:
    """Discover ``@tool`` methods on *instance* as instance-bound tools.

    Each returned tool is a fresh :class:`ToolDef` copied from the method's
    ``_tool_def`` but with ``func`` rebound to the instance, so the worker
    invokes it as a method (``self`` is supplied) rather than calling the
    unbound class function.
    """
    import dataclasses as _dc

    tools: List[Any] = []
    seen: set = set()
    for attr_name in dir(instance):
        if attr_name.startswith("__"):
            continue
        try:
            member = getattr(instance, attr_name)
        except Exception:
            continue
        td = getattr(member, "_tool_def", None)
        if td is None:
            continue
        underlying = getattr(member, "__func__", member)
        if id(underlying) in seen:
            continue
        seen.add(id(underlying))
        # Rebind func to the bound method so the worker passes ``self``.
        bound = _dc.replace(td, func=member)
        tools.append(bound)
    return tools


def _discover_instance_guardrails(instance: Any) -> List[Any]:
    """Discover ``@guardrail`` methods on *instance* as instance-bound guardrails."""
    from conductor.ai.agents.guardrail import Guardrail

    guardrails: List[Any] = []
    seen: set = set()
    for attr_name in dir(instance):
        if attr_name.startswith("__"):
            continue
        try:
            member = getattr(instance, attr_name)
        except Exception:
            continue
        gd = getattr(member, "_guardrail_def", None)
        if gd is None:
            continue
        underlying = getattr(member, "__func__", member)
        if id(underlying) in seen:
            continue
        seen.add(id(underlying))
        # Bind the guardrail func to the instance so the check runs as a method.
        guardrails.append(Guardrail(func=member, name=gd.name))
    return guardrails


def _select_named(
    requested: List[Any],
    discovered: Dict[str, Any],
    agent_name: str,
    instance: Any,
    kind: str,
) -> List[Any]:
    """Resolve an explicit tools/guardrails list that may mix names and objects.

    String entries are looked up by name in *discovered* (the instance's
    decorated members); non-string entries (already-resolved objects) pass
    through unchanged.  An unknown name raises with the available names.
    """
    out: List[Any] = []
    for entry in requested:
        if isinstance(entry, str):
            if entry not in discovered:
                raise ValueError(
                    f"No {kind} method named {entry!r} on {type(instance).__name__!r} "
                    f"(referenced by @agent {agent_name!r}). "
                    f"Available: {sorted(discovered)}"
                )
            out.append(discovered[entry])
        else:
            out.append(entry)
    return out


def _resolve_instance_agent(
    instance: Any,
    methods: Dict[str, Callable[..., Any]],
    name: str,
    parent_model: str,
    stack: List[str],
) -> "Agent":
    """Resolve one ``@agent`` method on *instance* into an :class:`Agent`.

    Recurses for sub-agents declared by name.  Mirrors the Java
    ``AgentRegistry.resolve`` semantics.
    """
    if name in stack:
        cycle = " -> ".join(stack + [name])
        raise ValueError(f"Cyclic @agent sub-agent reference: {cycle}")
    stack = stack + [name]

    method = methods[name]
    ad: AgentDef = method._agent_def  # type: ignore[attr-defined]
    model = ad.model or parent_model

    # Method body: None -> attrs only; str -> dynamic instructions;
    # Agent -> factory (returned as-is).
    body_result = method()
    if isinstance(body_result, Agent):
        return body_result

    if isinstance(body_result, str) and body_result:
        instructions: Any = body_result
    else:
        # Fall back to the docstring (decorator default).
        instructions = inspect_getdoc(method) or ""

    # Tools: explicit list on the decorator wins; otherwise attach ALL
    # @tool methods discovered on the instance. String entries in an
    # explicit list are resolved by name against the instance's @tool
    # methods (so a class can declare ``tools=["lookup"]`` by method name).
    if ad.tools:
        from conductor.ai.agents.tool import get_tool_def

        discovered_tools = {get_tool_def(t).name: t for t in _discover_instance_tools(instance)}
        tools = _select_named(ad.tools, discovered_tools, name, instance, "@tool")
    else:
        tools = _discover_instance_tools(instance)

    # Guardrails: explicit list wins; otherwise attach ALL @guardrail methods.
    if ad.guardrails:
        discovered_grs = {g.name: g for g in _discover_instance_guardrails(instance)}
        guardrails = _select_named(ad.guardrails, discovered_grs, name, instance, "@guardrail")
    else:
        guardrails = _discover_instance_guardrails(instance)

    # Sub-agents: resolve string entries by name against sibling @agent
    # methods; pass Agent / @agent-function entries through unchanged.
    sub_agents: List[Any] = []
    for entry in ad.agents:
        if isinstance(entry, str):
            if entry not in methods:
                raise ValueError(
                    f"Sub-agent {entry!r} referenced by @agent {name!r} not found on "
                    f"{type(instance).__name__!r}. Available: {sorted(methods)}"
                )
            sub_agents.append(_resolve_instance_agent(instance, methods, entry, model, stack))
        else:
            sub_agents.append(entry)

    return Agent(
        name=ad.name,
        model=model,
        instructions=instructions,
        tools=tools,
        guardrails=guardrails,
        agents=sub_agents,
        strategy=ad.strategy,
        max_turns=ad.max_turns,
        max_tokens=ad.max_tokens,
        temperature=ad.temperature,
        metadata=ad.metadata,
        credentials=ad.credentials or None,
        context_window_budget=ad.context_window_budget,
    )


def inspect_getdoc(obj: Any) -> Optional[str]:
    """Return the cleaned docstring of *obj* (thin wrapper over inspect.getdoc)."""
    import inspect as _inspect

    return _inspect.getdoc(obj)


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
        semantic_memory: Optional[Any] = None,
        memory_summary_model: Optional[str] = None,
        feedback_sink: Optional[Callable[..., Any]] = None,
        dependencies: Optional[Dict[str, Any]] = None,
        max_turns: int = 25,
        max_tokens: Optional[int] = None,
        timeout_seconds: int = 0,
        temperature: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
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
        enable_planning: bool = False,
        callbacks: Optional[List[Any]] = None,
        before_agent_callback: Optional[Callable[..., Any]] = None,
        after_agent_callback: Optional[Callable[..., Any]] = None,
        before_model_callback: Optional[Callable[..., Any]] = None,
        after_model_callback: Optional[Callable[..., Any]] = None,
        include_contents: Optional[str] = None,
        thinking_budget_tokens: Optional[int] = None,
        required_tools: Optional[List[str]] = None,
        gate: Optional[Any] = None,
        base_url: Optional[str] = None,
        credentials: Optional[List[Any]] = None,
        stateful: bool = False,
        context_window_budget: Optional[int] = None,
        prefill_tools: Optional[List[Any]] = None,
        fallback_max_turns: Optional[int] = None,
        plan_source: Optional[Dict[str, Any]] = None,
        synthesize: bool = True,
        masked_fields: Optional[List[str]] = None,
        # PLAN_EXECUTE named slots (replace positional ``agents=[planner, fallback]``)
        planner: Optional["Agent"] = None,
        fallback: Optional["Agent"] = None,
        planner_context: Optional[List[Any]] = None,
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
        # Named slots (``planner=``/``fallback=``) are PLAN_EXECUTE-only.
        # Every other strategy compiler iterates the ``agents=[…]`` list
        # directly; passing named slots with another strategy would either
        # NPE deep inside a strategy compiler or be silently ignored.
        # Reject at construction with a clear message rather than letting
        # the misconfig propagate to the server.
        if (planner is not None or fallback is not None) and strategy != "plan_execute":
            raise ValueError(
                "Named slots ``planner=`` and ``fallback=`` are only valid with "
                f"``strategy=Strategy.PLAN_EXECUTE``. Got strategy={strategy!r}. "
                "Either set ``strategy=Strategy.PLAN_EXECUTE`` or pass the sub-agents "
                "via ``agents=[…]`` instead."
            )
        # PLAN_EXECUTE shape — named-slot API. Reject the legacy
        # ``agents=[planner, fallback]`` indexing with a clear migration
        # message rather than silently doing the wrong thing if the user
        # mixes both shapes.
        if strategy == "plan_execute":
            if planner is None:
                if agents:
                    raise ValueError(
                        "Strategy.PLAN_EXECUTE no longer accepts ``agents=[planner, fallback]``. "
                        "Use the named slots: ``planner=<Agent>`` (required) and "
                        "``fallback=<Agent>`` (optional)."
                    )
                raise ValueError(
                    "Strategy.PLAN_EXECUTE requires ``planner=<Agent>`` (the agent that "
                    "produces the JSON plan)."
                )
            if not tools:
                raise ValueError(
                    "Strategy.PLAN_EXECUTE requires ``tools=[...]`` on the parent agent. "
                    "These are the canonical plan-executable tools — every ``op.tool`` in "
                    "the planner's JSON plan must be one of these. Listing tools here also "
                    "ensures the runtime starts workers for them."
                )
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

        self.base_url = base_url
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

        # PARALLEL parents need a model for the server-side aggregation step;
        # without one, compilation fails with an opaque HTTP 400 ("Cannot
        # compile external agent directly"). Auto-inherit from the first
        # child that has a model so the common case
        # ``Agent(agents=[a1, a2], strategy=PARALLEL)`` works without
        # repeating ``model=`` on the parent. Picks the *first* match by
        # design — children may have differing models for their own work,
        # and the parent's model is only used for aggregation; the caller
        # can pass an explicit ``model=`` to override. If no child has a
        # model either, raise a clear error here rather than surfacing the
        # opaque server 400 later.
        if strategy == Strategy.PARALLEL and not self.model and self.agents:
            inherited = next((a.model for a in self.agents if a.model), "")
            if inherited:
                self.model = inherited
            else:
                raise ValueError(
                    f"Strategy.PARALLEL agent '{name}' has no ``model=`` and "
                    "no child agent has one to inherit from. Set ``model=`` "
                    "on the parent (used for aggregation) or on at least "
                    "one child."
                )
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
        # OCG-backed long-term memory (see agents/ocg_memory.py). When set, the
        # runtime auto-injects relevant memories into the prompt before a run and,
        # after the run, summarizes the conversation into a memory. feedback_sink,
        # if provided, receives the good/bad capability links for that memory.
        self.semantic_memory = semantic_memory
        self.memory_summary_model = memory_summary_model
        self.feedback_sink = feedback_sink
        self.dependencies: Dict[str, Any] = dict(dependencies) if dependencies else {}
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.context_window_budget = context_window_budget
        self.prefill_tools: List[Any] = list(prefill_tools) if prefill_tools else []
        self.fallback_max_turns = fallback_max_turns
        self.plan_source = plan_source
        self.synthesize = synthesize
        self.masked_fields: List[str] = list(masked_fields) if masked_fields else []
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        # OpenAI reasoning models (o1, gpt-5-codex, etc.) accept
        # "minimal" | "low" | "medium" | "high". Server forwards to the
        # ChatCompletion.reasoningEffort field; ignored by non-reasoning models.
        self.reasoning_effort = reasoning_effort
        self.stop_when = stop_when
        self.termination = termination
        self.handoffs: List[Any] = list(handoffs) if handoffs else []
        self.allowed_transitions: Optional[Dict[str, List[str]]] = (
            dict(allowed_transitions) if allowed_transitions else None
        )
        self.introduction = introduction
        self.metadata: Dict[str, Any] = dict(metadata) if metadata else {}
        self.stateful = stateful
        self.enable_planning = enable_planning
        # PLAN_EXECUTE named slots — see __init__ docstring.
        self.planner: Optional["Agent"] = planner
        self.fallback: Optional["Agent"] = fallback

        # PLAN_EXECUTE planner context (text snippets + URLs whose
        # bodies are fetched per-planner-invocation and appended to
        # the planner's prompt). Normalise bare strings to
        # ``Context(text=...)`` so users can pass either shape.
        # Reject when set on a non-PLAN_EXECUTE strategy with a
        # clear migration message — same pattern as planner=/fallback=.
        if planner_context is not None:
            if strategy != "plan_execute":
                raise ValueError(
                    "``planner_context=`` is only valid with "
                    f"``strategy=Strategy.PLAN_EXECUTE``. Got strategy={strategy!r}. "
                    "The context block is appended to the planner's user prompt "
                    "at runtime, which only exists in PLAN_EXECUTE."
                )
            # Local import — Context lives in plans.py which imports Agent
            # transitively. Doing the import lazily avoids the cycle.
            from conductor.ai.agents.plans import Context as _Context

            normalised: List[Any] = []
            for i, entry in enumerate(planner_context):
                if isinstance(entry, _Context):
                    normalised.append(entry)
                elif isinstance(entry, str):
                    normalised.append(_Context(text=entry))
                elif isinstance(entry, dict):
                    # Already in wire shape — accept as-is so power users
                    # can hand-roll Maps if they prefer (matches how
                    # ``plan_source`` is typed as ``Dict[str, Any]``).
                    normalised.append(entry)
                else:
                    raise ValueError(
                        f"planner_context[{i}]: must be a Context, a string, "
                        f"or a dict; got {type(entry).__name__}"
                    )
            self.planner_context: Optional[List[Any]] = normalised
        else:
            self.planner_context = None
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
            from conductor.ai.agents.code_execution_config import CodeExecutionConfig

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
            from conductor.ai.agents.cli_config import CliConfig

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
            for t in self.tools:
                td = getattr(t, "_tool_def", None)
                if td is not None and not td.credentials and td.tool_type in ("cli", "code"):
                    td.credentials = list(self.credentials)
                    # Also update _tool_def on raw func for pickle survival
                    if td.func and hasattr(td.func, "_tool_def"):
                        td.func._tool_def.credentials = list(self.credentials)

    def _attach_code_execution_tool(self) -> None:
        """Auto-create and attach a code execution tool from config."""
        from conductor.ai.agents.code_execution_config import (
            _make_code_execution_tool,
        )
        from conductor.ai.agents.code_executor import LocalCodeExecutor

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
        from conductor.ai.agents.cli_config import _make_cli_tool

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

    # ── Instance-method resolution ──────────────────────────────────────

    @classmethod
    def from_instance(cls, instance: Any, name: Optional[str] = None) -> Any:
        """Resolve ``@agent``-decorated **methods** on an object into Agents.

        Mirrors the Java SDK's ``Agent.fromInstance``.  An object can group
        several agents, their tools, and their guardrails as methods on a
        single class — handy for dependency injection and stateful
        collaborators.

        - ``Agent.from_instance(instance)`` returns ``list[Agent]`` — one per
          ``@agent``-decorated method on the instance.
        - ``Agent.from_instance(instance, name)`` returns a single
          :class:`Agent` (the one whose resolved name matches *name*).

        Resolution rules (matching the Java reference):

        - **Tools / guardrails:** by default every ``@tool`` /
          ``@guardrail`` method on the same instance is attached to each
          agent, bound to the instance so the worker calls them as methods.
          If the ``@agent`` declares an explicit ``tools=`` / ``guardrails=``
          list, only those are attached.
        - **Sub-agents:** entries in the ``@agent``'s ``agents=`` list that
          are plain strings are resolved by name against the other ``@agent``
          methods on the instance (recursively).  Cyclic references raise.
        - **Model inheritance:** a sub-agent with no ``model`` inherits its
          parent's model at resolution time.
        - **Method body:** returning ``None`` uses the decorator attributes
          only; returning a ``str`` provides dynamic instructions (overriding
          the docstring); returning an :class:`Agent` makes the method a
          factory whose returned agent is used as-is.

        Raises:
            ValueError: If *name* is given but no ``@agent`` method resolves
                to that name, or on duplicate / cyclic agent names.
        """
        methods = _discover_agent_methods(instance)
        if not methods:
            raise ValueError(
                f"No @agent-decorated methods found on {type(instance).__name__!r}. "
                "Decorate one or more methods with @agent."
            )

        if name is not None:
            if name not in methods:
                raise ValueError(
                    f"No @agent method resolving to name {name!r} on "
                    f"{type(instance).__name__!r}. Available: {sorted(methods)}"
                )
            return _resolve_instance_agent(instance, methods, name, "", [])

        return [
            _resolve_instance_agent(instance, methods, agent_name, "", []) for agent_name in methods
        ]

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
    from conductor.ai.agents.tool import agent_tool

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
