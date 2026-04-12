"""iMessage tools — macOS osascript integration."""

from __future__ import annotations

import platform
import subprocess
from typing import Any, List

from agentspan.agents import tool


def _check_macos() -> None:
    """Raise RuntimeError if not running on macOS."""
    if platform.system() != "Darwin":
        raise RuntimeError(
            "iMessage integration is only available on macOS "
            f"(current platform: {platform.system()})"
        )


@tool
def imessage_send(to: str, text: str) -> str:
    """Send an iMessage using macOS osascript.

    Only works on macOS. Uses AppleScript to send via the Messages app.

    Args:
        to: Recipient phone number or Apple ID email.
        text: Message text to send.

    Returns:
        Confirmation message.
    """
    _check_macos()

    if not to:
        raise ValueError("to is required")
    if not text:
        raise ValueError("text is required")

    # Escape double quotes and backslashes for AppleScript
    escaped_text = text.replace("\\", "\\\\").replace('"', '\\"')
    escaped_to = to.replace("\\", "\\\\").replace('"', '\\"')

    script = f'''
    tell application "Messages"
        set targetService to 1st account whose service type = iMessage
        set targetBuddy to participant "{escaped_to}" of targetService
        send "{escaped_text}" to targetBuddy
    end tell
    '''

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(f"osascript failed: {result.stderr.strip()}")

    return f"Message sent to {to}"


def get_tools() -> List[Any]:
    """Return all imessage tools."""
    return [imessage_send]
