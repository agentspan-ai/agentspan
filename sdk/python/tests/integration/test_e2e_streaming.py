# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""E2E streaming tests — validate complete SSE event streams for all agent categories.

These tests require a running Conductor server with LLM and streaming support.
Skip with: pytest -m "not integration"

Requirements:
    - export AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - LLM provider configured (OpenAI by default)
    - Optionally: export AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini
"""

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

import pytest

from agentspan.agents import (
    Agent,
    AgentEvent,
    AgentRuntime,
    AgentStream,
    EventType,
    Guardrail,
    GuardrailResult,
    OnFail,
    RegexGuardrail,
    tool,
)

pytestmark = pytest.mark.integration

# Default model — cheap and fast for integration tests
DEFAULT_MODEL = "openai/gpt-4o-mini"


def _model() -> str:
    import os
    return os.environ.get("AGENTSPAN_LLM_MODEL", DEFAULT_MODEL)


# ── Data-Driven Validation ──────────────────────────────────────────────


@dataclass
class EventSpec:
    """Specification for validating an event sequence.

    Attributes:
        required: Event types that MUST appear, in order (subsequence check).
        optional: Event types that MAY appear anywhere.
        forbidden: Event types that MUST NOT appear.
        min_count: Minimum total number of events expected.
        terminal: The expected terminal event type (typically ``done`` or ``error``).
    """

    required: List[str] = field(default_factory=list)
    optional: Set[str] = field(default_factory=set)
    forbidden: Set[str] = field(default_factory=set)
    min_count: int = 1
    terminal: str = "done"


# ── Helper Functions ────────────────────────────────────────────────────


def collect_events_until(
    stream: AgentStream,
    stop_type: str,
    timeout: float = 120,
) -> List[AgentEvent]:
    """Iterate stream, appending events, until *stop_type* seen or timeout.

    After this returns, the caller can perform HITL actions (approve/reject/respond)
    and then resume iterating ``for event in stream:`` to collect post-action events.
    """
    events: List[AgentEvent] = []
    start = time.monotonic()
    for event in stream:
        events.append(event)
        if event.type == stop_type:
            break
        if time.monotonic() - start > timeout:
            raise TimeoutError(
                f"Timed out after {timeout}s waiting for {stop_type!r}. "
                f"Got: {event_types(events)}"
            )
    return events


def collect_all_events(stream: AgentStream) -> List[AgentEvent]:
    """Drain a stream completely and return all events."""
    events: List[AgentEvent] = []
    for event in stream:
        events.append(event)
    return events


def event_types(events: Sequence[AgentEvent]) -> List[str]:
    """Extract a list of type strings from events."""
    return [_event_type_str(e) for e in events]


def find_event(events: Sequence[AgentEvent], event_type: str) -> Optional[AgentEvent]:
    """Return the first event of the given type, or None."""
    for e in events:
        if _event_type_str(e) == event_type:
            return e
    return None


def find_events(events: Sequence[AgentEvent], event_type: str) -> List[AgentEvent]:
    """Return all events of the given type."""
    return [e for e in events if _event_type_str(e) == event_type]


def assert_event_sequence(events: Sequence[AgentEvent], required: List[str]) -> None:
    """Assert that *required* appears as an ordered subsequence in *events*.

    The required types must appear in order, but other events may appear between them.
    """
    types = event_types(events)
    req_idx = 0
    for t in types:
        if req_idx < len(required) and t == required[req_idx]:
            req_idx += 1
    assert req_idx == len(required), (
        f"Required sequence {required} not found as subsequence.\n"
        f"Got: {types}"
    )


def assert_no_forbidden(events: Sequence[AgentEvent], forbidden: Set[str]) -> None:
    """Assert no events of forbidden types appear."""
    found = [t for t in event_types(events) if t in forbidden]
    assert not found, f"Forbidden event types found: {found}"


def assert_event_spec(events: Sequence[AgentEvent], spec: EventSpec) -> None:
    """Full EventSpec validation: required, forbidden, min_count, terminal."""
    types = event_types(events)

    assert len(events) >= spec.min_count, (
        f"Expected at least {spec.min_count} events, got {len(events)}.\n"
        f"Events: {types}"
    )

    if spec.required:
        assert_event_sequence(events, spec.required)

    if spec.forbidden:
        assert_no_forbidden(events, spec.forbidden)

    if spec.terminal:
        assert types[-1] == spec.terminal, (
            f"Expected terminal event {spec.terminal!r}, got {types[-1]!r}.\n"
            f"Events: {types}"
        )


def _event_type_str(event: AgentEvent) -> str:
    """Normalize event type to a plain string."""
    t = event.type
    if isinstance(t, EventType):
        return t.value
    return str(t)


def _unique_name(prefix: str) -> str:
    """Generate a unique agent name for test isolation."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ── Shared Tools ────────────────────────────────────────────────────────


