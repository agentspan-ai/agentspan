"""Event formatting for the TUI — translates raw SSE events into polished user-facing messages.

Maps tool calls and results to user-friendly progress indicators:

- expand_prompt      -> "Expanding your request..."
- generate_agent     -> "Building agent..." + spec summary box on result
- validate_spec PASS -> checkmark "Specification valid"
- validate_spec FAIL -> warning "Specification issue: <reason>"
- deploy_agent       -> checkmark "Agent deployed! Execution ID: <id>"
- acquire_credentials-> "Opening browser for <service> authorization..."
- reply_to_user      -> clean message display
- web_search         -> "Searching: <query>"
- Other tool calls   -> "Working..." (no raw tool names for non-technical users)
"""

from __future__ import annotations

import json
import re
import textwrap
from typing import Optional

from agentspan.agents import EventType


# ---------------------------------------------------------------------------
# Box-drawing constants
# ---------------------------------------------------------------------------

_BOX_TL = "\u250c"  # top-left
_BOX_TR = "\u2510"  # top-right
_BOX_BL = "\u2514"  # bottom-left
_BOX_BR = "\u2518"  # bottom-right
_BOX_H = "\u2500"  # horizontal
_BOX_V = "\u2502"  # vertical

_CHECK = "\u2713"  # checkmark
_CROSS = "\u2717"  # cross
_WARN = "\u26a0"  # warning

_SEPARATOR = "\u2500" * 62


# ---------------------------------------------------------------------------
# Spec summary box
# ---------------------------------------------------------------------------

def render_spec_box(spec: dict, width: int = 51) -> str:
    """Render an agent spec summary inside a box-drawing frame.

    Args:
        spec: Parsed agent spec dict with keys like name, trigger, tools,
              credentials, instructions.
        width: Inner content width (excluding border characters).

    Returns:
        Multi-line string with box-drawn spec summary.
    """
    lines: list[str] = []
    inner = width

    def _pad(text: str) -> str:
        return f"  {_BOX_V}  {text:<{inner}}  {_BOX_V}"

    lines.append(f"  {_BOX_TL}{_BOX_H * (inner + 4)}{_BOX_TR}")

    # Agent name
    name = spec.get("name", "unnamed_agent")
    lines.append(_pad(f"Agent: {name}"))

    # Schedule / trigger
    trigger = spec.get("trigger", {})
    if isinstance(trigger, dict):
        ttype = trigger.get("type", "")
        schedule = trigger.get("schedule", "")
        if ttype == "cron" and schedule:
            lines.append(_pad(f"Schedule: {schedule}"))
        elif ttype:
            lines.append(_pad(f"Trigger: {ttype}"))
    elif isinstance(trigger, str):
        lines.append(_pad(f"Trigger: {trigger}"))

    # Integrations
    tools = spec.get("tools", [])
    if tools:
        tool_names = []
        for t in tools:
            if isinstance(t, str) and t.startswith("builtin:"):
                tool_names.append(t[len("builtin:"):])
            elif isinstance(t, str):
                tool_names.append(t)
        if tool_names:
            lines.append(_pad(f"Integrations: {', '.join(tool_names)}"))

    # Credentials
    creds = spec.get("credentials", [])
    if creds:
        lines.append(_pad(f"Credentials: {', '.join(str(c) for c in creds)}"))

    # Blank line
    lines.append(_pad(""))

    # Behavior summary from instructions
    instructions = spec.get("instructions", "")
    if instructions and isinstance(instructions, str):
        lines.append(_pad("Behavior:"))
        # Extract key bullet points from instructions
        behavior_lines = _extract_behavior_lines(instructions, inner - 2)
        for bl in behavior_lines[:6]:  # max 6 lines
            lines.append(_pad(f"  {bl}"))

    lines.append(f"  {_BOX_BL}{_BOX_H * (inner + 4)}{_BOX_BR}")
    return "\n".join(lines) + "\n"


