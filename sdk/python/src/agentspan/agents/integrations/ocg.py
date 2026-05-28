# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Orkes Open Context Graph (OCG) integration.

Provides a self-contained sub-agent (`ocg_agent`) and a set of `@tool`
functions that any parent agent can use for codebase/docs retrieval against
a running OCG deployment.

Usage::

    from agentspan.agents import Agent, agent_tool
    from agentspan.agents.integrations.ocg import ocg_agent

    ocg = agent_tool(
        ocg_agent,
        name="ocg",
        description="OCG retrieval. Pass a natural-language request.",
    )

    coder = Agent(
        name="coder",
        model="anthropic/claude-sonnet-4-20250514",
        tools=[ocg, *your_other_tools],
        ...,
    )

Environment:
    OCG_BASE_URL    default ``http://localhost:6100/api/v1``
    OCG_API_KEY     optional Bearer token
    OCG_TENANT_ID   default ``"default"``

The tool responses are projected to a compact, LLM-friendly shape (entities,
claims, relationships, citations) - the raw OCG body (full base64 blobs,
rendered narrative answers) is stripped, but the citation envelope is
preserved so the agent can traverse the graph to resolve fragments.
"""

from __future__ import annotations

import json as _json_mod
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from agentspan.agents import Agent, tool


# --- OCG HTTP client --------------------------------------------------------

_DEFAULT_BASE_URL = "https://dev.orkescontextgraph.io/api/v1"
_DEFAULT_TENANT = "default"


def _ocg_base_url() -> str:
    return os.environ.get("OCG_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def _ocg_headers() -> Dict[str, str]:
    headers = {
        "X-Tenant-ID": os.environ.get("OCG_TENANT_ID", _DEFAULT_TENANT),
        "Content-Type": "application/json",
    }
    api_key = os.environ.get("OCG_API_KEY")
    if api_key:
        headers["X-Api-Key"] = api_key
    return headers


# Bounds on what we return to the LLM. Each endpoint projects to the fields
# the LLM uses; the projection drops the full base64 content / rendered
# narrative / citation envelope. A hard byte cap is the safety net.
_OCG_RESPONSE_BYTE_CAP = int(os.environ.get("OCG_RESPONSE_BYTE_CAP", "24000"))
_OCG_STRING_CAP = int(os.environ.get("OCG_STRING_CAP", "400"))
_OCG_ARRAY_CAP = int(os.environ.get("OCG_ARRAY_CAP", "30"))


def _clip(s: Any, limit: int = _OCG_STRING_CAP) -> Any:
    if not isinstance(s, str) or len(s) <= limit:
        return s
    return s[:limit] + f"...[+{len(s) - limit}]"


def _cap_array(items: List[Any], limit: int = _OCG_ARRAY_CAP) -> List[Any]:
    if len(items) <= limit:
        return items
    return items[:limit] + [{"_truncated": True, "_omitted": len(items) - limit}]


def _enforce_response_cap(obj: Any) -> Any:
    """Final safety net: if rendered JSON still exceeds the byte cap, drop
    the body and return a compact descriptor."""
    rendered = _json_mod.dumps(obj, default=str)
    if len(rendered) <= _OCG_RESPONSE_BYTE_CAP:
        return obj
    return {
        "_truncated": True,
        "_reason": f"projection still > {_OCG_RESPONSE_BYTE_CAP} bytes",
        "_size_bytes": len(rendered),
        "_preview": rendered[:1500] + "...",
        "_hint": "narrow the query / drop depth / lower limit",
    }


def _ocg_request(
    method: str,
    path: str,
    json: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Single shared HTTP path for every OCG tool.

    On 2xx returns the parsed JSON body. On non-2xx returns a structured
    error the LLM can read and recover from rather than raising.
    """
    url = f"{_ocg_base_url()}{path}"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.request(
                method, url, headers=_ocg_headers(), json=json, params=params
            )
    except httpx.HTTPError as exc:
        return {"error": "transport", "message": str(exc), "endpoint": path}

    if 200 <= resp.status_code < 300:
        if not resp.content:
            return {"ok": True, "status_code": resp.status_code, "endpoint": path}
        try:
            return resp.json()
        except ValueError:
            return {"error": "decode", "message": resp.text[:500], "endpoint": path}

    return {
        "error": resp.status_code,
        "message": resp.text[:500],
        "endpoint": path,
    }


# --- Projections (raw OCG response -> compact LLM-visible shape) ------------

