"""LLM judge calls, baseline comparison, and confidence computation."""

from __future__ import annotations

import json
import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

from .config import MODELS, Settings
from .parsing import extract_prompt, load_raw_output
from .persistence import compute_output_hash, update_last_run_judge


def _safe_int(val: object) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


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
    """Mutable state tracked across judge_row() calls."""

    call_count: int = 0
    cache_hits: int = 0


def judge_row(
    row: dict,
    settings: Settings,
    outputs_dir: Path,
    providers: dict[str, str],
    prev_last_run: dict,
    last_run: dict,
    state: JudgeState,
    baseline: str | None = None,
    skip_judged: bool = False,
) -> list[str]:
    """Score one CSV row: individual + baseline. Returns display parts list."""
    example = row["example"]
    max_calls = settings.max_judge_calls
    rate_limit = settings.judge_rate_limit

    statuses = {p: row.get(f"{p}_status", "") for p in providers}
    completed = {p for p, s in statuses.items() if s == "COMPLETED"}

    if not completed:
        row["confidence"] = compute_confidence(row, providers)
        return [f"SKIP ({' '.join(f'{p}={s}' for p, s in statuses.items())})"]

    prompt = extract_prompt(example)

    prev_entry = prev_last_run.get("examples", {}).get(example, {})
    prev_hashes = prev_entry.get("output_hashes", {})
    prev_scores = prev_entry.get("judge_scores", {})

    score_parts: list[str] = []
    current_hashes: dict[str, str] = {}
    current_scores: dict[str, int] = {}

    for provider in providers:
        if provider not in completed:
            score_parts.append(f"{provider}=SKIP")
            continue

        output = load_raw_output(outputs_dir, example, provider)
        output_hash = compute_output_hash(output)
        current_hashes[provider] = output_hash

        # Skip if already judged
        if skip_judged and row.get(f"{provider}_judge_score"):
            current_scores[provider] = int(row[f"{provider}_judge_score"])
            score_parts.append(f"{provider}={row[f'{provider}_judge_score']}/5*")
            continue

        # Output hash cache
        if (
            prev_hashes.get(provider) == output_hash
            and prev_scores.get(provider)
            and not skip_judged
        ):
            cached_score = int(prev_scores[provider])
            row[f"{provider}_judge_score"] = cached_score
            row[f"{provider}_judge_reason"] = "cached (output unchanged)"
            current_scores[provider] = cached_score
            score_parts.append(f"{provider}={cached_score}/5$")
            state.cache_hits += 1
            continue

        if max_calls > 0 and state.call_count >= max_calls:
            score_parts.append(f"{provider}=BUDGET")
            continue

        if state.call_count > 0 and rate_limit > 0:
            time.sleep(rate_limit)

        score, reason = judge_individual(settings, prompt, output)
        row[f"{provider}_judge_score"] = score
        row[f"{provider}_judge_reason"] = reason
        current_scores[provider] = score
        score_parts.append(f"{provider}={score}/5")
        state.call_count += 1

    # Baseline comparison
    if baseline and baseline in completed:
        baseline_output = load_raw_output(outputs_dir, example, baseline)
        for provider in providers:
            if provider == baseline or provider not in completed:
                continue
            if skip_judged and row.get(f"{provider}_baseline_score"):
                continue
            if max_calls > 0 and state.call_count >= max_calls:
                break
            if state.call_count > 0 and rate_limit > 0:
                time.sleep(rate_limit)

            candidate_output = load_raw_output(outputs_dir, example, provider)
            bscore, breason = judge_comparison(settings, prompt, baseline_output, candidate_output)
            row[f"{provider}_baseline_score"] = bscore
            row[f"{provider}_baseline_reason"] = breason
            score_parts.append(f"{provider}_vs_{baseline}={bscore}/5")
            state.call_count += 1

    row["confidence"] = compute_confidence(row, providers)
    update_last_run_judge(last_run, example, current_scores, current_hashes)
    score_parts.append(f"[{row['confidence']}]")
    return score_parts


def compute_confidence(row: dict, models: dict[str, str] | None = None) -> str:
    providers = models or MODELS
    statuses = {p: row.get(f"{p}_status", "") for p in providers}
    completed = [p for p, s in statuses.items() if s == "COMPLETED"]

    if not completed:
        return "N/A"
    if len(completed) < len(providers):
        return "LOW"

    scores = {p: _safe_int(row.get(f"{p}_judge_score")) for p in providers}
    if any(s <= 2 for s in scores.values()):
        return "LOW"

    # Baseline scores — any <= 2 means LOW
    baseline_scores = [
        _safe_int(row.get(f"{p}_baseline_score"))
        for p in providers
        if row.get(f"{p}_baseline_score")
    ]
    if any(s <= 2 for s in baseline_scores):
        return "LOW"

    if all(s >= 4 for s in scores.values()):
        tool_counts = {p: _safe_int(row.get(f"{p}_tool_calls")) for p in providers}
        if len(set(tool_counts.values())) > 1:
            return "MEDIUM"
        return "HIGH"

    return "MEDIUM"
