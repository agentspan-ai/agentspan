"""Native Google ADK execution — run agents via their SDK, bypassing Conductor."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Generator

from conductor.ai.agents.result import (
    AgentEvent,
    AgentResult,
    FinishReason,
    Status,
    TokenUsage,
)

logger = logging.getLogger("validation.native.adk_runner")


# ── ADK native runner ────────────────────────────────────────────────────


def run_adk_native(agent_obj: Any, prompt: str) -> AgentResult:
    """Run a Google ADK agent natively via ``InMemoryRunner``."""
    prepared = _strip_model_prefix(agent_obj)
    logger.info(
        "Native sync: InMemoryRunner(agent=%s, model=%s, prompt=%.80s...)",
        getattr(prepared, "name", "?"),
        getattr(prepared, "model", "?"),
        prompt,
    )
    try:
        events = list(_run_sync(prepared, prompt))
    except Exception as e:
        logger.error("Native ADK run failed: %s", e)
        return AgentResult(
            output=None,
            status=Status.FAILED,
            finish_reason=FinishReason.ERROR,
            error=str(e),
        )
    return _map_events(events)


def run_adk_native_stream(agent_obj: Any, prompt: str) -> Generator[AgentEvent, None, None]:
    """Run a Google ADK agent natively and yield AgentEvent objects.

    ADK's ``Runner.run()`` is already a generator, so we can map events
    in real time.  Uses string event types so f-strings render as
    ``"tool_call"`` rather than ``"EventType.TOOL_CALL"`` (Python 3.12).
    """
    prepared = _strip_model_prefix(agent_obj)
    try:
        pending_call: dict | None = None
        for event in _run_sync(prepared, prompt):
            func_calls = event.get_function_calls()
            func_responses = event.get_function_responses()

            if func_calls:
                for fc in func_calls:
                    pending_call = {"name": fc.name}
                    yield AgentEvent(type="tool_call", tool_name=fc.name, args=dict(fc.args or {}))

            elif func_responses:
                for fr in func_responses:
                    name = fr.name
                    response = fr.response or {}
                    yield AgentEvent(type="tool_result", tool_name=name, result=response)
                pending_call = None

            elif event.is_final_response() and event.content:
                text = _extract_text(event)
                yield AgentEvent(type="done", output=text)

            elif event.content and not event.is_final_response():
                text = _extract_text(event)
                if text:
                    yield AgentEvent(type="thinking", content=text)

    except Exception as e:
        yield AgentEvent(type="error", content=str(e))


# ── Helpers ─────────────────────────────────────────────────────────────


def _run_sync(agent_obj: Any, prompt: str):
    """Run the agent via InMemoryRunner.run() (sync generator wrapper)."""
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    app_name = getattr(agent_obj, "name", "adk_native") or "adk_native"
    user_id = "native_user"
    session_id = f"session_{uuid.uuid4().hex[:8]}"

    runner = InMemoryRunner(agent=agent_obj, app_name=app_name)

    # create_session is async; use asyncio.run for the setup call
    asyncio.run(
        runner.session_service.create_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
    )

    new_message = types.Content(
        role="user", parts=[types.Part(text=prompt)]
    )
    yield from runner.run(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
    )


def _extract_text(event: Any) -> str:
    """Extract plain text from an ADK event's content parts."""
    if not event.content or not event.content.parts:
        return ""
    return "".join(
        part.text for part in event.content.parts if getattr(part, "text", None)
    )


def _map_events(events: list) -> AgentResult:
    """Convert a list of ADK Event objects to an AgentResult."""
    final_text: str = ""
    tool_calls: list[dict] = []
    prompt_tokens = 0
    completion_tokens = 0
    pending_call: dict | None = None

    for event in events:
        # Accumulate token usage
        if getattr(event, "usage_metadata", None):
            um = event.usage_metadata
            prompt_tokens += getattr(um, "prompt_token_count", 0) or 0
            completion_tokens += getattr(um, "candidates_token_count", 0) or 0

        func_calls = event.get_function_calls()
        func_responses = event.get_function_responses()

        if func_calls:
            for fc in func_calls:
                pending_call = {"name": fc.name, "args": dict(fc.args or {})}

        elif func_responses:
            for fr in func_responses:
                if pending_call is not None:
                    pending_call["result"] = fr.response or {}
                    tool_calls.append(pending_call)
                    pending_call = None

        if event.is_final_response():
            final_text = _extract_text(event)

    token_usage = (
        TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
        if (prompt_tokens or completion_tokens)
        else None
    )

    return AgentResult(
        output=final_text or None,
        tool_calls=tool_calls,
        status=Status.COMPLETED if final_text else Status.FAILED,
        finish_reason=FinishReason.STOP,
        token_usage=token_usage,
    )


def _strip_model_prefix(agent_obj: Any) -> Any:
    """Clone a Google ADK Agent, stripping 'provider/' prefix from model.

    ADK expects bare model names like ``gemini-2.5-flash``, not
    ``google_gemini/gemini-2.5-flash``.  Also recurses into sub_agents.

    Uses Pydantic v2's ``model_copy(update=...)`` to create a proper copy
    rather than ``copy.copy()`` + attribute mutation, which is unreliable for
    Pydantic models (especially frozen ones).
    """
    from google.adk.agents import BaseAgent

    if not isinstance(agent_obj, BaseAgent):
        return agent_obj

    updates: dict = {}

    raw_model = getattr(agent_obj, "model", None)
    if isinstance(raw_model, str) and "/" in raw_model:
        updates["model"] = raw_model.split("/", 1)[1]

    sub_agents = getattr(agent_obj, "sub_agents", None)
    if sub_agents:
        stripped = [_strip_model_prefix(a) for a in sub_agents]
        if stripped != list(sub_agents):
            updates["sub_agents"] = stripped

    if not updates:
        return agent_obj

    return agent_obj.model_copy(update=updates)
