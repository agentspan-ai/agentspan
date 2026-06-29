# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for the @agent decorator, AgentDef, and external agents."""

import pytest

from conductor.ai.agents.agent import Agent, AgentDef, _resolve_agent, agent


class TestAgentDecorator:
    """Test @agent decorator behavior."""

    def test_bare_decorator(self):
        @agent
        def my_agent():
            """You are a helpful assistant."""
            return "You are a helpful assistant."

        assert hasattr(my_agent, "_agent_def")
        ad = my_agent._agent_def
        assert isinstance(ad, AgentDef)
        assert ad.name == "my_agent"
        assert ad.model == ""  # no model — inherits from parent
        assert ad.func is not None

    def test_decorator_with_model(self):
        @agent(model="openai/gpt-4o")
        def weatherbot():
            """You are a weather assistant."""
            return "You are a weather assistant."

        ad = weatherbot._agent_def
        assert ad.name == "weatherbot"
        assert ad.model == "openai/gpt-4o"

    def test_decorator_with_custom_name(self):
        @agent(name="custom_name", model="openai/gpt-4o")
        def my_func():
            """Some instructions."""

        assert my_func._agent_def.name == "custom_name"

    def test_decorator_with_tools(self):
        from conductor.ai.agents.tool import tool

        @tool
        def search(query: str) -> str:
            """Search the web."""
            return query

        @agent(model="openai/gpt-4o", tools=[search])
        def researcher():
            """You do research."""

        ad = researcher._agent_def
        assert len(ad.tools) == 1

    def test_function_still_callable(self):
        @agent(model="openai/gpt-4o")
        def my_agent():
            """Instructions."""
            return "dynamic instructions"

        assert my_agent() == "dynamic instructions"

    def test_docstring_preserved(self):
        @agent(model="openai/gpt-4o")
        def my_agent():
            """You are a helpful assistant."""

        assert my_agent.__doc__ == "You are a helpful assistant."

    def test_decorator_kwargs(self):
        @agent(
            model="openai/gpt-4o",
            strategy="sequential",
            max_turns=10,
            max_tokens=500,
            temperature=0.5,
            metadata={"key": "value"},
        )
        def my_agent():
            """Instructions."""

        ad = my_agent._agent_def
        assert ad.strategy == "sequential"
        assert ad.max_turns == 10
        assert ad.max_tokens == 500
        assert ad.temperature == 0.5
        assert ad.metadata == {"key": "value"}


class TestResolveAgent:
    """Test _resolve_agent() helper."""

    def test_agent_instance_passthrough(self):
        a = Agent(name="test", model="openai/gpt-4o")
        result = _resolve_agent(a)
        assert result is a

    def test_resolve_decorated_function(self):
        @agent(model="openai/gpt-4o")
        def my_agent():
            """You are a helper."""

        result = _resolve_agent(my_agent)
        assert isinstance(result, Agent)
        assert result.name == "my_agent"
        assert result.model == "openai/gpt-4o"
        # instructions is the original function (callable)
        assert callable(result.instructions)

    def test_model_inheritance(self):
        @agent  # no model
        def my_agent():
            """Instructions."""

        result = _resolve_agent(my_agent, parent_model="anthropic/claude-sonnet-4-20250514")
        assert isinstance(result, Agent)
        assert result.model == "anthropic/claude-sonnet-4-20250514"

    def test_explicit_model_not_overridden(self):
        @agent(model="openai/gpt-4o")
        def my_agent():
            """Instructions."""

        result = _resolve_agent(my_agent, parent_model="anthropic/claude-sonnet-4-20250514")
        assert result.model == "openai/gpt-4o"

    def test_invalid_input_raises_type_error(self):
        with pytest.raises(TypeError, match="Expected an Agent"):
            _resolve_agent("not an agent")

    def test_invalid_callable_raises_type_error(self):
        def plain_func():
            pass

        with pytest.raises(TypeError, match="Expected an Agent"):
            _resolve_agent(plain_func)


