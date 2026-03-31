# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Record and replay agent execution traces for regression testing.

Usage::

    from agentspan.agents.testing import record, replay

    # Record a live execution
    result = runtime.run(agent, "What's the weather?")
    record(result, "tests/recordings/weather.json")

    # Later, replay it deterministically
    result = replay("tests/recordings/weather.json")
    assert_tool_used(result, "get_weather")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Union

from agentspan.agents.result import AgentEvent, AgentResult, TokenUsage


def _event_to_dict(event: AgentEvent) -> Dict[str, Any]:
    """Serialize an :class:`AgentEvent` to a JSON-compatible dict."""
    d: Dict[str, Any] = {"type": event.type}
    if event.content is not None:
        d["content"] = event.content
    if event.tool_name is not None:
        d["tool_name"] = event.tool_name
    if event.args is not None:
        d["args"] = event.args
    if event.result is not None:
        d["result"] = event.result
    if event.target is not None:
        d["target"] = event.target
    if event.output is not None:
        d["output"] = event.output
    if event.execution_id:
        d["execution_id"] = event.execution_id
    if event.guardrail_name is not None:
        d["guardrail_name"] = event.guardrail_name
    return d


def _dict_to_event(d: Dict[str, Any]) -> AgentEvent:
    """Deserialize a dict back to an :class:`AgentEvent`."""
    return AgentEvent(
        type=d.get("type", ""),
        content=d.get("content"),
        tool_name=d.get("tool_name"),
        args=d.get("args"),
        result=d.get("result"),
        target=d.get("target"),
        output=d.get("output"),
        execution_id=d.get("execution_id", ""),
        guardrail_name=d.get("guardrail_name"),
    )


def _result_to_dict(result: AgentResult) -> Dict[str, Any]:
    """Serialize an :class:`AgentResult` to a JSON-compatible dict."""
    d: Dict[str, Any] = {
        "output": result.output,
        "execution_id": result.execution_id,
        "messages": result.messages,
        "tool_calls": result.tool_calls,
        "status": result.status,
        "metadata": result.metadata,
        "events": [_event_to_dict(ev) for ev in result.events],
    }
    if result.correlation_id:
        d["correlation_id"] = result.correlation_id
    if result.finish_reason:
        d["finish_reason"] = result.finish_reason
    if result.token_usage:
        d["token_usage"] = {
            "prompt_tokens": result.token_usage.prompt_tokens,
            "completion_tokens": result.token_usage.completion_tokens,
            "total_tokens": result.token_usage.total_tokens,
        }
    return d


def _dict_to_result(d: Dict[str, Any]) -> AgentResult:
    """Deserialize a dict back to an :class:`AgentResult`."""
    token_usage = None
    if "token_usage" in d:
        tu = d["token_usage"]
        token_usage = TokenUsage(
            prompt_tokens=tu.get("prompt_tokens", 0),
            completion_tokens=tu.get("completion_tokens", 0),
            total_tokens=tu.get("total_tokens", 0),
        )

    return AgentResult(
        output=d.get("output"),
        execution_id=d.get("execution_id", ""),
        correlation_id=d.get("correlation_id"),
        messages=d.get("messages", []),
        tool_calls=d.get("tool_calls", []),
        status=d.get("status", "COMPLETED"),
        token_usage=token_usage,
        metadata=d.get("metadata", {}),
        finish_reason=d.get("finish_reason"),
        events=[_dict_to_event(ev) for ev in d.get("events", [])],
    )


def record(result: AgentResult, path: Union[str, Path]) -> None:
    """Save an :class:`AgentResult` to a JSON file.

    Args:
        result: The agent result to record.
        path: File path for the recording.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _result_to_dict(result)
    path.write_text(json.dumps(data, indent=2, default=str))


def replay(path: Union[str, Path]) -> AgentResult:
    """Load a recorded :class:`AgentResult` from a JSON file.

    Args:
        path: File path to the recording.

    Returns:
        The deserialized :class:`AgentResult`.
    """
    path = Path(path)
    data = json.loads(path.read_text())
    return _dict_to_result(data)