def _extract_behavior_lines(instructions: str, max_width: int) -> list[str]:
    """Extract key behavior points from instruction text.

    Looks for lines starting with '- ' or numbered items, and wraps long lines.
    Falls back to the first few sentences if no bullet points found.
    """
    bullets = []
    for line in instructions.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") or stripped.startswith("* "):
            text = stripped[2:].strip()
            wrapped = textwrap.wrap(text, width=max_width)
            if wrapped:
                bullets.append("- " + wrapped[0])
                for continuation in wrapped[1:]:
                    bullets.append("  " + continuation)
        elif re.match(r"^\d+\.\s", stripped):
            text = re.sub(r"^\d+\.\s*", "", stripped)
            wrapped = textwrap.wrap(text, width=max_width)
            if wrapped:
                bullets.append("- " + wrapped[0])
                for continuation in wrapped[1:]:
                    bullets.append("  " + continuation)

    if bullets:
        return bullets

    # Fallback: first 3 sentences
    sentences = re.split(r"(?<=[.!?])\s+", instructions.strip())
    result = []
    for s in sentences[:3]:
        wrapped = textwrap.wrap(s, width=max_width)
        if wrapped:
            result.append("- " + wrapped[0])
            for continuation in wrapped[1:]:
                result.append("  " + continuation)
    return result


# ---------------------------------------------------------------------------
# Agent table rendering (for list_agents results)
# ---------------------------------------------------------------------------

def render_agent_table(result_text: str) -> str:
    """Render a list_agents result as a formatted table.

    Args:
        result_text: Raw text from the list_agents tool result.

    Returns:
        Formatted table string, or the raw text if parsing fails.
    """
    lines = result_text.strip().splitlines()
    if len(lines) < 3:
        return f"  {result_text}\n"

    # The list_agents tool returns lines like:
    #   name                       STATUS     exec=...
    # Try to parse and reformat
    output = ["\n"]
    output.append(f"  {'Name':<28} {'Status':<12} {'Execution'}\n")
    output.append(f"  {_BOX_H * 28} {_BOX_H * 12} {_BOX_H * 16}\n")

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("Agents:"):
            continue
        parts = stripped.split()
        if len(parts) >= 2:
            name = parts[0]
            status = parts[1] if len(parts) > 1 else ""
            rest = " ".join(parts[2:]) if len(parts) > 2 else ""
            icon = _status_icon(status)
            output.append(f"  {icon} {name:<26} {status:<12} {rest}\n")
        else:
            output.append(f"  {stripped}\n")

    output.append("\n")
    return "".join(output)


def _status_icon(status: str) -> str:
    """Return a status icon character for an agent status."""
    s = status.upper()
    if s == "ACTIVE":
        return "\u25cf"  # filled circle
    if s == "PAUSED":
        return "\u25cb"  # empty circle
    if s == "ERROR":
        return "\u25cf"  # filled circle (red context)
    if s == "WAITING":
        return "\u25d4"  # circle with quarter
    if s == "DRAFT":
        return "\u25cb"  # empty circle
    if s == "ARCHIVED":
        return "\u25cb"  # empty circle
    return "\u25cf"


# ---------------------------------------------------------------------------
# Validation result parsing
# ---------------------------------------------------------------------------

def _parse_validation_result(result: str) -> tuple[bool, str]:
    """Parse a validation gate result into (passed, detail).

    Returns:
        Tuple of (True, "") if PASS, or (False, reason) if FAIL.
    """
    result = result.strip()
    if result == "PASS":
        return True, ""
    if result.startswith("FAIL:"):
        reason = result[5:].strip()
        return False, reason
    return False, result


# ---------------------------------------------------------------------------
# Main event formatter
# ---------------------------------------------------------------------------

# Track which tools we have seen a TOOL_CALL for, so we can correlate TOOL_RESULT
_PROGRESS_TOOLS = {
    "expand_prompt",
    "generate_agent",
    "validate_spec",
    "validate_code",
    "validate_integrations",
    "validate_deployment",
    "deploy_agent",
    "acquire_credentials",
    "signal_agent",
    "list_agents",
    "reply_to_user",
    "web_search",
    "check_credentials",
    "prompt_credentials",
    "read_agent_config",
    "get_agent_status",
    "get_notifications",
    "pause_agent",
    "resume_agent",
    "archive_agent",
    "update_agent",
    "resolve_integrations",
}


