#!/usr/bin/env python3
"""
02 — Tool Assertion Deep-Dive
==============================

Thorough testing of tool usage: argument validation, call ordering,
exact tool sets, regex output matching, and output type checking.

Covers:
  - assert_tool_called_with (subset arg matching)
  - assert_tool_call_order (subsequence ordering)
  - assert_tools_used_exactly (set equality)
  - assert_output_matches (regex)
  - assert_output_type (type checking)
  - assert_max_turns (turn budget)
  - assert_event_sequence (event ordering)

Run:
    pytest examples/mock_tests/02_tool_assertions.py -v
"""

import pytest

from agentspan.agents import Agent, tool
from agentspan.agents.result import EventType
from agentspan.agents.testing import (
    MockEvent,
    assert_event_sequence,
    assert_max_turns,
    assert_output_contains,
    assert_output_matches,
    assert_output_type,
    assert_tool_call_order,
    assert_tool_called_with,
    assert_tool_not_used,
    assert_tool_used,
    assert_tools_used_exactly,
    expect,
    mock_run,
)


# ── Tools ────────────────────────────────────────────────────────────


@tool
def search_products(query: str, max_results: int = 5) -> list:
    """Search the product catalog."""
    return [{"name": f"Product {i}", "price": 9.99 * i} for i in range(1, max_results + 1)]


@tool
def get_product_details(product_id: str) -> dict:
    """Get detailed info for a product."""
    return {"id": product_id, "name": "Widget", "stock": 42}


@tool
def add_to_cart(product_id: str, quantity: int) -> str:
    """Add a product to the shopping cart."""
    return f"Added {quantity}x {product_id} to cart"


@tool
def checkout(payment_method: str) -> dict:
    """Process checkout."""
    return {"order_id": "ORD-001", "status": "confirmed", "payment": payment_method}


# ── Agent ────────────────────────────────────────────────────────────

shop_agent = Agent(
    name="shop-assistant",
    model="openai/gpt-4o",
    instructions="Help customers find and purchase products.",
    tools=[search_products, get_product_details, add_to_cart, checkout],
)


# ── Tests ────────────────────────────────────────────────────────────


class TestToolArgValidation:
    """Verify tools are called with the expected arguments."""

    def test_exact_args(self):
        """Tool must be called with exactly these args."""
        result = mock_run(
            shop_agent,
            "Search for red shoes",
            events=[
                MockEvent.tool_call(
                    "search_products", args={"query": "red shoes", "max_results": 10}
                ),
                MockEvent.tool_result("search_products", result=[{"name": "Red Shoe"}]),
                MockEvent.done("I found Red Shoe for you."),
            ],
            auto_execute_tools=False,
        )

        assert_tool_called_with(
            result, "search_products", args={"query": "red shoes", "max_results": 10}
        )

    def test_subset_arg_match(self):
        """assert_tool_called_with does subset matching — extra args are OK."""
        result = mock_run(
            shop_agent,
            "Search for hats",
            events=[
                MockEvent.tool_call(
                    "search_products", args={"query": "hats", "max_results": 5}
                ),
                MockEvent.tool_result("search_products", result=[]),
                MockEvent.done("No hats found."),
            ],
            auto_execute_tools=False,
        )

        # Only check the query arg — max_results is ignored
        assert_tool_called_with(result, "search_products", args={"query": "hats"})

    def test_wrong_args_fails(self):
        """Mismatched args raise AssertionError."""
        result = mock_run(
            shop_agent,
            "Search for boots",
            events=[
                MockEvent.tool_call("search_products", args={"query": "boots"}),
                MockEvent.tool_result("search_products", result=[]),
                MockEvent.done("No boots."),
            ],
            auto_execute_tools=False,
        )

        with pytest.raises(AssertionError):
            assert_tool_called_with(
                result, "search_products", args={"query": "sneakers"}
            )


class TestToolCallOrdering:
    """Verify tools are called in the expected sequence."""

    def test_full_shopping_flow(self):
        """Search → details → add to cart → checkout must happen in order."""
        result = mock_run(
            shop_agent,
            "Find me a widget and buy it",
            events=[
                MockEvent.tool_call("search_products", args={"query": "widget"}),
                MockEvent.tool_result("search_products", result=[{"id": "W-1"}]),
                MockEvent.tool_call("get_product_details", args={"product_id": "W-1"}),
                MockEvent.tool_result(
                    "get_product_details", result={"id": "W-1", "stock": 42}
                ),
                MockEvent.tool_call(
                    "add_to_cart", args={"product_id": "W-1", "quantity": 1}
                ),
                MockEvent.tool_result("add_to_cart", result="Added 1x W-1 to cart"),
                MockEvent.tool_call("checkout", args={"payment_method": "credit_card"}),
                MockEvent.tool_result(
                    "checkout", result={"order_id": "ORD-001", "status": "confirmed"}
                ),
                MockEvent.done("Your order ORD-001 is confirmed!"),
            ],
            auto_execute_tools=False,
        )

        # Subsequence check: these must appear in this order
        assert_tool_call_order(
            result, ["search_products", "get_product_details", "add_to_cart", "checkout"]
        )

    def test_partial_order(self):
        """Subsequence — only check that search comes before checkout."""
        result = mock_run(
            shop_agent,
            "Quick buy",
            events=[
                MockEvent.tool_call("search_products", args={"query": "gadget"}),
                MockEvent.tool_result("search_products", result=[{"id": "G-1"}]),
                MockEvent.tool_call("get_product_details", args={"product_id": "G-1"}),
                MockEvent.tool_result("get_product_details", result={"id": "G-1"}),
                MockEvent.tool_call("checkout", args={"payment_method": "paypal"}),
                MockEvent.tool_result("checkout", result={"order_id": "ORD-002"}),
                MockEvent.done("Done!"),
            ],
            auto_execute_tools=False,
        )

        # Only check partial order
        assert_tool_call_order(result, ["search_products", "checkout"])


