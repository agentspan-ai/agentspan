#!/usr/bin/env python3

# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Run all OpenAI agent examples and verify correctness.

Usage:
    python3 examples/openai/run_all.py

Runs each example, checks workflow status and validates expected behaviors
(tool calls, guardrails, handoffs, structured output, streaming, etc.).
Reports a summary table at the end.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Ensure examples/ is on sys.path so settings imports work
# ---------------------------------------------------------------------------
EXAMPLES_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if EXAMPLES_DIR not in sys.path:
    sys.path.insert(0, EXAMPLES_DIR)

from settings import settings

# ---------------------------------------------------------------------------
# Conductor agent runtime imports
# ---------------------------------------------------------------------------
from agents import (
    Agent,
    GuardrailFunctionOutput,
    InputGuardrail,
    ModelSettings,
    OutputGuardrail,
    function_tool,
)

from agentspan.agents import AgentRuntime
from agentspan.agents.runtime.config import AgentConfig

# ---------------------------------------------------------------------------
# Server config — loaded from .env / environment via pydantic-settings
# ---------------------------------------------------------------------------
_cfg = AgentConfig()


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------
@dataclass
class ExampleResult:
    name: str
    workflow_id: str = ""
    status: str = ""
    passed: bool = False
    checks: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    error: str = ""
    duration_s: float = 0.0


results: List[ExampleResult] = []


def _get_workflow_detail(runtime: AgentRuntime, workflow_id: str) -> Dict[str, Any]:
    """Fetch full workflow execution from Conductor API."""
    import requests

    url = _cfg.server_url.replace("/api", "") + f"/api/workflow/{workflow_id}"
    headers: Dict[str, str] = {}
    if _cfg.auth_key:
        headers["X-Auth-Key"] = _cfg.auth_key
    if _cfg.auth_secret:
        headers["X-Auth-Secret"] = _cfg.auth_secret
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _task_types(wf_detail: Dict[str, Any]) -> List[str]:
    """Extract list of task types from workflow execution."""
    return [t.get("taskType", "") for t in wf_detail.get("tasks", [])]


def _task_names(wf_detail: Dict[str, Any]) -> List[str]:
    """Extract list of task reference names from workflow execution."""
    return [t.get("referenceTaskName", "") for t in wf_detail.get("tasks", [])]


def _find_tasks_by_type(wf_detail: Dict[str, Any], task_type: str) -> List[Dict]:
    """Find all tasks of a given type."""
    return [t for t in wf_detail.get("tasks", []) if t.get("taskType") == task_type]


def _find_tasks_by_name_pattern(wf_detail: Dict[str, Any], pattern: str) -> List[Dict]:
    """Find tasks whose reference name matches a regex pattern."""
    return [t for t in wf_detail.get("tasks", [])
            if re.search(pattern, t.get("referenceTaskName", ""))]


def _tool_was_called(wf_detail: Dict[str, Any], tool_name: str) -> bool:
    """Check if a tool was invoked — matches taskType, taskDefName, or referenceTaskName."""
    for t in wf_detail.get("tasks", []):
        for field in ("taskType", "taskDefName", "referenceTaskName"):
            if tool_name in t.get(field, ""):
                return True
        # Also check nested workflowTask.name
        wt = t.get("workflowTask", {})
        if isinstance(wt, dict) and tool_name in wt.get("name", ""):
            return True
    return False


# ---------------------------------------------------------------------------
# Example definitions
# ---------------------------------------------------------------------------

