# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OCG (Open Context Graph) retrieval sub-agent.

OCG is a retrieval engine over a knowledge graph of entities (messages,
channels, people) linked by claims and relationships. This module is
the canonical — and only — definition of the OCG integration: system
prompt, tool schemas, endpoint routing, and instance binding all live
here. The tools compile to plain Conductor HTTP tasks (with path
templating); there is no OCG-specific server code at all.

Typical usage — delegate retrieval from a main agent::

    from conductor.ai.agents import Agent, agent_tool
    from conductor.ai.agents.ocg import ocg_agent

    retriever = ocg_agent(model="anthropic/claude-sonnet-4-6",
                          url="https://ocg.example.com",
                          credential="OCG_KEY")
    main = Agent(name="support", model="openai/gpt-4o",
                 tools=[agent_tool(retriever)], instructions="...")

Multi-instance (e.g. data residency) — bind each retriever to its own OCG::

    us = ocg_agent(name="ocg_us", model="anthropic/claude-sonnet-4-6",
                   url="https://us.ocg.example.com", credential="OCG_US_KEY")
    ca = ocg_agent(name="ocg_canada", model="anthropic/claude-sonnet-4-6",
                   url="https://ca.ocg.example.com", credential="OCG_CA_KEY")

``url`` is required — every OCG tool set binds the instance it talks to;
there is no server-side default. ``credential`` names an entry in the
server's credential store — the secret itself never appears in Python code
or serialized configs.

.. warning::
    Agents bound to **different** OCG instances must have **distinct**
    ``name``s: inline ``agent_tool`` child workflows are registered by agent
    name, so two differently-configured agents sharing a name overwrite each
    other's workflow definition.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from conductor.ai.agents.tool import ToolDef

if TYPE_CHECKING:
    from conductor.ai.agents.agent import Agent

# ── System prompt ───────────────────────────────────────────────────────
#
# ``${workflow.input.__today__}`` is substituted by Conductor when the LLM
# task is scheduled — the agent_tool dispatch script injects ``__today__``
# with the current UTC date on every call, so relative-date queries anchor
# on the real current date instead of one baked in at definition time.

OCG_SYSTEM_PROMPT = """\
Today's date is ${workflow.input.__today__} (UTC). DEFAULT: do NOT set
start_time or end_time — OMIT BOTH ENTIRELY. Searching the full history is
the norm, and an unrequested time range silently drops older context that
is usually exactly what you need. ONLY add a time range when the user
EXPLICITLY asks about a recent or time-bounded window ("recent", "last
week", "since Friday", "in May"); then anchor on today's date and set
start_time (and set end_time only for a window that closed in the past).
Timestamps must be full RFC3339 (2026-06-04T00:00:00Z); a bare date is
rejected. Never invent a range the user did not ask for.

You are querying an OCG (Open Context Graph). It is a RETRIEVAL
engine over a knowledge graph of entities (messages, channels, people)
linked by claims and relationships — embedding/keyword search, NOT an LLM.
It is NOT an aggregation engine and NOT a conversation partner: rephrasing
the same intent returns the same results.

RETRIEVAL BUDGET: make at most 3 queries total, each with a genuinely
DIFFERENT keyword set. Never repeat or lightly rephrase a query. When the
budget is spent — or results start repeating — STOP querying and answer
from what you have. Timestamps must be full RFC3339
(2026-06-04T00:00:00Z); a bare date is rejected.

It can answer:
  - "Find messages in channel X about Y"
  - "Show TIMED_OUT errors for cluster <name>"
  - "What entities mention 'health check failure'?"
  - "Recent messages in #cloud_saas_health_check_alerts"

It CANNOT directly answer (you must do it yourself in two steps):
  - "How many of X are there?" / "Which X is most frequent?"
  - "Group these by Y" / "Top N by count"
  - Statistical or comparative questions

RESPONSE SIZE: ALWAYS request max_results=100 — it is both the maximum and
the floor for getting decent context; NEVER use a small value like 10 or
25, which starves your answer. ALWAYS set traversal_level = 1 (never 0,
never higher). To focus results, sharpen the KEYWORDS — never by lowering
max_results or by adding an unrequested time range.

DIG DEEPER: the first ocg_query is only your entry point. After it returns,
pick the 1-3 MOST RELEVANT entities from the citations (the ones most on
point for the question) and call ocg_neighborhood on each — using the
entity ids from the citation rows — to pull in their linked entities
(related tickets, incidents, sub-workflows, prior fixes). The actual fix
very often lives one hop away in a linked entity, not in the first page of
citations. Do not answer from the initial citations alone when a clearly
relevant entity is worth expanding.

For aggregation questions, use a TWO-STEP pattern:
  1. RETRIEVE: ask OCG for the relevant entities.
     - Use specific terms (cluster names, error codes, channel names).
     - Use start_time (and end_time only for windows closed in the
       past) to bound the range.
     - Avoid hedging words ("frequently", "across", "occurrences") —
       OCG ranks by keyword presence, and these are noise tokens.
  2. AGGREGATE: count, group, rank yourself from the citation list.

Query length: keep it under ~15 content words. Long prompts dilute the
BM25 keyword set; OCG's parser is extracting things like "happen",
"identify", "top one" which are not real signal.

Bad:  "Across all clusters, what alert/notification/error type appears
       most frequently? Group similar alerts and tell me which one has
       the highest count and how many clusters it affected."

Good (step 1): {
  "query": "TIMED_OUT health check failure cluster",
  "max_results": 100
}
(no start_time/end_time — the query runs across the full history.)
Then parse the returned citations, extract cluster names from titles,
build the frequency table in your reasoning."""


