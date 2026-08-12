"""Shared helpers for e2e tests."""

from __future__ import annotations


def assert_output_quality(output: str, min_length: int = 100):
    """Assert the agent produced meaningful output, not failure filler."""
    assert output, "Agent produced no output"
    assert len(output) > min_length, f"Output too short ({len(output)} chars)"

    failure_patterns = [
        "unable to find",
        "could not find",
        "no information available",
        "i don't have access",
        "cannot access",
        "i was unable",
        "no results found",
        "failed to retrieve",
    ]
    lower = output.lower()
    for pattern in failure_patterns:
        assert pattern not in lower, (
            f"Agent failed to accomplish goal — output contains '{pattern}':\n"
            f"{output[:300]}"
        )