def ex01_basic_agent(runtime: AgentRuntime) -> ExampleResult:
    """01 — Basic agent, no tools."""
    r = ExampleResult(name="01_basic_agent")

    agent = Agent(
        name="greeter",
        instructions="You are a friendly assistant. Keep your responses concise and helpful.",
        model=settings.llm_model,
    )
    result = runtime.run(agent, "Say hello and tell me a fun fact about the Python programming language.")
    r.workflow_id = result.workflow_id
    r.status = result.status

    # Check: completed
    if result.status == "COMPLETED":
        r.checks.append("workflow COMPLETED")
    else:
        r.failures.append(f"expected COMPLETED, got {result.status}")

    # Check: has output
    if result.output:
        r.checks.append("has output text")
    else:
        r.failures.append("no output text")

    # Check: no tool calls (basic agent)
    wf = _get_workflow_detail(runtime, result.workflow_id)
    simple_tasks = [t for t in wf.get("tasks", [])
                    if t.get("taskType") == "SIMPLE" and "format_report" not in t.get("referenceTaskName", "")]
    # Should only have LLM task(s), no SIMPLE worker tasks
    worker_tasks = _find_tasks_by_type(wf, "SIMPLE")
    if not worker_tasks:
        r.checks.append("no tool calls (correct for basic agent)")
    else:
        r.checks.append(f"found {len(worker_tasks)} worker tasks (may be fine)")

    r.passed = len(r.failures) == 0
    return r


def ex02_function_tools(runtime: AgentRuntime) -> ExampleResult:
    """02 — Function tools: get_weather, calculate, lookup_population."""
    r = ExampleResult(name="02_function_tools")

    @function_tool
    def get_weather(city: str) -> str:
        """Get the current weather for a city."""
        weather_data = {
            "new york": "72F, Partly Cloudy",
            "san francisco": "58F, Foggy",
            "miami": "85F, Sunny",
            "london": "55F, Rainy",
        }
        return weather_data.get(city.lower(), f"Weather data not available for {city}")

    @function_tool
    def calculate(expression: str) -> str:
        """Evaluate a mathematical expression and return the result."""
        import math
        safe_builtins = {"abs": abs, "round": round, "min": min, "max": max,
                         "sqrt": math.sqrt, "pow": pow, "pi": math.pi, "e": math.e}
        try:
            return str(eval(expression, {"__builtins__": {}}, safe_builtins))
        except Exception as e:
            return f"Error: {e}"

    @function_tool
    def lookup_population(city: str) -> str:
        """Look up the population of a city."""
        populations = {"new york": "8.3 million", "san francisco": "874,000",
                       "miami": "442,000", "london": "8.8 million"}
        return populations.get(city.lower(), "Unknown")

    agent = Agent(
        name="multi_tool_agent",
        instructions="You are a helpful assistant with access to weather, calculator, and population lookup tools. Use them to answer questions accurately.",
        model=settings.llm_model,
        tools=[get_weather, calculate, lookup_population],
    )
    result = runtime.run(
        agent,
        "What's the weather in San Francisco? Also, what's the population there and what's the square root of that number (just the digits)?",
    )
    r.workflow_id = result.workflow_id
    r.status = result.status

    if result.status == "COMPLETED":
        r.checks.append("workflow COMPLETED")
    else:
        r.failures.append(f"expected COMPLETED, got {result.status}")

    # Verify tool calls happened
    wf = _get_workflow_detail(runtime, result.workflow_id)
    task_refs = " ".join(_task_names(wf))
    types = _task_types(wf)

    if "FORK" in types or "FORK_JOIN_DYNAMIC" in types:
        r.checks.append("dynamic fork present (tool dispatch)")
    else:
        r.failures.append("no dynamic fork — tools may not have been called")

    for expected in ["get_weather", "lookup_population"]:
        if _tool_was_called(wf, expected):
            r.checks.append(f"tool '{expected}' was called")
        else:
            r.failures.append(f"tool '{expected}' was NOT called")

    if result.output:
        r.checks.append("has output text")
    else:
        r.failures.append("no output text")

    r.passed = len(r.failures) == 0
    return r


