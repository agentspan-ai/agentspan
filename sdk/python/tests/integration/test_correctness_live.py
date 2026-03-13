# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Live correctness tests — runs real agents with real LLM calls.

These tests verify that orchestration strategies actually work end-to-end:
  - Tools get called when needed
  - Handoffs route to the right agent
  - Sequential pipelines run in order
  - Parallel agents all execute
  - Round-robin agents alternate
  - Strategy validators catch real violations

Requires:
  - Agentspan server running (AGENTSPAN_SERVER_URL)
  - OPENAI_API_KEY set

Run with:
    python3 -m pytest tests/integration/test_correctness_live.py -v -s
"""

import pytest

from agentspan.agents import Agent, Strategy, tool
from agentspan.agents.result import AgentEvent, EventType
from agentspan.agents.runtime.config import AgentConfig
from agentspan.agents.runtime.runtime import AgentRuntime
from agentspan.agents.testing import (
    CorrectnessEval,
    EvalCase,
    assert_handoff_to,
    assert_no_errors,
    assert_tool_used,
    expect,
    validate_strategy,
)


# ── Mark all tests as integration ──────────────────────────────────────

pytestmark = pytest.mark.integration


# ── Shared fixture ─────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def runtime():
    config = AgentConfig.from_env()
    # Force polling mode — SSE puts call IDs as tool names and omits
    # HANDOFF events.  Polling generates correct tool names, handoff
    # events, and guardrail events from Conductor task inspection.
    config.streaming_enabled = False
    rt = AgentRuntime(config=config)
    yield rt
    rt.shutdown()


def _run_with_events(runtime, agent, prompt):
    """Run agent via stream() and return a fully-built AgentResult.

    stream().get_result() drains the event iterator and reconstructs
    tool_calls from TOOL_CALL/TOOL_RESULT event pairs, unlike run()
    which returns only output/status.
    """
    return runtime.stream(agent, prompt).get_result()


# ── Tools ──────────────────────────────────────────────────────────────


@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"72F and sunny in {city}"


@tool
def calculate(expression: str) -> str:
    """Evaluate a math expression. Returns the numeric result."""
    try:
        return str(eval(expression))  # noqa: S307
    except Exception as e:
        return f"Error: {e}"


@tool
def lookup_order(order_id: str) -> dict:
    """Look up an order by ID."""
    return {"order_id": order_id, "status": "shipped", "total": 49.99}


# ═══════════════════════════════════════════════════════════════════════
# 1. SINGLE AGENT WITH TOOLS
# ═══════════════════════════════════════════════════════════════════════


class TestSingleAgentTools:
    """Verify that a single agent uses tools when the prompt requires it."""

    def test_uses_weather_tool(self, runtime):
        """Agent should call get_weather for a weather question."""
        agent = Agent(
            name="weather_bot",
            model="openai/gpt-4o-mini",
            instructions="You are a weather assistant. Always use the get_weather tool to answer weather questions.",
            tools=[get_weather],
        )
        result = _run_with_events(runtime, agent, "What's the weather in NYC?")

        print(f"\nOutput: {result.output}")
        print(f"Tool calls: {result.tool_calls}")
        print(f"Events: {[(e.type, e.tool_name or e.target or '') for e in result.events]}")

        (expect(result)
            .completed()
            .used_tool("get_weather")
            .no_errors())

    def test_uses_calculator_tool(self, runtime):
        """Agent should call calculate for a math question."""
        agent = Agent(
            name="math_bot",
            model="openai/gpt-4o-mini",
            instructions="You are a math assistant. Always use the calculate tool to compute answers. Never calculate in your head.",
            tools=[calculate],
        )
        result = _run_with_events(runtime, agent, "What is 137 * 29?")

        print(f"\nOutput: {result.output}")
        print(f"Tool calls: {result.tool_calls}")

        (expect(result)
            .completed()
            .used_tool("calculate")
            .no_errors())

    def test_does_not_use_tools_for_greeting(self, runtime):
        """Agent should NOT use tools when they aren't needed."""
        agent = Agent(
            name="greeting_bot",
            model="openai/gpt-4o-mini",
            instructions="You are a friendly assistant with weather tools. Only use tools when asked about weather.",
            tools=[get_weather],
        )
        result = _run_with_events(runtime, agent, "Hello! How are you?")

        print(f"\nOutput: {result.output}")
        print(f"Tool calls: {result.tool_calls}")

        (expect(result)
            .completed()
            .did_not_use_tool("get_weather")
            .no_errors())


# ═══════════════════════════════════════════════════════════════════════
# 2. HANDOFF — LLM routes to the right sub-agent
# ═══════════════════════════════════════════════════════════════════════


