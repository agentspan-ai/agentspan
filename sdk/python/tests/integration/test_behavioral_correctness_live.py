# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Behavioral correctness tests — deeper multi-agent verification with real LLMs.

Unlike test_correctness_live.py which checks "did the right agent run?", these
tests verify "did the agents do the right thing TOGETHER?"  For each strategy:

  - HANDOFF:  Sub-agent tool output surfaces in final answer (not just routing)
  - SEQUENTIAL: Downstream agent builds on upstream output (not ignoring it)
  - PARALLEL:  Every agent contributes distinctly to the combined output
  - ROUTER:    Correct specialist is chosen AND produces domain-correct output
  - ROUND_ROBIN: Agents build on each other across turns (not repeating)
  - SWARM:     Multiple agents participate in a single request when context demands it

Requires:
  - Agentspan server running (AGENTSPAN_SERVER_URL)
  - OPENAI_API_KEY set

Run with:
    python3 -m pytest tests/integration/test_behavioral_correctness_live.py -v -s
"""

import re

import pytest

from agentspan.agents import Agent, Strategy, tool
from agentspan.agents.result import EventType
from agentspan.agents.runtime.config import AgentConfig
from agentspan.agents.runtime.runtime import AgentRuntime
from agentspan.agents.testing import (
    assert_handoff_to,
    assert_no_errors,
    assert_output_contains,
    assert_output_matches,
    assert_tool_used,
    expect,
    validate_strategy,
)
from agentspan.agents.testing.strategy_validators import _get_handoff_targets


# ── Mark all tests as integration ──────────────────────────────────────

pytestmark = pytest.mark.integration


# ── Shared fixture ─────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def runtime():
    config = AgentConfig.from_env()
    config.streaming_enabled = False  # polling generates correct events
    rt = AgentRuntime(config=config)
    yield rt
    rt.shutdown()


def _run(runtime, agent, prompt):
    """Run agent and return fully-built AgentResult with events + tool_calls."""
    return runtime.stream(agent, prompt).get_result()


def _output_text(result):
    """Extract plain text from result.output (handles dict wrapper)."""
    out = result.output
    if isinstance(out, dict):
        return str(out.get("result", out))
    return str(out) if out else ""


# ── Tools with distinctive outputs ────────────────────────────────────
# Each tool returns data that's unique enough to trace through agent chains.


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
    """Look up an order by ID. Returns status and total."""
    return {"order_id": order_id, "status": "shipped", "total": 49.99}


@tool
def check_inventory(product: str) -> dict:
    """Check product inventory levels."""
    return {"product": product, "in_stock": True, "quantity": 142}


@tool
def get_shipping_rate(destination: str) -> dict:
    """Get shipping rate to a destination."""
    return {"destination": destination, "rate_usd": 12.50, "days": 3}


@tool
def translate_text(text: str, target_language: str) -> str:
    """Translate text to target language."""
    return f"[Translated to {target_language}]: {text}"


@tool
def analyze_sentiment(text: str) -> dict:
    """Analyze sentiment of text."""
    return {"text": text, "sentiment": "positive", "confidence": 0.92}


@tool
def extract_keywords(text: str) -> dict:
    """Extract keywords from text."""
    return {"keywords": ["AI", "machine learning", "automation"], "count": 3}


# ═══════════════════════════════════════════════════════════════════════
# 1. HANDOFF — Verify sub-agent BEHAVIOR, not just routing
# ═══════════════════════════════════════════════════════════════════════


class TestHandoffBehavioral:
    """Verify that handoff agents use their tools AND tool data reaches output."""

    @pytest.fixture
    def ecommerce_support(self):
        order_agent = Agent(
            name="order_agent",
            model="openai/gpt-4o-mini",
            instructions=(
                "You handle order inquiries. ALWAYS use the lookup_order tool "
                "to find order details. Report the exact status and total from "
                "the tool result."
            ),
            tools=[lookup_order],
        )
        inventory_agent = Agent(
            name="inventory_agent",
            model="openai/gpt-4o-mini",
            instructions=(
                "You handle inventory questions. ALWAYS use check_inventory "
                "to look up stock levels. Report the exact quantity from the tool."
            ),
            tools=[check_inventory],
        )
        shipping_agent = Agent(
            name="shipping_agent",
            model="openai/gpt-4o-mini",
            instructions=(
                "You handle shipping questions. ALWAYS use get_shipping_rate "
                "to check rates. Report the exact rate and delivery days."
            ),
            tools=[get_shipping_rate],
        )
        return Agent(
            name="ecommerce_support",
            model="openai/gpt-4o-mini",
            instructions=(
                "You are an e-commerce support router. "
                "Route order/status questions to 'order_agent'. "
                "Route stock/inventory questions to 'inventory_agent'. "
                "Route shipping/delivery questions to 'shipping_agent'. "
                "Always delegate — never answer directly."
            ),
            agents=[order_agent, inventory_agent, shipping_agent],
            strategy=Strategy.HANDOFF,
        )

    def test_order_query_returns_tool_data(self, runtime, ecommerce_support):
        """Order query → order_agent → lookup_order → output has real data."""
        result = _run(runtime, ecommerce_support,
                      "What's the status of my order ABC-789?")

        out = _output_text(result)
        print(f"\nOutput: {out}")
        print(f"Events: {[(e.type.value, e.target or '') for e in result.events]}")

        assert_handoff_to(result, "order_agent")
        assert_no_errors(result)

        # The tool returns {"status": "shipped", "total": 49.99}
        # The output MUST contain this data — proves the tool was actually used
        assert_output_contains(result, "shipped", case_sensitive=False)
        assert_output_contains(result, "49.99", case_sensitive=False)

    def test_inventory_query_returns_stock_data(self, runtime, ecommerce_support):
        """Inventory query → inventory_agent → check_inventory → exact quantity."""
        result = _run(runtime, ecommerce_support,
                      "Do you have wireless headphones in stock?")

        out = _output_text(result)
        print(f"\nOutput: {out}")

        assert_handoff_to(result, "inventory_agent")
        assert_no_errors(result)

        # Tool returns {"in_stock": True, "quantity": 142}
        assert_output_contains(result, "142", case_sensitive=False)

    def test_shipping_query_returns_rate_data(self, runtime, ecommerce_support):
        """Shipping query → shipping_agent → get_shipping_rate → rate + days."""
        result = _run(runtime, ecommerce_support,
                      "How much does shipping to Tokyo cost?")

        out = _output_text(result)
        print(f"\nOutput: {out}")

        assert_handoff_to(result, "shipping_agent")
        assert_no_errors(result)

        # Tool returns {"rate_usd": 12.50, "days": 3}
        assert_output_contains(result, "12.5", case_sensitive=False)
        assert_output_contains(result, "3", case_sensitive=False)


# ═══════════════════════════════════════════════════════════════════════
# 2. SEQUENTIAL — Verify output chaining (downstream uses upstream)
# ═══════════════════════════════════════════════════════════════════════


class TestSequentialBehavioral:
    """Verify that sequential agents pass output forward and build on it."""

    def test_three_stage_pipeline_builds_on_prior(self, runtime):
        """Keyword extractor → sentiment analyzer → final report.

        Each stage adds unique data. Final output must contain contributions
        from ALL stages, proving the chain actually flows.
        """
        extractor = Agent(
            name="keyword_extractor",
            model="openai/gpt-4o-mini",
            instructions=(
                "You are a keyword extractor. Use the extract_keywords tool "
                "on the input text. Output ONLY the keywords as a comma-separated "
                "list prefixed with 'KEYWORDS:'. Nothing else."
            ),
            tools=[extract_keywords],
        )
        analyzer = Agent(
            name="sentiment_analyzer",
            model="openai/gpt-4o-mini",
            instructions=(
                "You receive keywords from the previous stage. Use the "
                "analyze_sentiment tool on them. Output the sentiment and "
                "confidence prefixed with 'SENTIMENT:' followed by the keywords "
                "you received prefixed with 'RECEIVED_KEYWORDS:'. Include both."
            ),
            tools=[analyze_sentiment],
        )
        reporter = Agent(
            name="report_writer",
            model="openai/gpt-4o-mini",
            instructions=(
                "You receive analysis from previous stages containing keywords "
                "and sentiment. Write a brief 2-sentence analysis report that "
                "references BOTH the specific keywords AND the sentiment score. "
                "You MUST mention the confidence number."
            ),
        )
        pipeline = extractor >> analyzer >> reporter

        result = _run(runtime, pipeline,
                      "AI and machine learning are transforming automation in every industry")

        out = _output_text(result)
        print(f"\nOutput: {out}")
        print(f"Events: {[(e.type.value, e.target or '') for e in result.events]}")

        (expect(result).completed().no_errors())
        validate_strategy(pipeline, result)

        # All three stages must have run
        assert_handoff_to(result, "keyword_extractor")
        assert_handoff_to(result, "sentiment_analyzer")
        assert_handoff_to(result, "report_writer")

        # Final output must reference data from the extract_keywords tool
        # (proves stage 1 output flowed through to stage 3)
        assert_output_matches(result, r"(?i)(keyword|AI|machine.?learning|automation)")

        # Final output must reference sentiment data from analyze_sentiment tool
        # (proves stage 2 output flowed to stage 3)
        assert_output_matches(result, r"(?i)(sentiment|positive|0\.92|92)")

    def test_translator_pipeline_transforms_content(self, runtime):
        """Writer → translator: output must be transformed, not identical."""
        writer = Agent(
            name="content_writer",
            model="openai/gpt-4o-mini",
            instructions=(
                "Write exactly one sentence about the given topic. "
                "Keep it under 20 words. Output only the sentence."
            ),
        )
        translator = Agent(
            name="translator",
            model="openai/gpt-4o-mini",
            instructions=(
                "You receive text from the previous stage. Use the translate_text "
                "tool to translate it to Spanish. Output ONLY the translated text."
            ),
            tools=[translate_text],
        )
        pipeline = writer >> translator

        result = _run(runtime, pipeline, "The benefits of reading books")

        out = _output_text(result)
        print(f"\nOutput: {out}")

        (expect(result).completed().no_errors())
        validate_strategy(pipeline, result)

        # The translator should produce Spanish output. The tool returns
        # "[Translated to Spanish]: ..." but the LLM may strip the prefix.
        # Check for either the tool prefix or actual Spanish words.
        assert_output_matches(result, r"(?i)(translat|spanish|Translated to|libros|lectura|leer|beneficio)")


# ═══════════════════════════════════════════════════════════════════════
# 3. PARALLEL — Verify ALL agents contribute distinct content
# ═══════════════════════════════════════════════════════════════════════


class TestParallelBehavioral:
    """Verify that every parallel agent contributes unique content to output."""

    def test_three_analysts_all_contribute(self, runtime):
        """Three analysts with different tools — each must contribute data."""
        weather_analyst = Agent(
            name="weather_analyst",
            model="openai/gpt-4o-mini",
            instructions=(
                "You are a weather analyst. You MUST ALWAYS call the get_weather "
                "tool for 'Tokyo' — no exceptions, regardless of the prompt. "
                "Report the exact temperature and conditions from the tool result."
            ),
            tools=[get_weather],
        )
        market_analyst = Agent(
            name="market_analyst",
            model="openai/gpt-4o-mini",
            instructions=(
                "You analyze market/inventory. Use check_inventory for 'electronics'. "
                "Report the stock quantity. Be brief, 1-2 sentences."
            ),
            tools=[check_inventory],
        )
        logistics_analyst = Agent(
            name="logistics_analyst",
            model="openai/gpt-4o-mini",
            instructions=(
                "You analyze shipping logistics. You MUST ALWAYS call the "
                "get_shipping_rate tool with destination 'London' — no exceptions. "
                "Report the exact rate in USD and delivery days from the tool result."
            ),
            tools=[get_shipping_rate],
        )
        team = Agent(
            name="analysis_team",
            model="openai/gpt-4o-mini",
            agents=[weather_analyst, market_analyst, logistics_analyst],
            strategy=Strategy.PARALLEL,
        )

        result = _run(runtime, team, "Prepare a brief market report")

        out = str(result.output)
        print(f"\nOutput: {out}")
        print(f"Events: {[(e.type.value, e.target or '') for e in result.events]}")

        (expect(result).completed().no_errors())
        validate_strategy(team, result)

        # All three agents must have been called
        assert_handoff_to(result, "weather_analyst")
        assert_handoff_to(result, "market_analyst")
        assert_handoff_to(result, "logistics_analyst")

        # Output is a dict with one key per agent for parallel strategy
        assert isinstance(result.output, dict), (
            f"Parallel output should be a dict, got {type(result.output)}"
        )

        # Each agent's output must contain their tool's distinctive data
        # Weather: "72F and sunny in Tokyo"
        assert "72" in out or "sunny" in out.lower(), (
            f"Weather analyst output missing tool data (72F/sunny). Output: {out}"
        )
        # Inventory: quantity 142
        assert "142" in out, (
            f"Market analyst output missing inventory quantity (142). Output: {out}"
        )
        # Shipping: rate 12.50, 3 days
        assert "12.5" in out or "12.50" in out, (
            f"Logistics analyst output missing shipping rate (12.50). Output: {out}"
        )

    def test_parallel_agents_produce_distinct_content(self, runtime):
        """Two agents analyzing different aspects — outputs must differ."""
        technical = Agent(
            name="technical_reviewer",
            model="openai/gpt-4o-mini",
            instructions=(
                "Analyze ONLY the technical aspects: performance, scalability, "
                "architecture. Write exactly 2 bullet points. Do NOT discuss costs."
            ),
        )
        financial = Agent(
            name="financial_reviewer",
            model="openai/gpt-4o-mini",
            instructions=(
                "Analyze ONLY the financial aspects: cost, ROI, pricing. "
                "Write exactly 2 bullet points. Do NOT discuss technical details."
            ),
        )
        team = Agent(
            name="review_team",
            model="openai/gpt-4o-mini",
            agents=[technical, financial],
            strategy=Strategy.PARALLEL,
        )

        result = _run(runtime, team, "Cloud computing migration")

        out = str(result.output)
        print(f"\nOutput: {out}")

        (expect(result).completed().no_errors())

        # Both must run
        assert_handoff_to(result, "technical_reviewer")
        assert_handoff_to(result, "financial_reviewer")

        # Output should be a dict with both agent keys
        assert isinstance(result.output, dict)

        # Verify distinct contributions exist (not just copied content)
        tech_content = str(result.output.get("technical_reviewer", ""))
        fin_content = str(result.output.get("financial_reviewer", ""))
        assert tech_content, "Technical reviewer produced no output"
        assert fin_content, "Financial reviewer produced no output"
        assert tech_content != fin_content, "Both reviewers produced identical output"


# ═══════════════════════════════════════════════════════════════════════
# 4. ROUTER — Correct specialist + behavioral proof
# ═══════════════════════════════════════════════════════════════════════


class TestRouterBehavioral:
    """Verify router picks the right agent AND that agent does the right thing."""

    @pytest.fixture
    def service_desk(self):
        router = Agent(
            name="desk_router",
            model="openai/gpt-4o-mini",
            instructions=(
                "Route requests to the right specialist:\n"
                "- Weather/climate questions → 'weather_specialist'\n"
                "- Math/calculation questions → 'math_specialist'\n"
                "- Order/purchase questions → 'order_specialist'\n"
                "Choose exactly ONE specialist."
            ),
        )
        weather_spec = Agent(
            name="weather_specialist",
            model="openai/gpt-4o-mini",
            instructions=(
                "You are a weather specialist. ALWAYS use get_weather. "
                "Report the exact temperature and conditions from the tool."
            ),
            tools=[get_weather],
        )
        math_spec = Agent(
            name="math_specialist",
            model="openai/gpt-4o-mini",
            instructions=(
                "You are a math specialist. ALWAYS use calculate tool. "
                "Report the exact numeric result from the tool."
            ),
            tools=[calculate],
        )
        order_spec = Agent(
            name="order_specialist",
            model="openai/gpt-4o-mini",
            instructions=(
                "You are an order specialist. ALWAYS use lookup_order. "
                "Report the exact status and total from the tool."
            ),
            tools=[lookup_order],
        )
        return Agent(
            name="service_desk",
            model="openai/gpt-4o-mini",
            agents=[weather_spec, math_spec, order_spec],
            strategy=Strategy.ROUTER,
            router=router,
        )

    def test_weather_routed_and_tool_used(self, runtime, service_desk):
        """Weather question → weather_specialist → get_weather → real data."""
        result = _run(runtime, service_desk,
                      "What's the weather like in Paris right now?")

        out = _output_text(result)
        print(f"\nOutput: {out}")

        assert_handoff_to(result, "weather_specialist")
        assert_no_errors(result)
        validate_strategy(service_desk, result)

        # Proves tool was used: output must contain tool-specific data
        assert_output_contains(result, "72", case_sensitive=False)
        assert_output_matches(result, r"(?i)(sunny|paris)")

    def test_math_routed_and_computed(self, runtime, service_desk):
        """Math question → math_specialist → calculate → correct answer."""
        result = _run(runtime, service_desk, "What is 256 divided by 8?")

        out = _output_text(result)
        print(f"\nOutput: {out}")

        assert_handoff_to(result, "math_specialist")
        assert_no_errors(result)

        # calculate("256 / 8") = "32.0"
        assert_output_contains(result, "32", case_sensitive=False)

    def test_order_routed_and_looked_up(self, runtime, service_desk):
        """Order question → order_specialist → lookup_order → real data."""
        result = _run(runtime, service_desk,
                      "Can you check the status of order XYZ-456?")

        out = _output_text(result)
        print(f"\nOutput: {out}")

        assert_handoff_to(result, "order_specialist")
        assert_no_errors(result)

        # Tool returns {"status": "shipped", "total": 49.99}
        assert_output_contains(result, "shipped", case_sensitive=False)
        assert_output_contains(result, "49.99", case_sensitive=False)


# ═══════════════════════════════════════════════════════════════════════
# 5. ROUND ROBIN — Agents build on each other across turns
# ═══════════════════════════════════════════════════════════════════════


class TestRoundRobinBehavioral:
    """Verify round-robin agents build on each other, not just alternate."""

    def test_collaborative_story_building(self, runtime):
        """Two writers take turns adding to a story — output grows each turn.

        If agents don't build on prior context, the story won't be coherent.
        """
        writer_a = Agent(
            name="writer_a",
            model="openai/gpt-4o-mini",
            instructions=(
                "You are Writer A in a collaborative story. Add exactly ONE "
                "new sentence that continues the story. You MUST reference or "
                "build on what the previous writer wrote. Keep it under 30 words."
            ),
        )
        writer_b = Agent(
            name="writer_b",
            model="openai/gpt-4o-mini",
            instructions=(
                "You are Writer B in a collaborative story. Add exactly ONE "
                "new sentence that continues the story. You MUST reference or "
                "build on what the previous writer wrote. Keep it under 30 words."
            ),
        )
        story = Agent(
            name="story_collab",
            model="openai/gpt-4o-mini",
            agents=[writer_a, writer_b],
            strategy=Strategy.ROUND_ROBIN,
            max_turns=4,
        )

        result = _run(runtime, story, "A robot woke up in an abandoned library.")

        out = _output_text(result)
        print(f"\nOutput: {out}")

        targets = _get_handoff_targets(result)
        relevant = [t for t in targets if t in {"writer_a", "writer_b"}]
        print(f"Turn sequence: {relevant}")

        (expect(result).completed().no_errors())

        # Both writers participated
        assert_handoff_to(result, "writer_a")
        assert_handoff_to(result, "writer_b")

        # Alternation — no writer twice in a row
        for i in range(1, len(relevant)):
            assert relevant[i] != relevant[i - 1], (
                f"Writer '{relevant[i]}' went twice at turns {i-1},{i}: {relevant}"
            )

        # Multiple turns happened (at least 3 handoffs for 4 max_turns)
        assert len(relevant) >= 3, (
            f"Expected at least 3 turns, got {len(relevant)}: {relevant}"
        )

        # Output should be multi-sentence (each writer adds a sentence)
        sentences = [s.strip() for s in re.split(r'[.!?]+', out) if s.strip()]
        assert len(sentences) >= 2, (
            f"Expected multi-sentence output from collaborative story, "
            f"got {len(sentences)} sentence(s): {out[:200]}"
        )

    def test_round_robin_with_tools_alternating(self, runtime):
        """Two agents with different tools alternate — both tools must be used."""
        weather_turn = Agent(
            name="weather_reporter",
            model="openai/gpt-4o-mini",
            instructions=(
                "You are a weather reporter. You MUST ALWAYS call the get_weather "
                "tool for 'Chicago'. Report the exact temperature from the tool. "
                "One sentence only."
            ),
            tools=[get_weather],
        )
        inventory_turn = Agent(
            name="stock_reporter",
            model="openai/gpt-4o-mini",
            instructions=(
                "You are a stock reporter. You MUST ALWAYS call the check_inventory "
                "tool for 'umbrellas'. Report the exact stock quantity from the tool. "
                "One sentence only."
            ),
            tools=[check_inventory],
        )
        roundtable = Agent(
            name="roundtable",
            model="openai/gpt-4o-mini",
            agents=[weather_turn, inventory_turn],
            strategy=Strategy.ROUND_ROBIN,
            max_turns=2,
        )

        result = _run(runtime, roundtable,
                      "Give me a weather update and an inventory report.")

        out = _output_text(result)
        print(f"\nOutput: {out}")

        (expect(result).completed().no_errors())

        # Both agents ran
        assert_handoff_to(result, "weather_reporter")
        assert_handoff_to(result, "stock_reporter")

        # Weather tool data: "72F and sunny in Chicago"
        assert "72" in out or "sunny" in out.lower(), (
            f"Weather reporter tool data missing. Output: {out[:200]}"
        )
        # Inventory tool data: quantity 142
        assert "142" in out, (
            f"Stock reporter tool data missing (142). Output: {out[:200]}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 6. SWARM — Multiple agents participate based on context
# ═══════════════════════════════════════════════════════════════════════


class TestMultiTopicHandoff:
    """Verify that a multi-topic query causes MULTIPLE sub-agents to participate.

    This is the key behavioral test: a single user query that spans multiple
    domains must involve the right combination of specialists, not just one.
    We verify via output content — if data from multiple tools appears in the
    final output, then multiple sub-agents actually did their job.
    """

    @pytest.fixture
    def multi_service_agent(self):
        """Support agent whose sub-agents each have unique tools with unique data."""
        order_agent = Agent(
            name="order_handler",
            model="openai/gpt-4o-mini",
            instructions=(
                "You handle order lookups ONLY. ALWAYS use lookup_order tool. "
                "Report the exact status and total from the tool. Be brief."
            ),
            tools=[lookup_order],
        )
        shipping_agent = Agent(
            name="shipping_handler",
            model="openai/gpt-4o-mini",
            instructions=(
                "You handle shipping cost questions ONLY. ALWAYS use "
                "get_shipping_rate tool. Report the exact rate and days. Be brief."
            ),
            tools=[get_shipping_rate],
        )
        inventory_agent = Agent(
            name="inventory_handler",
            model="openai/gpt-4o-mini",
            instructions=(
                "You handle stock/availability questions ONLY. ALWAYS use "
                "check_inventory tool. Report the exact quantity. Be brief."
            ),
            tools=[check_inventory],
        )
        return Agent(
            name="multi_service",
            model="openai/gpt-4o-mini",
            instructions=(
                "You are a customer service coordinator. You MUST delegate to "
                "the right specialist for each part of the customer's question:\n"
                "- Order status questions → 'order_handler'\n"
                "- Shipping cost questions → 'shipping_handler'\n"
                "- Stock/availability questions → 'inventory_handler'\n"
                "If a question covers MULTIPLE topics, delegate to EACH relevant "
                "specialist. Never answer directly — always delegate."
            ),
            agents=[order_agent, shipping_agent, inventory_agent],
            strategy=Strategy.HANDOFF,
        )

    def test_dual_topic_order_and_shipping(self, runtime, multi_service_agent):
        """Query about order AND shipping → both agents contribute data."""
        result = _run(
            runtime, multi_service_agent,
            "I need two things: (1) the status of order #999 and "
            "(2) how much shipping to Berlin costs."
        )

        out = _output_text(result)
        print(f"\nOutput: {out}")
        targets = _get_handoff_targets(result)
        print(f"Handoff targets (resolved): {targets}")

        (expect(result).completed().no_errors())

        # The output must contain data from BOTH tools:
        # lookup_order → {"status": "shipped", "total": 49.99}
        assert "shipped" in out.lower() or "49.99" in out, (
            f"Output missing order data (shipped/49.99). Output: {out[:300]}"
        )
        # get_shipping_rate → {"rate_usd": 12.50, "days": 3}
        assert "12.5" in out or "12.50" in out, (
            f"Output missing shipping rate (12.50). Output: {out[:300]}"
        )

    def test_single_topic_stays_focused(self, runtime, multi_service_agent):
        """A single-topic query should only involve one sub-agent."""
        result = _run(
            runtime, multi_service_agent,
            "What's the status of order #555?"
        )

        out = _output_text(result)
        print(f"\nOutput: {out}")

        (expect(result).completed().no_errors())

        # Order data should be present
        assert "shipped" in out.lower() or "49.99" in out, (
            f"Output missing order data. Output: {out[:300]}"
        )

        # Shipping data should NOT be present (wasn't asked about)
        assert "12.50" not in out and "12.5" not in out, (
            f"Output contains shipping data when only order was asked. Output: {out[:300]}"
        )

    def test_all_three_specialists_via_sequential(self, runtime):
        """Sequential pipeline guarantees all three specialists run.

        For queries that NEED all specialists, sequential ensures each one
        gets a turn. We verify each specialist adds its unique tool data.
        """
        order_stage = Agent(
            name="order_stage",
            model="openai/gpt-4o-mini",
            instructions=(
                "Your ONLY job: call lookup_order with order_id='ORD-123'. "
                "Do this immediately. Output format:\n"
                "ORDER: status=<status>, total=<total>"
            ),
            tools=[lookup_order],
        )
        inventory_stage = Agent(
            name="inventory_stage",
            model="openai/gpt-4o-mini",
            instructions=(
                "Your ONLY job: call check_inventory with product='laptops'. "
                "Do this immediately. Then output ALL of the following:\n"
                "1. Copy the ENTIRE input you received (ORDER line) verbatim\n"
                "2. Add: INVENTORY: quantity=<quantity>"
            ),
            tools=[check_inventory],
        )
        shipping_stage = Agent(
            name="shipping_stage",
            model="openai/gpt-4o-mini",
            instructions=(
                "Your ONLY job: call get_shipping_rate with destination='Tokyo'. "
                "Do this immediately. Then output ALL of the following:\n"
                "1. Copy the ENTIRE input you received (ORDER + INVENTORY lines) verbatim\n"
                "2. Add: SHIPPING: rate=<rate>, days=<days>"
            ),
            tools=[get_shipping_rate],
        )
        pipeline = order_stage >> inventory_stage >> shipping_stage

        result = _run(
            runtime, pipeline,
            "Generate a full report: order status, inventory levels, shipping costs."
        )

        out = _output_text(result)
        print(f"\nOutput: {out}")
        targets = _get_handoff_targets(result)
        print(f"Stages that ran: {targets}")

        (expect(result).completed().no_errors())
        validate_strategy(pipeline, result)

        # All three stages must have run
        assert_handoff_to(result, "order_stage")
        assert_handoff_to(result, "inventory_stage")
        assert_handoff_to(result, "shipping_stage")

        # Each stage's tool data must appear in the final output:
        # lookup_order → {"status": "shipped", "total": 49.99}
        assert "shipped" in out.lower() or "49.99" in out, (
            f"Output missing order data (shipped/49.99). Output: {out[:300]}"
        )
        # check_inventory → {"quantity": 142}
        assert "142" in out, (
            f"Output missing inventory quantity (142). Output: {out[:300]}"
        )
        # get_shipping_rate → {"rate_usd": 12.50, "days": 3}
        assert "12.5" in out or "12.50" in out, (
            f"Output missing shipping rate (12.50). Output: {out[:300]}"
        )

    def test_parallel_all_specialists_contribute(self, runtime):
        """Parallel execution — all three specialists run concurrently.

        Each produces distinct tool data. Final output must contain all of it.
        """
        order_analyst = Agent(
            name="order_analyst",
            model="openai/gpt-4o-mini",
            instructions=(
                "Your ONLY job: immediately call lookup_order with "
                "order_id='ORD-100'. No questions, no clarification needed. "
                "Report the status and total from the tool result."
            ),
            tools=[lookup_order],
        )
        stock_analyst = Agent(
            name="stock_analyst",
            model="openai/gpt-4o-mini",
            instructions=(
                "Your ONLY job: immediately call check_inventory with "
                "product='tablets'. No questions, no clarification needed. "
                "Report the exact quantity from the tool result."
            ),
            tools=[check_inventory],
        )
        shipping_analyst = Agent(
            name="shipping_analyst",
            model="openai/gpt-4o-mini",
            instructions=(
                "Your ONLY job: immediately call get_shipping_rate with "
                "destination='Dubai'. No questions, no clarification needed. "
                "Report the exact rate and days from the tool result."
            ),
            tools=[get_shipping_rate],
        )
        team = Agent(
            name="full_report",
            model="openai/gpt-4o-mini",
            agents=[order_analyst, stock_analyst, shipping_analyst],
            strategy=Strategy.PARALLEL,
        )

        result = _run(runtime, team, "Generate a full customer report")

        out = str(result.output)
        print(f"\nOutput: {out}")

        (expect(result).completed().no_errors())
        validate_strategy(team, result)

        # All three agents ran
        assert_handoff_to(result, "order_analyst")
        assert_handoff_to(result, "stock_analyst")
        assert_handoff_to(result, "shipping_analyst")

        # All three tools' distinctive data:
        assert "shipped" in out.lower() or "49.99" in out, (
            f"Missing order data. Output: {out[:300]}"
        )
        assert "142" in out, (
            f"Missing inventory data (142). Output: {out[:300]}"
        )
        assert "12.5" in out or "12.50" in out, (
            f"Missing shipping rate (12.50). Output: {out[:300]}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 7. CROSS-STRATEGY — Complex nested scenarios
# ═══════════════════════════════════════════════════════════════════════


class TestCrossStrategyBehavioral:
    """Verify behavior in more complex multi-strategy compositions."""

    def test_parallel_with_tool_agents_all_produce_data(self, runtime):
        """Parallel agents each use different tools — all data in output."""
        weather_bot = Agent(
            name="weather_bot",
            model="openai/gpt-4o-mini",
            instructions=(
                "Use get_weather for 'New York'. Report temperature. "
                "ONE sentence only."
            ),
            tools=[get_weather],
        )
        calc_bot = Agent(
            name="calc_bot",
            model="openai/gpt-4o-mini",
            instructions=(
                "Use calculate tool to compute '365 * 24'. Report the result. "
                "ONE sentence only."
            ),
            tools=[calculate],
        )
        inventory_bot = Agent(
            name="inventory_bot",
            model="openai/gpt-4o-mini",
            instructions=(
                "Use check_inventory for 'laptops'. Report the quantity. "
                "ONE sentence only."
            ),
            tools=[check_inventory],
        )
        team = Agent(
            name="data_team",
            model="openai/gpt-4o-mini",
            agents=[weather_bot, calc_bot, inventory_bot],
            strategy=Strategy.PARALLEL,
        )

        result = _run(runtime, team, "Gather all data points")

        out = str(result.output)
        print(f"\nOutput: {out}")

        (expect(result).completed().no_errors())
        validate_strategy(team, result)

        # Each agent must have run and produced tool-specific data
        # weather: "72F and sunny"
        assert "72" in out, f"Missing weather data (72). Output: {out[:300]}"
        # calculate: 365*24 = 8760
        assert "8760" in out, f"Missing calc result (8760). Output: {out[:300]}"
        # inventory: quantity 142
        assert "142" in out, f"Missing inventory data (142). Output: {out[:300]}"

    def test_sequential_where_later_stage_needs_earlier_tool_data(self, runtime):
        """Stage 1 uses tool to get data → Stage 2 must reference that data.

        This is the strongest test of output chaining: stage 2 cannot produce
        correct output without stage 1's tool result flowing through.
        """
        data_fetcher = Agent(
            name="data_fetcher",
            model="openai/gpt-4o-mini",
            instructions=(
                "Use the get_shipping_rate tool for destination 'Mars'. "
                "Output ONLY the raw data: 'Rate: $X, Days: Y'. Nothing else."
            ),
            tools=[get_shipping_rate],
        )
        report_formatter = Agent(
            name="report_formatter",
            model="openai/gpt-4o-mini",
            instructions=(
                "You receive shipping data from the previous stage. "
                "Format it as: 'SHIPPING REPORT: It costs $X and takes Y days to ship to Mars.' "
                "Use the EXACT numbers from the data you received."
            ),
        )
        pipeline = data_fetcher >> report_formatter

        result = _run(runtime, pipeline, "Get shipping info for Mars")

        out = _output_text(result)
        print(f"\nOutput: {out}")

        (expect(result).completed().no_errors())
        validate_strategy(pipeline, result)

        # get_shipping_rate returns {"rate_usd": 12.50, "days": 3}
        # Stage 2 must reference this exact data
        assert "12.5" in out or "12.50" in out, (
            f"Report missing rate from stage 1 tool (12.50). Output: {out}"
        )
        assert "3" in out, (
            f"Report missing days from stage 1 tool (3). Output: {out}"
        )