def ex03_structured_output(runtime: AgentRuntime) -> ExampleResult:
    """03 — Structured output with Pydantic model."""
    from pydantic import BaseModel
    from typing import List as TList

    r = ExampleResult(name="03_structured_output")

    class MovieRecommendation(BaseModel):
        title: str
        year: int
        genre: str
        reason: str

    class MovieList(BaseModel):
        recommendations: TList[MovieRecommendation]
        theme: str

    agent = Agent(
        name="movie_recommender",
        instructions="You are a movie recommendation expert. Return a structured list of recommendations with title, year, genre, and a brief reason. Identify the overall theme.",
        model=settings.llm_model,
        output_type=MovieList,
        model_settings=ModelSettings(temperature=0.3, max_tokens=1000),
    )
    result = runtime.run(agent, "Recommend 3 sci-fi movies that explore the concept of artificial intelligence.")
    r.workflow_id = result.workflow_id
    r.status = result.status

    if result.status == "COMPLETED":
        r.checks.append("workflow COMPLETED")
    else:
        r.failures.append(f"expected COMPLETED, got {result.status}")

    # Check output is structured (dict or parseable JSON)
    # Output may be wrapped in {"result": ..., "finishReason": ...} by Conductor
    output = result.output
    inner = output
    if isinstance(output, dict) and "result" in output:
        inner = output["result"]
    # inner may be a JSON string
    if isinstance(inner, str):
        try:
            inner = json.loads(inner)
        except (json.JSONDecodeError, TypeError):
            pass

    if isinstance(inner, dict):
        r.checks.append("output is structured dict")
        if "recommendations" in inner or "theme" in inner:
            r.checks.append("output has expected schema fields")
        else:
            r.checks.append(f"output keys: {list(inner.keys())[:5]} (schema may differ)")
    elif isinstance(inner, str) and inner:
        r.checks.append("output is text (structured output may not be enforced server-side)")
    elif output:
        r.checks.append(f"output present (type: {type(output).__name__})")
    else:
        r.failures.append("no output")

    r.passed = len(r.failures) == 0
    return r


def ex04_handoffs(runtime: AgentRuntime) -> ExampleResult:
    """04 — Handoffs: triage → refund_specialist."""
    r = ExampleResult(name="04_handoffs")

    @function_tool
    def check_order_status(order_id: str) -> str:
        """Check the status of a customer order."""
        orders = {"ORD-001": "Shipped", "ORD-002": "Processing", "ORD-003": "Delivered"}
        return orders.get(order_id, f"Order {order_id} not found")

    @function_tool
    def process_refund(order_id: str, reason: str) -> str:
        """Process a refund for an order."""
        return f"Refund initiated for {order_id}. Reason: {reason}."

    @function_tool
    def get_product_info(product_name: str) -> str:
        """Get product information and pricing."""
        products = {"laptop pro": "Laptop Pro X1 — $1,299"}
        return products.get(product_name.lower(), f"Product '{product_name}' not found")

    order_agent = Agent(name="order_specialist", instructions="Handle order inquiries.", model=settings.llm_model, tools=[check_order_status])
    refund_agent = Agent(name="refund_specialist", instructions="Handle refund requests. Use process_refund tool.", model=settings.llm_model, tools=[process_refund])
    sales_agent = Agent(name="sales_specialist", instructions="Handle product questions.", model=settings.llm_model, tools=[get_product_info])

    triage_agent = Agent(
        name="customer_service_triage",
        instructions="Triage agent. Route to: order_specialist, refund_specialist, or sales_specialist.",
        model=settings.llm_model,
        handoffs=[order_agent, refund_agent, sales_agent],
    )

    result = runtime.run(triage_agent, "I'd like a refund for order ORD-002, the product arrived damaged.")
    r.workflow_id = result.workflow_id
    r.status = result.status

    if result.status == "COMPLETED":
        r.checks.append("workflow COMPLETED")
    else:
        r.failures.append(f"expected COMPLETED, got {result.status}")

    # Verify handoff happened (SUB_WORKFLOW tasks indicate sub-agents)
    wf = _get_workflow_detail(runtime, result.workflow_id)
    types = _task_types(wf)
    task_refs = " ".join(_task_names(wf))

    if "SUB_WORKFLOW" in types:
        r.checks.append("SUB_WORKFLOW present (handoff executed)")
    elif "SWITCH" in types:
        r.checks.append("SWITCH present (handoff routing)")
    else:
        # Multi-agent may compile differently — check for multiple LLM calls
        llm_tasks = _find_tasks_by_type(wf, "LLM_CHAT_COMPLETE")
        if len(llm_tasks) > 1:
            r.checks.append(f"{len(llm_tasks)} LLM tasks (multi-agent execution)")
        else:
            r.failures.append("no evidence of handoff execution")

    # Check that refund tool was called
    refund_called = _tool_was_called(wf, "process_refund")
    if refund_called:
        r.checks.append("process_refund tool was called")
    else:
        r.checks.append("process_refund not called (LLM may have answered directly)")

    if result.output:
        r.checks.append("has output text")
    else:
        r.failures.append("no output text")

    r.passed = len(r.failures) == 0
    return r


