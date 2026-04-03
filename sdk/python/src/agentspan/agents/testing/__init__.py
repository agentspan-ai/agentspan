# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Agent correctness testing framework.

Provides composable assertions, mock execution, fluent API, and
record/replay for testing agent behavior without a live server.

Quick start::

    from agentspan.agents import Agent, tool
    from agentspan.agents.testing import mock_run, MockEvent, expect

    result = mock_run(agent, "Hello", events=[MockEvent.done("Hi!")])
    expect(result).completed().output_contains("Hi").no_errors()
"""

# Assertions
from agentspan.agents.testing.assertions import (
    assert_agent_ran,
    assert_event_sequence,
    assert_events_contain,
    assert_guardrail_failed,
    assert_guardrail_passed,
    assert_handoff_to,
    assert_max_turns,
    assert_no_errors,
    assert_output_contains,
    assert_output_matches,
    assert_output_type,
    assert_status,
    assert_tool_call_order,
    assert_tool_called_with,
    assert_tool_not_used,
    assert_tool_used,
    assert_tools_used_exactly,
)

# Eval runner
from agentspan.agents.testing.eval_runner import (
    CorrectnessEval,
    EvalCase,
    EvalCaseResult,
    EvalSuiteResult,
    capture_eval_case,
    eval_case_from_result,
)

# Fluent API
from agentspan.agents.testing.expect import AgentResultExpectation, expect

# Mock execution
from agentspan.agents.testing.mock import MockEvent, mock_run

# Record/replay
from agentspan.agents.testing.recording import record, replay

# Strategy validators
from agentspan.agents.testing.strategy_validators import (
    StrategyViolation,
    validate_strategy,
)

__all__ = [
    # Assertions
    "assert_tool_used",
    "assert_tool_not_used",
    "assert_tool_called_with",
    "assert_tool_call_order",
    "assert_tools_used_exactly",
    "assert_output_contains",
    "assert_output_matches",
    "assert_output_type",
    "assert_status",
    "assert_no_errors",
    "assert_events_contain",
    "assert_event_sequence",
    "assert_handoff_to",
    "assert_agent_ran",
    "assert_guardrail_passed",
    "assert_guardrail_failed",
    "assert_max_turns",
    # Fluent API
    "expect",
    "AgentResultExpectation",
    # Mock
    "mock_run",
    "MockEvent",
    # Recording
    "record",
    "replay",
    # Strategy validators
    "validate_strategy",
    "StrategyViolation",
    # Eval runner
    "CorrectnessEval",
    "EvalCase",
    "EvalCaseResult",
    "EvalSuiteResult",
    "eval_case_from_result",
    "capture_eval_case",
]