class TestExactToolSet:
    """Verify the exact set of tools used (no more, no less)."""

    def test_exactly_these_tools(self):
        """Only search and details were used — nothing else."""
        result = mock_run(
            shop_agent,
            "Just browse products",
            events=[
                MockEvent.tool_call("search_products", args={"query": "all"}),
                MockEvent.tool_result("search_products", result=[{"id": "P-1"}]),
                MockEvent.tool_call("get_product_details", args={"product_id": "P-1"}),
                MockEvent.tool_result("get_product_details", result={"id": "P-1"}),
                MockEvent.done("Here's what I found."),
            ],
            auto_execute_tools=False,
        )

        assert_tools_used_exactly(result, ["search_products", "get_product_details"])

    def test_exact_set_fails_when_extra_tool_used(self):
        """Fails if an unexpected tool was also called."""
        result = mock_run(
            shop_agent,
            "Browse and buy",
            events=[
                MockEvent.tool_call("search_products", args={"query": "item"}),
                MockEvent.tool_result("search_products", result=[]),
                MockEvent.tool_call("checkout", args={"payment_method": "cash"}),
                MockEvent.tool_result("checkout", result={}),
                MockEvent.done("Done."),
            ],
            auto_execute_tools=False,
        )

        # Expects ONLY search_products — but checkout was also used
        with pytest.raises(AssertionError):
            assert_tools_used_exactly(result, ["search_products"])


class TestOutputAssertions:
    """Validate the final output content and type."""

    def test_output_regex(self):
        """Output matches a regex pattern."""
        result = mock_run(
            shop_agent,
            "Place my order",
            events=[
                MockEvent.done("Your order ORD-12345 has been confirmed."),
            ],
        )

        assert_output_matches(result, r"ORD-\d{5}")

    def test_output_type_string(self):
        """Output is a string."""
        result = mock_run(
            shop_agent,
            "Hello",
            events=[MockEvent.done("Hi there!")],
        )

        assert_output_type(result, str)

    def test_output_type_dict(self):
        """Output can be a structured dict."""
        result = mock_run(
            shop_agent,
            "Order summary",
            events=[
                MockEvent.done({"order_id": "ORD-001", "total": 29.99}),
            ],
        )

        assert_output_type(result, dict)
        assert_output_contains(result, "ORD-001")


class TestEventSequence:
    """Verify the order of event types in the execution trace."""

    def test_think_then_act(self):
        """Thinking → tool call → tool result → done."""
        result = mock_run(
            shop_agent,
            "Find a product",
            events=[
                MockEvent.thinking("I should search for products..."),
                MockEvent.tool_call("search_products", args={"query": "widget"}),
                MockEvent.tool_result("search_products", result=[]),
                MockEvent.done("No products found."),
            ],
            auto_execute_tools=False,
        )

        assert_event_sequence(
            result,
            [
                EventType.THINKING,
                EventType.TOOL_CALL,
                EventType.TOOL_RESULT,
                EventType.DONE,
            ],
        )

    def test_event_sequence_is_subsequence(self):
        """Sequence check is a subsequence — extra events in between are OK."""
        result = mock_run(
            shop_agent,
            "Buy something",
            events=[
                MockEvent.thinking("Let me search..."),
                MockEvent.tool_call("search_products", args={"query": "thing"}),
                MockEvent.tool_result("search_products", result=[{"id": "T-1"}]),
                MockEvent.thinking("Found one, let me add to cart..."),
                MockEvent.tool_call(
                    "add_to_cart", args={"product_id": "T-1", "quantity": 1}
                ),
                MockEvent.tool_result("add_to_cart", result="Added"),
                MockEvent.done("Added to cart!"),
            ],
            auto_execute_tools=False,
        )

        # Only check the tool calls — thinking events are skipped
        assert_event_sequence(
            result, [EventType.TOOL_CALL, EventType.TOOL_CALL, EventType.DONE]
        )


class TestTurnBudget:
    """Verify the agent doesn't exceed turn limits."""

    def test_within_budget(self):
        """Agent uses 2 tool calls — within budget of 5."""
        result = mock_run(
            shop_agent,
            "Quick search",
            events=[
                MockEvent.tool_call("search_products", args={"query": "shoes"}),
                MockEvent.tool_result("search_products", result=[]),
                MockEvent.tool_call("search_products", args={"query": "boots"}),
                MockEvent.tool_result("search_products", result=[]),
                MockEvent.done("No results."),
            ],
            auto_execute_tools=False,
        )

        assert_max_turns(result, 5)

    def test_over_budget_fails(self):
        """Agent exceeds the allowed turn count."""
        result = mock_run(
            shop_agent,
            "Keep searching",
            events=[
                MockEvent.tool_call("search_products", args={"query": "a"}),
                MockEvent.tool_result("search_products", result=[]),
                MockEvent.tool_call("search_products", args={"query": "b"}),
                MockEvent.tool_result("search_products", result=[]),
                MockEvent.tool_call("search_products", args={"query": "c"}),
                MockEvent.tool_result("search_products", result=[]),
                MockEvent.done("Gave up."),
            ],
            auto_execute_tools=False,
        )

        # Budget is 2, but agent used 3 tool calls
        with pytest.raises(AssertionError):
            assert_max_turns(result, 2)
