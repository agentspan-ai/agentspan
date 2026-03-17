"""LLM judge calls, baseline comparison, and confidence computation."""

from __future__ import annotations

import json
import sys
import warnings
from dataclasses import dataclass

from .config import Settings


def _validate_judge_response(result: dict) -> tuple[int, str]:
    """Clamp score 1-5, warn on malformed."""
    score = result.get("score")
    reason = result.get("reason", result.get("error", ""))
    if score is None:
        warnings.warn(f"Judge returned no score: {result}")
        return 0, str(reason)
    try:
        score = int(score)
    except (TypeError, ValueError):
        warnings.warn(f"Judge returned non-integer score: {score}")
        return 0, str(reason)
    if score < 1 or score > 5:
        warnings.warn(f"Judge score {score} out of range, clamping to 1-5")
        score = max(1, min(5, score))
    return score, str(reason)


def call_judge(settings: Settings, prompt: str) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        print("ERROR: openai package not installed. uv add openai", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model=settings.judge_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=200,
        response_format={"type": "json_object"},
    )
    text = resp.choices[0].message.content.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": text}


def judge_individual(settings: Settings, prompt: str, output: str) -> tuple[int, str]:
    max_chars = settings.judge_max_output_chars
    judge_prompt = f"""You are evaluating an AI agent's output. The agent was given this task:
"{prompt}"

The agent produced this output:
"{output[:max_chars]}"

Rate the output on a scale of 1-5:
1 = Completely wrong, irrelevant, or empty
2 = Partially relevant but mostly incorrect or incomplete
3 = Relevant but missing key elements
4 = Good response, addresses the task well
5 = Excellent, fully addresses the task

Respond with ONLY a JSON object: {{"score": N, "reason": "brief explanation"}}"""

    result = call_judge(settings, judge_prompt)
    return _validate_judge_response(result)


def judge_comparison(
    settings: Settings, prompt: str, baseline_output: str, candidate_output: str
) -> tuple[int, str]:
    """Compare candidate output against baseline, scored 1-5 on task correctness."""
    max_chars = settings.judge_max_output_chars
    judge_prompt = f"""You are comparing two AI agent outputs for the same task. The task was:
"{prompt}"

BASELINE output:
"{baseline_output[:max_chars]}"

CANDIDATE output:
"{candidate_output[:max_chars]}"

Rate the CANDIDATE relative to the BASELINE on task correctness (1-5):
5 = Both correctly address the task, candidate equally valid
4 = Candidate addresses task well, minor completeness differences
3 = Candidate partially addresses task, misses key elements baseline covered
2 = Candidate attempts task but significant parts wrong
1 = Candidate fails the task or irrelevant

Different-but-valid approaches should score high. Judge task correctness, not surface similarity.

Respond with ONLY a JSON object: {{"score": N, "reason": "brief explanation"}}"""

    result = call_judge(settings, judge_prompt)
    return _validate_judge_response(result)


@dataclass
class JudgeState:
    """Mutable state tracked across judge calls."""

    call_count: int = 0
    cache_hits: int = 0
