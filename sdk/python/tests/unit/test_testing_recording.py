# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for agentspan.agents.testing.recording."""

import json

from agentspan.agents.result import AgentEvent, AgentResult, EventType, TokenUsage
from agentspan.agents.testing.recording import record, replay


def _make_result():
    return AgentResult(
        output="The weather is 72F",
        execution_id="wf-123",
        correlation_id="corr-456",
        messages=[
            {"role": "user", "content": "Weather?"},
            {"role": "assistant", "content": "The weather is 72F"},
        ],
        tool_calls=[{"name": "get_weather", "args": {"city": "NYC"}, "result": {"temp": 72}}],
        status="COMPLETED",
        token_usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        metadata={"model": "gpt-4o"},
        finish_reason="stop",
        events=[
            AgentEvent(type=EventType.THINKING, content="Let me check..."),
            AgentEvent(
                type=EventType.TOOL_CALL,
                tool_name="get_weather",
                args={"city": "NYC"},
            ),
            AgentEvent(
                type=EventType.TOOL_RESULT,
                tool_name="get_weather",
                result={"temp": 72},
            ),
            AgentEvent(type=EventType.DONE, output="The weather is 72F"),
        ],
    )


class TestRecordReplay:
    def test_roundtrip(self, tmp_path):
        original = _make_result()
        path = tmp_path / "recording.json"

        record(original, path)
        assert path.exists()

        restored = replay(path)

        assert restored.output == original.output
        assert restored.execution_id == original.execution_id
        assert restored.correlation_id == original.correlation_id
        assert restored.status == original.status
        assert restored.finish_reason == original.finish_reason
        assert restored.messages == original.messages
        assert restored.tool_calls == original.tool_calls
        assert restored.metadata == original.metadata

    def test_token_usage_preserved(self, tmp_path):
        original = _make_result()
        path = tmp_path / "recording.json"

        record(original, path)
        restored = replay(path)

        assert restored.token_usage is not None
        assert restored.token_usage.prompt_tokens == 100
        assert restored.token_usage.completion_tokens == 50
        assert restored.token_usage.total_tokens == 150

    def test_events_preserved(self, tmp_path):
        original = _make_result()
        path = tmp_path / "recording.json"

        record(original, path)
        restored = replay(path)

        assert len(restored.events) == 4
        assert restored.events[0].type == EventType.THINKING
        assert restored.events[0].content == "Let me check..."
        assert restored.events[1].type == EventType.TOOL_CALL
        assert restored.events[1].tool_name == "get_weather"
        assert restored.events[3].type == EventType.DONE
        assert restored.events[3].output == "The weather is 72F"

    def test_creates_parent_directories(self, tmp_path):
        original = _make_result()
        path = tmp_path / "nested" / "dir" / "recording.json"

        record(original, path)
        assert path.exists()

    def test_json_is_readable(self, tmp_path):
        original = _make_result()
        path = tmp_path / "recording.json"

        record(original, path)
        data = json.loads(path.read_text())

        assert data["output"] == "The weather is 72F"
        assert data["status"] == "COMPLETED"
        assert len(data["events"]) == 4

    def test_result_without_optional_fields(self, tmp_path):
        result = AgentResult(output="Simple", status="COMPLETED")
        path = tmp_path / "simple.json"

        record(result, path)
        restored = replay(path)

        assert restored.output == "Simple"
        assert restored.token_usage is None
        assert restored.correlation_id is None
        assert restored.events == []

    def test_guardrail_events(self, tmp_path):
        result = AgentResult(
            output="ok",
            events=[
                AgentEvent(
                    type=EventType.GUARDRAIL_PASS,
                    guardrail_name="safety",
                    content="Passed",
                ),
                AgentEvent(
                    type=EventType.GUARDRAIL_FAIL,
                    guardrail_name="pii",
                    content="Found PII",
                ),
            ],
        )
        path = tmp_path / "guardrails.json"

        record(result, path)
        restored = replay(path)

        assert restored.events[0].guardrail_name == "safety"
        assert restored.events[1].guardrail_name == "pii"
        assert restored.events[1].content == "Found PII"
