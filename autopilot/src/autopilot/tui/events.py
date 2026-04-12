"""Event formatting for the TUI — renders SSE events as display text."""

from __future__ import annotations

from agentspan.agents import EventType


_SEPARATOR = "\u2500" * 62
_THIN_SEP = "\u2504" * 62


def format_event(event) -> str:
    """Format a single stream event as display text. Returns empty string if suppressed."""
    etype = event.type
    args = event.args or {}

    if etype == EventType.TOOL_CALL:
        tool_name = event.tool_name or ""

        if tool_name == "reply_to_user":
            msg = args.get("message", "")
            return f"\n{'--- Claw ' + '-' * 53}\n{msg}\n"

        if tool_name == "wait_for_message":
            return ""

        if tool_name == "web_search":
            return f"  [search] {args.get('query', '')}\n"

        if tool_name == "read_document":
            return f"  [read] {args.get('path', '')}\n"

        if tool_name in ("expand_prompt", "generate_agent", "deploy_agent"):
            return f"  [{tool_name}] ...\n"

        return f"  [{tool_name}] {args}\n"

    if etype == EventType.TOOL_RESULT:
        tool_name = event.tool_name or ""
        if tool_name == "web_search" and event.result:
            raw = str(event.result)
            if len(raw) > 500:
                raw = raw[:500] + "\n  ... (truncated)"
            return f"  {raw}\n"
        return ""

    if etype == EventType.HANDOFF:
        target = getattr(event, "content", "") or ""
        return f"  [handoff -> {target}]\n"

    if etype == EventType.ERROR:
        return f"\n[ERROR] {event.content}\n"

    if etype == EventType.DONE:
        return ""

    return ""