def _project_query(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict) or "error" in raw:
        return raw

    md = raw.get("metadata") or {}
    out: Dict[str, Any] = {
        "confidence": md.get("confidence"),
        "result_quality": md.get("result_quality"),
        "items_in_result": md.get("items_in_result"),
    }
    for opt in ("intent", "conflicts", "truncated"):
        if md.get(opt):
            out[opt] = md.get(opt)

    # Citations — the primary input for graph-level traversal. Each citation
    # has a source_item_id the agent can pass to ocg_neighborhood to walk up
    # to the containing resource.
    citations_raw = (raw.get("output") or {}).get("citations") or []
    if citations_raw:
        citations = []
        for c in citations_raw:
            citations.append({
                "container_id": c.get("container_id"),
                "source_item_id": c.get("source_item_id"),
                "title": _clip(c.get("title"), 200),
                "snippet": _clip(c.get("snippet"), 300),
            })
        out["citations"] = _cap_array(citations, 10)

    blocks = ((raw.get("output") or {}).get("content") or {}).get("blocks") or []
    for block in blocks:
        btype = block.get("type")
        title = (block.get("title") or "").strip()

        if btype == "table" and title == "Matching Entities":
            entities = []
            for row in block.get("rows") or []:
                entities.append({
                    "id": row.get("id"),
                    "external_id": row.get("external_id") or None,
                    "name": row.get("name"),
                    "type": row.get("type"),
                    "description": _clip(row.get("description"), 300),
                })
            out["entities"] = _cap_array(entities)

        elif btype == "table" and title == "Key Facts":
            claims = []
            for row in block.get("rows") or []:
                conf = row.get("confidence")
                if isinstance(conf, str) and conf.strip("%") in ("0", "0.0"):
                    continue
                claims.append({
                    "entity": row.get("entity"),
                    "predicate": row.get("predicate"),
                    "value": _clip(row.get("value"), 300),
                    "confidence": conf,
                    "freshness": row.get("freshness"),
                })
            if claims:
                out["claims"] = _cap_array(claims)

        elif btype == "table" and title == "Relationships":
            rels = []
            for row in block.get("rows") or []:
                rels.append({
                    "source": row.get("source"),
                    "type": row.get("type"),
                    "target": row.get("target"),
                    "confidence": row.get("confidence"),
                })
            if rels:
                out["relationships"] = _cap_array(rels)

    return out


def _project_neighborhood(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict) or "error" in raw:
        return raw
    nodes = []
    for n in raw.get("nodes") or []:
        props = n.get("properties") or {}
        nodes.append({
            "id": n.get("id"),
            # container_id / node_type — what kind of entity this is.
            # Used by the agent to decide "self-contained resource vs fragment".
            "container_id": n.get("container_id") or n.get("node_type"),
            # external_id is typically the file path or resource locator.
            "external_id": n.get("external_id") or props.get("external_id") or None,
            "label": n.get("label"),
            "depth": n.get("depth"),
            "description": _clip(props.get("description"), 200),
        })
    links = []
    for l in raw.get("links") or []:
        links.append({
            "source": l.get("source"),
            "target": l.get("target"),
            "edge_type": l.get("edge_type"),
        })
    return {
        "center_id": raw.get("center_id"),
        "depth": raw.get("depth"),
        "nodes": _cap_array(nodes),
        # links[] includes both inbound and outbound edges.
        # To find the containing resource: filter where target == center_id
        # and edge_type implies containment (contains / declares / defines / owns).
        "links": _cap_array(links),
    }


def _project_entity(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict) or "error" in raw:
        return raw

    claims = []
    for c in raw.get("claims") or []:
        conf = c.get("confidence")
        try:
            conf_num = float(str(conf).strip("%")) if conf else 0
            if conf_num <= 1:
                conf_num *= 100
        except (TypeError, ValueError):
            conf_num = 0
        if conf_num < 50:
            continue
        claims.append({
            "predicate": c.get("predicate"),
            "value": _clip(c.get("value"), 300),
            "confidence": conf,
        })

    out = {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "type": raw.get("type"),
        "external_id": raw.get("external_id") or None,
        "description": _clip(raw.get("description"), 400),
    }
    if raw.get("labels"):
        out["labels"] = raw["labels"]
    if raw.get("aliases"):
        out["aliases"] = raw["aliases"]
    if claims:
        out["claims"] = _cap_array(claims)
    return out


