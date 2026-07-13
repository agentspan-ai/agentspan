# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for OCG-backed memory: the HTTP store adapter, the conversation
summary helpers, and the runtime save/retrieval hooks."""

from __future__ import annotations

import json
from typing import List

import httpx
import pytest

from conductor.ai.agents import Agent
from conductor.ai.agents.exceptions import AgentAPIError
from conductor.ai.agents.ocg_memory import FeedbackEvent, OCGMemoryStore
from conductor.ai.agents.result import AgentResult, Status
from conductor.ai.agents.runtime.runtime import (
    AgentRuntime,
    _agent_model_str,
    _parse_summary_output,
)
from conductor.ai.agents.semantic_memory import MemoryEntry, MemoryStore, SemanticMemory


def _store_with(handler) -> OCGMemoryStore:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OCGMemoryStore(url="https://ocg.test", agent="agent:a", user="user:bob", client=client)


class TestOCGMemoryStore:
    def test_add_posts_value_field_and_no_confidence(self):
        captured = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["url"] = str(req.url)
            captured["body"] = json.loads(req.content)
            return httpx.Response(200, json={"key": "k1"})

        store = _store_with(handler)
        key = store.add(MemoryEntry(content="alice prefers email", metadata={"key": "pref"}))

        assert key == "pref"
        assert captured["url"].endswith("/api/v1/memories")
        body = captured["body"]
        assert body["value"] == "alice prefers email"  # field is "value", NOT "string_value"
        assert "string_value" not in body
        assert "confidence" not in body  # confidence was removed from the API
        assert body["agent"] == "agent:a" and body["user"] == "user:bob"

    def test_search_folds_good_bad_signal_into_content(self):
        def handler(req: httpx.Request) -> httpx.Response:
            assert str(req.url).endswith("/api/v1/memories/search")
            return httpx.Response(
                200,
                json={
                    "memories": [
                        {
                            "key": "m1",
                            "value_preview": "use us-east-1",
                            "good_count": 2,
                            "bad_count": 1,
                            "relevance_score": 0.9,
                            "feedback_notes": [{"verdict": "bad", "reason": "stale region"}],
                        }
                    ]
                },
            )

        store = _store_with(handler)
        entries = store.search("which region", top_k=5)
        assert len(entries) == 1
        assert "[good 2 / bad 1]" in entries[0].content
        assert 'bad: "stale region"' in entries[0].content

    def test_feedback_links_hits_mint_route(self):
        def handler(req: httpx.Request) -> httpx.Response:
            assert str(req.url).split("?")[0].endswith("/api/v1/memories/k1/feedback-links")
            return httpx.Response(
                200,
                json={
                    "good_url": "https://ocg.test/api/v1/feedback/GOOD",
                    "bad_url": "https://ocg.test/api/v1/feedback/BAD",
                    "expires_at": "2026-09-01T00:00:00Z",
                },
            )

        store = _store_with(handler)
        links = store.feedback_links("k1")
        assert links["good_url"].endswith("/feedback/GOOD")
        assert links["bad_url"].endswith("/feedback/BAD")

    def test_non_2xx_raises(self):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        store = _store_with(handler)
        with pytest.raises(AgentAPIError):
            store.add(MemoryEntry(content="x", metadata={"key": "k"}))


class _FakeStore(MemoryStore):
    """Records add() calls and serves canned feedback links."""

    def __init__(self):
        self.added: List[MemoryEntry] = []
        self._agent = "agent:a"
        self._user = "user:bob"

    def add(self, entry: MemoryEntry) -> str:
        self.added.append(entry)
        return entry.id or "k"

    def search(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        return []

    def delete(self, memory_id: str) -> bool:
        return True

    def clear(self) -> None:
        pass

    def list_all(self) -> List[MemoryEntry]:
        return []

    def feedback_links(self, key: str):
        return {
            "good_url": "https://ocg.test/api/v1/feedback/GOOD",
            "bad_url": "https://ocg.test/api/v1/feedback/BAD",
            "expires_at": "2026-09-01T00:00:00Z",
        }


class TestRuntimeMemoryHooks:
    def test_save_stores_distilled_summary_and_invokes_sink(self, monkeypatch):
        rt = AgentRuntime()
        store = _FakeStore()
        events: List[FeedbackEvent] = []

        agent = Agent(
            name="support",
            model="openai/gpt-4o",
            semantic_memory=SemanticMemory(store=store),
            feedback_sink=lambda ev: events.append(ev),
        )

        # Stub the nested summarizer run — return distilled facts, NOT the transcript.
        def fake_run(summarizer_agent, transcript, **kwargs):
            assert summarizer_agent.name == "__memory_summarizer"
            return AgentResult(
                output={
                    "summary": "Alice is on Enterprise.",
                    "facts": ["plan=enterprise"],
                    "tags": ["billing"],
                },
                status=Status.COMPLETED,
            )

        monkeypatch.setattr(rt, "run", fake_run)

        result = AgentResult(
            output={"result": "ok"},
            execution_id="exec-1",
            status=Status.COMPLETED,
            messages=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        )

        rt._maybe_save_conversation_memory(agent, result, session_id="sess-9")

        assert len(store.added) == 1
        saved = store.added[0]
        assert saved.id == "conversation:sess-9"
        assert "Alice is on Enterprise." in saved.content
        assert "plan=enterprise" in saved.content
        assert "hello" not in saved.content  # the raw transcript is NOT stored
        assert "conversation" in saved.metadata["tags"]

        assert len(events) == 1
        assert events[0].good_url.endswith("/feedback/GOOD")
        assert events[0].bad_url.endswith("/feedback/BAD")
        assert events[0].memory_key == "conversation:sess-9"

    def test_save_skipped_when_no_semantic_memory(self, monkeypatch):
        rt = AgentRuntime()
        called = {"run": False}
        monkeypatch.setattr(rt, "run", lambda *a, **k: called.__setitem__("run", True))
        agent = Agent(name="plain", model="openai/gpt-4o")
        rt._maybe_save_conversation_memory(
            agent,
            AgentResult(status=Status.COMPLETED, messages=[{"role": "user", "content": "hi"}]),
            None,
        )
        assert called["run"] is False  # no nested summarizer run, no recursion

    def test_save_never_raises_on_failure(self, monkeypatch):
        rt = AgentRuntime()

        def boom(*a, **k):
            raise RuntimeError("summarizer exploded")

        monkeypatch.setattr(rt, "run", boom)
        agent = Agent(
            name="support",
            model="openai/gpt-4o",
            semantic_memory=SemanticMemory(store=_FakeStore()),
        )
        # Must not raise.
        rt._maybe_save_conversation_memory(
            agent,
            AgentResult(status=Status.COMPLETED, messages=[{"role": "user", "content": "hi"}]),
            None,
        )

    def test_apply_retrieval_prepends_context_without_mutating_original(self):
        rt = AgentRuntime()
        store = _FakeStore()
        sm = SemanticMemory(store=store)
        sm.get_context = lambda q: "Relevant context from memory:\n  1. plan=enterprise"  # type: ignore
        agent = Agent(
            name="support", model="openai/gpt-4o", instructions="Be helpful.", semantic_memory=sm
        )

        augmented = rt._apply_memory_retrieval(agent, "what plan?")
        assert augmented is not agent
        assert augmented.instructions.startswith("Relevant context from memory:")
        assert "Be helpful." in augmented.instructions
        assert agent.instructions == "Be helpful."  # original untouched

    def test_apply_retrieval_noop_without_memory(self):
        rt = AgentRuntime()
        agent = Agent(name="plain", model="openai/gpt-4o", instructions="Hi")
        assert rt._apply_memory_retrieval(agent, "q") is agent


class TestSummaryHelpers:
    def test_agent_model_str_fallback(self):
        assert _agent_model_str(Agent(name="a", model="openai/gpt-4o")) == "openai/gpt-4o"

    def test_parse_summary_from_dict(self):
        s, f, t = _parse_summary_output({"summary": "x", "facts": ["a"], "tags": ["b"]})
        assert s == "x" and f == ["a"] and t == ["b"]

    def test_parse_summary_from_wrapped_result(self):
        s, f, t = _parse_summary_output({"result": {"summary": "y", "facts": [], "tags": []}})
        assert s == "y"

    def test_agent_stores_memory_attrs(self):
        sm = SemanticMemory(store=_FakeStore())
        agent = Agent(name="a", model="openai/gpt-4o", semantic_memory=sm)
        assert agent.semantic_memory is sm
        assert agent.memory_summary_model is None  # defaults to None -> reuse agent model
        assert agent.feedback_sink is None