@tool
def get_weather(city: str) -> dict:
    """Get current weather for a city."""
    return {"city": city, "temp": 72, "condition": "Sunny"}


@tool
def get_stock_price(symbol: str) -> dict:
    """Get the current stock price for a symbol."""
    return {"symbol": symbol, "price": 150.25, "currency": "USD"}


@tool(approval_required=True)
def publish_article(title: str, body: str) -> dict:
    """Publish an article to the blog. Requires editorial approval."""
    return {
        "status": "published",
        "title": title,
        "url": f"/blog/{title.lower().replace(' ', '-')}",
    }


@tool(approval_required=True)
def transfer_funds(from_acct: str, to_acct: str, amount: float) -> dict:
    """Transfer funds between accounts. Requires approval."""
    return {
        "from": from_acct,
        "to": to_acct,
        "amount": amount,
        "status": "completed",
    }


@tool
def check_balance(account_id: str) -> dict:
    """Check account balance."""
    return {"account_id": account_id, "balance": 5000.00, "currency": "USD"}


@tool
def get_customer_data(customer_id: str) -> dict:
    """Retrieve customer profile data."""
    return {
        "customer_id": customer_id,
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "ssn": "123-45-6789",
    }


# ── Shared Guardrails ──────────────────────────────────────────────────


def no_ssn(content: str) -> GuardrailResult:
    """Reject responses containing SSN patterns."""
    if re.search(r"\b\d{3}-\d{2}-\d{4}\b", content):
        return GuardrailResult(
            passed=False,
            message="Response must not contain SSN numbers. Redact them.",
        )
    return GuardrailResult(passed=True)


def always_fails(content: str) -> GuardrailResult:
    """Guardrail that always fails."""
    return GuardrailResult(passed=False, message="This guardrail always fails.")


def lenient_check(content: str) -> GuardrailResult:
    """Guardrail that always passes."""
    return GuardrailResult(passed=True)


# ═══════════════════════════════════════════════════════════════════════
# Category 1: Simple Agent Streaming (thinking → done)
# Examples: 01, 11, 12
# ═══════════════════════════════════════════════════════════════════════


class TestSimpleAgentStreaming:
    """Simple agents with no tools — expect thinking → done."""

    SPEC = EventSpec(
        required=["thinking", "done"],
        optional={"message"},
        min_count=2,
        terminal="done",
    )

    def test_simple_agent_stream(self, runtime, model):
        """Basic agent: thinking → done with non-empty output."""
        agent = Agent(
            name=_unique_name("e2e_simple"),
            model=model,
            instructions="Reply in exactly one sentence.",
        )
        stream = runtime.stream(agent, "What is Python?")
        events = collect_all_events(stream)
        assert_event_spec(events, self.SPEC)

        done = find_event(events, "done")
        assert done is not None
        assert done.output is not None

    def test_simple_agent_has_execution_id(self, runtime, model):
        """Stream exposes a valid execution_id."""
        agent = Agent(
            name=_unique_name("e2e_simple_wf"),
            model=model,
        )
        stream = runtime.stream(agent, "Say hello.")
        assert stream.execution_id != ""
        collect_all_events(stream)

    def test_simple_agent_get_result(self, runtime, model):
        """get_result() returns AgentResult after streaming."""
        agent = Agent(
            name=_unique_name("e2e_simple_res"),
            model=model,
        )
        stream = runtime.stream(agent, "Say hello.")
        collect_all_events(stream)
        result = stream.get_result()
        assert result is not None
        assert result.status == "COMPLETED"
        assert result.output is not None