class TestExternalAgent:
    """Test external agent references."""

    def test_agent_no_model_is_external(self):
        a = Agent(name="remote_agent")
        assert a.external is True
        assert a.model == ""

    def test_agent_with_model_not_external(self):
        a = Agent(name="local_agent", model="openai/gpt-4o")
        assert a.external is False

    def test_external_repr(self):
        a = Agent(name="remote")
        assert "external=True" in repr(a)

    def test_external_in_agents_list(self):
        parent = Agent(
            name="team",
            model="openai/gpt-4o",
            agents=[
                Agent(name="external_one"),
                Agent(name="local", model="openai/gpt-4o"),
            ],
            strategy="sequential",
        )
        assert parent.agents[0].external is True
        assert parent.agents[1].external is False

    def test_external_agent_with_instructions(self):
        """External agents can have instructions for documentation purposes."""
        a = Agent(name="reviewer", instructions="Reviews compliance")
        assert a.external is True
        assert a.instructions == "Reviews compliance"


class TestAgentListResolution:
    """Test that Agent.agents resolves @agent-decorated functions."""

    def test_mixed_agents_list(self):
        @agent(model="openai/gpt-4o")
        def writer():
            """You write articles."""

        team = Agent(
            name="team",
            model="openai/gpt-4o",
            agents=[
                writer,
                Agent(name="editor", model="openai/gpt-4o"),
            ],
            strategy="sequential",
        )
        assert len(team.agents) == 2
        assert isinstance(team.agents[0], Agent)
        assert team.agents[0].name == "writer"
        assert isinstance(team.agents[1], Agent)
        assert team.agents[1].name == "editor"

    def test_model_inheritance_in_agents_list(self):
        @agent  # no model — should inherit from parent
        def summarizer():
            """Summarize text."""

        team = Agent(
            name="team",
            model="anthropic/claude-sonnet-4-20250514",
            agents=[summarizer],
            strategy="sequential",
        )
        assert team.agents[0].model == "anthropic/claude-sonnet-4-20250514"

    def test_invalid_agent_in_list_raises(self):
        with pytest.raises(TypeError, match="Expected an Agent"):
            Agent(
                name="team",
                model="openai/gpt-4o",
                agents=["not_an_agent"],
                strategy="sequential",
            )


class TestAgentDef:
    """Test AgentDef dataclass."""

    def test_defaults(self):
        ad = AgentDef(name="test")
        assert ad.name == "test"
        assert ad.model == ""
        assert ad.instructions == ""
        assert ad.tools == []
        assert ad.guardrails == []
        assert ad.agents == []
        assert ad.strategy == "handoff"
        assert ad.max_turns == 25
        assert ad.max_tokens is None
        assert ad.temperature is None
        assert ad.metadata == {}
        assert ad.func is None

    def test_all_fields(self):
        fn = lambda: "instructions"
        ad = AgentDef(
            name="test",
            model="openai/gpt-4o",
            instructions=fn,
            tools=["t1"],
            guardrails=["g1"],
            agents=["a1"],
            strategy="sequential",
            max_turns=10,
            max_tokens=500,
            temperature=0.7,
            metadata={"k": "v"},
            func=fn,
        )
        assert ad.model == "openai/gpt-4o"
        assert ad.func is fn


class TestBackwardCompatibility:
    """Ensure existing Agent() calls still work with model as keyword or positional."""

    def test_keyword_model(self):
        a = Agent(name="test", model="openai/gpt-4o")
        assert a.model == "openai/gpt-4o"
        assert a.external is False

    def test_positional_model(self):
        a = Agent("test", "openai/gpt-4o")
        assert a.model == "openai/gpt-4o"

    def test_rshift_still_works(self):
        a = Agent(name="a", model="openai/gpt-4o")
        b = Agent(name="b", model="openai/gpt-4o")
        c = a >> b
        assert c.strategy == "sequential"
        assert len(c.agents) == 2
