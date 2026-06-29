# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Typed plan builders for ``Strategy.PLAN_EXECUTE``.

These dataclasses produce the JSON shape PAC (the server's PLAN_AND_COMPILE
task) consumes. Use them to construct plans in Python with IDE autocomplete
and Pylance type-checking, instead of inlining JSON dict literals.

Example::

    from conductor.ai.agents.plans import Plan, Step, Op, Generate, Validation

    plan = Plan(
        steps=[
            Step("setup", operations=[Op("create_directory", args={"path": "out"})]),
            Step(
                "write_sections",
                depends_on=["setup"],
                parallel=True,
                operations=[
                    Op("write_file", generate=Generate(
                        instructions="Write the introduction.",
                        output_schema='{"path": "out/intro.md", "content": "..."}',
                    )),
                ],
            ),
        ],
        validation=[
            Validation("check_word_count", args={"path": "out/intro.md", "min_words": 200}),
        ],
    )

The ``Plan`` object is consumed by ``runtime.run(harness, plan=plan)`` —
the SDK serialises it to the same JSON the LLM planner would have emitted.

The schema mirrors what the server appends to the planner prompt at compile
time (the ``## Plan schema`` block). This module is the typed twin of that
contract: every field name, optionality, and sub-shape matches what PAC
parses. If PAC's parser changes, this module must change too.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass(frozen=True)
class Context:
    """A reference document made available to the PLAN_EXECUTE planner.

    Appended to the planner's user prompt as a ``## Reference Context``
    block on every planner invocation. Use to ground the planner in
    domain-specific rules / processes / edge cases that a static
    ``instructions`` string can't capture — onboarding playbooks, KYC
    rules, compliance thresholds, etc.

    Exactly one of ``text`` or ``url`` must be set:

    * ``text``: inlined verbatim — best for short, stable rules.
    * ``url``: HTTP GET on every planner run (no compile-time fetch,
      no cache — doc edits go live without recompile). Optional
      ``headers`` carry credential placeholders in the
      ``${CRED_NAME}`` shape; the server escapes them to
      ``#{CRED_NAME}`` so Conductor's templater doesn't consume them
      and the runtime credential resolver fills them in at request
      time — same auth pipeline as :class:`ToolConfig` HTTP tools.

    Attributes:
        text: Inline reference text.
        url: HTTP(S) URL to fetch at planner-run time.
        headers: Optional HTTP headers, may contain ``${CRED_NAME}``
            placeholders that resolve against the agent's credential
            store.
        required: When ``True`` (default) a fetch failure fails the
            workflow; when ``False`` a ``[doc unavailable]`` marker is
            substituted in the planner prompt and the workflow
            proceeds on partial context. Use ``required=False`` for
            nice-to-have docs (a glossary, an FAQ); leave it ``True``
            for load-bearing rules.
        max_bytes: Per-doc truncation cap (default 16384). Larger
            responses are truncated with a ``[doc truncated]`` marker
            so a single oversized wiki page can't blow the planner's
            context window.
    """

    text: Optional[str] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    required: bool = True
    max_bytes: int = 16384

    def __post_init__(self) -> None:
        if (self.text is None) == (self.url is None):
            raise ValueError("Context: exactly one of text or url must be set")
        if self.url is not None and not isinstance(self.url, str):
            raise ValueError(f"Context.url must be a string; got {type(self.url).__name__}")
        if self.text is not None and not isinstance(self.text, str):
            raise ValueError(f"Context.text must be a string; got {type(self.text).__name__}")

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.text is not None:
            out["text"] = self.text
        if self.url is not None:
            out["url"] = self.url
            if self.headers:
                out["headers"] = dict(self.headers)
            if not self.required:
                out["required"] = False
            if self.max_bytes != 16384:
                out["maxBytes"] = self.max_bytes
        return out


@dataclass(frozen=True)
class Ref:
    """A reference to a prior step's whole output.

    Use ``Ref("step_id")`` anywhere a literal value would go in an ``Op.args``
    or a ``Generate.context`` to wire one step's output into another step's
    input — no JSON path, no field selection. The whole result map becomes
    the value at that arg key.

    The referenced step must be declared in this step's ``depends_on`` and
    must exist in the plan; the server rejects the plan at compile time
    otherwise (no silent broken refs).

    Multi-dep / parallel composition is the obvious thing: ``Ref("a")`` and
    ``Ref("b")`` resolve independently. For a parallel step, ``Ref("a")``
    is the array of branch results.

    Example::

        plan = Plan(steps=[
            Step("fetch", operations=[Op("fetch_data", args={"url": URL})]),
            Step(
                "summarize",
                depends_on=["fetch"],
                operations=[
                    Op("summarize", args={"document": Ref("fetch")}),
                ],
            ),
        ])
    """

    step_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.step_id, str) or not self.step_id:
            raise ValueError(f"Ref step_id must be a non-empty string, got: {self.step_id!r}")

    def to_dict(self) -> Dict[str, str]:
        """Wire format the server's PAC consumes: ``{"$ref": "<step_id>"}``."""
        return {"$ref": self.step_id}


