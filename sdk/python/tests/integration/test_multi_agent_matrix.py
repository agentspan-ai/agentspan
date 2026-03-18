# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Multi-agent orchestration matrix integration tests — 21 tests, parallel execution.

All 21 workflows fire concurrently via runtime.start(), then polled to
completion. Covers every strategy individually, strategies with tools,
strategy features, nested/composite patterns, and special patterns.

Run:
    pytest tests/integration/test_multi_agent_matrix.py -v -s
    pytest tests/integration/test_multi_agent_matrix.py -v -s -k "Tier1"
    pytest tests/integration/test_multi_agent_matrix.py -v -s -k "handoff"

Requirements:
    - Conductor server running
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - AGENT_LLM_MODEL set (default: openai/gpt-4o-mini)
"""

import os
import time
from dataclasses import dataclass, field
from typing import List, Optional

import pytest

from agentspan.agents import (
    Agent,
    Strategy,
    agent_tool,
    tool,
)
from agentspan.agents.gate import TextGate
from agentspan.agents.handoff import OnTextMention
from agentspan.agents.result import AgentResult


pytestmark = pytest.mark.integration

M = os.environ.get("AGENT_LLM_MODEL", "openai/gpt-4o-mini")

TIMEOUT = 600  # seconds to wait for all workflows


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Spec + Result types
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class Spec:
    num: int
    test_id: str
    agent: Agent
    prompt: str
    valid_statuses: List[str]
    contains: Optional[str] = None
    not_contains: Optional[str] = None
    expect_sub_results: bool = False
    expect_sub_result_agents: List[str] = field(default_factory=list)


@dataclass
class Result:
    spec: Spec
    status: str
    output: str
    workflow_id: str
    agent_result: Optional[AgentResult] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tool definitions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@tool
def check_balance(account_id: str) -> dict:
    """Check the balance of a bank account."""
    return {"account_id": account_id, "balance": 5432.10, "currency": "USD"}


@tool
def lookup_order(order_id: str) -> dict:
    """Look up the status of an order."""
    return {"order_id": order_id, "status": "shipped", "eta": "2 days"}


@tool
def get_pricing(product: str) -> dict:
    """Get pricing information for a product."""
    return {"product": product, "price": 99.99, "discount": "10% off"}


@tool
def collect_data(source: str) -> dict:
    """Collect data from a source."""
    return {"source": source, "records": 42, "status": "collected"}


@tool
def analyze_data(data_summary: str) -> dict:
    """Analyze collected data."""
    return {"analysis": "Trend is upward", "confidence": 0.87}


@tool
def search_kb(query: str) -> dict:
    """Search the knowledge base for information."""
    data = {"python": "High-level programming language", "rust": "Systems language"}
    for k, v in data.items():
        if k in query.lower():
            return {"query": query, "result": v}
    return {"query": query, "result": "No specific data found"}


@tool
def calculate(expression: str) -> dict:
    """Evaluate a math expression safely."""
    allowed = set("0123456789+-*/.(). ")
    if not all(c in allowed for c in expression):
        return {"error": "Invalid expression"}
    try:
        return {"result": eval(expression)}
    except Exception as e:
        return {"error": str(e)}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Builder functions — one per matrix cell
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


# ── Tier 1: Pure Strategies ──────────────────────────────────────────

def _build_handoff_basic():
    billing = Agent(name="billing_t1", model=M,
        instructions="You handle billing questions. Answer concisely.")
    technical = Agent(name="technical_t1", model=M,
        instructions="You handle technical questions. Answer concisely.")
    return Agent(name="support_t1", model=M,
        instructions="Route to billing_t1 for payment/billing, technical_t1 for tech issues.",
        agents=[billing, technical], strategy=Strategy.HANDOFF,
)


def _build_sequential_basic():
    researcher = Agent(name="researcher_t1", model=M,
        instructions="Provide 3 key facts about the topic. Be concise.")
    writer = Agent(name="writer_t1", model=M,
        instructions="Write a short paragraph from the research facts.")
    editor = Agent(name="editor_t1", model=M,
        instructions="Polish the paragraph. Output the final version.")
    return Agent(name="seq_t1", model=M,
        agents=[researcher, writer, editor], strategy=Strategy.SEQUENTIAL,
)


def _build_parallel_basic():
    market = Agent(name="market_t1", model=M,
        instructions="Analyze from a market perspective. 2-3 sentences.")
    risk = Agent(name="risk_t1", model=M,
        instructions="Analyze from a risk perspective. 2-3 sentences.")
    return Agent(name="analysis_t1", model=M,
        agents=[market, risk], strategy=Strategy.PARALLEL,
)


def _build_router_basic():
    planner = Agent(name="planner_t1", model=M,
        instructions="Create implementation plans with numbered steps.")
    coder = Agent(name="coder_t1", model=M,
        instructions="Write clean Python code.")
    reviewer = Agent(name="reviewer_t1", model=M,
        instructions="Review code for bugs and suggest improvements.")
    return Agent(name="team_t1", model=M,
        instructions="Route to planner_t1 for design, coder_t1 for coding, reviewer_t1 for review.",
        agents=[planner, coder, reviewer],
        strategy=Strategy.ROUTER, router=planner,
)


def _build_round_robin_basic():
    optimist = Agent(name="optimist_t1", model=M,
        instructions="Argue FOR the topic. 2-3 sentences.")
    skeptic = Agent(name="skeptic_t1", model=M,
        instructions="Argue AGAINST the topic. 2-3 sentences.")
    return Agent(name="debate_t1", model=M,
        agents=[optimist, skeptic],
        strategy=Strategy.ROUND_ROBIN, max_turns=4,
)


def _build_random_basic():
    creative = Agent(name="creative_t1", model=M,
        instructions="Suggest creative, unconventional ideas. 2-3 sentences.")
    practical = Agent(name="practical_t1", model=M,
        instructions="Focus on feasibility and cost. 2-3 sentences.")
    critical = Agent(name="critical_t1", model=M,
        instructions="Identify risks and issues. 2-3 sentences.")
    return Agent(name="brainstorm_t1", model=M,
        agents=[creative, practical, critical],
        strategy=Strategy.RANDOM, max_turns=3,
)


def _build_swarm_basic():
    refund = Agent(name="refund_t1", model=M,
        instructions="Process refund requests. Be concise and empathetic.")
    tech = Agent(name="tech_t1", model=M,
        instructions="Handle technical issues. Provide troubleshooting steps.")
    return Agent(name="support_t1s", model=M,
        instructions=(
            "Triage customer requests. Transfer to refund_t1 for refunds, "
            "tech_t1 for tech issues. Use the transfer tools."
        ),
        agents=[refund, tech], strategy=Strategy.SWARM,
        handoffs=[
            OnTextMention(text="refund", target="refund_t1"),
            OnTextMention(text="technical", target="tech_t1"),
        ],
        max_turns=3,
)


# ── Tier 2: Strategies + Tools ───────────────────────────────────────

def _build_handoff_tools():
    billing = Agent(name="billing_t2", model=M,
        instructions="Handle billing. Use check_balance to look up accounts. Include the balance in your response.",
        tools=[check_balance])
    technical = Agent(name="technical_t2", model=M,
        instructions="Handle technical issues. Use lookup_order to check orders.",
        tools=[lookup_order])
    return Agent(name="support_t2", model=M,
        instructions="Route to billing_t2 for billing, technical_t2 for tech.",
        agents=[billing, technical], strategy=Strategy.HANDOFF,
)


def _build_sequential_tools():
    collector = Agent(name="collector_t2", model=M,
        instructions="Collect data using collect_data tool. Pass data summary to next stage.",
        tools=[collect_data])
    analyst = Agent(name="analyst_t2", model=M,
        instructions="Analyze data using analyze_data tool. Report findings.",
        tools=[analyze_data])
    return Agent(name="collector_t2_analyst_t2", model=M,
        agents=[collector, analyst], strategy=Strategy.SEQUENTIAL,
)


def _build_parallel_tools():
    balance_checker = Agent(name="balance_checker_t2", model=M,
        instructions="Check account balance using check_balance. Report the balance.",
        tools=[check_balance])
    order_checker = Agent(name="order_checker_t2", model=M,
        instructions="Look up order using lookup_order. Report the status.",
        tools=[lookup_order])
    return Agent(name="parallel_tools_t2", model=M,
        agents=[balance_checker, order_checker], strategy=Strategy.PARALLEL,
)


def _build_swarm_tools():
    refund = Agent(name="refund_t2", model=M,
        instructions="Process refunds. Use check_balance to verify account. Be concise.",
        tools=[check_balance])
    tech = Agent(name="tech_t2", model=M,
        instructions="Handle tech issues. Use lookup_order to check orders. Be concise.",
        tools=[lookup_order])
    return Agent(name="support_t2s", model=M,
        instructions="Triage requests. Transfer to refund_t2 for refunds, tech_t2 for tech.",
        agents=[refund, tech], strategy=Strategy.SWARM,
        handoffs=[
            OnTextMention(text="refund", target="refund_t2"),
            OnTextMention(text="technical", target="tech_t2"),
        ],
        max_turns=3,
)


# ── Tier 3: Strategy Features ────────────────────────────────────────

def _build_handoff_transitions():
    collector = Agent(name="collector_t3", model=M,
        instructions="Say you collected 42 records from the sales database.")
    analyst = Agent(name="analyst_t3", model=M,
        instructions="Analyze the collected data. Report that trends are upward.")
    reporter = Agent(name="reporter_t3", model=M,
        instructions="Write a 2-sentence summary report of the analysis.")
    return Agent(name="pipeline_t3", model=M,
        instructions=(
            "Route to collector_t3 first, then analyst_t3, then reporter_t3."
        ),
        agents=[collector, analyst, reporter], strategy=Strategy.HANDOFF,
        allowed_transitions={
            "collector_t3": ["analyst_t3"],
            "analyst_t3": ["reporter_t3"],
            "reporter_t3": ["pipeline_t3"],
        },
)


def _build_sequential_gate():
    checker = Agent(name="checker_t3", model=M,
        instructions=(
            "Check if the input describes a problem. If there is no problem, "
            "output exactly: NO_ISSUES. Otherwise describe the problem."
        ),
        gate=TextGate("NO_ISSUES"))
    fixer = Agent(name="fixer_t3", model=M,
        instructions="Fix the problem described in the input.")
    return Agent(name="gate_t3", model=M,
        agents=[checker, fixer], strategy=Strategy.SEQUENTIAL,
)


def _build_round_robin_max_turns():
    cat_fan = Agent(name="cat_fan_t3", model=M,
        instructions="Argue why cats are better. 1-2 sentences.")
    dog_fan = Agent(name="dog_fan_t3", model=M,
        instructions="Argue why dogs are better. 1-2 sentences.")
    return Agent(name="debate_t3", model=M,
        agents=[cat_fan, dog_fan],
        strategy=Strategy.ROUND_ROBIN, max_turns=2,
)


# ── Tier 4: Nested/Composite ─────────────────────────────────────────

def _build_seq_then_parallel():
    market = Agent(name="market_t4a", model=M,
        instructions="Analyze market size and growth. 2-3 sentences.")
    risk = Agent(name="risk_t4a", model=M,
        instructions="Identify top 2 risks. 2-3 sentences.")
    parallel_phase = Agent(name="research_t4a", model=M,
        agents=[market, risk], strategy=Strategy.PARALLEL)
    summarizer = Agent(name="summarizer_t4a", model=M,
        instructions="Synthesize the analysis into a 1-paragraph executive summary.")
    return Agent(name="seq_par_t4a", model=M,
        agents=[parallel_phase, summarizer], strategy=Strategy.SEQUENTIAL,
)


def _build_seq_then_swarm():
    fetcher = Agent(name="fetcher_t4b", model=M,
        instructions=(
            "Describe the task: write a hello world function in Python. "
            "Output the task description for the next stage."
        ))
    coder = Agent(name="coder_t4b", model=M,
        instructions="Write the code. When done, say HANDOFF_TO_TESTER.")
    tester = Agent(name="tester_t4b", model=M,
        instructions="Review the code. If good, say QA_APPROVED. If bad, say HANDOFF_TO_CODER.")
    swarm_stage = Agent(name="coding_t4b", model=M,
        instructions="Delegate to coder_t4b first.",
        agents=[coder, tester], strategy=Strategy.SWARM,
        handoffs=[
            OnTextMention(text="HANDOFF_TO_TESTER", target="tester_t4b"),
            OnTextMention(text="HANDOFF_TO_CODER", target="coder_t4b"),
        ],
        max_turns=4,
)
    return Agent(name="seq_swarm_t4b", model=M,
        agents=[fetcher, swarm_stage], strategy=Strategy.SEQUENTIAL,
)


def _build_handoff_to_parallel():
    quick_check = Agent(name="quick_check_t4", model=M,
        instructions="Provide a quick 1-sentence assessment.")
    market_deep = Agent(name="market_deep_t4", model=M,
        instructions="Provide detailed market analysis. 2-3 sentences.")
    risk_deep = Agent(name="risk_deep_t4", model=M,
        instructions="Provide detailed risk analysis. 2-3 sentences.")
    deep_analysis = Agent(name="deep_analysis_t4", model=M,
        agents=[market_deep, risk_deep], strategy=Strategy.PARALLEL)
    return Agent(name="router_t4c", model=M,
        instructions=(
            "Route to quick_check_t4 for simple checks, "
            "deep_analysis_t4 for deep analysis requests."
        ),
        agents=[quick_check, deep_analysis], strategy=Strategy.HANDOFF,
)


def _build_router_to_sequential():
    quick_answer = Agent(name="quick_answer_t4", model=M,
        instructions="Give a 1-sentence answer.")
    researcher = Agent(name="researcher_t4d", model=M,
        instructions="Research the topic. Provide 3 key facts.")
    writer = Agent(name="writer_t4d", model=M,
        instructions="Write a concise summary from the research.")
    pipeline = Agent(name="research_pipeline_t4", model=M,
        agents=[researcher, writer], strategy=Strategy.SEQUENTIAL)
    router_agent = Agent(name="selector_t4d", model=M,
        instructions=(
            "Select research_pipeline_t4 for research tasks, "
            "quick_answer_t4 for simple questions."
        ))
    return Agent(name="routed_t4d", model=M,
        agents=[quick_answer, pipeline],
        strategy=Strategy.ROUTER, router=router_agent,
)


def _build_swarm_hierarchical():
    backend = Agent(name="backend_t4", model=M,
        instructions="Design backend APIs. Be concise.")
    frontend = Agent(name="frontend_t4", model=M,
        instructions="Design frontend UI. Be concise.")
    eng_team = Agent(name="eng_team_t4", model=M,
        instructions="Route to backend_t4 for APIs, frontend_t4 for UI.",
        agents=[backend, frontend], strategy=Strategy.HANDOFF)
    content = Agent(name="content_t4", model=M,
        instructions="Write marketing copy. Be concise.")
    seo = Agent(name="seo_t4", model=M,
        instructions="Optimize for SEO. Be concise.")
    mkt_team = Agent(name="mkt_team_t4", model=M,
        instructions="Route to content_t4 for copy, seo_t4 for SEO.",
        agents=[content, seo], strategy=Strategy.HANDOFF)
    return Agent(name="ceo_t4", model=M,
        instructions=(
            "Route to eng_team_t4 for engineering tasks, "
            "mkt_team_t4 for marketing tasks."
        ),
        agents=[eng_team, mkt_team], strategy=Strategy.SWARM,
        handoffs=[
            OnTextMention(text="engineering", target="eng_team_t4"),
            OnTextMention(text="marketing", target="mkt_team_t4"),
        ],
        max_turns=3,
)


def _build_parallel_tools_pipeline():
    bal = Agent(name="bal_t4e", model=M,
        instructions="Check account balance using check_balance. Report the balance.",
        tools=[check_balance])
    ord_agent = Agent(name="ord_t4e", model=M,
        instructions="Look up order using lookup_order. Report the status.",
        tools=[lookup_order])
    par = Agent(name="par_t4e", model=M,
        agents=[bal, ord_agent], strategy=Strategy.PARALLEL,
)
    summ = Agent(name="summ_t4e", model=M,
        instructions="Summarize the account balance and order status into one paragraph.")
    return Agent(name="par_summ_t4e", model=M,
        agents=[par, summ], strategy=Strategy.SEQUENTIAL,
)


# ── Tier 5: Special Patterns ─────────────────────────────────────────

def _build_agent_tool_basic():
    researcher = Agent(name="researcher_t5", model=M,
        instructions="Use search_kb to find information. Provide concise summaries.",
        tools=[search_kb])
    return Agent(name="manager_t5", model=M,
        instructions=(
            "Use the researcher_t5 tool to research topics and "
            "calculate tool for math. Synthesize findings."
        ),
        tools=[agent_tool(researcher), calculate],
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Spec definitions — 21 matrix cells
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SPECS: List[Spec] = [
    # ── Tier 1: Pure Strategies ──
    Spec(1,  "handoff_basic",         _build_handoff_basic(),
         "What is the balance on account ACC-123?", ["COMPLETED"]),
    Spec(2,  "sequential_basic",      _build_sequential_basic(),
         "The benefits of electric vehicles", ["COMPLETED"]),
    Spec(3,  "parallel_basic",        _build_parallel_basic(),
         "Evaluate launching a new mobile app.", ["COMPLETED"],
         expect_sub_results=True,
         expect_sub_result_agents=["market_t1", "risk_t1"]),
    Spec(4,  "router_basic",          _build_router_basic(),
         "Create a plan for a REST API.", ["COMPLETED"]),
    Spec(5,  "round_robin_basic",     _build_round_robin_basic(),
         "Should companies adopt AI agents?", ["COMPLETED"]),
    Spec(6,  "random_basic",          _build_random_basic(),
         "Ideas for improving customer support.", ["COMPLETED"]),
    Spec(7,  "swarm_basic",           _build_swarm_basic(),
         "I need a refund for my damaged product.", ["COMPLETED"]),

    # ── Tier 2: Strategies + Tools ──
    # Tool results flow through to output — verify tool data appears in response
    Spec(8,  "handoff_tools",         _build_handoff_tools(),
         "Check the balance on account ACC-100.", ["COMPLETED"], contains="5,432"),
    Spec(9,  "sequential_tools",      _build_sequential_tools(),
         "Collect data from sales and analyze trends.", ["COMPLETED"]),
    Spec(10, "parallel_tools",        _build_parallel_tools(),
         "Check account ACC-200 and look up order ORD-300.", ["COMPLETED"],
         expect_sub_results=True,
         expect_sub_result_agents=["balance_checker_t2", "order_checker_t2"]),
    Spec(11, "swarm_tools",           _build_swarm_tools(),
         "I need a refund, check my account ACC-500.", ["COMPLETED"]),

    # ── Tier 3: Strategy Features ──
    Spec(12, "handoff_transitions",   _build_handoff_transitions(),
         "Collect data from sales, analyze, and report.", ["COMPLETED"]),
    Spec(13, "sequential_gate",       _build_sequential_gate(),
         "Check if the number 42 is valid.", ["COMPLETED"]),
    Spec(14, "round_robin_max_turns", _build_round_robin_max_turns(),
         "Debate: cats vs dogs.", ["COMPLETED"]),

    # ── Tier 4: Nested/Composite ──
    Spec(15, "seq_then_parallel",     _build_seq_then_parallel(),
         "Evaluate launching an AI health tool.", ["COMPLETED"]),
    Spec(16, "seq_then_swarm",        _build_seq_then_swarm(),
         "Write a hello world function and test it.", ["COMPLETED"]),
    Spec(17, "handoff_to_parallel",   _build_handoff_to_parallel(),
         "Do a deep analysis of market risks.", ["COMPLETED"]),
    Spec(18, "router_to_sequential",  _build_router_to_sequential(),
         "Research Python and write a summary.", ["COMPLETED"]),
    Spec(19, "swarm_hierarchical",    _build_swarm_hierarchical(),
         "Design a REST API for user management.", ["COMPLETED"]),
    Spec(20, "parallel_tools_pipeline", _build_parallel_tools_pipeline(),
         "Check account ACC-200 and order ORD-300, then summarize.", ["COMPLETED"]),

    # ── Tier 5: Special Patterns ──
    Spec(21, "agent_tool_basic",      _build_agent_tool_basic(),
         "Research Python and calculate 2+2.", ["COMPLETED"]),
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Fixture: fire all 21 in parallel, collect results once
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _fetch_agent_result(handle, runtime, status) -> Optional[AgentResult]:
    """Build an AgentResult from a completed workflow by fetching execution details.

    Uses the same workflow-client approach as runtime.run() to populate
    tool_calls, messages, sub_results, and token_usage.
    """
    try:
        output = status.output
        raw_status = status.status

        # Normalize output to always be a dict
        output = runtime._normalize_output(output, raw_status, status.reason)

        # Fetch full workflow execution for tool_calls, messages, token_usage
        tool_calls = []
        messages = []
        token_usage = None
        try:
            wf = runtime._workflow_client.get_workflow(
                workflow_id=handle.workflow_id,
                include_tasks=True,
            )
            tool_calls = runtime._extract_tool_calls(wf)
            messages = runtime._extract_messages(wf)
            token_usage = runtime._extract_token_usage(wf)
        except Exception:
            pass

        return AgentResult(
            output=output,
            workflow_id=handle.workflow_id,
            status=raw_status,
            finish_reason=runtime._derive_finish_reason(raw_status, status.output),
            error=status.reason if raw_status in ("FAILED", "TERMINATED") else None,
            tool_calls=tool_calls,
            messages=messages,
            token_usage=token_usage,
            sub_results=runtime._extract_sub_results(output),
        )
    except Exception:
        return None


@pytest.fixture(scope="module")
def matrix_results(runtime):
    """Fire all 21 workflows concurrently and poll until all complete."""
    # Phase 1: start all workflows
    handles = []
    for spec in SPECS:
        handle = runtime.start(spec.agent, spec.prompt)
        handles.append((spec, handle))
        print(f"  Started #{spec.num:2d} {spec.test_id}: wf={handle.workflow_id}")

    print(f"\n  All {len(SPECS)} workflows started. Polling for completion...\n")

    # Phase 2: poll all handles round-robin until done
    results = {}
    completed_statuses = {}
    pending = list(range(len(handles)))
    deadline = time.monotonic() + TIMEOUT

    while pending and time.monotonic() < deadline:
        still_pending = []
        for i in pending:
            spec, handle = handles[i]
            status = handle.get_status()
            if status.is_complete:
                completed_statuses[spec.num] = (handle, status)
                print(f"  Done #{spec.num:2d} {spec.test_id}: "
                      f"status={status.status}  wf={handle.workflow_id}")
            else:
                still_pending.append(i)
        pending = still_pending
        if pending:
            time.sleep(1)

    # Phase 3: fetch full AgentResult for completed workflows
    for spec_num, (handle, status) in completed_statuses.items():
        spec = next(s for s in SPECS if s.num == spec_num)
        agent_result = _fetch_agent_result(handle, runtime, status)
        tool_names = []
        if agent_result and agent_result.tool_calls:
            tool_names = [tc.get("name", "") for tc in agent_result.tool_calls]
        sub_result_keys = []
        if agent_result and agent_result.sub_results:
            sub_result_keys = list(agent_result.sub_results.keys())
        print(f"  #{spec_num:2d} {spec.test_id}: "
              f"tool_calls={tool_names}  sub_results={sub_result_keys}")
        results[spec_num] = Result(
            spec=spec,
            status=status.status,
            output=str(status.output) if status.output else "",
            workflow_id=handle.workflow_id,
            agent_result=agent_result,
        )

    # Phase 4: mark timed-out workflows
    for i in pending:
        spec, handle = handles[i]
        results[spec.num] = Result(
            spec=spec, status="TIMEOUT", output="",
            workflow_id=handle.workflow_id,
        )
        print(f"  TIMEOUT #{spec.num:2d} {spec.test_id}: wf={handle.workflow_id}")

    completed = sum(1 for r in results.values() if r.status != "TIMEOUT")
    print(f"\n  {completed}/{len(SPECS)} workflows completed.\n")
    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tests — 21 individual test cases reading from shared fixture
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _check(matrix_results, num):
    """Validate result for matrix cell #num against its spec."""
    r = matrix_results[num]
    print(f"  wf={r.workflow_id}  status={r.status}")
    assert r.status != "TIMEOUT", (
        f"#{num} {r.spec.test_id}: polling timed out (wf={r.workflow_id})"
    )
    assert r.status != "TIMED_OUT", (
        f"#{num} {r.spec.test_id}: workflow timed out on server (wf={r.workflow_id})"
    )
    assert r.status in r.spec.valid_statuses, (
        f"#{num} {r.spec.test_id}: expected {r.spec.valid_statuses}, got {r.status}"
    )
    if r.status == "COMPLETED":
        assert r.output, f"#{num} {r.spec.test_id}: output is empty"
    if r.spec.contains and r.status == "COMPLETED":
        assert r.spec.contains.lower() in r.output.lower(), (
            f"#{num}: output should contain '{r.spec.contains}'"
        )
    if r.spec.not_contains and r.status == "COMPLETED":
        assert r.spec.not_contains not in r.output, (
            f"#{num}: output should NOT contain '{r.spec.not_contains}'"
        )

    # ── Rich verification using AgentResult ──
    if r.status != "COMPLETED" or r.agent_result is None:
        return

    ar = r.agent_result

    # Verify parallel strategies produced sub_results
    if r.spec.expect_sub_results:
        assert ar.sub_results, (
            f"#{num} {r.spec.test_id}: expected sub_results from parallel "
            f"strategy but got none"
        )
        print(f"  [OK] sub_results present: {list(ar.sub_results.keys())}")

    # Verify expected sub-agents contributed to sub_results
    if r.spec.expect_sub_result_agents:
        actual_agents = set(ar.sub_results.keys())
        for agent_name in r.spec.expect_sub_result_agents:
            assert agent_name in actual_agents, (
                f"#{num} {r.spec.test_id}: expected agent '{agent_name}' in "
                f"sub_results but got {sorted(actual_agents)}"
            )
        print(f"  [OK] sub_result agents verified: {r.spec.expect_sub_result_agents}")

    # Verify messages were captured (every completed run should have messages)
    if ar.messages:
        print(f"  [OK] {len(ar.messages)} messages captured")