def format_event(event) -> str:
    """Format a single stream event as polished user-facing text.

    Translates raw tool calls into progress messages, renders spec summary
    boxes, and converts validation results into checkmark/warning indicators.

    Returns empty string for events that should be suppressed (like
    wait_for_message or internal bookkeeping).
    """
    etype = event.type
    args = event.args or {}

    # -- THINKING ----------------------------------------------------------
    if etype == EventType.THINKING:
        return ""  # suppress thinking from user view

    # -- TOOL_CALL ---------------------------------------------------------
    if etype == EventType.TOOL_CALL:
        return _format_tool_call(event.tool_name or "", args)

    # -- TOOL_RESULT -------------------------------------------------------
    if etype == EventType.TOOL_RESULT:
        return _format_tool_result(event.tool_name or "", event.result)

    # -- WAITING -----------------------------------------------------------
    if etype == EventType.WAITING:
        return ""  # handled by the app layer

    # -- GUARDRAIL_PASS / GUARDRAIL_FAIL -----------------------------------
    if etype == EventType.GUARDRAIL_PASS:
        name = getattr(event, "guardrail_name", None) or "guardrail"
        return f"  {_CHECK} Guardrail passed: {name}\n"

    if etype == EventType.GUARDRAIL_FAIL:
        name = getattr(event, "guardrail_name", None) or "guardrail"
        content = getattr(event, "content", "") or ""
        detail = f": {content}" if content else ""
        return f"  {_CROSS} Guardrail failed: {name}{detail}\n"

    # -- HANDOFF -----------------------------------------------------------
    if etype == EventType.HANDOFF:
        target = getattr(event, "target", None) or getattr(event, "content", "") or ""
        return f"  Handing off to {target}...\n"

    # -- ERROR / DONE ------------------------------------------------------
    if etype == EventType.ERROR:
        content = getattr(event, "content", "") or ""
        return f"\n  {_CROSS} Error: {content}\n"

    if etype == EventType.DONE:
        return ""

    return ""


def _format_tool_call(tool_name: str, args: dict) -> str:
    """Format a TOOL_CALL event into a user-friendly progress message."""

    # -- reply_to_user: show the agent's response cleanly --
    if tool_name == "reply_to_user":
        msg = args.get("message", "")
        # Detect future tense promises that create user-agent deadlocks.
        # The agent says "I'll investigate" then calls wait_for_message —
        # user thinks agent is working, agent is waiting for user. Deadlock.
        _FUTURE_PATTERNS = [
            "i'll ", "i will ", "going to ", "let me investigate",
            "i need to investigate", "will get back", "will investigate",
            "i'll need to", "let me look into", "i'm going to",
            "will try to", "will attempt to", "need to resolve",
        ]
        if any(p in msg.lower() for p in _FUTURE_PATTERNS):
            msg = msg.rstrip() + "\n\n(Ready for your next request.)"
        return f"\n{'--- Claw ' + '-' * 53}\n{msg}\n"

    # -- wait_for_message: suppress --
    if tool_name == "wait_for_message":
        return ""

    # -- expand_prompt: show progress --
    if tool_name == "expand_prompt":
        return f"\n  Expanding your request...\n"

    # -- generate_agent: show building progress --
    if tool_name == "generate_agent":
        agent_name = args.get("agent_name", "")
        suffix = f" ({agent_name})" if agent_name else ""
        return f"  Building agent{suffix}...\n"

    # -- validation gates --
    if tool_name == "validate_spec":
        return ""  # result will show the status
    if tool_name == "validate_code":
        return ""
    if tool_name == "validate_integrations":
        return ""
    if tool_name == "validate_deployment":
        return ""

    # -- deploy_agent --
    if tool_name == "deploy_agent":
        agent_name = args.get("agent_name", "")
        return f"  Deploying agent{' ' + agent_name if agent_name else ''}...\n"

    # -- acquire_credentials --
    if tool_name == "acquire_credentials":
        cred_name = args.get("credential_name", "")
        return f"  Setting up credentials ({cred_name})...\n"

    # -- check_credentials --
    if tool_name == "check_credentials":
        return ""  # result will show

    # -- signal_agent --
    if tool_name == "signal_agent":
        agent_name = args.get("agent_name", "")
        return f"  Sending signal to {agent_name}...\n"

    # -- list_agents --
    if tool_name == "list_agents":
        return ""  # result will render as table

    # -- web_search --
    if tool_name == "web_search":
        query = args.get("query", "")
        return f"  Searching: {query}\n"

    # -- read_document / read_agent_config --
    if tool_name == "read_document":
        path = args.get("path", "")
        return f"  Reading document: {path}\n"
    if tool_name == "read_agent_config":
        return ""  # silent

    # -- management tools --
    if tool_name == "get_agent_status":
        return ""
    if tool_name == "get_notifications":
        return ""
    if tool_name == "pause_agent":
        agent_name = args.get("agent_name", "")
        return f"  Pausing {agent_name}...\n"
    if tool_name == "resume_agent":
        agent_name = args.get("agent_name", "")
        return f"  Resuming {agent_name}...\n"
    if tool_name == "archive_agent":
        agent_name = args.get("agent_name", "")
        return f"  Archiving {agent_name}...\n"
    if tool_name == "update_agent":
        agent_name = args.get("agent_name", "")
        return f"  Updating {agent_name}...\n"
    if tool_name == "resolve_integrations":
        return ""

    if tool_name == "prompt_credentials":
        return ""

    # -- Anything else: generic "Working..." --
    return "  Working...\n"