class TestHandoffLive:
    """Verify that the parent agent delegates to the correct specialist."""

    @pytest.fixture
    def support_agent(self):
        billing = Agent(
            name="billing",
            model="openai/gpt-4o-mini",
            instructions="You handle billing and order questions. Use lookup_order to find orders.",
            tools=[lookup_order],
        )
        weather = Agent(
            name="weather",
            model="openai/gpt-4o-mini",
            instructions="You handle weather questions. Use get_weather to check weather.",
            tools=[get_weather],
        )
        return Agent(
            name="support",
            model="openai/gpt-4o-mini",
            instructions=(
                "You are a support router. Route billing/order questions to 'billing' "
                "and weather questions to 'weather'. Always delegate, never answer directly."
            ),
            agents=[billing, weather],
            strategy=Strategy.HANDOFF,
        )

    def test_billing_query_routes_to_billing(self, runtime, support_agent):
        """A billing question should go to the billing agent."""
        result = _run_with_events(runtime, support_agent, "What's the status of order #123?")

        print(f"\nOutput: {result.output}")
        print(f"Events: {[(e.type, e.target or e.tool_name or '') for e in result.events]}")

        assert_handoff_to(result, "billing")
        # Tool calls in sub-workflows aren't visible at the parent level
        assert_no_errors(result)
        validate_strategy(support_agent, result)

    def test_weather_query_routes_to_weather(self, runtime, support_agent):
        """A weather question should go to the weather agent."""
        result = _run_with_events(runtime, support_agent, "What's the weather in London?")

        print(f"\nOutput: {result.output}")
        print(f"Events: {[(e.type, e.target or e.tool_name or '') for e in result.events]}")

        assert_handoff_to(result, "weather")
        assert_no_errors(result)
        validate_strategy(support_agent, result)


# ═══════════════════════════════════════════════════════════════════════
# 3. SEQUENTIAL — all agents run in order
# ═══════════════════════════════════════════════════════════════════════


class TestSequentialLive:
    """Verify that a sequential pipeline runs all stages in order."""

    def test_two_stage_pipeline(self, runtime):
        """Researcher → writer pipeline should produce researched content."""
        researcher = Agent(
            name="researcher",
            model="openai/gpt-4o-mini",
            instructions="Research the topic. List 3 key facts. Be brief.",
        )
        writer = Agent(
            name="writer",
            model="openai/gpt-4o-mini",
            instructions="Take the research and write a short 2-sentence summary.",
        )
        pipeline = researcher >> writer

        result = _run_with_events(runtime, pipeline, "Python programming language")

        print(f"\nOutput: {result.output}")
        print(f"Events: {[(e.type, e.target or '') for e in result.events]}")

        (expect(result)
            .completed()
            .no_errors())

        validate_strategy(pipeline, result)


# ═══════════════════════════════════════════════════════════════════════
# 4. PARALLEL — all agents run concurrently
# ═══════════════════════════════════════════════════════════════════════


class TestParallelLive:
    """Verify that parallel agents all execute."""

    def test_two_analysts(self, runtime):
        """Both analysts should run and contribute to the output."""
        pros = Agent(
            name="pros_analyst",
            model="openai/gpt-4o-mini",
            instructions="List 2 pros/advantages. Be brief, one sentence each.",
        )
        cons = Agent(
            name="cons_analyst",
            model="openai/gpt-4o-mini",
            instructions="List 2 cons/disadvantages. Be brief, one sentence each.",
        )
        team = Agent(
            name="analysis",
            model="openai/gpt-4o-mini",
            agents=[pros, cons],
            strategy=Strategy.PARALLEL,
        )

        result = _run_with_events(runtime, team, "Remote work")

        print(f"\nOutput: {result.output}")
        print(f"Events: {[(e.type, e.target or '') for e in result.events]}")

        (expect(result)
            .completed()
            .no_errors())

        validate_strategy(team, result)


# ═══════════════════════════════════════════════════════════════════════
# 5. ROUTER — picks the right specialist
# ═══════════════════════════════════════════════════════════════════════


