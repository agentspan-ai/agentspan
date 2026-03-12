"""LLM judge calls and confidence computation."""

from __future__ import annotations

import json
import re
import sys

from .config import MODELS, Settings


def _safe_int(val: object) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def call_judge(settings: Settings, prompt: str) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        print("ERROR: openai package not installed. pip install openai", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model=settings.judge_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=200,
    )
    text = resp.choices[0].message.content.strip()

    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": text}


def judge_individual(settings: Settings, prompt: str, output: str) -> tuple[int, str]:
    judge_prompt = f"""You are evaluating an AI agent's output. The agent was given this task:
"{prompt}"

The agent produced this output:
"{output[:3000]}"

Rate the output on a scale of 1-5:
1 = Completely wrong, irrelevant, or empty
2 = Partially relevant but mostly incorrect or incomplete
3 = Relevant but missing key elements
4 = Good response, addresses the task well
5 = Excellent, fully addresses the task

Respond with ONLY a JSON object: {{"score": N, "reason": "brief explanation"}}"""

    result = call_judge(settings, judge_prompt)
    return result.get("score", 0), result.get("reason", result.get("error", ""))


def compute_confidence(row: dict) -> str:
    statuses = {p: row.get(f"{p}_status", "") for p in MODELS}
    completed = [p for p, s in statuses.items() if s == "COMPLETED"]

    if not completed:
        return "N/A"
    if len(completed) < len(MODELS):
        return "LOW"

    scores = {p: _safe_int(row.get(f"{p}_judge_score")) for p in MODELS}
    if any(s <= 2 for s in scores.values()):
        return "LOW"
    if all(s >= 4 for s in scores.values()):
        tool_counts = {p: _safe_int(row.get(f"{p}_tool_calls")) for p in MODELS}
        if len(set(tool_counts.values())) > 1:
            return "MEDIUM"
        return "HIGH"

    return "MEDIUM"
