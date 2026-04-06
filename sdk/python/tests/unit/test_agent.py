# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for the Agent class."""

import pytest

from agentspan.agents.agent import Agent


class TestAgentCreation:
    """Test Agent construction and validation."""

    def test_basic_agent(self):
        agent = Agent(name="test", model="openai/gpt-4o")
        assert agent.name == "test"
        assert agent.model == "openai/gpt-4o"
        assert agent.strategy == "handoff"
        assert agent.max_turns == 25
        assert agent.tools == []
        assert agent.agents == []

    def test_agent_with_instructions(self):
        agent = Agent(
            name="test",
            model="openai/gpt-4o",
            instructions="You are helpful.",
        )
        assert agent.instructions == "You are helpful."

    def test_agent_with_callable_instructions(self):
        def get_instructions():
            return "Dynamic instructions"

        agent = Agent(name="test", model="openai/gpt-4o", instructions=get_instructions)
        assert callable(agent.instructions)
        assert agent.instructions() == "Dynamic instructions"

    def test_agent_with_tools(self):
        from agentspan.agents.tool import tool

        @tool
        def my_tool(x: str) -> str:
            """A test tool."""
            return x

        agent = Agent(name="test", model="openai/gpt-4o", tools=[my_tool])
        assert len(agent.tools) == 1

    def test_agent_with_sub_agents(self):
        sub1 = Agent(name="sub1", model="openai/gpt-4o")
        sub2 = Agent(name="sub2", model="openai/gpt-4o")
        parent = Agent(
            name="parent",
            model="openai/gpt-4o",
            agents=[sub1, sub2],
            strategy="handoff",
        )
        assert len(parent.agents) == 2
        assert parent.strategy == "handoff"

    def test_round_robin_strategy_accepted(self):
        sub1 = Agent(name="a", model="openai/gpt-4o")
        sub2 = Agent(name="b", model="openai/gpt-4o")
        agent = Agent(
            name="debate",
            model="openai/gpt-4o",
            agents=[sub1, sub2],
            strategy="round_robin",
            max_turns=4,
        )
        assert agent.strategy == "round_robin"
        assert agent.max_turns == 4

    def test_invalid_strategy_raises(self):
        with pytest.raises(ValueError, match="Invalid strategy"):
            Agent(name="test", model="openai/gpt-4o", strategy="invalid")

    def test_router_requires_router_arg(self):
        sub = Agent(name="sub", model="openai/gpt-4o")
        with pytest.raises(ValueError, match="requires a router"):
            Agent(
                name="test",
                model="openai/gpt-4o",
                agents=[sub],
                strategy="router",
            )

    def test_agent_with_metadata(self):
        agent = Agent(
            name="test",
            model="openai/gpt-4o",
            metadata={"env": "prod", "version": "1.0"},
        )
        assert agent.metadata == {"env": "prod", "version": "1.0"}

    def test_random_strategy_accepted(self):
        sub1 = Agent(name="a", model="openai/gpt-4o")
        sub2 = Agent(name="b", model="openai/gpt-4o")
        agent = Agent(
            name="random_pick",
            model="openai/gpt-4o",
            agents=[sub1, sub2],
            strategy="random",
            max_turns=4,
        )
        assert agent.strategy == "random"
        assert agent.max_turns == 4

    def test_termination_param(self):
        from agentspan.agents.termination import TextMentionTermination

        cond = TextMentionTermination("DONE")
        agent = Agent(name="test", model="openai/gpt-4o", termination=cond)
        assert agent.termination is cond

    def test_allowed_transitions_param(self):
        sub1 = Agent(name="a", model="openai/gpt-4o")
        sub2 = Agent(name="b", model="openai/gpt-4o")
        transitions = {"a": ["b"], "b": ["a"]}
        agent = Agent(
            name="test",
            model="openai/gpt-4o",
            agents=[sub1, sub2],
            strategy="round_robin",
            allowed_transitions=transitions,
        )
        assert agent.allowed_transitions == transitions


class TestAgentChaining:
    """Test the >> operator for sequential pipelines."""

    def test_two_agents(self):
        a = Agent(name="a", model="openai/gpt-4o")
        b = Agent(name="b", model="openai/gpt-4o")
        pipeline = a >> b
        assert pipeline.strategy == "sequential"
        assert len(pipeline.agents) == 2
        assert pipeline.agents[0].name == "a"
        assert pipeline.agents[1].name == "b"

    def test_three_agents(self):
        a = Agent(name="a", model="openai/gpt-4o")
        b = Agent(name="b", model="openai/gpt-4o")
        c = Agent(name="c", model="openai/gpt-4o")
        pipeline = a >> b >> c
        assert pipeline.strategy == "sequential"
        assert len(pipeline.agents) == 3

    def test_pipeline_name(self):
        a = Agent(name="a", model="openai/gpt-4o")
        b = Agent(name="b", model="openai/gpt-4o")
        pipeline = a >> b
        assert pipeline.name == "a_b"