# ── JSON-schema helpers ─────────────────────────────────────────────────


def _prop(type_: str, description: str, default: Any = None) -> Dict[str, Any]:
    schema: Dict[str, Any] = {"type": type_, "description": description}
    if default is not None:
        schema["default"] = default
    return schema


def _array(item_type: str, description: str) -> Dict[str, Any]:
    return {"type": "array", "description": description, "items": {"type": item_type}}


def _object(properties: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
    schema: Dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


# ── Tool definitions ────────────────────────────────────────────────────


def _query_tool() -> Dict[str, Any]:
    return {
        "name": "ocg_query",
        "method": "POST",
        "path": "/api/v1/agent/query",
        "description": (
            "Query the Open Context Graph for structured retrieval. "
            "Returns citations (source_item_id, title, container_id, snippet) "
            "and traversal_results when traversal_level > 0."
        ),
        "schema": _object(
            {
                "query": _prop("string", "Natural-language retrieval query."),
                "max_results": {
                    "type": "integer",
                    "description": "Max citations to return. ALWAYS use 100 — it is both "
                    "the hard maximum and the floor for getting decent context; never "
                    "request fewer.",
                    "default": 100,
                    "minimum": 100,
                    "maximum": 100,
                },
                "traversal_level": {
                    "type": "integer",
                    "description": "ALWAYS 1 — pulls each citation's immediate neighborhood "
                    "in alongside it. Never 0 (too shallow) and never higher (dig deeper by "
                    "calling ocg_neighborhood on the most relevant entities, not by raising "
                    "this).",
                    "default": 1,
                    "minimum": 1,
                    "maximum": 1,
                },
                "start_time": _prop(
                    "string",
                    "LEAVE UNSET by default — omit it so the search covers the FULL "
                    "history. Set this ONLY when the user EXPLICITLY asked about a recent "
                    "or time-bounded window (e.g. 'last week', 'since Friday'). RFC3339 "
                    "lower bound (inclusive), e.g. 2026-06-04T00:00:00Z; a bare date like "
                    "2026-06-04 is REJECTED.",
                ),
                "end_time": _prop(
                    "string",
                    "LEAVE UNSET by default. Set this ONLY for a window the user said has "
                    "CLOSED in the past; for anything running through now, omit it. RFC3339 "
                    "upper bound (exclusive), e.g. 2026-06-11T00:00:00Z; a bare date is "
                    "REJECTED.",
                ),
            },
            ["query"],
        ),
    }


def _get_entity_tool() -> Dict[str, Any]:
    return {
        "name": "ocg_get_entity",
        "method": "GET",
        "path": "/api/v1/entities/{entity_id}",
        "description": "Fetch one entity by its canonical id.",
        "schema": _object(
            {"entity_id": _prop("string", "Canonical entity id from an ocg_query result row.")},
            ["entity_id"],
        ),
    }


def _neighborhood_tool() -> Dict[str, Any]:
    return {
        "name": "ocg_neighborhood",
        "method": "GET",
        "path": "/api/v1/graph/neighborhood/{entity_id}",
        "query_params": ["depth", "limit"],
        "description": (
            "Get an entity plus its graph neighbors out to `depth` hops. "
            "Use limit <= 10, depth=1 on the first call — well-connected "
            "entities can have many edges and large responses will be truncated."
        ),
        "schema": _object(
            {
                "entity_id": _prop("string", "Entity at the center of the neighborhood."),
                "depth": _prop("integer", "Hop depth (use depth=1 on first call).", 1),
                "limit": _prop(
                    "integer", "Cap on neighbors returned (use <= 10 on first call).", 50
                ),
            },
            ["entity_id"],
        ),
    }


def _memory_set_tool() -> Dict[str, Any]:
    return {
        "name": "ocg_memory_set",
        "method": "POST",
        "path": "/api/v1/memories",
        "description": (
            "Create or overwrite a memory in OCG. Cap inferred confidence at 0.7; "
            "never write PII or secrets."
        ),
        "schema": _object(
            {
                "key": _prop("string", "Memory key."),
                "agent": _prop("string", 'Agent owner (e.g. "agent:<name>").'),
                "user": _prop("string", 'User owner (e.g. "user:<name>").'),
                "string_value": _prop("string", "Stored value."),
                "description": _prop("string", "Human-readable description."),
                "scope": _prop(
                    "string",
                    "Memory scope. One of MEMORY_SCOPE_SESSION, MEMORY_SCOPE_AGENT, "
                    "MEMORY_SCOPE_USER, MEMORY_SCOPE_SHARED, MEMORY_SCOPE_GLOBAL.",
                    "MEMORY_SCOPE_USER",
                ),
                "confidence": _prop("number", "Inferred confidence in [0,1]. Cap at 0.7.", 0.7),
                "source_ref": _prop("string", "Free-form source reference (e.g. message id)."),
                "evidence_ids": _array("string", "Supporting evidence entity ids."),
                "tags": _array("string", "Tags."),
                "expires_at": _prop("string", "ISO-8601 expiry. Optional — default 180 days."),
                "idempotency_key": _prop("string", "Idempotency key. Optional."),
            },
            ["key", "agent", "user", "string_value", "description"],
        ),
    }


def _memory_reinforce_tool() -> Dict[str, Any]:
    return {
        "name": "ocg_memory_reinforce",
        "method": "POST",
        "path": "/api/v1/memories/{key}/reinforce",
        "description": (
            "Reinforce an existing memory on independent re-observation. confidence_boost must be <= 0.05."
        ),
        "schema": _object(
            {
                "key": _prop("string", "Memory key."),
                "agent": _prop("string", "Agent owner."),
                "user": _prop("string", "User owner."),
                "confidence_boost": _prop(
                    "number", "Boost to add (must be <= 0.05 to prevent compounding drift).", 0.05
                ),
                "source_ref": _prop("string", "Free-form source reference."),
            },
            ["key", "agent", "user"],
        ),
    }


def _memory_delete_tool() -> Dict[str, Any]:
    return {
        "name": "ocg_memory_delete",
        "method": "DELETE",
        "path": "/api/v1/memories/{key}",
        "query_params": ["agent", "user"],
        "description": (
            "Delete a memory by key. Prefer ocg_memory_set with a corrected value "
            "over deletion (preserves history)."
        ),
        "schema": _object(
            {
                "key": _prop("string", "Memory key."),
                "agent": _prop("string", "Agent owner."),
                "user": _prop("string", "User owner."),
            },
            ["key", "agent", "user"],
        ),
    }


# ── Public factories ────────────────────────────────────────────────────


def ocg_tools(
    *,
    url: str,
    credential: Optional[str] = None,
    query: bool = True,
    entities: bool = True,
    memory: bool = True,
) -> List[ToolDef]:
    """Build the raw OCG :class:`ToolDef` list for a custom retrieval agent.

    Each tool is a plain Conductor HTTP task: the compile bakes the
    instance URL, endpoint path template, and auth header into the tool's
    dispatch config, and the LLM's arguments fill the path/query/body at
    call time. No OCG-specific code runs server-side.

    Args:
        url: Base URL of the OCG instance this tool set targets. Required —
            there is no server-side default instance.
        credential: Name of a credential-store entry holding the OCG bearer
            token. The server resolves it at execution time — the secret
            never appears in the serialized config.
        query: Include ``ocg_query``.
        entities: Include ``ocg_get_entity`` + ``ocg_neighborhood``.
        memory: Include ``ocg_memory_set`` / ``ocg_memory_reinforce`` /
            ``ocg_memory_delete``.

    Raises:
        ValueError: If ``url`` is blank.
    """
    if not url or not url.strip():
        raise ValueError(
            "ocg_tools() requires a non-blank url: every OCG tool set binds its own instance."
        )

    base_url = url.strip().rstrip("/")
    headers: Dict[str, str] = {}
    credentials: List[str] = []
    if credential:
        # Standard http-tool placeholder — resolved server-side from the
        # credential store at execution; the token never appears here.
        headers["Authorization"] = "Bearer ${" + credential + "}"
        credentials = [credential]

    selected: List[Dict[str, Any]] = []
    if query:
        selected.append(_query_tool())
    if entities:
        selected.append(_get_entity_tool())
        selected.append(_neighborhood_tool())
    if memory:
        selected.append(_memory_set_tool())
        selected.append(_memory_reinforce_tool())
        selected.append(_memory_delete_tool())

    tools: List[ToolDef] = []
    for spec in selected:
        config: Dict[str, Any] = {
            "url": base_url,
            "method": spec["method"],
            "pathTemplate": spec["path"],
        }
        if spec.get("query_params"):
            config["queryParams"] = list(spec["query_params"])
        if headers:
            config["headers"] = dict(headers)
        tools.append(
            ToolDef(
                name=spec["name"],
                description=spec["description"],
                input_schema=spec["schema"],
                tool_type="http",
                config=config,
                credentials=list(credentials),
            )
        )
    return tools


def ocg_agent(
    *,
    model: str,
    url: str,
    name: str = "ocg_agent",
    credential: Optional[str] = None,
    instructions: Optional[str] = None,
    max_turns: int = 10,
    query: bool = True,
    entities: bool = True,
    memory: bool = True,
) -> "Agent":
    """Build the prebuilt OCG retrieval :class:`Agent`.

    Returns an ordinary :class:`Agent` — wrap it with :func:`agent_tool` to
    let a main agent delegate retrieval, or use it as a pipeline stage to
    retrieve before the main agent runs.

    Args:
        model: LLM for the retrieval agent's own turns (required — the right
            model depends on cost/latency targets and the OCG corpus).
        url: OCG instance base URL (required — no server-side default).
        name: Agent name. **Must be distinct per OCG instance** — child
            workflows are registered by agent name (see module warning).
        credential: Credential-store entry for the instance's bearer token.
        instructions: Override the canned :data:`OCG_SYSTEM_PROMPT`.
        max_turns: Retrieval loop budget.
        query / entities / memory: Tool subset switches, forwarded to
            :func:`ocg_tools`.
    """
    from conductor.ai.agents.agent import Agent

    return Agent(
        name=name,
        model=model,
        instructions=instructions if instructions is not None else OCG_SYSTEM_PROMPT,
        tools=ocg_tools(
            url=url,
            credential=credential,
            query=query,
            entities=entities,
            memory=memory,
        ),
        max_turns=max_turns,
    )
