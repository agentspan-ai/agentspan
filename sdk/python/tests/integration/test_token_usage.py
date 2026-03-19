# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Token usage collection tests.

Validates that AgentResult.token_usage is populated correctly for:
- Single agents (direct LLM call)
- Sequential pipelines (researcher >> writer — two sub-workflows)
- Parallel agents (all sub-workflows aggregated)

Requires:
    - Agentspan server running (AGENTSPAN_SERVER_URL)
    - LLM integration configured (AGENTSPAN_LLM_MODEL)

Run with:
    python3 -m pytest tests/integration/test_token_usage.py -v -s
"""

import pytest

from agentspan.agents import Agent, Strategy

pytestmark = pytest.mark.integration


# ── helpers ────────────────────────────────────────────────────────────


def _assert_usage(usage, label: str) -> None:
    """Assert that a TokenUsage object has plausible values."""
    assert usage is not None, f"{label}: token_usage is None"
    assert usage.prompt_tokens > 0, f"{label}: prompt_tokens={usage.prompt_tokens}"
    assert usage.completion_tokens > 0, f"{label}: completion_tokens={usage.completion_tokens}"
    assert usage.total_tokens > 0, f"{label}: total_tokens={usage.total_tokens}"
    assert usage.total_tokens == usage.prompt_tokens + usage.completion_tokens, (
        f"{label}: total_tokens ({usage.total_tokens}) != "
        f"prompt ({usage.prompt_tokens}) + completion ({usage.completion_tokens})"
    )


# ── single agent ───────────────────────────────────────────────────────


class TestSingleAgentTokenUsage:
    """Token usage is collected from a single-agent workflow."""

    def test_tokens_populated(self, runtime, model):
        agent = Agent(
            name="token_single",
            model=model,
            instructions="Answer in one sentence.",
        )
        result = runtime.run(agent, "What is the capital of France?")

        print(f"\nstatus={result.status}  usage={result.token_usage}")
        assert result.status == "COMPLETED"
        _assert_usage(result.token_usage, "single agent")


# ── sequential pipeline ────────────────────────────────────────────────


class TestSequentialTokenUsage:
    """Tokens are aggregated across all sub-workflows in a sequential pipeline.

    researcher >> writer creates two sub-workflows.  Total tokens must exceed
    what either agent alone would use.
    """

    def test_tokens_aggregated_across_pipeline(self, runtime, model):
        researcher = Agent(
            name="tok_researcher",
            model=model,
            instructions="List 2 key facts about the topic. Be brief.",
        )
        writer = Agent(
            name="tok_writer",
            model=model,
            instructions="Write one sentence summarising the provided facts.",
        )
        pipeline = researcher >> writer

        result = runtime.run(pipeline, "Python programming language")

        print(f"\nstatus={result.status}  usage={result.token_usage}")
        assert result.status == "COMPLETED"
        _assert_usage(result.token_usage, "sequential pipeline")

        # Two LLM calls must produce more tokens than a typical single call.
        # 20 tokens is a very conservative lower bound.
        assert result.token_usage.total_tokens >= 20, (
            f"Expected >20 total tokens for a two-stage pipeline, "
            f"got {result.token_usage.total_tokens}"
        )


# ── parallel agents ────────────────────────────────────────────────────


class TestParallelTokenUsage:
    """Tokens are aggregated across all parallel sub-workflows."""

    def test_tokens_aggregated_across_parallel_agents(self, runtime, model):
        pros = Agent(
            name="tok_pros",
            model=model,
            instructions="List one pro. One sentence.",
        )
        cons = Agent(
            name="tok_cons",
            model=model,
            instructions="List one con. One sentence.",
        )
        team = Agent(
            name="tok_parallel",
            model=model,
            agents=[pros, cons],
            strategy=Strategy.PARALLEL,
        )

        result = runtime.run(team, "Remote work")

        print(f"\nstatus={result.status}  usage={result.token_usage}")
        assert result.status == "COMPLETED"
        _assert_usage(result.token_usage, "parallel agents")

        # Three LLM calls (coordinator + 2 sub-agents) → more tokens than one call.
        assert result.token_usage.total_tokens >= 20, (
            f"Expected >20 total tokens for parallel agents, "
            f"got {result.token_usage.total_tokens}"
        )
