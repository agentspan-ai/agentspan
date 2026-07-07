# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OCG-backed long-term memory for agents.

This module backs agentspan's :class:`~conductor.ai.agents.semantic_memory.MemoryStore`
abstraction with an OCG (Open Context Graph) instance, so an agent's memories
persist in OCG and ride OCG's feedback-aware ranking.

Three pieces:

- :class:`OCGMemoryStore` — a synchronous HTTP adapter implementing ``MemoryStore``
  (``add`` / ``search`` / ``delete`` / ``clear`` / ``list_all``) against the OCG BFF.
- :class:`MemorySummary` + :func:`build_memory_summarizer` — a small agent that
  distills a conversation into durable facts (used by the runtime's post-run save).
- :class:`FeedbackEvent` — what the runtime hands to an Agent's ``feedback_sink``
  after saving a memory: the distilled summary plus signed *capability URLs* a human
  can click to mark the memory good/bad (no OCG account needed).

Design notes:

- The OCG bearer ``token`` is held **client-side** here (e.g. from ``OCG_TOKEN``),
  unlike the ``ocg.py`` retrieval tools which resolve a credential server-side.
- Agents only ever **create and read** memories. Good/bad feedback is human-only:
  it is delivered out-of-band through ``feedback_sink`` (e.g. into a Zendesk ticket)
  and the capability URLs are never surfaced to the agent's LLM.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import httpx

from conductor.ai.agents.exceptions import AgentAPIError
from conductor.ai.agents.semantic_memory import MemoryEntry, MemoryStore

if TYPE_CHECKING:
    from conductor.ai.agents.agent import Agent

logger = logging.getLogger("conductor.ai.agents.ocg_memory")


def _hash_key(content: str) -> str:
    return "mem-" + hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


class OCGMemoryStore(MemoryStore):
    """Back agentspan :class:`SemanticMemory` with an OCG instance.

    Implements the synchronous ``MemoryStore`` interface over the OCG BFF:

    - ``add``     -> ``POST   /api/v1/memories``
    - ``search``  -> ``POST   /api/v1/memories/search`` (feedback-blended ranking)
    - ``delete``  -> ``DELETE /api/v1/memories/{key}``
    - ``list_all``-> ``GET    /api/v1/memories``

    Args:
        url: Base URL of the OCG instance (required).
        agent: Agent owner key, e.g. ``"agent:support"`` (required).
        user: Optional user owner, e.g. ``"user:alice"``.
        token: OCG bearer token, held client-side (e.g. from ``OCG_TOKEN``).
            Used by the client-side ``run()`` path.
        credential: Server-resolvable credential NAME (default ``"OCG_PUBLIC_KEY"``)
            for the OCG bearer token. Used by the COMPILED/deployed path — the
            server resolves this via a ``#{NAME}`` HTTP-header placeholder. Distinct
            from ``token`` (the raw client token); both can coexist.
        scope: Memory scope for writes (default ``"user"``).
        timeout: Per-request timeout in seconds.
        client: Optional pre-built ``httpx.Client`` (mainly for tests).
    """

    def __init__(
        self,
        *,
        url: str,
        agent: str,
        user: Optional[str] = None,
        token: Optional[str] = None,
        credential: str = "OCG_PUBLIC_KEY",
        scope: str = "user",
        timeout: float = 10.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        if not url or not url.strip():
            raise ValueError("OCGMemoryStore requires a non-blank OCG instance url")
        if not agent or not agent.strip():
            raise ValueError("OCGMemoryStore requires a non-blank agent owner")
        self._base = url.strip().rstrip("/")
        self._agent = agent
        self._user = user
        self._credential = credential
        self._scope = scope
        headers: Dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = client or httpx.Client(timeout=timeout, headers=headers)

    # ── HTTP plumbing ───────────────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            resp = self._client.request(method, self._base + path, **kwargs)
        except httpx.HTTPError as exc:  # network/timeout
            raise AgentAPIError(status_code=0, message=str(exc), url=self._base + path) from exc
        if resp.status_code >= 400:
            raise AgentAPIError(
                status_code=resp.status_code,
                message=resp.text,
                url=self._base + path,
            )
        return resp

    # ── MemoryStore interface ───────────────────────────────────────────

    def add(self, entry: MemoryEntry) -> str:
        key = entry.id or str(entry.metadata.get("key") or "") or _hash_key(entry.content)
        body: Dict[str, Any] = {
            "key": key,
            "agent": self._agent,
            "value": entry.content,
            "description": entry.content[:200],
            "scope": self._scope,
            "source": "agent_inferred",
            "tags": list(entry.metadata.get("tags", []) or []),
        }
        if self._user:
            body["user"] = self._user
        self._request("POST", "/api/v1/memories", json=body)
        entry.id = key
        return key

    def search(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        body: Dict[str, Any] = {
            "query": query,
            "agent": self._agent,
            "limit": top_k,
            "include_shared": True,
        }
        if self._user:
            body["user"] = self._user
        resp = self._request("POST", "/api/v1/memories/search", json=body)
        out: List[MemoryEntry] = []
        for m in resp.json().get("memories", []) or []:
            out.append(
                MemoryEntry(
                    id=m.get("key", ""),
                    content=_with_signal(m.get("value_preview", ""), m),
                    metadata={
                        "relevance_score": m.get("relevance_score"),
                        "good_count": m.get("good_count", 0),
                        "bad_count": m.get("bad_count", 0),
                    },
                )
            )
        return out

    def delete(self, memory_id: str) -> bool:
        params: Dict[str, str] = {"agent": self._agent}
        if self._user:
            params["user"] = self._user
        try:
            self._request("DELETE", f"/api/v1/memories/{memory_id}", params=params)
        except AgentAPIError:
            return False
        return True

    def clear(self) -> None:
        # No bulk-clear endpoint — fan out over the listed keys. Guard usage:
        # this deletes every memory for the configured agent/user.
        entries = self.list_all()
        logger.warning(
            "OCGMemoryStore.clear() deleting %d memories for %s", len(entries), self._agent
        )
        for e in entries:
            self.delete(e.id)

    def list_all(self) -> List[MemoryEntry]:
        params: Dict[str, str] = {"agent": self._agent, "limit": "200"}
        if self._user:
            params["user"] = self._user
        resp = self._request("GET", "/api/v1/memories", params=params)
        return [
            MemoryEntry(id=m.get("key", ""), content=m.get("value_preview", ""))
            for m in resp.json().get("memories", []) or []
        ]

    # ── Capability feedback links (human-only, out-of-band) ─────────────

    def feedback_links(self, key: str) -> Dict[str, Any]:
        """Mint signed good/bad capability URLs for a memory.

        Returns ``{"good_url", "bad_url", "expires_at"}``. The URLs require no OCG
        login — a human (e.g. a support engineer) clicks them to vote. Requires the
        OCG instance to have a feedback-link secret configured (else OCG returns 501).
        """
        params: Dict[str, str] = {"agent": self._agent}
        if self._user:
            params["user"] = self._user
        resp = self._request("POST", f"/api/v1/memories/{key}/feedback-links", params=params)
        return resp.json()


def _with_signal(content: str, m: Dict[str, Any]) -> str:
    """Fold the human good/bad signal into a search result's content so the
    injected prompt context shows the agent when a memory was marked bad and why."""
    good = int(m.get("good_count", 0) or 0)
    bad = int(m.get("bad_count", 0) or 0)
    if not good and not bad:
        return content
    content += f"  [good {good} / bad {bad}]"
    for note in m.get("feedback_notes") or []:
        if note.get("verdict") == "bad" and note.get("reason"):
            content += f' (bad: "{note["reason"]}")'
    return content


# ── Conversation summarization (Claude-style distillation) ──────────────

try:  # pydantic is a core dep, but keep the import resilient.
    from pydantic import BaseModel, Field

    class MemorySummary(BaseModel):
        """Structured output for the conversation summarizer agent."""

        summary: str = Field(description="One short paragraph: what happened / what was learned.")
        facts: List[str] = Field(
            default_factory=list,
            description="Durable, reusable facts about the user or task (no chit-chat).",
        )
        tags: List[str] = Field(default_factory=list, description="Short topical tags.")

except Exception:  # pragma: no cover - pydantic always present in practice
    MemorySummary = None  # type: ignore[assignment]


MEMORY_SUMMARIZER_INSTRUCTIONS = (
    "You distill a conversation into a durable memory. Read the transcript and "
    "extract only reusable, durable facts about the user, their preferences, and "
    "the task — the kind of thing worth remembering for next time. Ignore greetings, "
    "filler, and one-off details. Write a one-paragraph summary, a short list of "
    "facts, and a few topical tags. Be concise and concrete."
)


def build_memory_summarizer(model: str, *, name: str = "__memory_summarizer") -> "Agent":
    """Build the internal agent that summarizes a conversation into a memory.

    It uses :class:`MemorySummary` structured output and is intentionally created
    WITHOUT ``semantic_memory`` so the post-run save hook skips it (no recursion).
    """
    from conductor.ai.agents.agent import Agent

    return Agent(
        name=name,
        model=model,
        instructions=MEMORY_SUMMARIZER_INSTRUCTIONS,
        output_type=MemorySummary,
        max_turns=1,
    )


@dataclass
class FeedbackEvent:
    """Handed to an Agent's ``feedback_sink`` after a conversation memory is saved.

    Carries the distilled summary plus the signed capability URLs a human can click
    to mark the memory good/bad. The integrator routes these out-of-band (e.g. posts
    them into a Zendesk ticket). These URLs are never shown to the agent's LLM.
    """

    memory_key: str
    summary: str
    facts: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    good_url: Optional[str] = None
    bad_url: Optional[str] = None
    expires_at: Optional[str] = None
    agent: Optional[str] = None
    user: Optional[str] = None
    session_id: Optional[str] = None
