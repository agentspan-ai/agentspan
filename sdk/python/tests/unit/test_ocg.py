# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for the OCG (Open Context Graph) retrieval sub-agent factories."""

import pytest

from conductor.ai.agents.ocg import OCG_SYSTEM_PROMPT, ocg_agent, ocg_tools
from conductor.ai.agents.tool import ToolDef

ALL_TOOL_NAMES = {
    "ocg_query",
    "ocg_get_entity",
    "ocg_neighborhood",
    "ocg_memory_set",
    "ocg_memory_reinforce",
    "ocg_memory_delete",
}


URL = "https://us.ocg.example.com"


class TestOcgTools:
    def test_default_returns_all_six(self):
        tools = ocg_tools(url=URL)
        assert len(tools) == 6
        assert {t.name for t in tools} == ALL_TOOL_NAMES
        # OCG tools ARE http tools — they execute as plain Conductor HTTP
        # tasks; there is no OCG-specific server code.
        assert all(t.tool_type == "http" for t in tools)
        assert all(isinstance(t, ToolDef) for t in tools)

    def test_memory_false_returns_retrieval_only(self):
        tools = ocg_tools(url=URL, memory=False)
        assert len(tools) == 3
        assert {t.name for t in tools} == {
            "ocg_query",
            "ocg_get_entity",
            "ocg_neighborhood",
        }

    def test_subset_switches(self):
        tools = ocg_tools(url=URL, entities=False, memory=False)
        assert [t.name for t in tools] == ["ocg_query"]

    def test_url_is_required(self):
        # There is no server-side default instance — every OCG tool set
        # binds its own.
        with pytest.raises(TypeError):
            ocg_tools()
        with pytest.raises(ValueError, match="url"):
            ocg_tools(url="")

    def test_instance_binding_lands_in_config(self):
        tools = ocg_tools(url=URL, credential="OCG_US_KEY")
        for t in tools:
            assert t.config["url"] == URL
            # Auth rides a standard http-tool header placeholder; the server
            # resolves ${NAME} from the credential store at execution.
            assert t.config["headers"] == {"Authorization": "Bearer ${OCG_US_KEY}"}
            # Declared so the execution token bounds credential resolution
            # (same wire contract as http_tool headers).
            assert t.credentials == ["OCG_US_KEY"]

    def test_endpoint_mapping(self):
        by_name = {t.name: t for t in ocg_tools(url=URL)}
        q = by_name["ocg_query"].config
        assert (q["method"], q["pathTemplate"]) == ("POST", "/api/v1/agent/query")
        e = by_name["ocg_get_entity"].config
        assert (e["method"], e["pathTemplate"]) == ("GET", "/api/v1/entities/{entity_id}")
        n = by_name["ocg_neighborhood"].config
        assert n["pathTemplate"] == "/api/v1/graph/neighborhood/{entity_id}"
        assert n["queryParams"] == ["depth", "limit"]
        r = by_name["ocg_memory_reinforce"].config
        assert (r["method"], r["pathTemplate"]) == ("POST", "/api/v1/memories/{key}/reinforce")
        d = by_name["ocg_memory_delete"].config
        assert (d["method"], d["pathTemplate"]) == ("DELETE", "/api/v1/memories/{key}")
        assert d["queryParams"] == ["agent", "user"]

    def test_trailing_slash_stripped_from_url(self):
        tools = ocg_tools(url="https://us.ocg.example.com/")
        assert all(t.config["url"] == "https://us.ocg.example.com" for t in tools)

    def test_url_without_credential_is_allowed(self):
        tools = ocg_tools(url="https://local-ocg:8080")
        for t in tools:
            assert t.config["url"] == "https://local-ocg:8080"
            assert "headers" not in t.config
            assert t.credentials == []

    def test_credential_without_url_raises(self):
        with pytest.raises(TypeError):
            ocg_tools(credential="OCG_US_KEY")

    def test_schemas_have_required_fields(self):
        by_type = {t.name: t for t in ocg_tools(url=URL)}
        assert by_type["ocg_query"].input_schema["required"] == ["query"]
        assert by_type["ocg_get_entity"].input_schema["required"] == ["entity_id"]
        # LLM-visible hard ceiling on result-set size.
        assert by_type["ocg_query"].input_schema["properties"]["max_results"]["maximum"] == 100
        assert by_type["ocg_memory_set"].input_schema["required"] == [
            "key",
            "agent",
            "user",
            "string_value",
            "description",
        ]


