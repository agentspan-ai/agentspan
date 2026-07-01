# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for ConversationMemory."""

from conductor.ai.agents.memory import ConversationMemory


class TestConversationMemoryBasic:
    """Test basic message operations."""

    def test_defaults(self):
        mem = ConversationMemory()
        assert mem.messages == []
        assert mem.max_messages is None

    def test_add_user_message(self):
        mem = ConversationMemory()
        mem.add_user_message("Hello")
        assert len(mem.messages) == 1
        assert mem.messages[0] == {"role": "user", "message": "Hello"}

    def test_add_assistant_message(self):
        mem = ConversationMemory()
        mem.add_assistant_message("Hi there")
        assert len(mem.messages) == 1
        assert mem.messages[0]["role"] == "assistant"
        assert mem.messages[0]["message"] == "Hi there"

    def test_add_system_message(self):
        mem = ConversationMemory()
        mem.add_system_message("You are helpful.")
        assert mem.messages[0]["role"] == "system"

    def test_add_tool_call(self):
        mem = ConversationMemory()
        mem.add_tool_call("weather", {"city": "NYC"})
        assert len(mem.messages) == 1
        assert mem.messages[0]["role"] == "tool_call"
        assert mem.messages[0]["tool_calls"][0]["name"] == "weather"

    def test_add_tool_result(self):
        mem = ConversationMemory()
        mem.add_tool_result("weather", "72F and sunny")
        assert mem.messages[0]["role"] == "tool"
        assert "72F" in mem.messages[0]["message"]
        assert mem.messages[0]["toolCallId"] == "weather_ref"

    def test_add_tool_result_with_ref(self):
        mem = ConversationMemory()
        mem.add_tool_result("weather", "72F", task_reference_name="call_abc")
        assert mem.messages[0]["toolCallId"] == "call_abc"

    def test_to_chat_messages(self):
        mem = ConversationMemory()
        mem.add_system_message("System")
        mem.add_user_message("User")
        msgs = mem.to_chat_messages()
        assert len(msgs) == 2
        # Should be a copy
        msgs.append({"role": "test"})
        assert len(mem.messages) == 2

    def test_clear(self):
        mem = ConversationMemory()
        mem.add_user_message("A")
        mem.add_user_message("B")
        mem.clear()
        assert mem.messages == []


class TestConversationMemoryTrimming:
    """Test message trimming with max_messages."""

    def test_no_trimming_when_under_limit(self):
        mem = ConversationMemory(max_messages=5)
        mem.add_user_message("A")
        mem.add_user_message("B")
        assert len(mem.messages) == 2

    def test_trims_to_max(self):
        mem = ConversationMemory(max_messages=3)
        mem.add_user_message("A")
        mem.add_user_message("B")
        mem.add_user_message("C")
        mem.add_user_message("D")
        assert len(mem.messages) == 3
        # Oldest non-system message should be trimmed
        assert mem.messages[0]["message"] == "B"

    def test_preserves_system_messages(self):
        mem = ConversationMemory(max_messages=3)
        mem.add_system_message("System prompt")
        mem.add_user_message("A")
        mem.add_user_message("B")
        mem.add_user_message("C")
        assert len(mem.messages) == 3
        # System message preserved
        assert mem.messages[0]["role"] == "system"
        # Oldest user message trimmed
        assert mem.messages[1]["message"] == "B"
        assert mem.messages[2]["message"] == "C"

    def test_multiple_system_messages(self):
        mem = ConversationMemory(max_messages=4)
        mem.add_system_message("Sys1")
        mem.add_system_message("Sys2")
        mem.add_user_message("A")
        mem.add_user_message("B")
        mem.add_user_message("C")
        assert len(mem.messages) == 4
        assert mem.messages[0]["role"] == "system"
        assert mem.messages[1]["role"] == "system"

    def test_pre_populated_messages(self):
        existing = [
            {"role": "system", "message": "You are helpful"},
            {"role": "user", "message": "Hi"},
            {"role": "assistant", "message": "Hello"},
        ]
        mem = ConversationMemory(messages=existing)
        assert len(mem.messages) == 3
        assert mem.messages[0]["role"] == "system"


# ── P3-C / P4-G: Memory edge cases ──────────────────────────────────


class TestConversationMemoryTrimOrdering:
    """Test that _trim() preserves original message ordering."""

    def test_mid_conversation_system_message_preserved_in_order(self):
        """System message in the middle of conversation keeps its position."""
        mem = ConversationMemory(max_messages=4)
        mem.add_user_message("A")
        mem.add_assistant_message("B")
        mem.add_system_message("Mid-system")
        mem.add_user_message("C")
        mem.add_assistant_message("D")
        # We have 5 messages, limit 4.
        # Should drop oldest non-system ("A"), keep system in place.
        assert len(mem.messages) == 4
        roles = [m["role"] for m in mem.messages]
        assert "system" in roles
        # System should still be before "C" and "D"
        sys_idx = roles.index("system")
        assert sys_idx < roles.index("user")  # system before "C"
        # "A" should be gone
        assert all(m["message"] != "A" for m in mem.messages)

    def test_all_system_messages_preserved(self):
        """All system messages survive trimming."""
        mem = ConversationMemory(max_messages=3)
        mem.add_system_message("Sys1")
        mem.add_user_message("A")
        mem.add_system_message("Sys2")
        mem.add_user_message("B")
        # 4 messages, limit 3. 2 system, 1 non-system slot.
        assert len(mem.messages) == 3
        system_msgs = [m for m in mem.messages if m["role"] == "system"]
        assert len(system_msgs) == 2

    def test_trim_when_system_exceeds_budget(self):
        """When system messages alone exceed the budget, keep latest system only."""
        mem = ConversationMemory(max_messages=2)
        mem.add_system_message("Sys1")
        mem.add_system_message("Sys2")
        mem.add_system_message("Sys3")
        assert len(mem.messages) == 2
        assert mem.messages[0]["message"] == "Sys2"
        assert mem.messages[1]["message"] == "Sys3"

    def test_no_max_messages_no_trim(self):
        """Without max_messages, no trimming occurs."""
        mem = ConversationMemory()
        for i in range(100):
            mem.add_user_message(f"msg_{i}")
        assert len(mem.messages) == 100

    def test_max_tokens_field_removed(self):
        """max_tokens field was removed from ConversationMemory."""
        import dataclasses

        field_names = [f.name for f in dataclasses.fields(ConversationMemory)]
        assert "max_tokens" not in field_names


class TestConversationMemoryMutationIsolation:
    """Test that to_chat_messages() returns a deep copy."""

    def test_dict_mutation_does_not_affect_internal_state(self):
        """Mutating a returned message dict does not change internal messages."""
        mem = ConversationMemory()
        mem.add_user_message("Hello")
        msgs = mem.to_chat_messages()
        msgs[0]["role"] = "hacked"
        assert mem.messages[0]["role"] == "user"

    def test_nested_mutation_does_not_affect_internal_state(self):
        """Mutating nested tool_calls in returned message does not corrupt internal state."""
        mem = ConversationMemory()
        mem.add_tool_call("weather", {"city": "NYC"})
        msgs = mem.to_chat_messages()
        # Mutate the nested tool_calls list
        msgs[0]["tool_calls"][0]["name"] = "hacked"
        assert mem.messages[0]["tool_calls"][0]["name"] == "weather"