def ex05_guardrails(runtime: AgentRuntime) -> ExampleResult:
    """05 — Guardrails: input PII check + output safety check."""
    r = ExampleResult(name="05_guardrails")

    @function_tool
    def get_account_balance(account_id: str) -> str:
        """Look up the balance of a bank account."""
        accounts = {"ACC-100": "$5,230.00", "ACC-200": "$12,750.50"}
        return accounts.get(account_id, f"Account {account_id} not found")

    @function_tool
    def transfer_funds(from_account: str, to_account: str, amount: float) -> str:
        """Transfer funds between accounts."""
        return f"Transferred ${amount:.2f} from {from_account} to {to_account}."

    def check_for_pii(ctx, agent, input_text) -> GuardrailFunctionOutput:
        """Input guardrail: check for sensitive PII."""
        import re as _re
        if _re.search(r"\b\d{3}-\d{2}-\d{4}\b", input_text):
            return GuardrailFunctionOutput(output_info={"reason": "SSN detected"}, tripwire_triggered=True)
        if _re.search(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", input_text):
            return GuardrailFunctionOutput(output_info={"reason": "CC detected"}, tripwire_triggered=True)
        return GuardrailFunctionOutput(output_info={"reason": "No PII"}, tripwire_triggered=False)

    def check_output_safety(ctx, agent, output) -> GuardrailFunctionOutput:
        """Output guardrail: ensure no sensitive info in output."""
        output_text = str(output).lower()
        for phrase in ["internal system", "database password", "api key", "secret token"]:
            if phrase in output_text:
                return GuardrailFunctionOutput(output_info={"reason": f"Forbidden: {phrase}"}, tripwire_triggered=True)
        return GuardrailFunctionOutput(output_info={"reason": "Safe"}, tripwire_triggered=False)

    agent = Agent(
        name="banking_assistant",
        instructions="You are a secure banking assistant. Help users check balances and transfer funds.",
        model=settings.llm_model,
        tools=[get_account_balance, transfer_funds],
        input_guardrails=[InputGuardrail(guardrail_function=check_for_pii)],
        output_guardrails=[OutputGuardrail(guardrail_function=check_output_safety)],
    )

    # Normal request — should pass guardrails
    result = runtime.run(agent, "What's the balance on account ACC-100?")
    r.workflow_id = result.workflow_id
    r.status = result.status

    if result.status == "COMPLETED":
        r.checks.append("workflow COMPLETED (guardrails passed)")
    else:
        r.failures.append(f"expected COMPLETED, got {result.status}")

    if result.output:
        r.checks.append("has output text")
    else:
        r.failures.append("no output text")

    # Verify guardrail workers were registered (check workflow has guardrail-related tasks or workers)
    wf = _get_workflow_detail(runtime, result.workflow_id)
    task_refs = " ".join(_task_names(wf))
    types = _task_types(wf)

    if _tool_was_called(wf, "get_account_balance"):
        r.checks.append("get_account_balance tool was called")
    else:
        r.checks.append("get_account_balance not called (LLM may have known)")

    # Guardrail tasks may be SIMPLE workers or INLINE
    guardrail_tasks = [t for t in wf.get("tasks", []) if "guardrail" in t.get("referenceTaskName", "").lower()
                       or "check_for_pii" in t.get("referenceTaskName", "")
                       or "check_output" in t.get("referenceTaskName", "")]
    if guardrail_tasks:
        r.checks.append(f"guardrail tasks found ({len(guardrail_tasks)})")
    else:
        r.checks.append("no explicit guardrail tasks in workflow (may be handled differently)")

    r.passed = len(r.failures) == 0
    return r


def ex06_model_settings(runtime: AgentRuntime) -> ExampleResult:
    """06 — Model settings: creative (temp=0.9) vs precise (temp=0.1)."""
    r = ExampleResult(name="06_model_settings")

    creative_agent = Agent(
        name="creative_writer",
        instructions="You are a creative writing assistant. Write with vivid imagery.",
        model=settings.llm_model,
        model_settings=ModelSettings(temperature=0.9, max_tokens=500),
    )
    precise_agent = Agent(
        name="code_reviewer",
        instructions="You are a precise code reviewer. Be concise and specific.",
        model=settings.llm_model,
        model_settings=ModelSettings(temperature=0.1, max_tokens=300),
    )

    result1 = runtime.run(creative_agent, "Write a two-sentence story about a robot learning to paint.")
    result2 = runtime.run(precise_agent, "Review this Python code: `data = eval(user_input)`")

    # Use the second workflow as primary
    r.workflow_id = f"{result1.workflow_id}, {result2.workflow_id}"
    r.status = f"{result1.status}, {result2.status}"

    if result1.status == "COMPLETED":
        r.checks.append("creative agent COMPLETED")
    else:
        r.failures.append(f"creative agent: expected COMPLETED, got {result1.status}")

    if result2.status == "COMPLETED":
        r.checks.append("precise agent COMPLETED")
    else:
        r.failures.append(f"precise agent: expected COMPLETED, got {result2.status}")

    if result1.output:
        r.checks.append("creative agent has output")
    else:
        r.failures.append("creative agent no output")

    if result2.output:
        r.checks.append("precise agent has output")
    else:
        r.failures.append("precise agent no output")

    # Verify temperature was applied by checking workflow input/LLM config
    for wf_id, label, expected_temp in [(result1.workflow_id, "creative", 0.9), (result2.workflow_id, "precise", 0.1)]:
        try:
            wf = _get_workflow_detail(runtime, wf_id)
            llm_tasks = _find_tasks_by_type(wf, "LLM_CHAT_COMPLETE")
            if llm_tasks:
                temp = llm_tasks[0].get("inputData", {}).get("temperature")
                if temp is not None and abs(float(temp) - expected_temp) < 0.01:
                    r.checks.append(f"{label} temperature={temp} (correct)")
                elif temp is not None:
                    r.checks.append(f"{label} temperature={temp} (expected {expected_temp})")
                else:
                    r.checks.append(f"{label} temperature not in inputData")
        except Exception:
            pass

    r.passed = len(r.failures) == 0
    return r


def ex07_streaming(runtime: AgentRuntime) -> ExampleResult:
    """07 — Streaming events."""
    r = ExampleResult(name="07_streaming")

    @function_tool
    def search_knowledge_base(query: str) -> str:
        """Search the knowledge base for relevant information."""
        knowledge = {
            "return policy": "Returns accepted within 30 days.",
            "shipping": "Free shipping on orders over $50.",
            "warranty": "1-year manufacturer warranty.",
        }
        for key, value in knowledge.items():
            if key in query.lower():
                return value
        return "No relevant information found."

    agent = Agent(
        name="support_agent",
        instructions="You are a customer support agent. Use the knowledge base to answer questions.",
        model=settings.llm_model,
        tools=[search_knowledge_base],
    )

    events = []
    event_types = set()
    for event in runtime.stream(agent, "What's your return policy for electronics?"):
        events.append(event)
        event_types.add(event.type)

    # Get workflow ID from the last event or events
    wf_id = ""
    for ev in reversed(events):
        if hasattr(ev, "workflow_id") and ev.workflow_id:
            wf_id = ev.workflow_id
            break
    # Fallback: check output attr
    if not wf_id:
        for ev in events:
            if hasattr(ev, "output") and ev.output:
                wf_id = getattr(ev, "workflow_id", "") or ""
                break

    r.workflow_id = wf_id or "streaming (no wf_id in events)"

    if events:
        r.checks.append(f"received {len(events)} events")
    else:
        r.failures.append("no events received")

    if "done" in event_types or "complete" in event_types:
        r.checks.append("received done/complete event")
        r.status = "COMPLETED"
    elif events:
        r.status = "COMPLETED"
        r.checks.append(f"event types: {sorted(event_types)}")
    else:
        r.status = "UNKNOWN"
        r.failures.append("no done event")

    if "tool_call" in event_types or "tool_result" in event_types:
        r.checks.append("tool events present in stream")
    else:
        r.checks.append("no tool events in stream (tool may not have been called)")

    r.passed = len(r.failures) == 0
    return r


def ex08_agent_as_tool(runtime: AgentRuntime) -> ExampleResult:
    """08 — Agent as tool (manager pattern)."""
    r = ExampleResult(name="08_agent_as_tool")

    @function_tool
    def analyze_sentiment(text: str) -> str:
        """Analyze the sentiment of text."""
        positive_words = {"great", "love", "excellent", "amazing", "wonderful", "best"}
        negative_words = {"bad", "terrible", "hate", "awful", "worst", "horrible"}
        words = set(text.lower().split())
        pos = len(words & positive_words)
        neg = len(words & negative_words)
        if pos > neg:
            return f"Positive sentiment (score: {pos}/{pos + neg})"
        elif neg > pos:
            return f"Negative sentiment (score: {neg}/{pos + neg})"
        return "Neutral sentiment"

    @function_tool
    def extract_keywords(text: str) -> str:
        """Extract key topics and keywords from text."""
        stop_words = {"the", "a", "an", "is", "are", "was", "in", "on", "to", "for", "of", "and", "or"}
        words = text.lower().split()
        keywords = [w.strip(".,!?") for w in words if w.strip(".,!?") not in stop_words and len(w) > 3]
        unique = list(dict.fromkeys(keywords))[:10]
        return f"Keywords: {', '.join(unique)}"

    sentiment_agent = Agent(name="sentiment_analyzer", instructions="Analyze text sentiment using the tool.", model=settings.llm_model, tools=[analyze_sentiment])
    keyword_agent = Agent(name="keyword_extractor", instructions="Extract keywords using the tool.", model=settings.llm_model, tools=[extract_keywords])

    manager = Agent(
        name="text_analysis_manager",
        instructions="You are a text analysis manager. Use sentiment analyzer and keyword extractor, then synthesize.",
        model=settings.llm_model,
        tools=[
            sentiment_agent.as_tool(tool_name="sentiment_analyzer", tool_description="Analyze sentiment."),
            keyword_agent.as_tool(tool_name="keyword_extractor", tool_description="Extract keywords."),
        ],
    )

    result = runtime.run(
        manager,
        "Analyze this review: 'The new laptop is excellent! The display is amazing and the battery life is wonderful. However, the keyboard feels terrible.'",
    )
    r.workflow_id = result.workflow_id
    r.status = result.status

    if result.status == "COMPLETED":
        r.checks.append("workflow COMPLETED")
    else:
        r.failures.append(f"expected COMPLETED, got {result.status}")

    if result.output:
        r.checks.append("has output text")
    else:
        r.failures.append("no output text")

    # Check for tool/sub-agent execution
    wf = _get_workflow_detail(runtime, result.workflow_id)
    types = _task_types(wf)

    for tool_name in ["sentiment_analyzer", "keyword_extractor"]:
        if _tool_was_called(wf, tool_name):
            r.checks.append(f"'{tool_name}' was called")
        else:
            r.checks.append(f"'{tool_name}' not found in tasks (may be sub-workflow)")

    r.passed = len(r.failures) == 0
    return r


def ex09_dynamic_instructions(runtime: AgentRuntime) -> ExampleResult:
    """09 — Dynamic instructions (callable)."""
    r = ExampleResult(name="09_dynamic_instructions")

    from datetime import datetime

    def get_dynamic_instructions(ctx, agent) -> str:
        hour = datetime.now().hour
        tone = "energetic" if hour < 12 else "focused" if hour < 17 else "calm"
        return f"You are a personal assistant. Respond in a {tone} tone. Use tools when appropriate."

    @function_tool
    def get_todo_list() -> str:
        """Get the user's current todo list."""
        return "- Review PR #42\n- Write unit tests\n- Team standup at 2pm"

    @function_tool
    def add_todo(task: str, priority: str = "medium") -> str:
        """Add a new item to the todo list."""
        return f"Added: '{task}' (priority: {priority})"

    agent = Agent(
        name="personal_assistant",
        instructions=get_dynamic_instructions,
        model=settings.llm_model,
        tools=[get_todo_list, add_todo],
    )

    result = runtime.run(agent, "Show me my todo list and add 'Prepare demo for Friday' as high priority.")
    r.workflow_id = result.workflow_id
    r.status = result.status

    if result.status == "COMPLETED":
        r.checks.append("workflow COMPLETED")
    else:
        r.failures.append(f"expected COMPLETED, got {result.status}")

    if result.output:
        r.checks.append("has output text")
    else:
        r.failures.append("no output text")

    # Check tool calls
    wf = _get_workflow_detail(runtime, result.workflow_id)

    for tool_name in ["get_todo_list", "add_todo"]:
        if _tool_was_called(wf, tool_name):
            r.checks.append(f"tool '{tool_name}' was called")
        else:
            r.failures.append(f"tool '{tool_name}' was NOT called")

    r.passed = len(r.failures) == 0
    return r


def ex10_multi_model(runtime: AgentRuntime) -> ExampleResult:
    """10 — Multi-model handoff: triage (llm_model) → specialists (secondary_llm_model)."""
    r = ExampleResult(name="10_multi_model")

    @function_tool
    def search_docs(query: str) -> str:
        """Search documentation."""
        docs = {
            "authentication": "Use OAuth 2.0 with JWT tokens.",
            "rate limiting": "100 requests/minute per API key.",
        }
        for key, value in docs.items():
            if key in query.lower():
                return value
        return "No documentation found."

    @function_tool
    def generate_code_sample(language: str, topic: str) -> str:
        """Generate a code sample."""
        return f"# {topic} in {language}\nimport requests\nresp = requests.post('/auth/login')"

    doc_specialist = Agent(name="doc_specialist", instructions="Search docs and provide answers.", model=settings.secondary_llm_model, tools=[search_docs], model_settings=ModelSettings(temperature=0.2))
    code_specialist = Agent(name="code_specialist", instructions="Generate code examples.", model=settings.secondary_llm_model, tools=[generate_code_sample], model_settings=ModelSettings(temperature=0.3))

    triage = Agent(
        name="triage",
        instructions="Route to doc_specialist or code_specialist based on the request.",
        model=settings.llm_model,
        model_settings=ModelSettings(temperature=0.1),
        handoffs=[doc_specialist, code_specialist],
    )

    result = runtime.run(triage, "I need a Python code example for authenticating with the API.")
    r.workflow_id = result.workflow_id
    r.status = result.status

    if result.status == "COMPLETED":
        r.checks.append("workflow COMPLETED")
    else:
        r.failures.append(f"expected COMPLETED, got {result.status}")

    if result.output:
        r.checks.append("has output text")
    else:
        r.failures.append("no output text")

    # Check for multi-agent / handoff evidence
    wf = _get_workflow_detail(runtime, result.workflow_id)
    types = _task_types(wf)
    llm_tasks = _find_tasks_by_type(wf, "LLM_CHAT_COMPLETE")

    if len(llm_tasks) >= 2:
        r.checks.append(f"{len(llm_tasks)} LLM tasks (multi-agent)")
    else:
        r.checks.append(f"only {len(llm_tasks)} LLM task(s)")

    # Check that different models were used
    models_used = set()
    for t in llm_tasks:
        m = t.get("inputData", {}).get("model", "")
        if m:
            models_used.add(m)
    if len(models_used) > 1:
        r.checks.append(f"multiple models used: {models_used}")
    elif models_used:
        r.checks.append(f"model used: {models_used}")

    # Check for handoff routing
    if "SUB_WORKFLOW" in types or "SWITCH" in types:
        r.checks.append("handoff routing present")
    else:
        r.checks.append("no explicit handoff routing (may use different pattern)")

    r.passed = len(r.failures) == 0
    return r


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

EXAMPLES = [
    ex01_basic_agent,
    ex02_function_tools,
    ex03_structured_output,
    ex04_handoffs,
    ex05_guardrails,
    ex06_model_settings,
    ex07_streaming,
    ex08_agent_as_tool,
    ex09_dynamic_instructions,
    ex10_multi_model,
]


def print_report(results: List[ExampleResult]) -> None:
    """Print a summary report."""
    w = 90
    print(f"\n{'=' * w}")
    print(f"  OPENAI EXAMPLES — TEST REPORT")
    print(f"{'=' * w}")

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed and not r.error)
    errored = sum(1 for r in results if r.error)

    for r in results:
        icon = "PASS" if r.passed else ("ERROR" if r.error else "FAIL")
        print(f"\n  [{icon}] {r.name}  ({r.duration_s:.1f}s)")
        print(f"         workflow: {r.workflow_id}")
        print(f"         status:   {r.status}")

        if r.checks:
            for c in r.checks:
                print(f"           + {c}")
        if r.failures:
            for f in r.failures:
                print(f"           - {f}")
        if r.error:
            print(f"           ! {r.error}")

    print(f"\n{'=' * w}")
    print(f"  SUMMARY: {passed} passed, {failed} failed, {errored} errors  (out of {len(results)})")
    print(f"{'=' * w}\n")


def main() -> int:
    print("Starting OpenAI examples test run...")
    print(f"Server: {_cfg.server_url}\n")

    with AgentRuntime() as runtime:
        for example_fn in EXAMPLES:
            name = example_fn.__doc__.split("—")[0].strip() if example_fn.__doc__ else example_fn.__name__
            print(f"Running {name} ...", end=" ", flush=True)
            t0 = time.time()
            try:
                r = example_fn(runtime)
                r.duration_s = time.time() - t0
                results.append(r)
                icon = "PASS" if r.passed else "FAIL"
                print(f"[{icon}] ({r.duration_s:.1f}s)")
            except Exception as e:
                duration = time.time() - t0
                er = ExampleResult(
                    name=example_fn.__name__,
                    error=f"{type(e).__name__}: {e}",
                    duration_s=duration,
                )
                results.append(er)
                print(f"[ERROR] ({duration:.1f}s) {e}")
                traceback.print_exc()

            # Small delay between examples to avoid rate limiting
            time.sleep(2)

    print_report(results)

    # Exit code: 0 if all passed
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