class TestRouterLive:
    """Verify that the router selects the correct agent."""

    @pytest.fixture
    def dev_team(self):
        router = Agent(
            name="router",
            model="openai/gpt-4o-mini",
            instructions="Route coding tasks to 'coder' and math tasks to 'calculator'.",
        )
        coder = Agent(
            name="coder",
            model="openai/gpt-4o-mini",
            instructions="Write Python code. Be brief.",
        )
        calculator = Agent(
            name="calculator",
            model="openai/gpt-4o-mini",
            instructions="Solve math problems. Use the calculate tool.",
            tools=[calculate],
        )
        return Agent(
            name="dev_team",
            model="openai/gpt-4o-mini",
            agents=[coder, calculator],
            strategy=Strategy.ROUTER,
            router=router,
        )

    def test_coding_routed_to_coder(self, runtime, dev_team):
        """A coding request should go to the coder."""
        result = _run_with_events(runtime, dev_team, "Write a Python function to reverse a string")

        print(f"\nOutput: {result.output}")
        print(f"Events: {[(e.type, e.target or '') for e in result.events]}")

        assert_handoff_to(result, "coder")
        assert_no_errors(result)
        validate_strategy(dev_team, result)

    def test_math_routed_to_calculator(self, runtime, dev_team):
        """A math request should go to the calculator."""
        result = _run_with_events(runtime, dev_team, "What is 42 * 17?")

        print(f"\nOutput: {result.output}")
        print(f"Events: {[(e.type, e.target or '') for e in result.events]}")

        assert_handoff_to(result, "calculator")
        assert_no_errors(result)
        validate_strategy(dev_team, result)


# ═══════════════════════════════════════════════════════════════════════
# 6. ROUND_ROBIN — agents alternate
# ═══════════════════════════════════════════════════════════════════════


class TestRoundRobinLive:
    """Verify that round-robin agents alternate turns correctly."""

    def test_debate_alternates(self, runtime):
        """Two debaters should alternate: optimist → pessimist → optimist → pessimist."""
        optimist = Agent(
            name="optimist",
            model="openai/gpt-4o-mini",
            instructions="Argue ONE positive point about the topic. One sentence only.",
        )
        pessimist = Agent(
            name="pessimist",
            model="openai/gpt-4o-mini",
            instructions="Argue ONE negative point about the topic. One sentence only.",
        )
        debate = Agent(
            name="debate",
            model="openai/gpt-4o-mini",
            agents=[optimist, pessimist],
            strategy=Strategy.ROUND_ROBIN,
            max_turns=4,
        )

        result = _run_with_events(runtime, debate, "AI in education")

        print(f"\nOutput: {result.output}")
        handoffs = [(e.type, e.target) for e in result.events if e.type == EventType.HANDOFF]
        print(f"Handoffs: {handoffs}")

        (expect(result)
            .completed()
            .no_errors())

        # Verify both agents participated (server may reorder from definition)
        assert_handoff_to(result, "optimist")
        assert_handoff_to(result, "pessimist")

        # Verify alternation — no agent runs twice in a row
        from agentspan.agents.testing.strategy_validators import (
            _get_handoff_targets,
        )
        targets = _get_handoff_targets(result)
        relevant = [t for t in targets if t in {"optimist", "pessimist"}]
        for i in range(1, len(relevant)):
            assert relevant[i] != relevant[i - 1], (
                f"Agent '{relevant[i]}' ran twice in a row at positions {i-1} and {i}. "
                f"Sequence: {relevant}"
            )


# ═══════════════════════════════════════════════════════════════════════
# 7. EVAL RUNNER — batch correctness evaluation
# ═══════════════════════════════════════════════════════════════════════


class TestEvalRunnerLive:
    """Run a batch of eval cases and verify all pass."""

    def test_eval_suite(self, runtime):
        """Run multiple correctness checks in one eval suite."""
        weather_agent = Agent(
            name="weather_eval",
            model="openai/gpt-4o-mini",
            instructions="You are a weather assistant. Always use the get_weather tool.",
            tools=[get_weather],
        )
        math_agent = Agent(
            name="math_eval",
            model="openai/gpt-4o-mini",
            instructions="You are a math assistant. Always use the calculate tool. Never calculate in your head.",
            tools=[calculate],
        )

        # Wrap runtime to use stream() for full event capture
        class EventCapturingRuntime:
            def __init__(self, rt):
                self._rt = rt
            def run(self, agent, prompt):
                return self._rt.stream(agent, prompt).get_result()

        eval_rt = EventCapturingRuntime(runtime)
        eval = CorrectnessEval(eval_rt)
        results = eval.run([
            EvalCase(
                name="weather_uses_tool",
                agent=weather_agent,
                prompt="What's the weather in Tokyo?",
                expect_tools=["get_weather"],
            ),
            EvalCase(
                name="math_uses_tool",
                agent=math_agent,
                prompt="What is 256 * 4?",
                expect_tools=["calculate"],
            ),
            EvalCase(
                name="weather_no_tool_for_greeting",
                agent=weather_agent,
                prompt="Hi there!",
                expect_tools_not_used=["get_weather"],
            ),
        ])

        results.print_summary()
        assert results.all_passed, (
            f"{results.fail_count}/{results.total} eval(s) failed:\n"
            + "\n".join(
                f"  - {c.name}: {[ch.message for ch in c.checks if not ch.passed]}"
                for c in results.failed_cases()
            )
        )