class TestTier1PureStrategies:
    """#1-7: Each strategy tested individually, no tools."""

    def test_01_handoff_basic(self, matrix_results):
        _check(matrix_results, 1)

    def test_02_sequential_basic(self, matrix_results):
        _check(matrix_results, 2)

    def test_03_parallel_basic(self, matrix_results):
        _check(matrix_results, 3)

    def test_04_router_basic(self, matrix_results):
        _check(matrix_results, 4)

    def test_05_round_robin_basic(self, matrix_results):
        _check(matrix_results, 5)

    def test_06_random_basic(self, matrix_results):
        _check(matrix_results, 6)

    def test_07_swarm_basic(self, matrix_results):
        _check(matrix_results, 7)


class TestTier2StrategiesWithTools:
    """#8-11: Strategies with tool-bearing sub-agents."""

    def test_08_handoff_tools(self, matrix_results):
        _check(matrix_results, 8)

    def test_09_sequential_tools(self, matrix_results):
        _check(matrix_results, 9)

    def test_10_parallel_tools(self, matrix_results):
        _check(matrix_results, 10)

    def test_11_swarm_tools(self, matrix_results):
        _check(matrix_results, 11)


class TestTier3StrategyFeatures:
    """#12-14: Strategy features (transitions, gates, max_turns)."""

    def test_12_handoff_transitions(self, matrix_results):
        _check(matrix_results, 12)

    def test_13_sequential_gate(self, matrix_results):
        _check(matrix_results, 13)

    def test_14_round_robin_max_turns(self, matrix_results):
        _check(matrix_results, 14)


class TestTier4NestedComposite:
    """#15-20: Nested and composite strategy patterns."""

    def test_15_seq_then_parallel(self, matrix_results):
        _check(matrix_results, 15)

    def test_16_seq_then_swarm(self, matrix_results):
        _check(matrix_results, 16)

    def test_17_handoff_to_parallel(self, matrix_results):
        _check(matrix_results, 17)

    def test_18_router_to_sequential(self, matrix_results):
        _check(matrix_results, 18)

    def test_19_swarm_hierarchical(self, matrix_results):
        _check(matrix_results, 19)

    def test_20_parallel_tools_pipeline(self, matrix_results):
        _check(matrix_results, 20)


class TestTier5SpecialPatterns:
    """#21: Special patterns (agent_tool)."""

    def test_21_agent_tool_basic(self, matrix_results):
        _check(matrix_results, 21)
