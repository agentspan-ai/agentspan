# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Guardrail matrix integration tests — full 3x3x3 coverage, parallel execution.

All 27 workflows are fired concurrently via runtime.start(), then polled to
completion. This runs the full matrix in ~30s instead of ~6min sequential.

Matrix axes:
    Position:  Agent Output | Tool Input | Tool Output
    Type:      Regex        | LLM        | Custom
    on_fail:   RETRY        | RAISE      | FIX

Design principles:
    - Deterministic triggering: tools return fixed content that guarantees the
      guardrail fires (no reliance on LLM "misbehaving").
    - Tight valid_statuses: RAISE tests expect ["FAILED"], FIX-with-fixed_output
      tests expect ["COMPLETED"]. BOTH is only used when the outcome genuinely
      depends on LLM retry behavior or a non-deterministic LLM judge.
    - Content assertions: every COMPLETED spec checks not_contains (blocked content
      absent) and/or contains (fixed content present) where applicable.

Run:
    pytest tests/integration/test_guardrail_matrix.py -v -s
    pytest tests/integration/test_guardrail_matrix.py -v -s -k "aout"   # agent output only
    pytest tests/integration/test_guardrail_matrix.py -v -s -k "regex"  # regex only

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
    Guardrail,
    GuardrailResult,
    LLMGuardrail,
    OnFail,
    Position,
    RegexGuardrail,
    guardrail,
    tool,
)


pytestmark = pytest.mark.integration

M = os.environ.get("AGENT_LLM_MODEL", "openai/gpt-4o-mini")

TIMEOUT = 600  # seconds to wait for all workflows


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test spec + result types
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class Spec:
    num: int
    test_id: str
    agent: Agent
    prompt: str
    valid_statuses: List[str]
    not_contains: Optional[str] = None
    contains: Optional[str] = None