def _project_code_history(raw: Any) -> Any:
    if isinstance(raw, dict) and "error" in raw:
        return raw
    items = raw if isinstance(raw, list) else (raw.get("commits") if isinstance(raw, dict) else None)
    if not isinstance(items, list):
        return raw
    out = []
    for c in items:
        if not isinstance(c, dict):
            continue
        sha = c.get("commit_sha") or c.get("sha") or ""
        out.append({
            "sha": sha[:10] if isinstance(sha, str) else sha,
            "author": c.get("author"),
            "timestamp": c.get("timestamp"),
            "message": _clip(c.get("message"), 200),
            "lines_added": c.get("lines_added"),
            "lines_removed": c.get("lines_removed"),
        })
    return _cap_array(out)


# --- OCG read tools ---------------------------------------------------------

@tool(timeout_seconds=30)
def ocg_query(query: str, max_results: int = 10, traversal_level: int = 1) -> dict:
    """Query the Open Context Graph for structured retrieval.

    traversal_level: 0 = citations only, 1 = include graph neighborhood (default),
    2-3 = multi-hop traversal (expensive, use sparingly).

    Returns citations[] (source_item_id, title, container_id, snippet) and
    traversal_results[] when traversal_level > 0.
    """
    raw = _ocg_request(
        "POST",
        "/agent/query",
        json={
            "query": query,
            "max_results": max_results,
            "traversal_level": traversal_level,
        },
    )
    return _enforce_response_cap(_project_query(raw))


@tool(timeout_seconds=15)
def ocg_get_entity(entity_id: str) -> dict:
    """Fetch one entity by its canonical id (from an ocg_query result row)."""
    raw = _ocg_request("GET", f"/entities/{entity_id}")
    return _enforce_response_cap(_project_entity(raw))


@tool(timeout_seconds=20)
def ocg_neighborhood(entity_id: str, depth: int = 2, limit: int = 50) -> dict:
    """Get an entity plus its graph neighbors out to `depth` hops.

    Use ``limit <= 10, depth=1`` on the first call - well-connected entities
    can have many edges and large responses will be truncated.
    """
    raw = _ocg_request(
        "GET",
        f"/graph/neighborhood/{entity_id}",
        params={"depth": depth, "limit": limit},
    )
    return _enforce_response_cap(_project_neighborhood(raw))


@tool(timeout_seconds=15)
def ocg_code_history(repo_id: str, path: str, limit: int = 20) -> dict:
    """Last N commits that touched a file in an ingested repo."""
    raw = _ocg_request(
        "GET",
        f"/code/history/{repo_id}",
        params={"path": path, "limit": limit},
    )
    return _enforce_response_cap(_project_code_history(raw))


# --- OCG memory write tools -------------------------------------------------

_VALID_MEMORY_SCOPES = {
    "MEMORY_SCOPE_SESSION",
    "MEMORY_SCOPE_AGENT",
    "MEMORY_SCOPE_USER",
    "MEMORY_SCOPE_SHARED",
    "MEMORY_SCOPE_GLOBAL",
}


def _default_expires_at(days: int = 180) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


@tool(timeout_seconds=20)
def ocg_memory_set(
    key: str,
    agent: str,
    user: str,
    string_value: str,
    description: str,
    scope: str = "MEMORY_SCOPE_USER",
    confidence: float = 0.7,
    source_ref: str = "",
    evidence_ids: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    expires_at: str = "",
    idempotency_key: str = "",
) -> dict:
    """Create or overwrite a memory in OCG.

    `agent` should look like ``"agent:<name>"``; `user` like ``"user:<name>"``.
    `scope` must be one of the MEMORY_SCOPE_* enum values. Cap inferred
    confidence at 0.7; never write PII or secrets.
    """
    if scope not in _VALID_MEMORY_SCOPES:
        return {
            "error": "invalid_scope",
            "message": f"scope must be one of {sorted(_VALID_MEMORY_SCOPES)}",
        }
    if not 0.0 <= confidence <= 1.0:
        return {"error": "invalid_confidence", "message": "confidence must be 0..1"}

    body: Dict[str, Any] = {
        "key": key,
        "agent": agent,
        "user": user,
        "string_value": string_value,
        "description": description,
        "scope": scope,
        "confidence": confidence,
        "source": "MEMORY_SOURCE_AGENT_INFERRED",
        "idempotency_key": idempotency_key or f"{agent}|{user}|{key}",
        "expires_at": expires_at or _default_expires_at(),
    }
    if source_ref:
        body["source_ref"] = source_ref
    if evidence_ids:
        body["evidence_ids"] = evidence_ids
    if tags:
        body["tags"] = tags

    return _ocg_request("POST", "/memories", json=body)


