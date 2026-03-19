"""Native LangGraph / LangChain execution — run agents directly, bypassing Conductor."""

from __future__ import annotations

import logging
from typing import Any

from agentspan.agents.result import (
    AgentResult,
    FinishReason,
    Status,
    TokenUsage,
)

logger = logging.getLogger("validation.native.langgraph_runner")

# In-memory session state: session_id → list[BaseMessage]
_SESSION_STATE: dict[str, list] = {}


# ── LangGraph native runner ──────────────────────────────────────────────


def run_langgraph_native(
    agent_obj: Any, prompt: str, session_id: str | None = None
) -> AgentResult:
    """Run a LangGraph ``CompiledStateGraph`` natively via ``.invoke()``."""
    from langchain_core.messages import AIMessage, HumanMessage

    logger.info(
        "Native LangGraph: invoke(session=%s, prompt=%.80s...)",
        session_id,
        prompt,
    )

    has_checkpointer = getattr(agent_obj, "checkpointer", None) is not None

    if has_checkpointer and session_id:
        # Graph manages its own state; only send the new message
        messages_input = [HumanMessage(content=prompt)]
        invoke_config = {"configurable": {"thread_id": session_id}}
    else:
        # No checkpointer — pass full history ourselves
        history = _SESSION_STATE.get(session_id, []) if session_id else []
        messages_input = history + [HumanMessage(content=prompt)]
        invoke_config = None

    try:
        result = agent_obj.invoke(
            {"messages": messages_input},
            config=invoke_config,
        )
    except Exception as e:
        logger.error("Native LangGraph run failed: %s", e)
        return AgentResult(
            output=None,
            status=Status.FAILED,
            finish_reason=FinishReason.ERROR,
            error=str(e),
        )

    result_messages = result.get("messages", [])

    # Persist history for future turns (no-checkpointer path)
    if session_id and not has_checkpointer:
        _SESSION_STATE[session_id] = result_messages

    return _map_messages(result_messages)


# ── LangChain native runner ──────────────────────────────────────────────


def run_langchain_native(
    agent_obj: Any, prompt: str, session_id: str | None = None
) -> AgentResult:
    """Run a LangChain ``AgentExecutor`` natively via ``.invoke()``."""
    logger.info(
        "Native LangChain: invoke(session=%s, prompt=%.80s...)",
        session_id,
        prompt,
    )

    history = _SESSION_STATE.get(session_id, []) if session_id else []

    try:
        result = agent_obj.invoke({"input": prompt, "chat_history": history})
    except Exception as e:
        logger.error("Native LangChain run failed: %s", e)
        return AgentResult(
            output=None,
            status=Status.FAILED,
            finish_reason=FinishReason.ERROR,
            error=str(e),
        )

    output = result.get("output", "")

    # Update session history for next turn
    if session_id and output:
        from langchain_core.messages import AIMessage, HumanMessage

        _SESSION_STATE[session_id] = history + [
            HumanMessage(content=prompt),
            AIMessage(content=output),
        ]

    tool_calls = []
    intermediate = result.get("intermediate_steps", [])
    for action, observation in intermediate:
        tool_calls.append(
            {
                "name": getattr(action, "tool", str(action)),
                "args": getattr(action, "tool_input", {}),
                "result": str(observation),
            }
        )

    return AgentResult(
        output=output or None,
        tool_calls=tool_calls,
        status=Status.COMPLETED if output else Status.FAILED,
        finish_reason=FinishReason.STOP,
        token_usage=None,
    )


# ── Helpers ──────────────────────────────────────────────────────────────


def _map_messages(messages: list) -> AgentResult:
    """Extract output, tool calls, and token usage from a LangGraph messages list."""
    from langchain_core.messages import AIMessage

    final_text = ""
    tool_calls: list[dict] = []
    prompt_tokens = 0
    completion_tokens = 0

    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue

        # Accumulate token usage from response_metadata
        usage = (getattr(msg, "response_metadata", None) or {}).get("token_usage")
        if usage:
            prompt_tokens += usage.get("prompt_tokens", 0)
            completion_tokens += usage.get("completion_tokens", 0)

        msg_tool_calls = getattr(msg, "tool_calls", None) or []
        if msg_tool_calls:
            for tc in msg_tool_calls:
                tool_calls.append(
                    {
                        "name": tc.get("name", ""),
                        "args": tc.get("args", {}),
                    }
                )
        elif msg.content:
            # Final response — no tool calls
            final_text = (
                msg.content
                if isinstance(msg.content, str)
                else str(msg.content)
            )

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
