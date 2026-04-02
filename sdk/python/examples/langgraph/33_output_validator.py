# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Output Validator — validate LLM output and retry until it meets criteria.

Demonstrates:
    - Generating structured output (JSON) and validating it against a schema
    - Looping back to regenerate if validation fails
    - Tracking validation attempts in state to prevent infinite loops
    - Practical use case: ensuring the LLM always returns valid JSON

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import json
from typing import TypedDict, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

MAX_ATTEMPTS = 4

REQUIRED_FIELDS = {"name", "age", "occupation", "hobby"}


class State(TypedDict):
    prompt: str
    raw_output: str
    validation_error: Optional[str]
    attempts: int
    valid_data: Optional[dict]


def generate_profile(state: State) -> State:
    attempt = state.get("attempts", 0) + 1
    error_hint = ""
    if state.get("validation_error"):
        error_hint = f"\n\nPrevious attempt failed validation: {state['validation_error']}. Please fix this."

    response = llm.invoke([
        SystemMessage(
            content=(
                "Generate a fictional person profile as a JSON object with exactly these fields: "
                "name (string), age (integer), occupation (string), hobby (string). "
                "Return ONLY valid JSON — no markdown, no backticks, no explanation."
                + error_hint
            )
        ),
        HumanMessage(content=state["prompt"]),
    ])
    return {"raw_output": response.content.strip(), "attempts": attempt}


def validate_output(state: State) -> State:
    raw = state.get("raw_output", "")
    # Strip markdown code fences if present
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError as e:
        return {"validation_error": f"JSON parse error: {e}", "valid_data": None}

    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        return {"validation_error": f"Missing fields: {missing}", "valid_data": None}

    if not isinstance(data.get("age"), int):
        return {"validation_error": "Field 'age' must be an integer", "valid_data": None}

    return {"validation_error": None, "valid_data": data}


def should_retry(state: State) -> str:
    if state.get("validation_error") and state.get("attempts", 0) < MAX_ATTEMPTS:
        return "retry"
    return "done"


def finalize(state: State) -> State:
    if state.get("valid_data"):
        d = state["valid_data"]
        summary = (
            f"Valid profile generated:\n"
            f"  Name:       {d['name']}\n"
            f"  Age:        {d['age']}\n"
            f"  Occupation: {d['occupation']}\n"
            f"  Hobby:      {d['hobby']}\n"
            f"  (Attempts:  {state.get('attempts', 1)})"
        )
        return {"raw_output": summary}
    return {"raw_output": f"Failed to generate valid output after {state.get('attempts', 1)} attempts."}


builder = StateGraph(State)
builder.add_node("generate", generate_profile)
builder.add_node("validate", validate_output)
builder.add_node("finalize", finalize)

builder.add_edge(START, "generate")
builder.add_edge("generate", "validate")
builder.add_conditional_edges("validate", should_retry, {"retry": "generate", "done": "finalize"})
builder.add_edge("finalize", END)

graph = builder.compile(name="output_validator_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "Create a fictional software engineer from Japan")
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.33_output_validator
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