def _serialize_value(v: Any) -> Any:
    """Walk an arg value tree and replace nested ``Ref`` objects with their
    JSON wire form. Lists and dicts are traversed; scalars pass through.
    """
    if isinstance(v, Ref):
        return v.to_dict()
    if isinstance(v, dict):
        return {k: _serialize_value(sub) for k, sub in v.items()}
    if isinstance(v, list):
        return [_serialize_value(item) for item in v]
    if isinstance(v, tuple):
        return [_serialize_value(item) for item in v]
    return v


@dataclass
class Generate:
    """LLM-generated arguments for a tool call inside a plan step.

    When an ``Op`` carries ``generate``, the server emits an LLM call at run
    time that produces the tool's args from these instructions, then runs
    the tool with the generated args. Use this when arg values aren't known
    at plan-construction time (e.g., the body of a ``write_file`` for a
    section the LLM should write).

    Attributes:
        instructions: What the LLM should produce.
        output_schema: A JSON-shape string the LLM's output is parsed into;
            becomes the tool's args. Example: ``'{"path": "out/intro.md",
            "content": "..."}'``.
        max_tokens: Optional cap on the LLM's response token count.
            Defaults to PAC's per-op default if omitted.
    """

    instructions: str
    output_schema: str
    max_tokens: Optional[int] = None
    context: Optional[Any] = None
    """Optional extra text appended to the LLM's user message. Accepts a
    plain string or a ``Ref(...)`` — when a ``Ref`` is passed, the server
    substitutes the upstream step's output at run time, so the LLM sees
    real values instead of the literal ``{"$ref":...}`` marker."""

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "instructions": self.instructions,
            "output_schema": self.output_schema,
        }
        if self.max_tokens is not None:
            out["max_tokens"] = self.max_tokens
        if self.context is not None:
            out["context"] = _serialize_value(self.context)
        return out


@dataclass
class Op:
    """A single tool invocation within a plan step.

    Exactly one of ``args`` or ``generate`` should be set. ``args`` runs
    the tool deterministically with literal values; ``generate`` defers
    arg construction to a per-op LLM call at run time.

    Attributes:
        tool: Tool name. Must be in the harness's ``tools`` list.
        args: Literal arg map for a deterministic call.
        generate: LLM-generated args (mutually exclusive with ``args``).
    """

    tool: str
    args: Optional[Dict[str, Any]] = None
    generate: Optional[Generate] = None

    def __post_init__(self) -> None:
        if (self.args is None) == (self.generate is None):
            raise ValueError(f"Op('{self.tool}'): exactly one of args or generate must be set")

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"tool": self.tool}
        if self.args is not None:
            # Walk for Ref(...) values; literal data passes through unchanged.
            out["args"] = _serialize_value(self.args)
        if self.generate is not None:
            out["generate"] = self.generate.to_dict()
        return out


@dataclass
class Step:
    """A node in the plan DAG.

    Steps run sequentially by default; ``depends_on`` overrides to express
    cross-step concurrency (a step starts when all listed deps complete).
    ``parallel=True`` runs the step's own ``operations`` concurrently
    (FORK_JOIN); without it, operations run in order within the step.

    Attributes:
        id: Unique identifier within the plan.
        operations: One or more ``Op`` entries to run.
        depends_on: Other step ids this step waits for.
        parallel: When True, run ``operations`` concurrently inside this step.
    """

    id: str
    operations: List[Op] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    parallel: bool = False

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": self.id,
            "operations": [op.to_dict() for op in self.operations],
        }
        if self.depends_on:
            out["depends_on"] = list(self.depends_on)
        if self.parallel:
            out["parallel"] = True
        return out


@dataclass
class Validation:
    """A post-execution check.

    Runs after all ``steps`` complete. PAC routes the workflow to
    ``on_success`` when every validation passes, else to ``on_failure``.

    Attributes:
        tool: Tool name. Must be in the harness's ``tools``.
        args: Literal arg map for the validator call.
        success_condition: Optional JS expression evaluated against the
            tool's output (``$`` is the parsed output map). Returns truthy
            on pass. When omitted, PAC checks that ``output.passed`` is
            not ``false`` and that the output is not an ``ERROR`` string.
    """

    tool: str
    args: Optional[Dict[str, Any]] = None
    success_condition: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"tool": self.tool}
        if self.args is not None:
            out["args"] = _serialize_value(self.args)
        if self.success_condition is not None:
            out["success_condition"] = self.success_condition
        return out


@dataclass
class Action:
    """A tool call attached to ``on_success`` or ``on_failure``.

    Same shape as a deterministic ``Op`` (``args`` only — no ``generate``,
    since success/failure handlers run with known context).
    """

    tool: str
    args: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"tool": self.tool}
        if self.args is not None:
            out["args"] = _serialize_value(self.args)
        return out


