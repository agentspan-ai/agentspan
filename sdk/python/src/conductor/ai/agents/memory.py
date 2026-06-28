# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Memory — session and conversation history management.

Conversation state is persisted in Conductor workflow variables, surviving
process crashes.  This module handles message accumulation, trimming, and
(future) summarisation.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ConversationMemory:
    """Manages conversation history for an agent session.

    Stores messages in a format compatible with Conductor's
    ``workflow.variables`` so that conversation state is persisted
    across workflow executions and process restarts.

    Attributes:
        messages: The accumulated conversation messages.
        max_messages: Maximum messages to retain (oldest are trimmed).
    """

    messages: List[Dict[str, Any]] = field(default_factory=list)
    max_messages: Optional[int] = None

    def add_user_message(self, content: str) -> None:
        """Append a user message to the conversation."""
        self.messages.append({"role": "user", "message": content})
        self._trim()

    def add_assistant_message(self, content: str) -> None:
        """Append an assistant message to the conversation."""
        self.messages.append({"role": "assistant", "message": content})
        self._trim()

    def add_system_message(self, content: str) -> None:
        """Append a system message to the conversation."""
        self.messages.append({"role": "system", "message": content})
        self._trim()

    def add_tool_call(
        self, tool_name: str, arguments: Dict[str, Any], task_reference_name: Optional[str] = None
    ) -> None:
        """Record a tool call in the conversation."""
        ref = task_reference_name or f"{tool_name}_ref"
        self.messages.append(
            {
                "role": "tool_call",
                "message": "",
                "tool_calls": [{"name": tool_name, "taskReferenceName": ref, "input": arguments}],
            }
        )
        self._trim()

    def add_tool_result(
        self, tool_name: str, result: Any, task_reference_name: Optional[str] = None
    ) -> None:
        """Record a tool result in the conversation."""
        ref = task_reference_name or f"{tool_name}_ref"
        self.messages.append(
            {
                "role": "tool",
                "message": str(result),
                "toolCallId": ref,
                "taskReferenceName": ref,
            }
        )
        self._trim()

    def to_chat_messages(self) -> List[Dict[str, Any]]:
        """Return messages in a format compatible with ``ChatMessage``."""
        return copy.deepcopy(self.messages)

    def clear(self) -> None:
        """Clear all conversation history."""
        self.messages.clear()

    def _trim(self) -> None:
        """Trim messages to stay within configured limits.

        Preserves original ordering: removes the oldest non-system messages
        first while keeping all system messages in their original positions.
        """
        if self.max_messages and len(self.messages) > self.max_messages:
            system_count = sum(1 for m in self.messages if m.get("role") == "system")
            if system_count >= self.max_messages:
                # More system messages than budget — keep only the latest
                system_msgs = [m for m in self.messages if m.get("role") == "system"]
                self.messages = system_msgs[-self.max_messages :]
                return

            # Number of non-system messages we can keep
            keep_non_system = self.max_messages - system_count
            # Count non-system messages from the end to find the cutoff
            non_system_seen = 0
            cutoff_idx = len(self.messages)
            for i in range(len(self.messages) - 1, -1, -1):
                if self.messages[i].get("role") != "system":
                    non_system_seen += 1
                    if non_system_seen == keep_non_system:
                        cutoff_idx = i
                        break

            # Keep all messages from cutoff_idx onward, plus system messages before it
            result = [m for m in self.messages[:cutoff_idx] if m.get("role") == "system"]
            result.extend(self.messages[cutoff_idx:])
            self.messages = result
