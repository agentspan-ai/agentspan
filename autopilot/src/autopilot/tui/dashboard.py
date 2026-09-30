"""Dashboard view — renders agent list and notifications with box-drawing characters.

Renders a polished dashboard panel for the TUI:

    +==============================================================+
    |  AGENTSPAN CLAW -- Dashboard                                  |
    +==============================================================+
    |                                                                |
    |  AGENTS                         STATUS    TRIGGER   LAST RUN   |
    |  ...                                                           |
    |                                                                |
    |  NOTIFICATIONS (N new)                                         |
    |  ...                                                           |
    |                                                                |
    +==============================================================+
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Box-drawing characters
# ---------------------------------------------------------------------------

_DH = "\u2550"  # double horizontal
_DV = "\u2551"  # double vertical
_DTL = "\u2554"  # double top-left
_DTR = "\u2557"  # double top-right
_DBL = "\u255a"  # double bottom-left
_DBR = "\u255d"  # double bottom-right
_DML = "\u2560"  # double left-T
_DMR = "\u2563"  # double right-T

_SH = "\u2500"  # single horizontal

_WIDTH = 62  # inner content width


# ---------------------------------------------------------------------------
# Status indicators per agent state
# ---------------------------------------------------------------------------

_STATUS_ICONS = {
    "active": "\u25cf",  # filled circle
    "paused": "\u25cb",  # empty circle
    "waiting": "\u25d4",  # circle with upper-right quadrant
    "error": "\u25cf",  # filled circle (contextually red)
    "archived": "\u25cb",  # empty circle
    "draft": "\u25cb",  # empty circle
    "deploying": "\u25d4",  # circle with quarter
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_time(ts: Optional[str]) -> str:
    """Format an ISO timestamp for compact display, or return 'never' if missing."""
    if not ts:
        return "never"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        delta = now - dt
        if delta.days == 0:
            return "today"
        if delta.days == 1:
            return "yesterday"
        if delta.days < 7:
            return f"{delta.days}d ago"
        return dt.strftime("%b %d")
    except (ValueError, AttributeError, TypeError):
        if len(ts) >= 10:
            return ts[:10]
        return ts


def _dpad(text: str, width: int = _WIDTH) -> str:
    """Pad text inside double-border lines."""
    return f"{_DV}  {text:<{width}}  {_DV}"


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_dashboard(agents: list[dict], notifications: list[dict]) -> str:
    """Render the dashboard view as formatted text with box-drawing borders.

    Args:
        agents: List of agent dicts with keys: name, status, last_run, trigger.
        notifications: List of notification dicts with keys: agent_name, timestamp,
            summary, priority, read.

    Returns:
        Formatted multi-line string suitable for appending to the TUI output area.
    """
    W = _WIDTH
    lines: list[str] = []

    # -- Top border + title --
    lines.append("")
    lines.append(f"{_DTL}{_DH * (W + 4)}{_DTR}")
    lines.append(_dpad("AGENTSPAN CLAW \u2014 Dashboard", W))
    lines.append(f"{_DML}{_DH * (W + 4)}{_DMR}")
    lines.append(_dpad("", W))

    # -- Agent table --
    if not agents:
        lines.append(_dpad("No agents configured.", W))
    else:
        # Header
        header = f"{'AGENTS':<30}{'STATUS':<10}{'TRIGGER':<10}{'LAST RUN'}"
        lines.append(_dpad(header, W))
        sep = f"{_SH * 30}{_SH * 10}{_SH * 10}{_SH * 12}"
        lines.append(_dpad(sep, W))

        for agent in agents:
            name = agent.get("name", "unknown")
            status = agent.get("status", "unknown")
            trigger = agent.get("trigger", "")
            last_run = _format_time(agent.get("last_run"))
            icon = _STATUS_ICONS.get(status.lower(), "\u25cf")

            row = f"{icon} {name:<28}{status:<10}{trigger:<10}{last_run}"
            lines.append(_dpad(row, W))

    lines.append(_dpad("", W))

    # -- Notifications section --
    unread = [n for n in notifications if not n.get("read", False)]
    unread_count = len(unread)
    notif_header = f"NOTIFICATIONS ({unread_count} new)"
    lines.append(_dpad(notif_header, W))
    notif_sep = _SH * (W)
    lines.append(_dpad(notif_sep, W))

    if not notifications:
        lines.append(_dpad("No notifications.", W))
    else:
        recent = notifications[:10]
        for notif in recent:
            priority = notif.get("priority", "info")
            icon = {"urgent": "!", "normal": "\u2713", "info": "\u2022"}.get(priority, "\u2022")
            read_mark = " " if notif.get("read", False) else "*"
            ts = _format_time_short(notif.get("timestamp"))
            agent_name = notif.get("agent_name", "")
            summary = notif.get("summary", "")

            # Truncate long summaries
            max_summary = W - len(ts) - len(agent_name) - 10
            if len(summary) > max_summary and max_summary > 3:
                summary = summary[:max_summary - 3] + "..."

            row = f"{read_mark} {icon} {ts}  {agent_name}: {summary}"
            lines.append(_dpad(row, W))

    lines.append(_dpad("", W))

    # -- Bottom border --
    lines.append(f"{_DBL}{_DH * (W + 4)}{_DBR}")
    lines.append("")

    return "\n".join(lines)


def _format_time_short(ts: Optional[str]) -> str:
    """Format a timestamp as a short time string like '7:58am'."""
    if not ts:
        return "     "
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        hour = dt.hour
        minute = dt.minute
        ampm = "am" if hour < 12 else "pm"
        display_hour = hour % 12
        if display_hour == 0:
            display_hour = 12
        return f"{display_hour}:{minute:02d}{ampm}"
    except (ValueError, AttributeError, TypeError):
        if len(ts) >= 5:
            return ts[11:16] if len(ts) > 16 else ts[:5]
        return ts