@tool(timeout_seconds=15)
def ocg_memory_reinforce(
    key: str,
    agent: str,
    user: str,
    confidence_boost: float = 0.05,
    source_ref: str = "",
) -> dict:
    """Reinforce an existing memory (only on independent re-observation).

    `confidence_boost` compounds; keep <= 0.05.
    """
    if confidence_boost > 0.05:
        return {
            "error": "boost_too_high",
            "message": "confidence_boost must be <= 0.05 to prevent compounding drift",
        }
    body: Dict[str, Any] = {"agent": agent, "user": user}
    if confidence_boost:
        body["confidence_boost"] = confidence_boost
    if source_ref:
        body["source_ref"] = source_ref
    return _ocg_request("POST", f"/memories/{key}/reinforce", json=body)


@tool(timeout_seconds=15)
def ocg_memory_delete(key: str, agent: str, user: str) -> dict:
    """Delete a memory by key. Prefer `ocg_memory_set` with a corrected
    value over deletion (preserves history)."""
    return _ocg_request(
        "DELETE",
        f"/memories/{key}",
        params={"agent": agent, "user": user},
    )


OCG_TOOLS = [
    ocg_query,
    ocg_get_entity,
    ocg_neighborhood,
    ocg_code_history,
    ocg_memory_set,
    ocg_memory_reinforce,
    ocg_memory_delete,
]


# --- The OCG specialist sub-agent ------------------------------------------

