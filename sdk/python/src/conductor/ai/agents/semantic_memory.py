# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Semantic memory — long-term memory with similarity-based retrieval.

Provides cross-session memory for agents, enabling them to recall
relevant information from past interactions based on semantic similarity.

Example::

    from conductor.ai.agents import Agent
    from conductor.ai.agents.semantic_memory import SemanticMemory

    memory = SemanticMemory()
    memory.add("User prefers concise answers", metadata={"type": "preference"})
    memory.add("Project uses Python 3.12 with FastAPI", metadata={"type": "fact"})

    agent = Agent(
        name="assistant",
        model="openai/gpt-4o",
        semantic_memory=memory,
    )

    # At runtime, relevant memories are injected into the system prompt.
"""

from __future__ import annotations

import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("conductor.ai.agents.semantic_memory")


@dataclass
class MemoryEntry:
    """A single memory entry.

    Attributes:
        id: Unique identifier for the memory.
        content: The memory text.
        metadata: Arbitrary metadata (type, source, timestamp, etc.).
        embedding: Optional embedding vector for similarity search.
        created_at: Unix timestamp when the memory was created.
    """

    id: str = ""
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    created_at: float = 0.0


class MemoryStore(ABC):
    """Abstract interface for a memory storage backend.

    Implement this to integrate with external vector databases
    (Pinecone, Weaviate, ChromaDB, etc.) or services like Mem0.
    """

    @abstractmethod
    def add(self, entry: MemoryEntry) -> str:
        """Store a memory entry. Returns the entry ID."""
        ...

    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        """Search for memories similar to the query."""
        ...

    @abstractmethod
    def delete(self, memory_id: str) -> bool:
        """Delete a memory entry by ID."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Delete all memories."""
        ...

    @abstractmethod
    def list_all(self) -> List[MemoryEntry]:
        """Return all stored memories."""
        ...


class InMemoryStore(MemoryStore):
    """Simple in-memory store using keyword overlap for similarity.

    This is a lightweight fallback when no vector database is available.
    For production use, plug in a real vector store via :class:`MemoryStore`.

    Similarity is computed as keyword overlap (Jaccard similarity)
    between the query and stored memory texts.
    """

    def __init__(self) -> None:
        self._memories: Dict[str, MemoryEntry] = {}

    def add(self, entry: MemoryEntry) -> str:
        if not entry.id:
            entry.id = hashlib.sha256(f"{entry.content}{time.time()}".encode()).hexdigest()[:16]
        if not entry.created_at:
            entry.created_at = time.time()
        self._memories[entry.id] = entry
        return entry.id

    def search(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        if not self._memories:
            return []

        query_words = set(query.lower().split())
        scored = []
        for entry in self._memories.values():
            entry_words = set(entry.content.lower().split())
            if not query_words or not entry_words:
                score = 0.0
            else:
                intersection = query_words & entry_words
                union = query_words | entry_words
                score = len(intersection) / len(union) if union else 0.0
            scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for score, entry in scored[:top_k] if score > 0]

    def delete(self, memory_id: str) -> bool:
        return self._memories.pop(memory_id, None) is not None

    def clear(self) -> None:
        self._memories.clear()

    def list_all(self) -> List[MemoryEntry]:
        return list(self._memories.values())


class SemanticMemory:
    """High-level semantic memory for agents.

    Manages short-term (session) and long-term (persistent) memories
    with similarity-based retrieval.  Relevant memories are automatically
    injected into the agent's system prompt at execution time.

    Args:
        store: A :class:`MemoryStore` backend. Defaults to
            :class:`InMemoryStore` (non-persistent).
        max_results: Maximum memories to retrieve per query (default 5).
        session_id: Optional session ID for scoping memories.

    Example::

        memory = SemanticMemory()

        # Add memories
        memory.add("User's name is Alice")
        memory.add("User prefers Python over JavaScript")

        # Search
        results = memory.search("What language does the user like?")
        # Returns: ["User prefers Python over JavaScript"]
    """

    def __init__(
        self,
        store: Optional[MemoryStore] = None,
        max_results: int = 5,
        session_id: Optional[str] = None,
    ) -> None:
        self.store = store or InMemoryStore()
        self.max_results = max_results
        self.session_id = session_id

    def add(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add a memory.

        Args:
            content: The memory text.
            metadata: Optional metadata (e.g. type, source, importance).

        Returns:
            The memory entry ID.
        """
        meta = metadata or {}
        if self.session_id:
            meta["session_id"] = self.session_id

        entry = MemoryEntry(content=content, metadata=meta)
        entry_id = self.store.add(entry)
        logger.debug("Added memory %s: %s", entry_id, content[:50])
        return entry_id

    def search(self, query: str, top_k: Optional[int] = None) -> List[str]:
        """Search for relevant memories.

        Args:
            query: The search query.
            top_k: Max results (defaults to ``self.max_results``).

        Returns:
            List of memory content strings, most relevant first.
        """
        k = top_k or self.max_results
        entries = self.store.search(query, top_k=k)
        return [e.content for e in entries]

    def search_entries(self, query: str, top_k: Optional[int] = None) -> List[MemoryEntry]:
        """Search and return full :class:`MemoryEntry` objects."""
        k = top_k or self.max_results
        return self.store.search(query, top_k=k)

    def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        return self.store.delete(memory_id)

    def clear(self) -> None:
        """Delete all memories."""
        self.store.clear()

    def list_all(self) -> List[MemoryEntry]:
        """Return all stored memories."""
        return self.store.list_all()

    def get_context(self, query: str) -> str:
        """Get relevant memories formatted for injection into a prompt.

        Args:
            query: The user's current message.

        Returns:
            A formatted string of relevant memories, or empty string.
        """
        memories = self.search(query)
        if not memories:
            return ""
        lines = ["Relevant context from memory:"]
        for i, mem in enumerate(memories, 1):
            lines.append(f"  {i}. {mem}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        count = len(self.store.list_all())
        return f"SemanticMemory(entries={count}, max_results={self.max_results})"