@dataclass
class Plan:
    """A compiled plan ready for ``Strategy.PLAN_EXECUTE`` execution.

    Construct directly in Python or pass to ``runtime.run(harness,
    plan=...)`` to skip the planner LLM and run a fully deterministic
    pipeline.

    Attributes:
        steps: The DAG of operations.
        validation: Optional post-execution checks.
        on_success: Tools to run when validation passes.
        on_failure: Tools to run when validation fails.
    """

    steps: List[Step] = field(default_factory=list)
    validation: List[Validation] = field(default_factory=list)
    on_success: List[Action] = field(default_factory=list)
    on_failure: List[Action] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"steps": [s.to_dict() for s in self.steps]}
        if self.validation:
            out["validation"] = [v.to_dict() for v in self.validation]
        if self.on_success:
            out["on_success"] = [a.to_dict() for a in self.on_success]
        if self.on_failure:
            out["on_failure"] = [a.to_dict() for a in self.on_failure]
        return out


# Public API — both the dataclasses and a lowercase alias for code readability.
PlanLike = Union[Plan, Dict[str, Any]]
"""Anything ``runtime.run(plan=...)`` accepts: a typed Plan or a raw dict."""


def coerce_plan(plan: PlanLike) -> Dict[str, Any]:
    """Normalize a Plan-or-dict into the dict shape PAC expects."""
    if isinstance(plan, Plan):
        return plan.to_dict()
    if isinstance(plan, dict):
        return plan
    raise TypeError(f"plan must be a Plan or a dict; got {type(plan).__name__}")


def plan_execute(
    name: str,
    *,
    tools: List[Any],
    planner_instructions: str = "",
    fallback_instructions: Optional[str] = None,
    model: Optional[str] = None,
    fallback_max_turns: Optional[int] = None,
    planner_context: Optional[List[Union[str, "Context"]]] = None,
) -> Any:
    """Construct a ``Strategy.PLAN_EXECUTE`` harness in one call.

    Wraps the boilerplate of building a planner sub-agent, an optional
    fallback sub-agent, and the parent coordinator. All ``Agent`` defaults
    apply unchanged — ``model`` falls back to the empty string (interpreted
    by Agent's existing resolution logic), ``max_turns`` / ``max_tokens``
    use Agent's defaults.

    Pass ``planner_instructions=""`` (or omit) when you intend to inject a
    static plan via ``runtime.run(harness, plan=...)``; the planner LLM
    will still run but its output is discarded by PAC's extract_json.

    Args:
        name: Harness name. Sub-agents are auto-named ``<name>_planner``
            and ``<name>_fallback``.
        tools: Canonical plan-executable tool set. PAC validates every
            ``op.tool`` against this list and propagates each tool's
            guardrails into the compiled plan.
        planner_instructions: Domain-level guidance for the planner. The
            server auto-appends a ``## Available tools`` block and a
            ``## Plan schema`` block; you don't need to repeat them.
        fallback_instructions: When non-empty, builds a fallback agent with
            the same ``tools`` set. Omit to leave the harness without a
            fallback (failures TERMINATE).
        model: LLM model string. When omitted, Agent's default applies.
        fallback_max_turns: Per-execution turn cap for the fallback agent
            during recovery; passed to ``Agent.fallback_max_turns``.

    Returns:
        An :class:`conductor.ai.agents.Agent` configured with
        ``strategy=Strategy.PLAN_EXECUTE``, ready for ``runtime.run``.
    """
    # Local import to avoid the agent.py ↔ plans.py circular at module
    # import time (plans.py is small and stable; agent.py is large and
    # pulls many transitive deps).
    from conductor.ai.agents.agent import Agent, Strategy

    planner_kwargs: Dict[str, Any] = {
        "name": f"{name}_planner",
        "instructions": planner_instructions,
    }
    if model is not None:
        planner_kwargs["model"] = model
    planner = Agent(**planner_kwargs)

    fallback = None
    if fallback_instructions:
        fb_kwargs: Dict[str, Any] = {
            "name": f"{name}_fallback",
            "instructions": fallback_instructions,
            "tools": tools,
        }
        if model is not None:
            fb_kwargs["model"] = model
        fallback = Agent(**fb_kwargs)

    harness_kwargs: Dict[str, Any] = {
        "name": name,
        "strategy": Strategy.PLAN_EXECUTE,
        "planner": planner,
        "tools": tools,
    }
    if fallback is not None:
        harness_kwargs["fallback"] = fallback
    if model is not None:
        harness_kwargs["model"] = model
    if fallback_max_turns is not None:
        harness_kwargs["fallback_max_turns"] = fallback_max_turns
    if planner_context is not None:
        harness_kwargs["planner_context"] = planner_context

    return Agent(**harness_kwargs)
