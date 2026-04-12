"""Dashboard view — renders agent list and notifications as formatted text for the TUI."""

from __future__ import annotations

from datetime import datetime
from typing import Optional


_SEPARATOR = "\u2500" * 62

# Status indicators per agent state
_STATUS_ICONS = {
    "active": "[*]",
    "paused": "[-]",
    "waiting": "[?]",
    "error": "[!]",
    "archived": "[x]",
    "draft": "[ ]",
    "deploying": "[~]",
}


def _format_time(ts: Optional[str]) -> str:
    """Format an ISO timestamp for display, or return 'never' if missing."""
    if not ts:
        return "never"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return ts[:16] if len(ts) >= 16 else ts


def render_dashboard(agents: list[dict], notifications: list[dict]) -> str:
    """Render the dashboard view as formatted text for the TUI.

    Args:
        agents: List of agent dicts with keys: name, status, last_run, trigger.
        notifications: List of notification dicts with keys: agent_name, timestamp,
            summary, priority, read.

    Returns:
        Formatted multi-line string suitable for appending to the TUI output area.
    """
    lines: list[str] = []

    # Header
    lines.append("")
    lines.append(f"{'=' * 62}")
    lines.append("  DASHBOARD")
    lines.append(f"{'=' * 62}")
    lines.append("")

    # Agent table
    lines.append("  AGENTS")
    lines.append(f"  {_SEPARATOR}")

    if not agents:
        lines.append("  No agents configured.")
    else:
        # Header row
        lines.append(f"  {'Status':<8} {'Name':<24} {'Last Run':<18} {'Trigger'}")
        lines.append(f"  {'------':<8} {'----':<24} {'--------':<18} {'-------'}")
        for agent in agents:
            name = agent.get("name", "unknown")
            status = agent.get("status", "unknown")
            last_run = _format_time(agent.get("last_run"))
            trigger = agent.get("trigger", "")
            icon = _STATUS_ICONS.get(status, "[?]")
            lines.append(f"  {icon:<8} {name:<24} {last_run:<18} {trigger}")

    lines.append("")

    # Notifications section
    unread = [n for n in notifications if not n.get("read", False)]
    unread_count = len(unread)

    lines.append(f"  NOTIFICATIONS ({unread_count} unread)")
    lines.append(f"  {_SEPARATOR}")

    if not notifications:
        lines.append("  No notifications.")
    else:
        # Show most recent notifications (up to 10)
        recent = notifications[:10]
        for notif in recent:
            priority = notif.get("priority", "info")
            icon = {"urgent": "(!)", "normal": "( )", "info": "(i)"}.get(priority, "( )")
            read_mark = " " if notif.get("read", False) else "*"
            ts = _format_time(notif.get("timestamp"))
            agent_name = notif.get("agent_name", "")
            summary = notif.get("summary", "")
            lines.append(f"  {read_mark} {icon} {ts}  {agent_name}: {summary}")

    lines.append("")
    lines.append(f"{'=' * 62}")
    lines.append("")

    return "\n".join(lines)
