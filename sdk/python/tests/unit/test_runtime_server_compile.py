# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for server-side compilation in AgentRuntime."""


class TestServerCompileIntegration:
    """Test server-side compilation flow in AgentRuntime."""

    def test_compile_via_server_serializes_correctly(self):
        """AgentConfigSerializer produces correct JSON for server compilation."""
        from conductor.ai.agents.agent import Agent
        from conductor.ai.agents.config_serializer import AgentConfigSerializer

        agent = Agent(name="test", model="openai/gpt-4o", instructions="Hello")
        serializer = AgentConfigSerializer()
        result = serializer.serialize(agent)

        assert result["name"] == "test"
        assert result["model"] == "openai/gpt-4o"
        assert result["instructions"] == "Hello"