class TestOcgAgent:
    def test_returns_plain_agent(self):
        from conductor.ai.agents.agent import Agent

        agent = ocg_agent(model="anthropic/claude-sonnet-4-6", url=URL)
        assert isinstance(agent, Agent)
        assert agent.name == "ocg_agent"
        assert agent.model == "anthropic/claude-sonnet-4-6"
        assert agent.max_turns == 10

    def test_model_is_required(self):
        with pytest.raises(TypeError):
            ocg_agent(url=URL)  # no model

    def test_url_is_required(self):
        with pytest.raises(TypeError):
            ocg_agent(model="anthropic/claude-sonnet-4-6")  # no url

    def test_canned_prompt_is_default(self):
        agent = ocg_agent(model="anthropic/claude-sonnet-4-6", url=URL)
        assert agent.instructions == OCG_SYSTEM_PROMPT
        # Execution-time date anchor must survive into the prompt verbatim —
        # Conductor substitutes it when the LLM task is scheduled.
        assert "${workflow.input.__today__}" in agent.instructions

    def test_instructions_override(self):
        agent = ocg_agent(
            model="anthropic/claude-sonnet-4-6", url=URL, instructions="Custom retrieval prompt."
        )
        assert agent.instructions == "Custom retrieval prompt."

    def test_instance_binding_flows_to_tools(self):
        agent = ocg_agent(
            name="ocg_us",
            model="anthropic/claude-sonnet-4-6",
            url="https://us.ocg.example.com",
            credential="OCG_US_KEY",
        )
        assert agent.name == "ocg_us"
        from conductor.ai.agents.tool import get_tool_def

        tool_defs = [get_tool_def(t) for t in agent.tools]
        assert len(tool_defs) == 6
        for td in tool_defs:
            assert td.config["url"] == "https://us.ocg.example.com"
            assert td.config["headers"] == {"Authorization": "Bearer ${OCG_US_KEY}"}
            assert td.credentials == ["OCG_US_KEY"]

    def test_tool_subset_flags_forwarded(self):
        agent = ocg_agent(model="anthropic/claude-sonnet-4-6", url=URL, memory=False)
        assert len(agent.tools) == 3

    def test_exported_from_agents_package(self):
        from conductor.ai.agents import ocg_agent as exported_agent
        from conductor.ai.agents import ocg_tools as exported_tools

        assert exported_agent is ocg_agent
        assert exported_tools is ocg_tools


class TestOcgWireFormat:
    def test_serializes_with_instance_config(self):
        """The serialized agent_tool child must carry each OCG tool's
        toolType + config so ToolCompiler can bake the instance binding."""
        from conductor.ai.agents.agent import Agent
        from conductor.ai.agents.config_serializer import AgentConfigSerializer
        from conductor.ai.agents.tool import agent_tool

        retriever = ocg_agent(
            name="ocg_us",
            model="anthropic/claude-sonnet-4-6",
            url="https://us.ocg.example.com",
            credential="OCG_US_KEY",
        )
        main = Agent(
            name="main",
            model="openai/gpt-4o",
            instructions="Delegate retrieval.",
            tools=[agent_tool(retriever)],
        )

        serialized = AgentConfigSerializer().serialize(main)

        at = serialized["tools"][0]
        assert at["toolType"] == "agent_tool"
        child = at["config"]["agentConfig"]
        assert child["name"] == "ocg_us"
        ocg_query = next(t for t in child["tools"] if t["name"] == "ocg_query")
        # OCG tools are plain http tools on the wire.
        assert ocg_query["toolType"] == "http"
        assert ocg_query["config"]["url"] == "https://us.ocg.example.com"
        assert ocg_query["config"]["pathTemplate"] == "/api/v1/agent/query"
        assert ocg_query["config"]["headers"] == {"Authorization": "Bearer ${OCG_US_KEY}"}
        assert ocg_query["config"]["credentials"] == ["OCG_US_KEY"]