def _format_tool_result(tool_name: str, result) -> str:
    """Format a TOOL_RESULT event into a user-friendly status message."""
    result_str = str(result) if result is not None else ""

    # -- expand_prompt result: show checkmark --
    if tool_name == "expand_prompt":
        return f"  {_CHECK} Generated specification\n\n  Here's what I'll build:\n"

    # -- generate_agent result: try to render spec box --
    if tool_name == "generate_agent":
        if "created successfully" in result_str:
            return f"  {_CHECK} Agent files created\n"
        if result_str.startswith("Error:"):
            return f"  {_CROSS} Agent creation failed: {result_str}\n"
        return f"  {_CHECK} Agent files created\n"

    # -- validate_spec --
    if tool_name == "validate_spec":
        passed, detail = _parse_validation_result(result_str)
        if passed:
            return f"  {_CHECK} Specification valid\n"
        return f"  {_CROSS} Specification issue: {detail}\n"

    # -- validate_code --
    if tool_name == "validate_code":
        passed, detail = _parse_validation_result(result_str)
        if passed:
            return f"  {_CHECK} Code validated\n"
        return f"  {_CROSS} Code issue: {detail}\n"

    # -- validate_integrations --
    if tool_name == "validate_integrations":
        passed, detail = _parse_validation_result(result_str)
        if passed:
            return f"  {_CHECK} Integrations available\n"
        # Extract missing credentials for a nice warning
        if "missing credentials:" in detail.lower():
            cred_match = re.search(r"missing credentials?:\s*(.+)", detail, re.IGNORECASE)
            if cred_match:
                cred_names = cred_match.group(1).strip()
                return f"  {_WARN} Missing credential: {cred_names}\n"
        return f"  {_WARN} Integration issue: {detail}\n"

    # -- validate_deployment --
    if tool_name == "validate_deployment":
        passed, detail = _parse_validation_result(result_str)
        if passed:
            return f"  {_CHECK} Deployment check passed\n"
        return f"  {_CROSS} Deployment issue: {detail}\n"

    # -- deploy_agent -- show the agent's actual output
    if tool_name == "deploy_agent":
        if result_str.startswith("Error") or "Agent failed:" in result_str:
            return f"  {_CROSS} Deployment failed:\n{result_str}\n"
        if "Failed to install dependencies" in result_str:
            return f"  {_CROSS} Dependency installation failed:\n{result_str}\n"
        if "syntax error" in result_str.lower():
            return f"  {_CROSS} Worker code error:\n{result_str}\n"

        lines = []

        # Extract execution ID
        eid_match = re.search(r"Execution ID:\s*(\S+)", result_str)
        eid = eid_match.group(1) if eid_match else ""
        lines.append(f"  {_CHECK} Agent deployed{' (Execution: ' + eid + ')' if eid else ''}")

        # Extract and display the agent's output — this is the important part
        output_match = re.search(r"Agent output:\n(.+)", result_str, re.DOTALL)
        if output_match:
            agent_output = output_match.group(1).strip()
            # Clean up dict-like output from subprocess
            if agent_output.startswith("{'result':") or agent_output.startswith('{"result":'):
                try:
                    import ast
                    parsed = ast.literal_eval(agent_output)
                    if isinstance(parsed, dict) and "result" in parsed:
                        agent_output = str(parsed["result"])
                except Exception:
                    pass
            lines.append("")
            lines.append(f"{'=' * 60}")
            lines.append(f"  AGENT OUTPUT:")
            lines.append(f"{'=' * 60}")
            lines.append(agent_output)
            lines.append(f"{'=' * 60}")

        return "\n".join(lines) + "\n"

    # -- acquire_credentials --
    if tool_name == "acquire_credentials":
        if "acquired" in result_str.lower() and "success" in result_str.lower():
            return f"  {_CHECK} Credential acquired\n"
        if "error" in result_str.lower():
            return f"  {_WARN} Credential issue: {result_str}\n"
        return f"  {result_str}\n"

    # -- check_credentials --
    if tool_name == "check_credentials":
        if "does not require" in result_str:
            return f"  {_CHECK} No credentials needed\n"
        return ""  # detail is handled by the orchestrator

    # -- signal_agent --
    if tool_name == "signal_agent":
        if "Signal sent" in result_str:
            agent_match = re.search(r"'([^']+)'", result_str)
            agent = agent_match.group(1) if agent_match else "agent"
            return f"  {_CHECK} Signal sent to {agent}\n"
        return f"  {result_str}\n"

    # -- list_agents: render as table --
    if tool_name == "list_agents":
        if result_str and "No agents" not in result_str:
            return render_agent_table(result_str)
        return f"  {result_str}\n"

    # -- web_search result: truncated --
    if tool_name == "web_search":
        if result_str:
            truncated = result_str[:500]
            if len(result_str) > 500:
                truncated += "\n  ... (truncated)"
            return f"  {truncated}\n"
        return ""

    # -- reply_to_user: suppress result (already shown in TOOL_CALL) --
    if tool_name == "reply_to_user":
        return ""

    # -- wait_for_message: suppress --
    if tool_name == "wait_for_message":
        return ""

    # -- management results: typically shown by orchestrator reply --
    if tool_name in (
        "read_agent_config",
        "get_agent_status",
        "get_notifications",
        "update_agent",
        "resolve_integrations",
        "prompt_credentials",
    ):
        return ""

    if tool_name in ("pause_agent", "resume_agent", "archive_agent"):
        if "Error" in result_str:
            return f"  {_CROSS} {result_str}\n"
        return f"  {_CHECK} {result_str}\n"

    # -- Everything else: suppress --
    return ""