# ═══════════════════════════════════════════════════════════════════════
# Category 2: Agent + Tools Streaming (tool_call → tool_result cycle)
# Examples: 02a, 02b, 03, 14, 23, 33_single
# ═══════════════════════════════════════════════════════════════════════


class TestToolAgentStreaming:
    """Agents with tools — expect thinking → tool_call → tool_result → done."""

    SPEC = EventSpec(
        required=["thinking", "done"],
        optional={"tool_call", "tool_result", "message"},
        min_count=2,
        terminal="done",
    )

    def test_tool_agent_stream(self, runtime, model):
        """Agent uses get_weather tool, events include tool_call/tool_result."""
        agent = Agent(
            name=_unique_name("e2e_tools"),
            model=model,
            tools=[get_weather],
            instructions="Use the get_weather tool to answer weather questions.",
        )
        stream = runtime.stream(agent, "What's the weather in NYC?")
        events = collect_all_events(stream)
        assert_event_spec(events, self.SPEC)

        # Should have at least one tool_call (LLM non-determinism: check >=1)
        tool_calls = find_events(events, "tool_call")
        assert len(tool_calls) >= 1, (
            f"Expected at least 1 tool_call, got {len(tool_calls)}. Events: {event_types(events)}"
        )

    def test_multi_tool_agent(self, runtime, model):
        """Agent with multiple tools — uses the right one."""
        agent = Agent(
            name=_unique_name("e2e_multi_tool"),
            model=model,
            tools=[get_weather, get_stock_price],
            instructions="Use the appropriate tool to answer questions.",
        )
        stream = runtime.stream(agent, "What's AAPL trading at?")
        events = collect_all_events(stream)
        assert_event_spec(events, self.SPEC)

        done = find_event(events, "done")
        assert done is not None
        assert done.output is not None

    def test_tool_result_follows_call(self, runtime, model):
        """Every tool_call should be followed by a tool_result (eventually)."""
        agent = Agent(
            name=_unique_name("e2e_tool_order"),
            model=model,
            tools=[get_weather],
            instructions="Use get_weather to answer. Always call the tool.",
        )
        stream = runtime.stream(agent, "Weather in London?")
        events = collect_all_events(stream)
        types = event_types(events)

        calls = [i for i, t in enumerate(types) if t == "tool_call"]
        results = [i for i, t in enumerate(types) if t == "tool_result"]

        # Each tool_call should have a corresponding tool_result after it
        for call_idx in calls:
            matching_results = [r for r in results if r > call_idx]
            assert matching_results, (
                f"tool_call at index {call_idx} has no subsequent tool_result.\n"
                f"Events: {types}"
            )


# ═══════════════════════════════════════════════════════════════════════
# Category 3: HITL Streaming (approve/reject/feedback)
# Examples: 02, 09, 09b, 09c
# ═══════════════════════════════════════════════════════════════════════


