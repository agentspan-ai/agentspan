"""ClaudeCode configuration for Agent(model=ClaudeCode(...)) or Agent(model='claude-code/opus')."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

_MODEL_ALIASES = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5",
}


def resolve_claude_code_model(alias: str) -> Optional[str]:
    """Resolve a short model alias to a full model ID. Returns None for empty alias (CLI default)."""
    if not alias:
        return None
    return _MODEL_ALIASES.get(alias, alias)


@dataclass
class ClaudeCode:
    """Configuration for Agent(model=ClaudeCode(...)).

    Example::

        from agentspan.agents import Agent, ClaudeCode

        reviewer = Agent(
            name="reviewer",
            model=ClaudeCode("opus", permission_mode=ClaudeCode.PermissionMode.ACCEPT_EDITS),
            instructions="Review code quality",
            tools=["Read", "Edit", "Bash"],
        )

    Or use the slash syntax shorthand::

        reviewer = Agent(name="reviewer", model="claude-code/opus", ...)
    """

    class PermissionMode(str, Enum):
        DEFAULT = "default"
        ACCEPT_EDITS = "acceptEdits"
        PLAN = "plan"
        BYPASS = "bypassPermissions"

    model_name: str = ""
    permission_mode: PermissionMode = PermissionMode.ACCEPT_EDITS

    def to_model_string(self) -> str:
        """Convert to the model string format used by Agent.model."""
        if self.model_name:
            return f"claude-code/{self.model_name}"
        return "claude-code"
