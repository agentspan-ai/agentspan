#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""118 — Adaptive loop: travel planner that iterates inside a single agent execution.

ONE runtime.run() call. ONE execution ID. The agent loops inside that
single execution — calling validate_itinerary() repeatedly until all
constraints pass or max_turns is reached.

How it works:
  1. The agent generates an itinerary (JSON in its response).
  2. It calls validate_itinerary(json) — a deterministic tool, no LLM.
  3. If validation fails, the tool returns the exact failure messages.
  4. The agent fixes the issues and calls validate_itinerary() again.
  5. Loop continues inside the SAME execution until "ALL PASSED".

The LLM drives the retry loop; validation is purely deterministic.
Every tool call (each attempt + verdict) is logged under one execution
ID and visible in the UI at http://localhost:6767.

This is the correct Agentspan adaptive loop pattern — not Python
coordinating multiple runtime.run() calls, but the agent itself
iterating within a single durable server-side execution.

Constraints verified by the tool (pure Python — no LLM judge):
  1. Exactly 3 days, 3 activities each (morning/afternoon/evening).
  2. Daily total ≤ DAILY_BUDGET.
  3. Daily total ≥ MIN_DAILY_SPEND (can't be all free).
  4. At least 1 free/cheap activity per day (cost ≤ FREE_THRESHOLD).
  5. At least 1 paid experience per day (cost ≥ MIN_PAID_COST).
  6. Evening must be the most expensive slot each day.

Usage:
    agentspan server start
    export OPENAI_API_KEY=sk-...
    uv run python3 118_adaptive_loop_showcase.py "Tokyo"
    uv run python3 118_adaptive_loop_showcase.py "Paris" --budget 60
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

from conductor.ai.agents import Agent, AgentRuntime, tool

# ── Constraints ───────────────────────────────────────────────────────────────

DAILY_BUDGET: int = int(os.environ.get("DAILY_BUDGET", "75"))
FREE_THRESHOLD: int = 5    # cost ≤ this counts as "free/cheap"
MIN_PAID_COST: int = 15    # at least one activity per day must cost ≥ this
MIN_DAILY_SPEND: int = 20  # each day must spend at least this much
NUM_DAYS: int = 3
MODEL: str = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini")


# ── Validation tool (deterministic — no LLM) ─────────────────────────────────

@tool
def validate_itinerary(itinerary_json: str) -> str:
    """Check the itinerary against all budget and structure constraints.

    Returns "ALL PASSED" when every constraint is satisfied, or a detailed
    list of failures so the agent knows exactly what to fix.

    This tool is 100% deterministic — no LLM involved.
    """
    # Accept either a JSON string or an already-parsed dict.
    if isinstance(itinerary_json, dict):
        data: dict[str, Any] = itinerary_json
    else:
        try:
            data = json.loads(str(itinerary_json).strip())
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", str(itinerary_json), re.DOTALL)
            if not m:
                return "INVALID JSON — respond with a valid JSON object."
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                return "INVALID JSON — respond with a valid JSON object."

    failures: list[str] = []
    days: list[dict] = data.get("days", [])

    if len(days) != NUM_DAYS:
        failures.append(f"Need exactly {NUM_DAYS} days, got {len(days)}.")

    for day_data in days:
        n = day_data.get("day", "?")
        acts = day_data.get("activities", [])

        if len(acts) != 3:
            failures.append(f"Day {n}: need 3 activities (morning/afternoon/evening), got {len(acts)}.")
            continue

        missing = [a.get("name", "?") for a in acts if "cost_usd" not in a]
        if missing:
            failures.append(f"Day {n}: missing cost_usd on {missing}.")
            continue

        total = sum(a["cost_usd"] for a in acts)
        if total > DAILY_BUDGET:
            failures.append(f"Day {n}: total ${total} exceeds daily budget of ${DAILY_BUDGET}.")
        if total < MIN_DAILY_SPEND:
            failures.append(f"Day {n}: total ${total} is under minimum spend of ${MIN_DAILY_SPEND}.")

        free_ct = sum(1 for a in acts if a["cost_usd"] <= FREE_THRESHOLD)
        if free_ct == 0:
            failures.append(
                f"Day {n}: needs at least 1 free/cheap activity (cost ≤ ${FREE_THRESHOLD})."
            )

        paid_ct = sum(1 for a in acts if a["cost_usd"] >= MIN_PAID_COST)
        if paid_ct == 0:
            failures.append(
                f"Day {n}: needs at least 1 paid experience (cost ≥ ${MIN_PAID_COST})."
            )

        by_slot = {a["time"]: a["cost_usd"] for a in acts}
        eve = by_slot.get("evening", 0)
        other_max = max(by_slot.get("morning", 0), by_slot.get("afternoon", 0))
        if eve < other_max:
            failures.append(
                f"Day {n}: evening (${eve}) must be the priciest slot "
                f"— currently morning/afternoon has a ${other_max} activity."
            )

    if failures:
        return "CONSTRAINTS FAILED — fix these issues:\n" + "\n".join(
            f"  • {f}" for f in failures
        )
    return "ALL PASSED"


# ── Agent ─────────────────────────────────────────────────────────────────────

INSTRUCTIONS = f"""You are a travel planner that iterates until your itinerary passes validation.

Workflow (repeat until validate_itinerary returns "ALL PASSED"):
  1. Draft a {NUM_DAYS}-day itinerary as a JSON object.
  2. Call validate_itinerary() with that JSON.
  3. If it returns failures, fix every listed issue and call validate_itinerary() again.
  4. Stop only when validate_itinerary() returns "ALL PASSED".

JSON format:
{{
  "destination": "...",
  "days": [
    {{
      "day": 1,
      "activities": [
        {{"time": "morning",   "name": "...", "cost_usd": 0}},
        {{"time": "afternoon", "name": "...", "cost_usd": 20}},
        {{"time": "evening",   "name": "...", "cost_usd": 35}}
      ]
    }}
  ]
}}

Rules the validator enforces:
- Exactly 3 days, exactly 3 activities each.
- Daily total ≤ ${DAILY_BUDGET}.
- Daily total ≥ ${MIN_DAILY_SPEND} (no all-free days).
- At least 1 activity per day with cost ≤ ${FREE_THRESHOLD} (free/cheap slot).
- At least 1 activity per day with cost ≥ ${MIN_PAID_COST} (real experience).
- Evening must be the most expensive slot each day.
"""

agent = Agent(
    name="travel_planner_loop",
    model=MODEL,
    instructions=INSTRUCTIONS,
    tools=[validate_itinerary],
    max_turns=12,
)


# ── Run ───────────────────────────────────────────────────────────────────────

def main(destination: str) -> None:
    print(f"Planning {NUM_DAYS}-day trip to {destination}")
    print(f"Budget: ${DAILY_BUDGET}/day  |  Model: {MODEL}\n")

    with AgentRuntime() as runtime:
        result = runtime.run(agent, f"Plan a {NUM_DAYS}-day trip to {destination}.")

    print(f"Status:       {result.status}")
    print(f"Execution ID: {result.execution_id}")
    print(f"View at:      http://localhost:6767/execution/{result.execution_id}")
    print(f"Turns used:   {result.turns_used if hasattr(result, 'turns_used') else 'see UI'}")

    # Show the final itinerary
    raw = (result.output or {}).get("result") or str(result.output)
    if isinstance(raw, dict):
        data = raw
    else:
        m = re.search(r"\{.*\}", str(raw), re.DOTALL)
        data = json.loads(m.group()) if m else None

    if data and "days" in data:
        print()
        total = sum(a["cost_usd"] for d in data["days"] for a in d["activities"])
        print(f"Destination: {data.get('destination', destination)}  |  Total: ${total}")
        for day_data in data["days"]:
            print(f"\n  Day {day_data['day']}:")
            for act in day_data["activities"]:
                cost = f"${act['cost_usd']}" if act["cost_usd"] > 0 else "free"
                print(f"    {act['time']:12s}  {act['name']}  ({cost})")


if __name__ == "__main__":
    destination = sys.argv[1] if len(sys.argv) > 1 else "Tokyo"
    main(destination)