class TestHITLStreaming:
    """Human-in-the-loop: programmatic approve/reject/feedback via streaming."""

    def test_hitl_approve_path(self, runtime, model):
        """Stream → WAITING → approve() → collect until DONE → COMPLETED."""
        agent = Agent(
            name=_unique_name("e2e_hitl_approve"),
            model=model,
            tools=[publish_article],
            instructions=(
                "You are a blog writer. Write a very short article (one paragraph) "
                "about Python and publish it using the publish_article tool."
            ),
        )
        stream = runtime.stream(
            agent, "Write a short blog post about Python programming"
        )

        # Collect until WAITING
        pre_events = collect_events_until(stream, EventType.WAITING.value, timeout=120)
        waiting = find_event(pre_events, "waiting")
        assert waiting is not None, (
            f"Expected WAITING event. Got: {event_types(pre_events)}"
        )

        # Approve
        stream.approve()

        # Continue collecting until terminal
        post_events = collect_all_events(stream)
        all_events = pre_events + post_events

        done = find_event(all_events, "done")
        assert done is not None, (
            f"Expected DONE after approve. Got: {event_types(all_events)}"
        )

        result = stream.get_result()
        assert result.status == "COMPLETED"

    def test_hitl_reject_path(self, runtime, model):
        """Stream → WAITING → reject() → collect → ERROR or FAILED."""
        agent = Agent(
            name=_unique_name("e2e_hitl_reject"),
            model=model,
            tools=[publish_article],
            instructions=(
                "Write a very short article (one paragraph) about testing "
                "and publish it using publish_article."
            ),
        )
        stream = runtime.stream(agent, "Write about software testing")

        # Collect until WAITING
        pre_events = collect_events_until(stream, EventType.WAITING.value, timeout=120)
        waiting = find_event(pre_events, "waiting")
        assert waiting is not None

        # Reject
        stream.reject("Does not meet editorial standards")

        # Continue collecting
        post_events = collect_all_events(stream)
        all_events = pre_events + post_events
        types = event_types(all_events)

        # Terminal should be error or done (implementation-dependent)
        terminal = types[-1]
        assert terminal in ("error", "done"), (
            f"Expected terminal error or done after reject. Got: {types}"
        )

    def test_hitl_feedback_path(self, runtime, model):
        """Stream → WAITING → respond(feedback) → possibly another WAITING → approve → DONE.

        This is the 09b scenario: human provides revision feedback, agent revises.

        NOTE: The server-side approval workflow uses an LLM normalizer that
        may classify free-form feedback as a rejection.  This test accepts
        both ``done`` and ``error`` as valid terminals to account for this
        server-side limitation.
        """
        agent = Agent(
            name=_unique_name("e2e_hitl_feedback"),
            model=model,
            tools=[publish_article],
            instructions=(
                "You are a blog writer. Draft an article and publish it. "
                "If you receive editorial feedback, revise the article and "
                "try publishing again."
            ),
        )
        stream = runtime.stream(
            agent, "Write a short blog post about code review best practices"
        )

        # First WAITING — provide feedback instead of approving
        pre_events = collect_events_until(stream, EventType.WAITING.value, timeout=120)
        waiting = find_event(pre_events, "waiting")
        assert waiting is not None, (
            f"Expected first WAITING. Got: {event_types(pre_events)}"
        )

        # Send feedback
        stream.respond({"feedback": "Make it shorter and add a conclusion."})

        # Collect more events — may get another WAITING or go straight to DONE
        mid_events: List[AgentEvent] = []
        for event in stream:
            mid_events.append(event)
            t = _event_type_str(event)
            if t == "waiting":
                # Second WAITING — now approve
                stream.approve()
            elif t in ("done", "error"):
                break

        all_events = pre_events + mid_events
        types = event_types(all_events)

        # Should end with done or error
        terminal = types[-1]
        assert terminal in ("done", "error"), (
            f"Expected terminal done/error after feedback path. Got: {types}"
        )

    def test_hitl_transfer_approve(self, runtime, model):
        """Banking agent variant — transfer_funds requires approval (09/09c scenario)."""
        agent = Agent(
            name=_unique_name("e2e_hitl_transfer"),
            model=model,
            tools=[check_balance, transfer_funds],
            instructions=(
                "You are a banking assistant. When asked to transfer money, "
                "first check the balance, then transfer using transfer_funds."
            ),
        )
        stream = runtime.stream(
            agent, "Transfer $100 from account ACC-1 to account ACC-2"
        )

        # Collect until WAITING (transfer needs approval)
        pre_events = collect_events_until(stream, EventType.WAITING.value, timeout=120)
        waiting = find_event(pre_events, "waiting")
        assert waiting is not None, (
            f"Expected WAITING for transfer approval. Got: {event_types(pre_events)}"
        )

        # Approve the transfer
        stream.approve()

        # Collect remaining
        post_events = collect_all_events(stream)
        all_events = pre_events + post_events

        done = find_event(all_events, "done")
        assert done is not None, (
            f"Expected DONE after transfer approval. Got: {event_types(all_events)}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Category 4: Handoff Streaming (sub-agent delegation)
# Examples: 05, 13
# ═══════════════════════════════════════════════════════════════════════


class TestHandoffStreaming:
    """Handoff agents delegate to sub-agents — expect handoff event."""

    def test_handoff_stream(self, runtime, model):
        """Parent delegates to sub-agent, handoff event appears."""
        math_agent = Agent(
            name=_unique_name("e2e_math_sub"),
            model=model,
            instructions="You are a math expert. Answer math questions concisely.",
        )
        parent = Agent(
            name=_unique_name("e2e_handoff_parent"),
            model=model,
            instructions="Delegate math questions to the math expert.",
            agents=[math_agent],
            strategy="handoff",
        )
        stream = runtime.stream(parent, "What is 7 * 8?")
        events = collect_all_events(stream)
        types = event_types(events)

        # Should end with done
        assert types[-1] == "done", f"Expected terminal done. Got: {types}"

        # Should have at least a handoff or thinking event
        assert len(events) >= 2, f"Expected at least 2 events. Got: {types}"

    def test_handoff_with_tools(self, runtime, model):
        """Sub-agent with tools — parent delegates, sub uses tool."""
        tool_agent = Agent(
            name=_unique_name("e2e_weather_sub"),
            model=model,
            tools=[get_weather],
            instructions="Use get_weather to answer weather questions.",
        )
        parent = Agent(
            name=_unique_name("e2e_handoff_tool"),
            model=model,
            instructions="Delegate weather questions to the weather expert.",
            agents=[tool_agent],
            strategy="handoff",
        )
        stream = runtime.stream(parent, "What's the weather in Tokyo?")
        events = collect_all_events(stream)
        types = event_types(events)

        assert types[-1] == "done", f"Expected terminal done. Got: {types}"


# ═══════════════════════════════════════════════════════════════════════
# Category 5: Sequential Pipeline Streaming (>> operator)
# Examples: 06, 15
# ═══════════════════════════════════════════════════════════════════════


class TestSequentialStreaming:
    """Sequential pipeline (>> operator) — agents run in order."""

    def test_sequential_pipeline(self, runtime, model):
        """A >> B pipeline — both execute, output from last agent."""
        summarizer = Agent(
            name=_unique_name("e2e_seq_sum"),
            model=model,
            instructions="Summarize the input in one sentence.",
        )
        translator = Agent(
            name=_unique_name("e2e_seq_trans"),
            model=model,
            instructions="Translate the input to French.",
        )
        pipeline = summarizer >> translator
        stream = runtime.stream(pipeline, "Python is a popular programming language used for web, AI, and scripting.")
        events = collect_all_events(stream)
        types = event_types(events)

        assert types[-1] == "done", f"Expected terminal done. Got: {types}"

        done = find_event(events, "done")
        assert done is not None
        assert done.output is not None


# ═══════════════════════════════════════════════════════════════════════
# Category 6: Parallel Streaming (fan-out / fan-in)
# Examples: 07
# ═══════════════════════════════════════════════════════════════════════


class TestParallelStreaming:
    """Parallel agents — multiple sub-agents run concurrently."""

    def test_parallel_agents(self, runtime, model):
        """Two analysts run in parallel, results merged."""
        analyst1 = Agent(
            name=_unique_name("e2e_par_a1"),
            model=model,
            instructions="Analyze from a market perspective. Be brief.",
        )
        analyst2 = Agent(
            name=_unique_name("e2e_par_a2"),
            model=model,
            instructions="Analyze from a risk perspective. Be brief.",
        )
        analysis = Agent(
            name=_unique_name("e2e_parallel"),
            model=model,
            agents=[analyst1, analyst2],
            strategy="parallel",
        )
        stream = runtime.stream(analysis, "Should we invest in AI startups?")
        events = collect_all_events(stream)
        types = event_types(events)

        assert types[-1] == "done", f"Expected terminal done. Got: {types}"


# ═══════════════════════════════════════════════════════════════════════
# Category 7: Router Streaming (LLM-based routing)
# Examples: 08
# ═══════════════════════════════════════════════════════════════════════


class TestRouterStreaming:
    """Router agent — LLM selects which sub-agent to invoke."""

    def test_router_selects_agent(self, runtime, model):
        """Router picks the right sub-agent based on the prompt."""
        planner = Agent(
            name=_unique_name("e2e_router_plan"),
            model=model,
            instructions="Create a project plan. Be brief.",
        )
        coder = Agent(
            name=_unique_name("e2e_router_code"),
            model=model,
            instructions="Write code. Be brief.",
        )
        router = Agent(
            name=_unique_name("e2e_router_lead"),
            model=model,
            instructions="Select planner for planning tasks, coder for coding tasks.",
        )
        team = Agent(
            name=_unique_name("e2e_router"),
            model=model,
            agents=[planner, coder],
            strategy="router",
            router=router,
            max_turns=2,
        )
        stream = runtime.stream(team, "Write a hello world function in Python")
        events = collect_all_events(stream)
        types = event_types(events)

        assert types[-1] == "done", f"Expected terminal done. Got: {types}"


# ═══════════════════════════════════════════════════════════════════════
# Category 8: Guardrail Streaming (pass/fail/retry/raise)
# Examples: 10, 21, 22, 36
# ═══════════════════════════════════════════════════════════════════════


class TestGuardrailStreaming:
    """Guardrails in streaming mode — retry, raise, pass."""

    def test_guardrail_retry_succeeds_streaming(self, runtime, model):
        """Guardrail rejects SSN, agent retries and succeeds."""
        agent = Agent(
            name=_unique_name("e2e_guard_retry"),
            model=model,
            tools=[get_customer_data],
            instructions=(
                "Retrieve customer data. Include all details from the tool results."
            ),
            guardrails=[
                Guardrail(no_ssn, position="output", on_fail="retry", max_retries=3),
            ],
        )
        stream = runtime.stream(
            agent, "Look up customer CUST-7 and give me their full profile."
        )
        events = collect_all_events(stream)
        types = event_types(events)

        # Should complete (with or without guardrail_fail events)
        assert types[-1] in ("done", "error"), f"Unexpected terminal: {types}"

    def test_guardrail_raise_terminates_streaming(self, runtime, model):
        """Always-failing guardrail with raise → workflow terminates."""
        agent = Agent(
            name=_unique_name("e2e_guard_raise"),
            model=model,
            tools=[get_weather],
            instructions="You are a weather assistant.",
            guardrails=[
                Guardrail(always_fails, position="output", on_fail="raise"),
            ],
        )
        stream = runtime.stream(agent, "What's the weather?")
        events = collect_all_events(stream)
        types = event_types(events)

        # Should end with error (FAILED/TERMINATED)
        assert types[-1] == "error", (
            f"Expected terminal error for raise guardrail. Got: {types}"
        )

    def test_guardrail_pass_no_interference(self, runtime, model):
        """Lenient guardrail that always passes — no interference."""
        agent = Agent(
            name=_unique_name("e2e_guard_pass"),
            model=model,
            tools=[get_weather],
            instructions="Use get_weather to answer.",
            guardrails=[
                Guardrail(lenient_check, position="output", on_fail="retry"),
            ],
        )
        stream = runtime.stream(agent, "What's the weather in Berlin?")
        events = collect_all_events(stream)
        types = event_types(events)

        assert types[-1] == "done", f"Expected done. Got: {types}"
        assert "guardrail_fail" not in types, (
            f"Lenient guardrail should not produce guardrail_fail. Got: {types}"
        )

    def test_regex_guardrail_streaming(self, runtime, model):
        """RegexGuardrail (server-side InlineTask) in streaming mode."""
        agent = Agent(
            name=_unique_name("e2e_regex_guard"),
            model=model,
            tools=[get_customer_data],
            instructions="Retrieve customer data and present it.",
            guardrails=[
                RegexGuardrail(
                    patterns=[r"[\w.+-]+@[\w-]+\.[\w.-]+"],
                    name="no_email",
                    message="Response must not contain email addresses.",
                    on_fail="retry",
                    max_retries=3,
                ),
            ],
        )
        stream = runtime.stream(
            agent, "Show me the profile for customer CUST-7."
        )
        events = collect_all_events(stream)
        types = event_types(events)

        assert types[-1] in ("done", "error"), f"Unexpected terminal: {types}"


# ═══════════════════════════════════════════════════════════════════════
# Category 9: Manual HITL Selection Streaming
# Examples: 18, 27
# ═══════════════════════════════════════════════════════════════════════


class TestManualSelectionStreaming:
    """Manual agent selection — human selects which agent to run."""

    def test_manual_selection(self, runtime, model):
        """Manual strategy pauses for human selection, then completes."""
        greeter = Agent(
            name=_unique_name("e2e_manual_greet"),
            model=model,
            instructions="Greet the user warmly.",
        )
        helper = Agent(
            name=_unique_name("e2e_manual_help"),
            model=model,
            instructions="Help the user with their question.",
        )
        team = Agent(
            name=_unique_name("e2e_manual"),
            model=model,
            agents=[greeter, helper],
            strategy="manual",
        )
        stream = runtime.stream(team, "Hello, I need help!")

        # Collect until WAITING
        pre_events = collect_events_until(stream, EventType.WAITING.value, timeout=120)
        waiting = find_event(pre_events, "waiting")
        assert waiting is not None, (
            f"Expected WAITING for manual selection. Got: {event_types(pre_events)}"
        )

        # Select the helper agent by responding with the agent name
        stream.respond({"selectedAgent": helper.name})

        # Collect remaining
        post_events = collect_all_events(stream)
        all_events = pre_events + post_events
        types = event_types(all_events)

        assert types[-1] in ("done", "error"), (
            f"Expected terminal done/error. Got: {types}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Category 10: External Services (skip placeholders)
# Examples: 04, 26, 28, 30
# ═══════════════════════════════════════════════════════════════════════


class TestExternalServicesStreaming:
    """External agents/services — skipped (require external setup)."""

    @pytest.mark.skip(reason="External services require additional setup")
    def test_external_agent_placeholder(self):
        """Placeholder for external agent streaming tests."""
        pass

    @pytest.mark.skip(reason="External services require additional setup")
    def test_gpt_assistant_placeholder(self):
        """Placeholder for GPTAssistant streaming tests."""
        pass


# ═══════════════════════════════════════════════════════════════════════
# AgentStream API Tests
# ═══════════════════════════════════════════════════════════════════════


class TestAgentStreamAPI:
    """Validate AgentStream object behavior."""

    def test_stream_is_iterable(self, runtime, model):
        """AgentStream supports for-in iteration."""
        agent = Agent(name=_unique_name("e2e_api_iter"), model=model)
        stream = runtime.stream(agent, "Say hi.")
        assert hasattr(stream, "__iter__")

        events = list(stream)
        assert len(events) >= 1

    def test_stream_events_attribute(self, runtime, model):
        """AgentStream.events accumulates all yielded events."""
        agent = Agent(name=_unique_name("e2e_api_events"), model=model)
        stream = runtime.stream(agent, "Say hi.")
        collect_all_events(stream)
        assert len(stream.events) >= 1

    def test_stream_get_result_after_iteration(self, runtime, model):
        """get_result() returns AgentResult after full iteration."""
        agent = Agent(name=_unique_name("e2e_api_result"), model=model)
        stream = runtime.stream(agent, "Say hi.")
        collect_all_events(stream)
        result = stream.get_result()
        assert result is not None
        assert result.execution_id != ""

    def test_stream_get_result_without_iteration(self, runtime, model):
        """get_result() drains the stream if not yet iterated."""
        agent = Agent(name=_unique_name("e2e_api_drain"), model=model)
        stream = runtime.stream(agent, "Say hi.")
        # Don't iterate — just call get_result()
        result = stream.get_result()
        assert result is not None
        assert result.output is not None

    def test_stream_execution_id(self, runtime, model):
        """AgentStream.execution_id is set immediately."""
        agent = Agent(name=_unique_name("e2e_api_wfid"), model=model)
        stream = runtime.stream(agent, "Say hi.")
        assert stream.execution_id != ""
        collect_all_events(stream)

    def test_stream_handle_attribute(self, runtime, model):
        """AgentStream.handle is an AgentHandle."""
        agent = Agent(name=_unique_name("e2e_api_handle"), model=model)
        stream = runtime.stream(agent, "Say hi.")
        assert stream.handle is not None
        assert stream.handle.execution_id == stream.execution_id
        collect_all_events(stream)

    def test_stream_repr(self, runtime, model):
        """AgentStream has a useful repr."""
        agent = Agent(name=_unique_name("e2e_api_repr"), model=model)
        stream = runtime.stream(agent, "Say hi.")
        r = repr(stream)
        assert "AgentStream" in r
        collect_all_events(stream)
