# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for extended agent types — GPTAssistantAgent."""

from unittest.mock import MagicMock, patch

from conductor.ai.agents.ext import GPTAssistantAgent


class TestGPTAssistantAgent:
    def test_creation_with_assistant_id(self):
        agent = GPTAssistantAgent(name="coder", assistant_id="asst_abc123")
        assert agent.assistant_id == "asst_abc123"
        assert agent.metadata["_assistant_id"] == "asst_abc123"
        assert agent.metadata["_agent_type"] == "gpt_assistant"

    def test_creation_normalizes_model(self):
        agent = GPTAssistantAgent(name="test", model="gpt-4o")
        assert agent.model == "openai/gpt-4o"

    def test_creation_model_already_prefixed(self):
        agent = GPTAssistantAgent(name="test", model="openai/gpt-4o")
        assert agent.model == "openai/gpt-4o"

    def test_repr(self):
        agent = GPTAssistantAgent(name="test", assistant_id="asst_123")
        r = repr(agent)
        assert "GPTAssistantAgent" in r
        assert "asst_123" in r

    def test_run_assistant_openai_not_installed(self):
        agent = GPTAssistantAgent(name="test")
        with patch.dict("sys.modules", {"openai": None}):
            with patch("builtins.__import__", side_effect=ImportError("no openai")):
                result = agent._run_assistant("hello")
        assert "openai package not installed" in result

    def test_run_assistant_missing_api_key(self):
        agent = GPTAssistantAgent(name="test")
        with patch("conductor.ai.agents.ext.GPTAssistantAgent._run_assistant") as mock_run:
            # Use the actual implementation but mock the openai import
            mock_openai = MagicMock()
            with patch.dict("sys.modules", {"openai": mock_openai}):
                import os

                old_key = os.environ.pop("OPENAI_API_KEY", None)
                try:
                    agent._api_key = None
                    result = (
                        agent._run_assistant.__wrapped__(agent, "hello")
                        if hasattr(agent._run_assistant, "__wrapped__")
                        else None
                    )
                finally:
                    if old_key:
                        os.environ["OPENAI_API_KEY"] = old_key

    def test_run_assistant_with_existing_id(self):
        agent = GPTAssistantAgent(name="test", assistant_id="asst_existing", api_key="sk-test")

        mock_openai = MagicMock()
        mock_client = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        # Mock thread creation and run
        mock_thread = MagicMock()
        mock_thread.id = "thread_123"
        mock_client.beta.threads.create.return_value = mock_thread

        mock_run = MagicMock()
        mock_run.status = "completed"
        mock_client.beta.threads.runs.create_and_poll.return_value = mock_run

        # Mock messages
        mock_block = MagicMock()
        mock_block.text.value = "Hello from assistant"
        mock_msg = MagicMock()
        mock_msg.role = "assistant"
        mock_msg.content = [mock_block]
        mock_messages = MagicMock()
        mock_messages.data = [mock_msg]
        mock_client.beta.threads.messages.list.return_value = mock_messages

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = agent._run_assistant("test message")

        assert result == "Hello from assistant"
        # Should NOT create a new assistant since we have an ID
        mock_client.beta.assistants.create.assert_not_called()

    def test_run_assistant_creates_assistant_when_no_id(self):
        agent = GPTAssistantAgent(name="test", api_key="sk-test")
        agent.assistant_id = None

        mock_openai = MagicMock()
        mock_client = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        # Mock assistant creation
        mock_assistant = MagicMock()
        mock_assistant.id = "asst_new"
        mock_client.beta.assistants.create.return_value = mock_assistant

        # Mock thread and run
        mock_thread = MagicMock()
        mock_thread.id = "thread_456"
        mock_client.beta.threads.create.return_value = mock_thread

        mock_run = MagicMock()
        mock_run.status = "completed"
        mock_client.beta.threads.runs.create_and_poll.return_value = mock_run

        mock_block = MagicMock()
        mock_block.text.value = "Created and replied"
        mock_msg = MagicMock()
        mock_msg.role = "assistant"
        mock_msg.content = [mock_block]
        mock_messages = MagicMock()
        mock_messages.data = [mock_msg]
        mock_client.beta.threads.messages.list.return_value = mock_messages

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = agent._run_assistant("hello")

        assert result == "Created and replied"
        mock_client.beta.assistants.create.assert_called_once()
        assert agent.assistant_id == "asst_new"

    def test_run_assistant_api_error(self):
        agent = GPTAssistantAgent(name="test", assistant_id="asst_123", api_key="sk-test")

        mock_openai = MagicMock()
        mock_client = MagicMock()
        mock_openai.OpenAI.return_value = mock_client
        mock_client.beta.threads.create.side_effect = Exception("API rate limited")

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = agent._run_assistant("hello")

        assert "OpenAI Assistant error" in result

    def test_run_assistant_non_completed_status(self):
        agent = GPTAssistantAgent(name="test", assistant_id="asst_123", api_key="sk-test")

        mock_openai = MagicMock()
        mock_client = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        mock_thread = MagicMock()
        mock_thread.id = "thread_789"
        mock_client.beta.threads.create.return_value = mock_thread

        mock_run = MagicMock()
        mock_run.status = "failed"
        mock_client.beta.threads.runs.create_and_poll.return_value = mock_run

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = agent._run_assistant("hello")

        assert "failed" in result
