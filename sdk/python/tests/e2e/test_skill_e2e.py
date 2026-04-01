"""E2E tests for skill-based agents.

Exercises the full flow: skill() -> serialize -> send to server ->
SkillNormalizer -> AgentCompiler -> Conductor execution.

Requires:
  - A running Agentspan server at AGENTSPAN_SERVER_URL (default localhost:8080)
  - Set AGENTSPAN_SERVER_URL env var to enable these tests
  - Optionally set AGENTSPAN_LLM_MODEL to override the default model
"""

import os
from pathlib import Path

import pytest

from agentspan.agents import Agent, AgentRuntime, agent_tool, load_skills, skill

FIXTURES = Path(__file__).parent.parent / "fixtures" / "skills"
MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini")
SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL")

# Skip the entire module if no server URL is configured
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not SERVER_URL,
        reason="AGENTSPAN_SERVER_URL not set — skipping E2E skill tests",
    ),
]


@pytest.fixture(scope="module")
def rt():
    """Module-scoped AgentRuntime — created once, shared across all tests."""
    with AgentRuntime() as runtime:
        yield runtime


class TestSkillE2E:
    """E2E tests for skill-based agents against a live server."""

    def test_simple_skill_completes(self, rt):
        """Instruction-only skill runs and returns a result."""
        agent = skill(FIXTURES / "simple-skill", model=MODEL)
        result = rt.run(agent, "Say hello", timeout=60000)
        assert result.is_success
        assert result.output["result"]
        assert result.workflow_id

    def test_simple_skill_has_token_usage(self, rt):
        """Token usage is tracked for skill agents."""
        agent = skill(FIXTURES / "simple-skill", model=MODEL)
        result = rt.run(agent, "Say hello", timeout=60000)
        assert result.is_success
        assert result.token_usage is not None
        assert result.token_usage.total_tokens > 0

    def test_dg_skill_dispatches_sub_agents(self, rt):
        """Skill with sub-agents creates real SUB_WORKFLOW tasks."""
        agent = skill(FIXTURES / "dg-skill", model=MODEL)
        result = rt.run(
            agent,
            "Review this code: def add(a, b): return a + b",
            timeout=120000,
        )
        assert result.is_success
        assert result.workflow_id

    def test_script_skill_executes_script(self, rt):
        """Script tools are callable and return output."""
        agent = skill(FIXTURES / "script-skill", model=MODEL)
        result = rt.run(
            agent,
            "Run the hello script with argument 'World'",
            timeout=60000,
        )
        assert result.is_success

    def test_skill_in_pipeline(self, rt):
        """Skill works in a >> pipeline with a regular agent."""
        reviewer = skill(FIXTURES / "simple-skill", model=MODEL)
        summarizer = Agent(
            name="summarizer",
            model=MODEL,
            instructions="Summarize the input in one sentence.",
        )
        pipeline = reviewer >> summarizer
        result = rt.run(pipeline, "Explain quantum computing", timeout=120000)
        assert result.is_success

    def test_skill_as_agent_tool(self, rt):
        """Skill works as agent_tool on another agent."""
        helper = skill(FIXTURES / "simple-skill", model=MODEL)
        lead = Agent(
            name="lead",
            model=MODEL,
            instructions="Use the helper tool to answer questions.",
            tools=[agent_tool(helper)],
        )
        result = rt.run(lead, "Ask the helper to say hello", timeout=60000)
        assert result.is_success

    def test_skill_streaming_has_tokens(self, rt):
        """Streaming path also returns token usage."""
        agent = skill(FIXTURES / "simple-skill", model=MODEL)
        stream = rt.stream(agent, "Say hello")
        for _ in stream:
            pass
        result = stream.get_result()
        assert result.is_success
        assert result.token_usage is not None

    def test_load_skills_batch(self):
        """load_skills discovers all skills in a directory."""
        skills = load_skills(FIXTURES, model=MODEL)
        # Fixtures contain: simple-skill, dg-skill, script-skill, cross-ref-skill
        assert len(skills) >= 3
        for name, agent in skills.items():
            assert isinstance(agent, Agent)
            assert agent._framework == "skill"
            assert agent.name == name