# ---------------------------------------------------------------------------
# Welcome screen
# ---------------------------------------------------------------------------

def render_welcome(session_id: str = "") -> str:
    """Render the Claw welcome screen with ASCII art logo.

    Args:
        session_id: Optional session/execution ID to display.

    Returns:
        Multi-line welcome banner string.
    """
    W = 62  # inner width

    H = "\u2550"  # double horizontal
    V = "\u2551"  # double vertical
    TL = "\u2554"  # double top-left
    TR = "\u2557"  # double top-right
    BL = "\u255a"  # double bottom-left
    BR = "\u255d"  # double bottom-right

    def _dpad(text: str) -> str:
        return f"{V}  {text:<{W - 2}}  {V}"

    lines = []
    lines.append(f"{TL}{H * (W + 2)}{TR}")
    lines.append(_dpad(""))
    lines.append(_dpad("\u2584\u2580\u2580 \u2588   \u2584\u2580\u2584 \u2588   \u2588"))
    lines.append(_dpad("\u2588   \u2588   \u2588\u2580\u2588 \u2588\u2584\u2588\u2584\u2588"))
    lines.append(_dpad("\u2580\u2584\u2584 \u2580\u2584\u2584 \u2580 \u2580  \u2580 \u2580   Agentspan Claw"))
    lines.append(_dpad(""))
    lines.append(_dpad("Describe what you want automated."))
    lines.append(_dpad("Type /help for commands, /dashboard for agent status."))
    if session_id:
        lines.append(_dpad(""))
        short = session_id[:16] + "..." if len(session_id) > 16 else session_id
        lines.append(_dpad(f"Session: {short}"))
    lines.append(_dpad(""))
    lines.append(f"{BL}{H * (W + 2)}{BR}")
    lines.append("")

    return "\n".join(lines) + "\n"