class TestAgentRepr:
    """Test Agent string representation."""

    def test_simple_repr(self):
        agent = Agent(name="test", model="openai/gpt-4o")
        assert "Agent(" in repr(agent)
        assert "test" in repr(agent)
        assert "openai/gpt-4o" in repr(agent)

    def test_repr_with_tools(self):
        from agentspan.agents.tool import tool

        @tool
        def t(x: str) -> str:
            """T."""
            return x

        agent = Agent(name="test", model="openai/gpt-4o", tools=[t])
        assert "tools=1" in repr(agent)

    def test_repr_with_agents(self):
        sub = Agent(name="sub", model="openai/gpt-4o")
        parent = Agent(name="parent", model="openai/gpt-4o", agents=[sub])
        assert "agents=1" in repr(parent)
        assert "handoff" in repr(parent)


# ── PromptTemplate ───────────────────────────────────────────────────


class TestPromptTemplate:
    """Test the PromptTemplate dataclass."""

    def test_basic_creation(self):
        from agentspan.agents.agent import PromptTemplate

        t = PromptTemplate("my-prompt")
        assert t.name == "my-prompt"
        assert t.variables == {}
        assert t.version is None

    def test_with_variables_and_version(self):
        from agentspan.agents.agent import PromptTemplate

        t = PromptTemplate("support-v2", variables={"company": "Acme"}, version=3)
        assert t.name == "support-v2"
        assert t.variables == {"company": "Acme"}
        assert t.version == 3

    def test_is_frozen(self):
        from agentspan.agents.agent import PromptTemplate

        t = PromptTemplate("test")
        with pytest.raises(AttributeError):
            t.name = "changed"

    def test_agent_accepts_prompt_template(self):
        from agentspan.agents.agent import PromptTemplate

        t = PromptTemplate("my-instructions", variables={"tone": "formal"})
        agent = Agent(name="test", model="openai/gpt-4o", instructions=t)
        assert isinstance(agent.instructions, PromptTemplate)
        assert agent.instructions.name == "my-instructions"

    def test_import_from_init(self):
        from agentspan.agents import PromptTemplate

        t = PromptTemplate("test")
        assert t.name == "test"


# ── P2-A / P2-B / P4-A: Agent validation edge cases ──────────────────


class TestAgentNameValidation:
    """Test Agent name validation."""

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="non-empty string"):
            Agent(name="", model="openai/gpt-4o")

    def test_none_name_raises(self):
        with pytest.raises(ValueError, match="non-empty string"):
            Agent(name=None, model="openai/gpt-4o")

    def test_special_chars_raises(self):
        with pytest.raises(ValueError, match="Invalid agent name"):
            Agent(name="my agent!", model="openai/gpt-4o")

    def test_starts_with_number_raises(self):
        with pytest.raises(ValueError, match="Invalid agent name"):
            Agent(name="123agent", model="openai/gpt-4o")

    def test_valid_underscore_name(self):
        agent = Agent(name="_private", model="openai/gpt-4o")
        assert agent.name == "_private"

    def test_valid_hyphen_name(self):
        agent = Agent(name="my-agent", model="openai/gpt-4o")
        assert agent.name == "my-agent"

    def test_valid_alphanumeric(self):
        agent = Agent(name="agent_v2", model="openai/gpt-4o")
        assert agent.name == "agent_v2"


class TestAgentMaxTurnsValidation:
    """Test Agent max_turns validation."""

    def test_zero_raises(self):
        with pytest.raises(ValueError, match="max_turns must be >= 1"):
            Agent(name="test", model="openai/gpt-4o", max_turns=0)

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="max_turns must be >= 1"):
            Agent(name="test", model="openai/gpt-4o", max_turns=-1)

    def test_one_is_valid(self):
        agent = Agent(name="test", model="openai/gpt-4o", max_turns=1)
        assert agent.max_turns == 1

    def test_default_25(self):
        agent = Agent(name="test", model="openai/gpt-4o")
        assert agent.max_turns == 25


