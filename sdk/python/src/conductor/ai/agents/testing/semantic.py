# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Semantic assertions using an LLM judge.

Requires ``litellm`` (optional dependency).  Install with::

    pip install agentspan[testing]

Usage::

    from conductor.ai.agents.testing import assert_output_satisfies

    assert_output_satisfies(
        result,
        criterion="The output should contain weather information for NYC",
        model="anthropic/claude-sonnet-4-6",
    )
"""

from __future__ import annotations

from conductor.ai.agents.result import AgentResult


def assert_output_satisfies(
    result: AgentResult,
    criterion: str,
    *,
    model: str = "anthropic/claude-sonnet-4-6",
    threshold: float = 0.7,
) -> None:
    """Assert that the agent output semantically satisfies a criterion.

    Uses an LLM judge to evaluate the output against the criterion.  The judge
    returns a score from 0 to 1; the assertion passes if the score meets the
    *threshold*.

    Args:
        result: The agent execution result.
        criterion: A natural-language description of what the output should
            satisfy.
        model: The LLM to use as judge (in ``"provider/model"`` format).
        threshold: Minimum score (0-1) for the assertion to pass.

    Raises:
        ImportError: If ``litellm`` is not installed.
        AssertionError: If the output does not satisfy the criterion.
    """
    try:
        import litellm
    except ImportError:
        raise ImportError(
            "litellm is required for semantic assertions.\n"
            "Install it with: pip install agentspan[testing]"
        )

    output = str(result.output) if result.output is not None else ""

    response = litellm.completion(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an evaluation judge. Given an agent's output and a "
                    "criterion, respond with ONLY a JSON object: "
                    '{"score": <float 0-1>, "reason": "<brief explanation>"}. '
                    "Score 1.0 means the output fully satisfies the criterion. "
                    "Score 0.0 means it completely fails."
                ),
            },
            {
                "role": "user",
                "content": (f"Criterion: {criterion}\n\nAgent output:\n{output}"),
            },
        ],
        temperature=0,
    )

    import json

    raw = response.choices[0].message.content.strip()
    try:
        verdict = json.loads(raw)
        score = float(verdict.get("score", 0))
        reason = verdict.get("reason", "")
    except (json.JSONDecodeError, ValueError, TypeError):
        raise AssertionError(f"LLM judge returned unparseable response: {raw}")

    if score < threshold:
        preview = output[:200] + ("..." if len(output) > 200 else "")
        raise AssertionError(
            f"Output does not satisfy criterion (score={score:.2f}, "
            f"threshold={threshold:.2f}).\n"
            f"Criterion: {criterion}\n"
            f"Reason: {reason}\n"
            f"Output: {preview}"
        )