_OCG_INSTRUCTIONS = """\
You are the OCG retrieval specialist. The parent agent gives you ONE
natural-language `request` and expects ONE focused answer. OCG is your ONLY
source of truth — no filesystem, no URLs, no other tools exist for you.

=== HOW OCG RANKS (shape your queries) ===
The NL parser infers `type_hints` from NOUNS in your query:
   "X variable"              -> type_hints: [variable]
   "X function"              -> type_hints: [function]
   "documentation files about X" -> type_hints: [file, variable]
   "the X struct"            -> type_hints: [struct]
   "tests for X"             -> type_hints: [test]

Type_hints are a hard filter, not a re-rank weight. Picking the right noun
decides which entity-type bucket results come from. Literal identifiers
(e.g. AGENTSPAN_LOG_LEVEL) can HURT retrieval — they're indexed as claim
values, not symbol names.

=== QUERY SHAPES (retry palette — never reuse the same shape twice) ===
  SHAPE-LITERAL    "where is <IDENTIFIER> defined in <repo>"
  SHAPE-CATEGORY   "<conceptual category> <topic> in <repo>"
  SHAPE-FILE       "documentation files about <topic>" / "files containing X"
  SHAPE-SYMBOL     "<symbol_name>" or "<symbol_name> in <scope>"
  SHAPE-RELATION   "what calls <X>" / "what tests <X>" / "what uses <X>"

=== YOUR PROCEDURE ===

── STEP 1: QUERY ──────────────────────────────────────────────────────────
Call ocg_query with the best shape:
  - SHAPE-LITERAL  if the request has a clear literal (UPPER_SNAKE, CamelCase)
  - SHAPE-FILE     if the parent wants a docs or config file path
  - SHAPE-CATEGORY otherwise

For documentation/file-location tasks, run enough independent shapes to avoid
overfitting to the first plausible hit:
  - Always try at least one SHAPE-FILE query.
  - If the request names a literal identifier, also try SHAPE-LITERAL unless
    SHAPE-FILE already returns a high-confidence self-contained file path.
  - If the first resolved file is narrow (e.g. self-hosting, install-only,
    vendor-specific) and the request is broad (configuration, environment
    variables, SDK behavior), try SHAPE-CATEGORY or SHAPE-RELATION before
    finalizing.

Default max_results is 50. If a query returns no self-contained file paths
after traversal, retry the same or different shape with max_results=200 to
expand citation coverage before giving up.

You may make up to 4 ocg_query calls total. Never reuse the same shape.

── STEP 2: CLASSIFY EACH CITATION ─────────────────────────────────────────
For each citation in citations[], reason as a human:

  Self-contained resource (use directly):
    - title is a standalone artifact name, not an inner label
    - container_id or title looks like a real file/resource, not a section key
    - snippet describes the entity in its own terms

  Fragment (needs traversal):
    - title is a section heading, a key path, or a symbol identifier
    - snippet says "in X" / "from X" / "part of X"
    - container_id/title looks like a fragment identifier, not a file/resource

If self-contained → record it as a resolved resource, skip to STEP 4.
If fragment → go to STEP 3.

── STEP 3: WALK UP THE GRAPH (per fragment, max 3 hops) ───────────────────
Call ocg_neighborhood(entity_id=<source_item_id>, depth=1, limit=20).

In links[], find inbound edges where target == this entity's id. Among those
inbound edges, pick the one whose edge_type semantically means containment
(e.g. "contains", "declares", "defines", "owns", "part_of" — use judgment,
not a hardcoded list). Never pick the first edge blindly; read the semantics.

The source of that containment edge is the parent. Read that node from
nodes[] to get its container_id, external_id, and label.

Apply STEP 2 reasoning to the parent:
  - Self-contained → stop, record this as the resolved resource.
  - Still a fragment → recurse from parent's id (cap at 3 hops total).
  - No usable inbound edge → report "no containing resource found for <id>."

Never invent identifiers. Never trust a citation's external_id as a file
path without verifying it looks like one. Snippet prose may mention a parent
in natural language — ignore it; only the graph edges are authoritative.

── STEP 4: DEDUPLICATE AND RANK ───────────────────────────────────────────
Multiple citations may resolve to the same parent entity. Collapse them into
one result entry. Nine fragments inside the same document → 1 cited resource.

Do not stop at the first resolved file. Resolve and rank the useful candidates
you have evidence for, then choose `primary_path`.

Ranking rules for documentation tasks:
  1. Prefer public docs pages whose path/title matches the requested scope
     (configuration, deployment, environment variables, SDK behavior).
  2. Prefer broader docs files over narrow topic pages when the parent asks
     where to add general documentation.
  3. Prefer files with direct evidence that they already contain nearby config
     tables, environment-variable references, or the named identifier.
  4. Only choose a narrow file (self-hosting, install-only, provider-specific)
     when no broader candidate is supported by OCG evidence.

── STEP 5: WRITE FINAL TEXT (required — never leave the parent waiting) ───
Budget: at most 4 queries + targeted neighborhood traversal for high-signal
citations. You MUST produce text on or before turn 14. If you haven't found a
result by then, write `status: no_match` immediately — an empty finish costs
the parent ~50K tokens per re-attempt.

=== TOOL RESPONSE SHAPES ===
ocg_query:       {confidence, result_quality, items_in_result, intent?,
                  conflicts?, citations: [{container_id, source_item_id,
                  title, snippet}], entities: [...], claims: [...],
                  relationships: [...]}
ocg_neighborhood:{center_id, depth,
                  nodes: [{id, container_id, external_id, label, depth,
                           description}],
                  links: [{source, target, edge_type}]}
ocg_get_entity:  {id, name, type, external_id, description, labels,
                  aliases, claims: [{predicate, value, confidence}]}

external_id is typically the file path. confidence < 0.5 = trust nothing.

=== FINAL RESPONSE FORMAT ===

Match found:
  status:        match
  primary_path:  <resolved file path, or "(not indexed)">
  entity_id:     <entity id of the resolved resource>
  entity_name:   <name>
  entity_type:   <container_id / type>
  confidence:    <0.0-1.0 from the query>
  shape_used:    <SHAPE-* that produced this result>
  traversal:     <"direct" | "N hop(s) up from <fragment_title>">
  candidate_paths:<ranked paths considered, with one short reason each>
  summary:       <one paragraph — key facts OCG returned>
  drill_ids:     <other relevant entity ids the parent could query>

No match (after up to 4 shapes attempted):
  status:        no_match
  shapes_tried:  <e.g. "SHAPE-LITERAL (conf 0.39), SHAPE-FILE (conf 0.51)">
  best_seen:     <best (confidence, entity_name) across attempts, if any>
  reason:        <one sentence — what OCG kept returning that didn't match>

No preamble, no narrative, no advice for the parent. Structured data only.

=== MEMORY WRITES (optional, only on independent re-observation) ===
ocg_memory_reinforce when you've re-observed a fact; ocg_memory_set for
new/corrected facts. Cap inferred confidence at 0.7. Always
agent='agent:ocg_agent'. Never write PII, secrets, transcripts, or facts
that contradict a high-confidence connector claim.
"""


ocg_agent = Agent(
    name="ocg_agent",
    model="anthropic/claude-sonnet-4-20250514",
    tools=OCG_TOOLS,
    instructions=_OCG_INSTRUCTIONS,
    thinking_budget_tokens=1024,
    max_tokens=4096,
    max_turns=25,  # up to 4 queries + targeted citation traversal + final text
    timeout_seconds=300,
)


__all__ = [
    "ocg_agent",
    "OCG_TOOLS",
    "ocg_query",
    "ocg_get_entity",
    "ocg_neighborhood",
    "ocg_code_history",
    "ocg_memory_set",
    "ocg_memory_reinforce",
    "ocg_memory_delete",
]