class TestAgentEdgeCases:
    """Additional edge case tests for Agent."""

    def test_rshift_with_external_agent(self):
        a = Agent(name="a", model="openai/gpt-4o")
        b = Agent(name="b")  # external
        pipeline = a >> b
        assert pipeline.strategy == "sequential"
        assert len(pipeline.agents) == 2
        assert pipeline.agents[1].external is True

    def test_empty_tools_list(self):
        agent = Agent(name="test", model="openai/gpt-4o", tools=[])
        assert agent.tools == []

    def test_empty_agents_list(self):
        agent = Agent(name="test", model="openai/gpt-4o", agents=[])
        assert agent.agents == []

    def test_external_agent_detection(self):
        agent = Agent(name="ext")
        assert agent.external is True
        assert agent.model == ""

    def test_non_external_agent(self):
        agent = Agent(name="test", model="openai/gpt-4o")
        assert agent.external is False


class TestDuplicateSubAgentNames:
    """Test BUG-P2-06: duplicate sub-agent names are caught at construction."""

    def test_duplicate_names_raises(self):
        worker = Agent(name="worker", model="openai/gpt-4o")
        with pytest.raises(ValueError, match="Duplicate sub-agent names"):
            Agent(
                name="team",
                model="openai/gpt-4o",
                agents=[worker, worker, worker],
                strategy="parallel",
            )

    def test_unique_names_ok(self):
        a = Agent(name="worker_a", model="openai/gpt-4o")
        b = Agent(name="worker_b", model="openai/gpt-4o")
        team = Agent(
            name="team",
            model="openai/gpt-4o",
            agents=[a, b],
            strategy="parallel",
        )
        assert len(team.agents) == 2

    def test_error_message_includes_duplicates(self):
        w = Agent(name="dup", model="openai/gpt-4o")
        with pytest.raises(ValueError, match="dup") as exc_info:
            Agent(name="team", model="openai/gpt-4o", agents=[w, w])
        assert "unique name" in str(exc_info.value).lower()


# ── Scatter-Gather helper ─────────────────────────────────────────────


class TestScatterGather:
    """Test the scatter_gather() convenience helper."""

    def test_creates_agent_with_agent_tool(self):
        from agentspan.agents.agent import scatter_gather

        worker = Agent(name="researcher", model="openai/gpt-4o")
        coord = scatter_gather("coordinator", worker)
        assert isinstance(coord, Agent)
        assert coord.name == "coordinator"
        assert len(coord.tools) == 1
        assert coord.tools[0].name == "researcher"

    def test_instructions_include_decomposition_prefix(self):
        from agentspan.agents.agent import _SCATTER_GATHER_PREFIX, scatter_gather

        worker = Agent(name="worker", model="openai/gpt-4o")
        coord = scatter_gather("coord", worker, instructions="Be concise.")
        expected_prefix = _SCATTER_GATHER_PREFIX.format(worker_name="worker")
        assert coord.instructions.startswith(expected_prefix)
        assert "Be concise." in coord.instructions

    def test_extra_tools_included(self):
        from agentspan.agents.agent import scatter_gather
        from agentspan.agents.tool import tool

        @tool
        def helper(x: str) -> str:
            """A helper."""
            return x

        worker = Agent(name="w", model="openai/gpt-4o")
        coord = scatter_gather("coord", worker, tools=[helper])
        assert len(coord.tools) == 2
        # First tool is the agent_tool wrapper, second is the extra tool
        assert coord.tools[0].name == "w"

    def test_model_inherited_from_worker(self):
        from agentspan.agents.agent import scatter_gather

        worker = Agent(name="w", model="anthropic/claude-sonnet")
        coord = scatter_gather("coord", worker)
        assert coord.model == "anthropic/claude-sonnet"

    def test_model_override(self):
        from agentspan.agents.agent import scatter_gather

        worker = Agent(name="w", model="openai/gpt-4o")
        coord = scatter_gather("coord", worker, model="anthropic/claude-sonnet")
        assert coord.model == "anthropic/claude-sonnet"

    def test_kwargs_forwarded(self):
        from agentspan.agents.agent import scatter_gather

        worker = Agent(name="w", model="openai/gpt-4o")
        coord = scatter_gather("coord", worker, max_turns=10, temperature=0.5)
        assert coord.max_turns == 10
        assert coord.temperature == 0.5

    def test_retry_config_passed_to_agent_tool(self):
        from agentspan.agents.agent import scatter_gather

        worker = Agent(name="w", model="openai/gpt-4o")
        coord = scatter_gather("coord", worker, retry_count=5, retry_delay_seconds=10)
        worker_tool = coord.tools[0]
        assert worker_tool.config["retryCount"] == 5
        assert worker_tool.config["retryDelaySeconds"] == 10

    def test_fail_fast_sets_optional_false(self):
        from agentspan.agents.agent import scatter_gather

        worker = Agent(name="w", model="openai/gpt-4o")
        coord = scatter_gather("coord", worker, fail_fast=True)
        worker_tool = coord.tools[0]
        assert worker_tool.config["optional"] is False

    def test_default_is_not_fail_fast(self):
        from agentspan.agents.agent import scatter_gather

        worker = Agent(name="w", model="openai/gpt-4o")
        coord = scatter_gather("coord", worker)
        worker_tool = coord.tools[0]
        # optional should not be set — server defaults to True
        assert "optional" not in worker_tool.config

    def test_default_timeout_300(self):
        from agentspan.agents.agent import scatter_gather

        worker = Agent(name="w", model="openai/gpt-4o")
        coord = scatter_gather("coord", worker)
        assert coord.timeout_seconds == 300

    def test_timeout_override(self):
        from agentspan.agents.agent import scatter_gather

        worker = Agent(name="w", model="openai/gpt-4o")
        coord = scatter_gather("coord", worker, timeout_seconds=600)
        assert coord.timeout_seconds == 600