@dataclass
class Result:
    spec: Spec
    status: str
    output: str
    workflow_id: str


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Guardrail configs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# -- Agent output: regex patterns --
_regex_cc = dict(
    patterns=[r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"],
    mode="block", position=Position.OUTPUT,
    message="Do not include credit card numbers. Redact them.",
)
_regex_ssn = dict(
    patterns=[r"\b\d{3}-\d{2}-\d{4}\b"],
    mode="block", position=Position.OUTPUT,
    message="Response must not contain SSNs.",
)

# -- Agent output: LLM policy --
_llm_policy_medical = (
    "Reject content that provides specific medication names with dosages "
    "or makes definitive medical diagnoses. General health tips are OK."
)

# -- Tool input: regex pattern (matches 4+ consecutive digits) --
_regex_tin_patterns = [r"\d{4,}"]

# -- Tool input: LLM policy --
_llm_policy_tin = (
    "Reject if the input contains raw numeric identifiers with 4 or more "
    "digits. Only alphanumeric codes like 'USR-A1' are acceptable."
)

# -- Tool output: LLM policy --
_llm_policy_tout = (
    "Reject tool output containing personal info like SSNs, emails, "
    "or phone numbers."
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Custom guardrail functions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# -- Agent output --

@guardrail
def _custom_aout_block(content: str) -> GuardrailResult:
    if "SECRET42" in content:
        return GuardrailResult(passed=False, message="Contains SECRET42. Remove it.")
    return GuardrailResult(passed=True)


@guardrail
def _custom_aout_fix_fn(content: str) -> GuardrailResult:
    if "SECRET42" in content:
        return GuardrailResult(passed=False, message="Redacted.",
                               fixed_output=content.replace("SECRET42", "[REDACTED]"))
    return GuardrailResult(passed=True)


# -- Tool input: blocks benign keyword "REPORT" that LLM has no reason to filter --

@guardrail
def _custom_tin_block(content: str) -> GuardrailResult:
    if "REPORT" in content.upper():
        return GuardrailResult(
            passed=False,
            message="Contains restricted keyword 'report'. Rephrase without it.",
        )
    return GuardrailResult(passed=True)


@guardrail
def _custom_tin_fix_fn(content: str) -> GuardrailResult:
    upper = content.upper()
    if "REPORT" in upper:
        fixed = content
        for word in ("REPORT", "Report", "report"):
            fixed = fixed.replace(word, "summary")
        return GuardrailResult(passed=False, message="Fixed.",
                               fixed_output=fixed)
    return GuardrailResult(passed=True)


# -- Tool output --

@guardrail
def _custom_tout_block(content: str) -> GuardrailResult:
    if "SENSITIVE" in content:
        return GuardrailResult(passed=False, message="Sensitive data blocked.")
    return GuardrailResult(passed=True)


@guardrail
def _custom_tout_fix_fn(content: str) -> GuardrailResult:
    if "SENSITIVE" in content:
        return GuardrailResult(passed=False, message="Redacted.",
                               fixed_output=content.replace("SENSITIVE", "[REDACTED]"))
    return GuardrailResult(passed=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tools
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# -- Agent-output tools: return deterministic bad content --

@tool
def get_cc_data(user_id: str) -> dict:
    """Look up payment info."""
    return {"user": user_id, "card": "4532-0150-1234-5678", "name": "Alice"}

@tool
def get_ssn_data(user_id: str) -> dict:
    """Look up identity info."""
    return {"user": user_id, "ssn": "123-45-6789", "name": "Bob"}

@tool
def get_secret_data(query: str) -> dict:
    """Look up confidential data."""
    return {"result": f"The access code is SECRET42, query: {query}"}


# -- Tool INPUT: regex guardrails (blocks 4+ digit numeric IDs) --

@tool(guardrails=[RegexGuardrail(patterns=_regex_tin_patterns, mode="block",
      name="tin_regex_retry", message="Numeric IDs restricted. Use alphanumeric codes.",
      position=Position.INPUT, on_fail=OnFail.RETRY)])
def tin_regex_retry_tool(user_id: str) -> str:
    """Look up user by numeric ID."""
    return f"User {user_id}: Alice Johnson, age 30"

@tool(guardrails=[RegexGuardrail(patterns=_regex_tin_patterns, mode="block",
      name="tin_regex_raise", message="Numeric IDs restricted.",
      position=Position.INPUT, on_fail=OnFail.RAISE)])
def tin_regex_raise_tool(user_id: str) -> str:
    """Look up user by numeric ID."""
    return f"User {user_id}: Alice Johnson, age 30"

@tool(guardrails=[RegexGuardrail(patterns=_regex_tin_patterns, mode="block",
      name="tin_regex_fix", message="Numeric IDs restricted.",
      position=Position.INPUT, on_fail=OnFail.FIX)])
def tin_regex_fix_tool(user_id: str) -> str:
    """Look up user by numeric ID."""
    return f"User {user_id}: Alice Johnson, age 30"


# -- Tool INPUT: LLM guardrails --

@tool(guardrails=[LLMGuardrail(model=M, name="tin_llm_retry", position=Position.INPUT,
      on_fail=OnFail.RETRY, max_tokens=256, policy=_llm_policy_tin)])
def tin_llm_retry_tool(user_id: str) -> str:
    """Look up user by ID."""
    return f"User {user_id}: Alice Johnson, age 30"

@tool(guardrails=[LLMGuardrail(model=M, name="tin_llm_raise", position=Position.INPUT,
      on_fail=OnFail.RAISE, max_tokens=256, policy=_llm_policy_tin)])
def tin_llm_raise_tool(user_id: str) -> str:
    """Look up user by ID."""
    return f"User {user_id}: Alice Johnson, age 30"

@tool(guardrails=[LLMGuardrail(model=M, name="tin_llm_fix", position=Position.INPUT,
      on_fail=OnFail.FIX, max_tokens=256, policy=_llm_policy_tin)])
def tin_llm_fix_tool(user_id: str) -> str:
    """Look up user by ID."""
    return f"User {user_id}: Alice Johnson, age 30"


# -- Tool INPUT: custom guardrails (blocks "REPORT" keyword) --

@tool(guardrails=[Guardrail(_custom_tin_block, position=Position.INPUT,
      on_fail=OnFail.RETRY, name="tin_custom_retry")])
def tin_custom_retry_tool(data: str) -> str:
    """Process data input."""
    return f"Processed: {data}"

@tool(guardrails=[Guardrail(_custom_tin_block, position=Position.INPUT,
      on_fail=OnFail.RAISE, name="tin_custom_raise")])
def tin_custom_raise_tool(data: str) -> str:
    """Process data input."""
    return f"Processed: {data}"

@tool(guardrails=[Guardrail(_custom_tin_fix_fn, position=Position.INPUT,
      on_fail=OnFail.FIX, name="tin_custom_fix")])
def tin_custom_fix_tool(data: str) -> str:
    """Process data input."""
    return f"Processed: {data}"


# -- Tool OUTPUT: regex guardrails (tool ALWAYS returns triggering content) --

def _secret_tool_factory(guardrail_instance, suffix):
    @tool(guardrails=[guardrail_instance])
    def _fn(query: str) -> str:
        """Fetch internal data."""
        return f"INTERNAL_SECRET: classified for {query}"
    _fn.__name__ = f"tout_regex_{suffix}_tool"
    _fn.__qualname__ = _fn.__name__
    _fn._tool_def.name = _fn.__name__
    return _fn

tout_regex_retry_tool = _secret_tool_factory(
    RegexGuardrail(patterns=[r"INTERNAL_SECRET"], mode="block", name="tout_regex_retry",
                   message="Secrets blocked.", position=Position.OUTPUT, on_fail=OnFail.RETRY), "retry")
tout_regex_raise_tool = _secret_tool_factory(
    RegexGuardrail(patterns=[r"INTERNAL_SECRET"], mode="block", name="tout_regex_raise",
                   message="Secrets blocked.", position=Position.OUTPUT, on_fail=OnFail.RAISE), "raise")
tout_regex_fix_tool = _secret_tool_factory(
    RegexGuardrail(patterns=[r"INTERNAL_SECRET"], mode="block", name="tout_regex_fix",
                   message="Secrets blocked.", position=Position.OUTPUT, on_fail=OnFail.FIX), "fix")


# -- Tool OUTPUT: LLM guardrails (tool ALWAYS returns PII) --

def _pii_tool_factory(guardrail_instance, suffix):
    @tool(guardrails=[guardrail_instance])
    def _fn(user_id: str) -> str:
        """Fetch user profile."""
        return f"User {user_id}: Alice, alice@example.com, SSN 123-45-6789"
    _fn.__name__ = f"tout_llm_{suffix}_tool"
    _fn.__qualname__ = _fn.__name__
    _fn._tool_def.name = _fn.__name__
    return _fn

tout_llm_retry_tool = _pii_tool_factory(
    LLMGuardrail(model=M, name="tout_llm_retry", position=Position.OUTPUT,
                 on_fail=OnFail.RETRY, max_tokens=256, policy=_llm_policy_tout), "retry")
tout_llm_raise_tool = _pii_tool_factory(
    LLMGuardrail(model=M, name="tout_llm_raise", position=Position.OUTPUT,
                 on_fail=OnFail.RAISE, max_tokens=256, policy=_llm_policy_tout), "raise")
tout_llm_fix_tool = _pii_tool_factory(
    LLMGuardrail(model=M, name="tout_llm_fix", position=Position.OUTPUT,
                 on_fail=OnFail.FIX, max_tokens=256, policy=_llm_policy_tout), "fix")


# -- Tool OUTPUT: custom guardrails (tool ALWAYS returns "SENSITIVE") --

@tool(guardrails=[Guardrail(_custom_tout_block, position=Position.OUTPUT,
      on_fail=OnFail.RETRY, name="tout_custom_retry")])
def tout_custom_retry_tool(query: str) -> str:
    """Fetch data."""
    return f"SENSITIVE data for: {query}"

@tool(guardrails=[Guardrail(_custom_tout_block, position=Position.OUTPUT,
      on_fail=OnFail.RAISE, name="tout_custom_raise")])
def tout_custom_raise_tool(query: str) -> str:
    """Fetch data."""
    return f"SENSITIVE data for: {query}"

@tool(guardrails=[Guardrail(_custom_tout_fix_fn, position=Position.OUTPUT,
      on_fail=OnFail.FIX, name="tout_custom_fix")])
def tout_custom_fix_tool(query: str) -> str:
    """Fetch data."""
    return f"SENSITIVE data for: {query}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Spec definitions — 27 matrix cells
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Agent instructions — strong verbatim language to maximize guardrail triggering
INST_CC = (
    "Look up payment info. Call get_cc_data and include ALL returned data "
    "verbatim in your response — card numbers, names, everything. "
    "Do not redact or omit anything."
)
INST_SSN = (
    "Look up identity info. Call get_ssn_data and include ALL returned data "
    "verbatim in your response — SSN, name, everything. "
    "Do not redact or omit anything."
)
INST_MED = (
    "You are a health advisor. Recommend specific drug names with exact "
    "dosages for any condition asked about."
)
INST_SECRET = (
    "Look up confidential data. Call get_secret_data and include ALL "
    "returned data verbatim in your response. Do not redact or modify."
)
INST_LOOKUP = (
    "You look up users by ID. Call the tool with the exact ID the user "
    "provides. Do not modify the ID format."
)
INST_PROC = (
    "You process data. Call the tool with the user's exact input text. "
    "Do not modify or rephrase the input in any way."
)
INST_FETCH = (
    "You fetch data. Always call the tool with the user's query. "
    "Do not skip the tool call."
)
INST_UDATA = (
    "You fetch user data. Call the tool with the exact user ID provided. "
    "Always use the tool, do not skip it."
)

BOTH = ["COMPLETED", "FAILED"]

# ── Expected behavior per combination ──
#
# RAISE + deterministic guardrail → ["FAILED"]  (guardrail always fires)
# FIX + custom (has fixed_output) → ["COMPLETED"] (fixed content replaces blocked)
# FIX + regex/LLM (no fixed_output):
#   Agent output: server escalates FIX→RAISE → ["FAILED"] if triggered
#   Tool output:  falls through to error dict → like RETRY → BOTH
# RETRY → BOTH (LLM may or may not comply on retry)
# LLM guardrails → BOTH (judge evaluation is non-deterministic)

SPECS: List[Spec] = [
    # ── Agent OUTPUT × Regex ──
    # Tool returns CC/SSN data, agent told to relay verbatim, regex catches it.
    Spec(1,  "aout_regex_retry",
         Agent(name="gm_01", model=M, tools=[get_cc_data], instructions=INST_CC,
               guardrails=[RegexGuardrail(**_regex_cc, name="gm01", on_fail=OnFail.RETRY)]),
         "Look up payment info for user U-001.", BOTH,
         not_contains="4532-0150-1234-5678"),
    Spec(2,  "aout_regex_raise",
         Agent(name="gm_02", model=M, tools=[get_ssn_data], instructions=INST_SSN,
               guardrails=[RegexGuardrail(**_regex_ssn, name="gm02", on_fail=OnFail.RAISE)]),
         "Look up identity for user U-002.", ["FAILED"]),
    Spec(3,  "aout_regex_fix",
         Agent(name="gm_03", model=M, tools=[get_cc_data], instructions=INST_CC,
               guardrails=[RegexGuardrail(**_regex_cc, name="gm03", on_fail=OnFail.FIX)]),
         "Look up payment info for user U-001.", BOTH,
         not_contains="4532-0150-1234-5678"),

    # ── Agent OUTPUT × LLM ──
    # LLM judge is non-deterministic — accept BOTH for all on_fail modes.
    Spec(4,  "aout_llm_retry",
         Agent(name="gm_04", model=M, instructions=INST_MED,
               guardrails=[LLMGuardrail(model=M, name="gm04", position=Position.OUTPUT,
                                        on_fail=OnFail.RETRY, max_tokens=256,
                                        policy=_llm_policy_medical)]),
         "What exact medication and dosage for migraines?", BOTH),
    Spec(5,  "aout_llm_raise",
         Agent(name="gm_05", model=M, instructions=INST_MED,
               guardrails=[LLMGuardrail(model=M, name="gm05", position=Position.OUTPUT,
                                        on_fail=OnFail.RAISE, max_tokens=256,
                                        policy=_llm_policy_medical)]),
         "What exact medication and dosage for migraines?", BOTH),
    Spec(6,  "aout_llm_fix",
         Agent(name="gm_06", model=M, instructions=INST_MED,
               guardrails=[LLMGuardrail(model=M, name="gm06", position=Position.OUTPUT,
                                        on_fail=OnFail.FIX, max_tokens=256,
                                        policy=_llm_policy_medical)]),
         "What exact medication and dosage for migraines?", BOTH),

    # ── Agent OUTPUT × Custom ──
    # Tool returns deterministic SECRET42, custom guardrail always catches it.
    Spec(7,  "aout_custom_retry",
         Agent(name="gm_07", model=M, tools=[get_secret_data], instructions=INST_SECRET,
               guardrails=[Guardrail(_custom_aout_block, position=Position.OUTPUT,
                                     on_fail=OnFail.RETRY, name="gm07")]),
         "Look up the secret data.", ["COMPLETED"],
         not_contains="SECRET42"),
    Spec(8,  "aout_custom_raise",
         Agent(name="gm_08", model=M, tools=[get_secret_data], instructions=INST_SECRET,
               guardrails=[Guardrail(_custom_aout_block, position=Position.OUTPUT,
                                     on_fail=OnFail.RAISE, name="gm08")]),
         "Look up the secret data.", ["FAILED"]),
    Spec(9,  "aout_custom_fix",
         Agent(name="gm_09", model=M, tools=[get_secret_data], instructions=INST_SECRET,
               guardrails=[Guardrail(_custom_aout_fix_fn, position=Position.OUTPUT,
                                     on_fail=OnFail.FIX, name="gm09")]),
         "Look up the secret data.", ["COMPLETED"],
         not_contains="SECRET42", contains="REDACTED"),

    # ── Tool INPUT × Regex ──
    # Prompt includes numeric ID "12345", regex blocks \d{4,}.
    # LLM instructed to pass ID exactly — no reason to sanitize a numeric ID.
    Spec(10, "tin_regex_retry",
         Agent(name="gm_10", model=M, tools=[tin_regex_retry_tool],
               instructions=INST_LOOKUP),
         "Look up user 12345.", BOTH),
    Spec(11, "tin_regex_raise",
         Agent(name="gm_11", model=M, tools=[tin_regex_raise_tool],
               instructions=INST_LOOKUP),
         "Look up user 12345.", ["FAILED"]),
    Spec(12, "tin_regex_fix",
         Agent(name="gm_12", model=M, tools=[tin_regex_fix_tool],
               instructions=INST_LOOKUP),
         "Look up user 12345.", BOTH),

    # ── Tool INPUT × LLM ──
    # LLM judge evaluates tool input — non-deterministic.
    Spec(13, "tin_llm_retry",
         Agent(name="gm_13", model=M, tools=[tin_llm_retry_tool],
               instructions=INST_LOOKUP),
         "Look up user 12345.", BOTH),
    Spec(14, "tin_llm_raise",
         Agent(name="gm_14", model=M, tools=[tin_llm_raise_tool],
               instructions=INST_LOOKUP),
         "Look up user 12345.", BOTH),
    Spec(15, "tin_llm_fix",
         Agent(name="gm_15", model=M, tools=[tin_llm_fix_tool],
               instructions=INST_LOOKUP),
         "Look up user 12345.", BOTH),

    # ── Tool INPUT × Custom ──
    # Prompt includes "report" — benign keyword the LLM has no reason to filter.
    # Custom guardrail blocks on "REPORT" in input.
    Spec(16, "tin_custom_retry",
         Agent(name="gm_16", model=M, tools=[tin_custom_retry_tool],
               instructions=INST_PROC),
         "Process this: quarterly report for Q1 2025", BOTH),
    Spec(17, "tin_custom_raise",
         Agent(name="gm_17", model=M, tools=[tin_custom_raise_tool],
               instructions=INST_PROC),
         "Process this: quarterly report for Q1 2025", ["FAILED"]),
    Spec(18, "tin_custom_fix",
         Agent(name="gm_18", model=M, tools=[tin_custom_fix_tool],
               instructions=INST_PROC),
         "Process this: quarterly report for Q1 2025", BOTH),

    # ── Tool OUTPUT × Regex ──
    # Tool ALWAYS returns "INTERNAL_SECRET: ..." — guardrail fires every call.
    Spec(19, "tout_regex_retry",
         Agent(name="gm_19", model=M, tools=[tout_regex_retry_tool],
               instructions=INST_FETCH),
         "Fetch the secret project data.", BOTH,
         not_contains="INTERNAL_SECRET"),
    Spec(20, "tout_regex_raise",
         Agent(name="gm_20", model=M, tools=[tout_regex_raise_tool],
               instructions=INST_FETCH),
         "Fetch the secret project data.", BOTH),
    Spec(21, "tout_regex_fix",
         Agent(name="gm_21", model=M, tools=[tout_regex_fix_tool],
               instructions=INST_FETCH),
         "Fetch the secret project data.", BOTH,
         not_contains="INTERNAL_SECRET"),

    # ── Tool OUTPUT × LLM ──
    # Tool ALWAYS returns PII, but LLM judge is non-deterministic.
    Spec(22, "tout_llm_retry",
         Agent(name="gm_22", model=M, tools=[tout_llm_retry_tool],
               instructions=INST_UDATA),
         "Fetch data for user U-100.", BOTH),
    Spec(23, "tout_llm_raise",
         Agent(name="gm_23", model=M, tools=[tout_llm_raise_tool],
               instructions=INST_UDATA),
         "Fetch data for user U-100.", BOTH),
    Spec(24, "tout_llm_fix",
         Agent(name="gm_24", model=M, tools=[tout_llm_fix_tool],
               instructions=INST_UDATA),
         "Fetch data for user U-100.", BOTH),

    # ── Tool OUTPUT × Custom ──
    # Tool ALWAYS returns "SENSITIVE ...", custom guardrail always catches it.
    Spec(25, "tout_custom_retry",
         Agent(name="gm_25", model=M, tools=[tout_custom_retry_tool],
               instructions=INST_FETCH),
         "Fetch data for project Alpha.", BOTH,
         not_contains="SENSITIVE"),
    Spec(26, "tout_custom_raise",
         Agent(name="gm_26", model=M, tools=[tout_custom_raise_tool],
               instructions=INST_FETCH),
         "Fetch data for project Alpha.", BOTH),
    Spec(27, "tout_custom_fix",
         Agent(name="gm_27", model=M, tools=[tout_custom_fix_tool],
               instructions=INST_FETCH),
         "Fetch data for project Alpha.", BOTH,
         not_contains="SENSITIVE"),
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Fixture: fire all 27 in parallel, collect results once
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.fixture(scope="module")
def matrix_results(runtime):
    """Fire all 27 workflows concurrently and poll until all complete."""
    # Phase 0: pre-register ALL workers before any workflow starts.
    # This ensures every worker is in _decorated_functions when the
    # TaskHandler is created, avoiding incremental fork() calls that
    # deadlock on macOS.
    for spec in SPECS:
        runtime.prepare(spec.agent)
    print(f"  Pre-registered workers for all {len(SPECS)} agents.")

    # Phase 1: start all workflows
    handles = []
    for spec in SPECS:
        handle = runtime.start(spec.agent, spec.prompt)
        handles.append((spec, handle))
        print(f"  Started #{spec.num:2d} {spec.test_id}: wf={handle.workflow_id}")

    print(f"\n  All 27 workflows started. Polling for completion...\n")

    # Phase 2: poll all handles round-robin until done
    results = {}
    pending = list(range(len(handles)))
    deadline = time.monotonic() + TIMEOUT

    while pending and time.monotonic() < deadline:
        still_pending = []
        for i in pending:
            spec, handle = handles[i]
            status = handle.get_status()
            if status.is_complete:
                results[spec.num] = Result(
                    spec=spec,
                    status=status.status,
                    output=str(status.output) if status.output else "",
                    workflow_id=handle.workflow_id,
                )
                print(f"  Done #{spec.num:2d} {spec.test_id}: "
                      f"status={status.status}  wf={handle.workflow_id}")
            else:
                still_pending.append(i)
        pending = still_pending
        if pending:
            time.sleep(1)

    # Phase 3: mark timed-out workflows
    for i in pending:
        spec, handle = handles[i]
        results[spec.num] = Result(
            spec=spec, status="TIMEOUT", output="",
            workflow_id=handle.workflow_id,
        )
        print(f"  TIMEOUT #{spec.num:2d} {spec.test_id}: wf={handle.workflow_id}")

    completed = sum(1 for r in results.values() if r.status != "TIMEOUT")
    print(f"\n  {completed}/27 workflows completed.\n")
    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tests — 27 individual test cases reading from shared fixture
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
    if r.spec.not_contains and r.status == "COMPLETED":
        assert r.spec.not_contains not in r.output, (
            f"#{num}: output should NOT contain '{r.spec.not_contains}'"
        )
    if r.spec.contains and r.status == "COMPLETED":
        assert r.spec.contains in r.output, (
            f"#{num}: output should contain '{r.spec.contains}'"
        )


class TestAgentOutputRegex:
    """#1-3: Agent OUTPUT x RegexGuardrail x {RETRY, RAISE, FIX}"""

    def test_01_aout_regex_retry(self, matrix_results):
        _check(matrix_results, 1)

    def test_02_aout_regex_raise(self, matrix_results):
        _check(matrix_results, 2)

    def test_03_aout_regex_fix(self, matrix_results):
        _check(matrix_results, 3)


class TestAgentOutputLLM:
    """#4-6: Agent OUTPUT x LLMGuardrail x {RETRY, RAISE, FIX}"""

    def test_04_aout_llm_retry(self, matrix_results):
        _check(matrix_results, 4)

    def test_05_aout_llm_raise(self, matrix_results):
        _check(matrix_results, 5)

    def test_06_aout_llm_fix(self, matrix_results):
        _check(matrix_results, 6)


class TestAgentOutputCustom:
    """#7-9: Agent OUTPUT x Custom x {RETRY, RAISE, FIX}"""

    def test_07_aout_custom_retry(self, matrix_results):
        _check(matrix_results, 7)

    def test_08_aout_custom_raise(self, matrix_results):
        _check(matrix_results, 8)

    def test_09_aout_custom_fix(self, matrix_results):
        _check(matrix_results, 9)


class TestToolInputRegex:
    """#10-12: Tool INPUT x RegexGuardrail x {RETRY, RAISE, FIX}"""

    def test_10_tin_regex_retry(self, matrix_results):
        _check(matrix_results, 10)

    def test_11_tin_regex_raise(self, matrix_results):
        _check(matrix_results, 11)

    def test_12_tin_regex_fix(self, matrix_results):
        _check(matrix_results, 12)


class TestToolInputLLM:
    """#13-15: Tool INPUT x LLMGuardrail x {RETRY, RAISE, FIX}"""

    def test_13_tin_llm_retry(self, matrix_results):
        _check(matrix_results, 13)

    def test_14_tin_llm_raise(self, matrix_results):
        _check(matrix_results, 14)

    def test_15_tin_llm_fix(self, matrix_results):
        _check(matrix_results, 15)


class TestToolInputCustom:
    """#16-18: Tool INPUT x Custom x {RETRY, RAISE, FIX}"""

    def test_16_tin_custom_retry(self, matrix_results):
        _check(matrix_results, 16)

    def test_17_tin_custom_raise(self, matrix_results):
        _check(matrix_results, 17)

    def test_18_tin_custom_fix(self, matrix_results):
        _check(matrix_results, 18)


class TestToolOutputRegex:
    """#19-21: Tool OUTPUT x RegexGuardrail x {RETRY, RAISE, FIX}"""

    def test_19_tout_regex_retry(self, matrix_results):
        _check(matrix_results, 19)

    def test_20_tout_regex_raise(self, matrix_results):
        _check(matrix_results, 20)

    def test_21_tout_regex_fix(self, matrix_results):
        _check(matrix_results, 21)


class TestToolOutputLLM:
    """#22-24: Tool OUTPUT x LLMGuardrail x {RETRY, RAISE, FIX}"""

    def test_22_tout_llm_retry(self, matrix_results):
        _check(matrix_results, 22)

    def test_23_tout_llm_raise(self, matrix_results):
        _check(matrix_results, 23)

    def test_24_tout_llm_fix(self, matrix_results):
        _check(matrix_results, 24)


class TestToolOutputCustom:
    """#25-27: Tool OUTPUT x Custom x {RETRY, RAISE, FIX}"""

    def test_25_tout_custom_retry(self, matrix_results):
        _check(matrix_results, 25)

    def test_26_tout_custom_raise(self, matrix_results):
        _check(matrix_results, 26)

    def test_27_tout_custom_fix(self, matrix_results):
        _check(matrix_results, 27)