class TestAgentCredentials:
    """Agent credentials param and CLI auto-mapping."""

    def test_credentials_defaults_to_empty_list(self):
        from agentspan.agents.agent import Agent
        a = Agent(name="test_agent", model="openai/gpt-4o")
        assert a.credentials == []

    def test_explicit_credentials_stored(self):
        from agentspan.agents.agent import Agent
        a = Agent(
            name="test_agent",
            model="openai/gpt-4o",
            credentials=["GITHUB_TOKEN", "OPENAI_API_KEY"],
        )
        assert "GITHUB_TOKEN" in a.credentials
        assert "OPENAI_API_KEY" in a.credentials

    def test_cli_allowed_commands_without_credentials_stays_empty(self):
        """CLI commands without explicit credentials produce empty credentials list."""
        from agentspan.agents.agent import Agent
        a = Agent(
            name="test_agent",
            model="openai/gpt-4o",
            cli_commands=True,
            cli_allowed_commands=["gh", "git"],
        )
        assert a.credentials == []

    def test_cli_allowed_commands_with_explicit_credentials(self):
        """Explicit credentials are required — no auto-mapping from CLI commands."""
        from agentspan.agents.agent import Agent
        a = Agent(
            name="test_agent",
            model="openai/gpt-4o",
            cli_commands=True,
            cli_allowed_commands=["aws"],
            credentials=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
        )
        assert "AWS_ACCESS_KEY_ID" in a.credentials
        assert "AWS_SECRET_ACCESS_KEY" in a.credentials

    def test_terraform_without_credentials_allowed(self):
        """terraform in cli_allowed_commands without credentials is allowed (no auto-mapping)."""
        from agentspan.agents.agent import Agent
        a = Agent(
            name="test_agent",
            model="openai/gpt-4o",
            cli_commands=True,
            cli_allowed_commands=["terraform"],
        )
        assert a.credentials == []

    def test_terraform_with_explicit_credentials_does_not_raise(self):
        """terraform is fine when explicit credentials are declared."""
        from agentspan.agents.agent import Agent
        # Should not raise
        a = Agent(
            name="test_agent",
            model="openai/gpt-4o",
            cli_commands=True,
            cli_allowed_commands=["terraform", "aws"],
            credentials=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "TF_VAR_db_password"],
        )
        assert "TF_VAR_db_password" in a.credentials

    def test_commands_not_in_map_are_ignored_gracefully(self):
        """CLI commands like mktemp, rm not in map produce no credentials (no error)."""
        from agentspan.agents.agent import Agent
        a = Agent(
            name="test_agent",
            model="openai/gpt-4o",
            cli_commands=True,
            cli_allowed_commands=["mktemp", "rm"],
        )
        # Neither command has credentials — empty list is fine
        assert a.credentials == []

    def test_explicit_credentials_override_automapping(self):
        """When explicit credentials provided, auto-mapping is not applied."""
        from agentspan.agents.agent import Agent
        a = Agent(
            name="test_agent",
            model="openai/gpt-4o",
            cli_commands=True,
            cli_allowed_commands=["gh"],
            credentials=["MY_CUSTOM_TOKEN"],
        )
        # Only explicit credentials, no auto-mapped ones added on top
        assert a.credentials == ["MY_CUSTOM_TOKEN"]
        assert "GITHUB_TOKEN" not in a.credentials
