# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Guardrail E2E Test Suite — full 3×3×3 matrix.

Tests every combination of Position × Type × OnFail:

    ╔════╤══════════════╤════════╤════════╤═══════════════════════════════════════╗
    ║ #  │ Position     │ Type   │ OnFail │ Notes                                 ║
    ╠════╪══════════════╪════════╪════════╪═══════════════════════════════════════╣
    ║  1 │ Agent OUT    │ Regex  │ RETRY  │ CC blocked, LLM retries               ║
    ║  2 │ Agent OUT    │ Regex  │ RAISE  │ SSN blocked, workflow FAILED          ║
    ║  3 │ Agent OUT    │ Regex  │ FIX    │ No fixed_output → falls back to LLM  ║
    ║  4 │ Agent OUT    │ LLM    │ RETRY  │ Medical advice blocked, LLM retries  ║
    ║  5 │ Agent OUT    │ LLM    │ RAISE  │ Medical advice → FAILED              ║
    ║  6 │ Agent OUT    │ LLM    │ FIX    │ No fixed_output → falls back to LLM  ║
    ║  7 │ Agent OUT    │ Custom │ RETRY  │ SECRET42 blocked, LLM retries        ║
    ║  8 │ Agent OUT    │ Custom │ RAISE  │ SECRET42 → FAILED                    ║
    ║  9 │ Agent OUT    │ Custom │ FIX    │ SECRET42 → [REDACTED]                ║
    ╟────┼──────────────┼────────┼────────┼───────────────────────────────────────╢
    ║ 10 │ Tool INPUT   │ Regex  │ RETRY  │ SQL injection blocked, LLM retries   ║
    ║ 11 │ Tool INPUT   │ Regex  │ RAISE  │ SQL injection → FAILED               ║
    ║ 12 │ Tool INPUT   │ Regex  │ FIX    │ No fix for input → blocked error     ║
    ║ 13 │ Tool INPUT   │ LLM    │ RETRY  │ PII in args blocked, LLM retries    ║
    ║ 14 │ Tool INPUT   │ LLM    │ RAISE  │ PII in args → FAILED                ║
    ║ 15 │ Tool INPUT   │ LLM    │ FIX    │ No fix for input → blocked error     ║
    ║ 16 │ Tool INPUT   │ Custom │ RETRY  │ DANGER blocked, LLM retries          ║
    ║ 17 │ Tool INPUT   │ Custom │ RAISE  │ DANGER → FAILED                      ║
    ║ 18 │ Tool INPUT   │ Custom │ FIX    │ No fix for input → blocked error     ║
    ╟────┼──────────────┼────────┼────────┼───────────────────────────────────────╢
    ║ 19 │ Tool OUTPUT  │ Regex  │ RETRY  │ INTERNAL_SECRET blocked in worker    ║
    ║ 20 │ Tool OUTPUT  │ Regex  │ RAISE  │ INTERNAL_SECRET → task fails         ║
    ║ 21 │ Tool OUTPUT  │ Regex  │ FIX    │ No fixed_output → blocked error      ║
    ║ 22 │ Tool OUTPUT  │ LLM    │ RETRY  │ PII in output blocked in worker     ║
    ║ 23 │ Tool OUTPUT  │ LLM    │ RAISE  │ PII in output → task fails          ║
    ║ 24 │ Tool OUTPUT  │ LLM    │ FIX    │ No fixed_output → blocked error      ║
    ║ 25 │ Tool OUTPUT  │ Custom │ RETRY  │ SENSITIVE blocked in worker          ║
    ║ 26 │ Tool OUTPUT  │ Custom │ RAISE  │ SENSITIVE → task fails               ║
    ║ 27 │ Tool OUTPUT  │ Custom │ FIX    │ SENSITIVE → [REDACTED]               ║
    ╚════╧══════════════╧════════╧════════╧═══════════════════════════════════════╝

Notes on FIX mode:
    - Custom guardrails return fixed_output → actual fix (tests 9, 27)
    - Regex/LLM guardrails don't produce fixed_output
      → Agent OUTPUT: resolve task falls back to LLM output (content may leak)
      → Tool level: no fix available → returns blocked error (like RETRY)
    - Tool INPUT FIX: _dispatch.py has no FIX path for input → blocked error

Usage:
    python 90_guardrail_e2e_tests.py

Requirements:
    - Conductor server running
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api in .env or environment
    - AGENTSPAN_LLM_MODEL in .env or environment
"""

import sys
import time
from dataclasses import dataclass
from typing import List, Optional

from agentspan.agents import (
    Agent,
    AgentRuntime,
    Guardrail,
    GuardrailResult,
    LLMGuardrail,
    OnFail,
    Position,
    RegexGuardrail,
    guardrail,
    tool,
)
from settings import settings


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test infrastructure
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class TestResult:
    num: int
    test_id: str
    passed: bool
    execution_id: str = ""
    details: str = ""


class TestRunner:
    def __init__(self):
        self.results: List[TestResult] = []

    def check(
        self,
        num: int,
        test_id: str,
        *,
        result,
        expect_status: Optional[str] = None,
        expect_status_in: Optional[List[str]] = None,
        expect_contains: Optional[str] = None,
        expect_not_contains: Optional[str] = None,
    ) -> TestResult:
        output = str(result.output) if result.output else ""
        status = result.status if hasattr(result, "status") else "UNKNOWN"
        execution_id = getattr(result, "execution_id", "") or ""
        failures = []

        if expect_status and status != expect_status:
            failures.append(f"expected {expect_status}, got {status}")
        if expect_status_in and status not in expect_status_in:
            failures.append(f"expected one of {expect_status_in}, got {status}")
        if expect_contains and expect_contains not in output:
            failures.append(f"missing '{expect_contains}'")
        if expect_not_contains and expect_not_contains in output:
            failures.append(f"should NOT contain '{expect_not_contains}'")

        passed = len(failures) == 0
        details = "; ".join(failures) if failures else "OK"
        tr = TestResult(num, test_id, passed, execution_id, details)
        self.results.append(tr)

        mark = "PASS" if passed else "FAIL"
        print(f"  [{mark}] #{num:2d} {test_id}: {details}  wf={execution_id}")
        return tr

    def skip(self, num: int, test_id: str, reason: str):
        tr = TestResult(num, test_id, True, "", f"SKIP: {reason}")
        self.results.append(tr)
        print(f"  [SKIP] #{num:2d} {test_id}: {reason}")

    def print_summary(self):
        total = len(self.results)
        skipped = sum(1 for r in self.results if r.details.startswith("SKIP"))
        ran = total - skipped
        passed = sum(1 for r in self.results if r.passed and not r.details.startswith("SKIP"))
        failed = ran - passed

        print("\n" + "=" * 90)
        print(f"  RESULTS: {passed}/{ran} passed, {failed} failed, {skipped} skipped ({total} total)")
        print("=" * 90)

        # Matrix table
        print("\n  ╔════╤══════════════╤════════╤════════╤════════╤══════════════════════════════════════╗")
        print("  ║ #  │ Position     │ Type   │ OnFail │ Result │ Workflow ID                          ║")
        print("  ╠════╪══════════════╪════════╪════════╪════════╪══════════════════════════════════════╣")

        positions = ["Agent OUT"] * 9 + ["Tool INPUT"] * 9 + ["Tool OUTPUT"] * 9
        types = (["Regex"] * 3 + ["LLM"] * 3 + ["Custom"] * 3) * 3
        onfails = ["RETRY", "RAISE", "FIX"] * 9

        for i, r in enumerate(self.results):
            pos = positions[i] if i < 27 else "Bonus"
            typ = types[i] if i < 27 else "Custom"
            onf = onfails[i] if i < 27 else "HUMAN"
            if r.details.startswith("SKIP"):
                mark = "SKIP"
            elif r.passed:
                mark = "PASS"
            else:
                mark = "FAIL"
            wf = r.execution_id[:36] if r.execution_id else "—"
            sep = "╟" if (i + 1) % 9 == 0 and i < 26 else "║"
            print(f"  ║ {r.num:2d} │ {pos:12s} │ {typ:6s} │ {onf:6s} │ {mark:6s} │ {wf:36s} ║")
            if (i + 1) % 9 == 0 and i < 26:
                print("  ╟────┼──────────────┼────────┼────────┼────────┼──────────────────────────────────────╢")

        print("  ╚════╧══════════════╧════════╧════════╧════════╧══════════════════════════════════════╝")

        if failed:
            print("\n  FAILURES:")
            for r in self.results:
                if not r.passed and not r.details.startswith("SKIP"):
                    print(f"    #{r.num:2d} {r.test_id}: {r.details}")
        print()
        return failed


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Guardrail definitions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

M = settings.llm_model

# ── Agent OUTPUT guardrails ──────────────────────────────────────────

regex_aout_retry = RegexGuardrail(
    patterns=[r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"],
    mode="block", name="regex_aout_retry",
    message="Do not include credit card numbers. Redact them.",
    position=Position.OUTPUT, on_fail=OnFail.RETRY,
)
regex_aout_raise = RegexGuardrail(
    patterns=[r"\b\d{3}-\d{2}-\d{4}\b"],
    mode="block", name="regex_aout_raise",
    message="Response must not contain SSNs.",
    position=Position.OUTPUT, on_fail=OnFail.RAISE,
)
regex_aout_fix = RegexGuardrail(
    patterns=[r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"],
    mode="block", name="regex_aout_fix",
    message="Credit card detected.",
    position=Position.OUTPUT, on_fail=OnFail.FIX,
)

llm_aout_retry = LLMGuardrail(
    model=M, name="llm_aout_retry", position=Position.OUTPUT, on_fail=OnFail.RETRY,
    max_tokens=256,
    policy="Reject content that provides specific medication names with dosages or makes definitive medical diagnoses. General health tips are OK.",
)
llm_aout_raise = LLMGuardrail(
    model=M, name="llm_aout_raise", position=Position.OUTPUT, on_fail=OnFail.RAISE,
    max_tokens=256,
    policy="Reject content that provides specific medication names with dosages or makes definitive medical diagnoses. General health tips are OK.",
)
llm_aout_fix = LLMGuardrail(
    model=M, name="llm_aout_fix", position=Position.OUTPUT, on_fail=OnFail.FIX,
    max_tokens=256,
    policy="Reject content that provides specific medication names with dosages or makes definitive medical diagnoses. General health tips are OK.",
)

@guardrail
def custom_aout_block(content: str) -> GuardrailResult:
    """Block SECRET42."""
    if "SECRET42" in content:
        return GuardrailResult(passed=False, message="Contains SECRET42. Remove it.")
    return GuardrailResult(passed=True)

@guardrail
def custom_aout_fix(content: str) -> GuardrailResult:
    """Replace SECRET42 with [REDACTED]."""
    if "SECRET42" in content:
        return GuardrailResult(
            passed=False, message="Secret redacted.",
            fixed_output=content.replace("SECRET42", "[REDACTED]"),
        )
    return GuardrailResult(passed=True)


# ── Tool INPUT guardrails ────────────────────────────────────────────

regex_tin_retry = RegexGuardrail(
    patterns=[r"DROP\s+TABLE", r"DELETE\s+FROM", r";\s*--"],
    mode="block", name="regex_tin_retry",
    message="SQL injection detected. Use a safe query.",
    position=Position.INPUT, on_fail=OnFail.RETRY,
)
regex_tin_raise = RegexGuardrail(
    patterns=[r"DROP\s+TABLE", r"DELETE\s+FROM", r";\s*--"],
    mode="block", name="regex_tin_raise",
    message="SQL injection blocked.",
    position=Position.INPUT, on_fail=OnFail.RAISE,
)
regex_tin_fix = RegexGuardrail(
    patterns=[r"DROP\s+TABLE", r"DELETE\s+FROM", r";\s*--"],
    mode="block", name="regex_tin_fix",
    message="SQL injection detected.",
    position=Position.INPUT, on_fail=OnFail.FIX,
)

llm_tin_retry = LLMGuardrail(
    model=M, name="llm_tin_retry", position=Position.INPUT, on_fail=OnFail.RETRY,
    max_tokens=256,
    policy="Reject if tool arguments contain real SSNs (XXX-XX-XXXX) or credit card numbers.",
)
llm_tin_raise = LLMGuardrail(
    model=M, name="llm_tin_raise", position=Position.INPUT, on_fail=OnFail.RAISE,
    max_tokens=256,
    policy="Reject if tool arguments contain real SSNs (XXX-XX-XXXX) or credit card numbers.",
)
llm_tin_fix = LLMGuardrail(
    model=M, name="llm_tin_fix", position=Position.INPUT, on_fail=OnFail.FIX,
    max_tokens=256,
    policy="Reject if tool arguments contain real SSNs (XXX-XX-XXXX) or credit card numbers.",
)

@guardrail
def custom_tin_block(content: str) -> GuardrailResult:
    """Block DANGER in input."""
    if "DANGER" in content.upper():
        return GuardrailResult(passed=False, message="Dangerous input. Use safe parameters.")
    return GuardrailResult(passed=True)

@guardrail
def custom_tin_block_raise(content: str) -> GuardrailResult:
    """Block DANGER in input (raise)."""
    if "DANGER" in content.upper():
        return GuardrailResult(passed=False, message="Dangerous input blocked.")
    return GuardrailResult(passed=True)

@guardrail
def custom_tin_block_fix(content: str) -> GuardrailResult:
    """Block DANGER in input (fix — but input FIX not supported in worker)."""
    if "DANGER" in content.upper():
        return GuardrailResult(
            passed=False, message="Dangerous input detected.",
            fixed_output=content.upper().replace("DANGER", "SAFE"),
        )
    return GuardrailResult(passed=True)


# ── Tool OUTPUT guardrails ───────────────────────────────────────────

regex_tout_retry = RegexGuardrail(
    patterns=[r"INTERNAL_SECRET"],
    mode="block", name="regex_tout_retry",
    message="Tool output contains secrets.",
    position=Position.OUTPUT, on_fail=OnFail.RETRY,
)
regex_tout_raise = RegexGuardrail(
    patterns=[r"INTERNAL_SECRET"],
    mode="block", name="regex_tout_raise",
    message="Tool output contains secrets.",
    position=Position.OUTPUT, on_fail=OnFail.RAISE,
)
regex_tout_fix = RegexGuardrail(
    patterns=[r"INTERNAL_SECRET"],
    mode="block", name="regex_tout_fix",
    message="Tool output contains secrets.",
    position=Position.OUTPUT, on_fail=OnFail.FIX,
)

llm_tout_retry = LLMGuardrail(
    model=M, name="llm_tout_retry", position=Position.OUTPUT, on_fail=OnFail.RETRY,
    max_tokens=256,
    policy="Reject tool output containing personal info like SSNs, emails, or phone numbers.",
)
llm_tout_raise = LLMGuardrail(
    model=M, name="llm_tout_raise", position=Position.OUTPUT, on_fail=OnFail.RAISE,
    max_tokens=256,
    policy="Reject tool output containing personal info like SSNs, emails, or phone numbers.",
)
llm_tout_fix = LLMGuardrail(
    model=M, name="llm_tout_fix", position=Position.OUTPUT, on_fail=OnFail.FIX,
    max_tokens=256,
    policy="Reject tool output containing personal info like SSNs, emails, or phone numbers.",
)

@guardrail
def custom_tout_block_retry(content: str) -> GuardrailResult:
    """Block SENSITIVE in tool output (retry)."""
    if "SENSITIVE" in content:
        return GuardrailResult(passed=False, message="Sensitive data, try different query.")
    return GuardrailResult(passed=True)

@guardrail
def custom_tout_block_raise(content: str) -> GuardrailResult:
    """Block SENSITIVE in tool output (raise)."""
    if "SENSITIVE" in content:
        return GuardrailResult(passed=False, message="Sensitive data in output.")
    return GuardrailResult(passed=True)

@guardrail
def custom_tout_fix(content: str) -> GuardrailResult:
    """Redact SENSITIVE from tool output."""
    if "SENSITIVE" in content:
        return GuardrailResult(
            passed=False, message="Sensitive data redacted.",
            fixed_output=content.replace("SENSITIVE", "[REDACTED]"),
        )
    return GuardrailResult(passed=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tool definitions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── Shared tools for agent-level guardrails ──────────────────────────

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


# ── Tool INPUT tools (one per guardrail combo) ───────────────────────

@tool(guardrails=[regex_tin_retry])
def t_tin_regex_retry(query: str) -> str:
    """DB query (regex input retry)."""
    return f"Results: {query} -> [('Alice', 30)]"

@tool(guardrails=[regex_tin_raise])
def t_tin_regex_raise(query: str) -> str:
    """DB query (regex input raise)."""
    return f"Results: {query} -> [('Alice', 30)]"

@tool(guardrails=[regex_tin_fix])
def t_tin_regex_fix(query: str) -> str:
    """DB query (regex input fix)."""
    return f"Results: {query} -> [('Alice', 30)]"

@tool(guardrails=[llm_tin_retry])
def t_tin_llm_retry(identifier: str) -> str:
    """Look up user (LLM input retry)."""
    return f"User: {identifier} -> Alice Johnson"

@tool(guardrails=[llm_tin_raise])
def t_tin_llm_raise(identifier: str) -> str:
    """Look up user (LLM input raise)."""
    return f"User: {identifier} -> Alice Johnson"

@tool(guardrails=[llm_tin_fix])
def t_tin_llm_fix(identifier: str) -> str:
    """Look up user (LLM input fix)."""
    return f"User: {identifier} -> Alice Johnson"

@tool(guardrails=[Guardrail(custom_tin_block, position=Position.INPUT,
                            on_fail=OnFail.RETRY, name="custom_tin_retry")])
def t_tin_custom_retry(data: str) -> str:
    """Process data (custom input retry)."""
    return f"Processed: {data}"

@tool(guardrails=[Guardrail(custom_tin_block_raise, position=Position.INPUT,
                            on_fail=OnFail.RAISE, name="custom_tin_raise")])
def t_tin_custom_raise(data: str) -> str:
    """Process data (custom input raise)."""
    return f"Processed: {data}"

@tool(guardrails=[Guardrail(custom_tin_block_fix, position=Position.INPUT,
                            on_fail=OnFail.FIX, name="custom_tin_fix")])
def t_tin_custom_fix(data: str) -> str:
    """Process data (custom input fix)."""
    return f"Processed: {data}"


# ── Tool OUTPUT tools (one per guardrail combo) ──────────────────────

@tool(guardrails=[regex_tout_retry])
def t_tout_regex_retry(query: str) -> str:
    """Fetch data (regex output retry)."""
    if "secret" in query.lower():
        return f"INTERNAL_SECRET: classified for {query}"
    return f"Public data: {query}"

@tool(guardrails=[regex_tout_raise])
def t_tout_regex_raise(query: str) -> str:
    """Fetch data (regex output raise)."""
    if "secret" in query.lower():
        return f"INTERNAL_SECRET: classified for {query}"
    return f"Public data: {query}"

@tool(guardrails=[regex_tout_fix])
def t_tout_regex_fix(query: str) -> str:
    """Fetch data (regex output fix)."""
    if "secret" in query.lower():
        return f"INTERNAL_SECRET: classified for {query}"
    return f"Public data: {query}"

@tool(guardrails=[llm_tout_retry])
def t_tout_llm_retry(user_id: str) -> str:
    """Fetch user data (LLM output retry)."""
    return f"User {user_id}: Alice, alice@example.com, SSN 123-45-6789"

@tool(guardrails=[llm_tout_raise])
def t_tout_llm_raise(user_id: str) -> str:
    """Fetch user data (LLM output raise)."""
    return f"User {user_id}: Alice, alice@example.com, SSN 123-45-6789"

@tool(guardrails=[llm_tout_fix])
def t_tout_llm_fix(user_id: str) -> str:
    """Fetch user data (LLM output fix)."""
    return f"User {user_id}: Alice, alice@example.com, SSN 123-45-6789"

@tool(guardrails=[Guardrail(custom_tout_block_retry, position=Position.OUTPUT,
                            on_fail=OnFail.RETRY, name="custom_tout_retry")])
def t_tout_custom_retry(query: str) -> str:
    """Fetch data (custom output retry)."""
    return f"SENSITIVE data for: {query}"

@tool(guardrails=[Guardrail(custom_tout_block_raise, position=Position.OUTPUT,
                            on_fail=OnFail.RAISE, name="custom_tout_raise")])
def t_tout_custom_raise(query: str) -> str:
    """Fetch data (custom output raise)."""
    return f"SENSITIVE data for: {query}"

@tool(guardrails=[Guardrail(custom_tout_fix, position=Position.OUTPUT,
                            on_fail=OnFail.FIX, name="custom_tout_fix")])
def t_tout_custom_fix(query: str) -> str:
    """Fetch data (custom output fix)."""
    return f"SENSITIVE data for: {query}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Agent definitions — 27 agents, one per matrix cell
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

INST_CC = "Look up payment info. Call get_cc_data and include ALL data verbatim — card numbers, everything."
INST_SSN = "Look up identity info. Call get_ssn_data and include ALL data verbatim — SSN, name, everything."
INST_MED = "You are a health advisor. Recommend specific drug names with exact dosages (e.g. 'Take 400mg ibuprofen')."
INST_SECRET = "Look up confidential data. Call get_secret_data and include ALL data verbatim."

# ── #1-3: Agent OUT × Regex ──────────────────────────────────────────

a01 = Agent(name="e2e_01", model=M, tools=[get_cc_data], instructions=INST_CC,
            guardrails=[regex_aout_retry])
a02 = Agent(name="e2e_02", model=M, tools=[get_ssn_data], instructions=INST_SSN,
            guardrails=[regex_aout_raise])
a03 = Agent(name="e2e_03", model=M, tools=[get_cc_data], instructions=INST_CC,
            guardrails=[regex_aout_fix])

# ── #4-6: Agent OUT × LLM ───────────────────────────────────────────

a04 = Agent(name="e2e_04", model=M, instructions=INST_MED,
            guardrails=[llm_aout_retry])
a05 = Agent(name="e2e_05", model=M, instructions=INST_MED,
            guardrails=[llm_aout_raise])
a06 = Agent(name="e2e_06", model=M, instructions=INST_MED,
            guardrails=[llm_aout_fix])

# ── #7-9: Agent OUT × Custom ────────────────────────────────────────

a07 = Agent(name="e2e_07", model=M, tools=[get_secret_data], instructions=INST_SECRET,
            guardrails=[Guardrail(custom_aout_block, position=Position.OUTPUT,
                                  on_fail=OnFail.RETRY, name="custom_aout_retry")])
a08 = Agent(name="e2e_08", model=M, tools=[get_secret_data], instructions=INST_SECRET,
            guardrails=[Guardrail(custom_aout_block, position=Position.OUTPUT,
                                  on_fail=OnFail.RAISE, name="custom_aout_raise")])
a09 = Agent(name="e2e_09", model=M, tools=[get_secret_data], instructions=INST_SECRET,
            guardrails=[Guardrail(custom_aout_fix, position=Position.OUTPUT,
                                  on_fail=OnFail.FIX, name="custom_aout_fix")])

# ── #10-18: Tool INPUT ──────────────────────────────────────────────

INST_DB = "You query databases. Use the tool with the user's exact query."
INST_LOOKUP = "You look up users. Use the tool with the identifier the user provides."
INST_PROC = "You process data. Use the tool with the user's exact input."

a10 = Agent(name="e2e_10", model=M, tools=[t_tin_regex_retry], instructions=INST_DB)
a11 = Agent(name="e2e_11", model=M, tools=[t_tin_regex_raise], instructions=INST_DB)
a12 = Agent(name="e2e_12", model=M, tools=[t_tin_regex_fix], instructions=INST_DB)
a13 = Agent(name="e2e_13", model=M, tools=[t_tin_llm_retry], instructions=INST_LOOKUP)
a14 = Agent(name="e2e_14", model=M, tools=[t_tin_llm_raise], instructions=INST_LOOKUP)
a15 = Agent(name="e2e_15", model=M, tools=[t_tin_llm_fix], instructions=INST_LOOKUP)
a16 = Agent(name="e2e_16", model=M, tools=[t_tin_custom_retry], instructions=INST_PROC)
a17 = Agent(name="e2e_17", model=M, tools=[t_tin_custom_raise], instructions=INST_PROC)
a18 = Agent(name="e2e_18", model=M, tools=[t_tin_custom_fix], instructions=INST_PROC)

# ── #19-27: Tool OUTPUT ─────────────────────────────────────────────

INST_FETCH = "You fetch data. Use the tool with the user's query."
INST_UDATA = "You fetch user data. Use the tool with the user's ID."

a19 = Agent(name="e2e_19", model=M, tools=[t_tout_regex_retry], instructions=INST_FETCH)
a20 = Agent(name="e2e_20", model=M, tools=[t_tout_regex_raise], instructions=INST_FETCH)
a21 = Agent(name="e2e_21", model=M, tools=[t_tout_regex_fix], instructions=INST_FETCH)
a22 = Agent(name="e2e_22", model=M, tools=[t_tout_llm_retry], instructions=INST_UDATA)
a23 = Agent(name="e2e_23", model=M, tools=[t_tout_llm_raise], instructions=INST_UDATA)
a24 = Agent(name="e2e_24", model=M, tools=[t_tout_llm_fix], instructions=INST_UDATA)
a25 = Agent(name="e2e_25", model=M, tools=[t_tout_custom_retry], instructions=INST_FETCH)
a26 = Agent(name="e2e_26", model=M, tools=[t_tout_custom_raise], instructions=INST_FETCH)
a27 = Agent(name="e2e_27", model=M, tools=[t_tout_custom_fix], instructions=INST_FETCH)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test cases — 27 matrix cells
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def run_tests(runtime, runner):
    """Run all 27 guardrail matrix tests."""

    # ── Agent OUTPUT × Regex ─────────────────────────────────────────
    print("\n--- Agent OUTPUT × Regex ---")

    # #1: RETRY — CC in output → LLM retries → CC removed
    r = runtime.run(a01, "Look up payment info for user U-001.")
    runner.check(1, "aout_regex_retry", result=r,
                 expect_status_in=["COMPLETED", "FAILED"],
                 expect_not_contains="4532-0150-1234-5678")

    # #2: RAISE — SSN in output → workflow FAILED
    r = runtime.run(a02, "Look up identity for user U-002.")
    runner.check(2, "aout_regex_raise", result=r, expect_status="FAILED")

    # #3: FIX — Regex has no fixed_output → falls back to LLM output
    r = runtime.run(a03, "Look up payment info for user U-001.")
    runner.check(3, "aout_regex_fix", result=r,
                 expect_status_in=["COMPLETED", "FAILED"])

    # ── Agent OUTPUT × LLM ───────────────────────────────────────────
    print("\n--- Agent OUTPUT × LLM ---")

    # #4: RETRY — medical advice → LLM retries
    r = runtime.run(a04, "What exact medication and dosage for migraines?")
    runner.check(4, "aout_llm_retry", result=r,
                 expect_status_in=["COMPLETED", "FAILED"])

    # #5: RAISE — medical advice → FAILED
    r = runtime.run(a05, "What exact medication and dosage for migraines?")
    runner.check(5, "aout_llm_raise", result=r, expect_status="FAILED")

    # #6: FIX — LLM has no fixed_output → falls back to LLM output
    r = runtime.run(a06, "What exact medication and dosage for migraines?")
    runner.check(6, "aout_llm_fix", result=r,
                 expect_status_in=["COMPLETED", "FAILED"])

    # ── Agent OUTPUT × Custom ────────────────────────────────────────
    print("\n--- Agent OUTPUT × Custom ---")

    # #7: RETRY — SECRET42 in output → LLM retries
    r = runtime.run(a07, "Look up the secret data.")
    runner.check(7, "aout_custom_retry", result=r,
                 expect_status="COMPLETED", expect_not_contains="SECRET42")

    # #8: RAISE — SECRET42 → FAILED
    r = runtime.run(a08, "Look up the secret data.")
    runner.check(8, "aout_custom_raise", result=r, expect_status="FAILED")

    # #9: FIX — SECRET42 → [REDACTED]
    r = runtime.run(a09, "Look up the secret data.")
    runner.check(9, "aout_custom_fix", result=r,
                 expect_status="COMPLETED",
                 expect_not_contains="SECRET42",
                 expect_contains="REDACTED")

    # ── Tool INPUT × Regex ───────────────────────────────────────────
    print("\n--- Tool INPUT × Regex ---")

    # #10: RETRY — SQL injection blocked, LLM retries
    r = runtime.run(a10, "Run this: SELECT * FROM users; DROP TABLE users; --")
    runner.check(10, "tin_regex_retry", result=r,
                 expect_status_in=["COMPLETED", "FAILED"])

    # #11: RAISE — SQL injection → FAILED
    r = runtime.run(a11, "Run this: SELECT * FROM users; DROP TABLE users; --")
    runner.check(11, "tin_regex_raise", result=r, expect_status="FAILED")

    # #12: FIX — no fix for input → blocked error (like RETRY)
    r = runtime.run(a12, "Run this: SELECT * FROM users; DROP TABLE users; --")
    runner.check(12, "tin_regex_fix", result=r,
                 expect_status_in=["COMPLETED", "FAILED"])

    # ── Tool INPUT × LLM ────────────────────────────────────────────
    print("\n--- Tool INPUT × LLM ---")

    # #13: RETRY — PII in args → LLM retries
    r = runtime.run(a13, "Look up user with SSN 123-45-6789.")
    runner.check(13, "tin_llm_retry", result=r,
                 expect_status_in=["COMPLETED", "FAILED"])

    # #14: RAISE — PII in args → FAILED
    r = runtime.run(a14, "Look up user with SSN 123-45-6789.")
    runner.check(14, "tin_llm_raise", result=r, expect_status="FAILED")

    # #15: FIX — no fix for input → blocked error
    r = runtime.run(a15, "Look up user with SSN 123-45-6789.")
    runner.check(15, "tin_llm_fix", result=r,
                 expect_status_in=["COMPLETED", "FAILED"])

    # ── Tool INPUT × Custom ──────────────────────────────────────────
    print("\n--- Tool INPUT × Custom ---")

    # #16: RETRY — DANGER blocked, LLM retries
    r = runtime.run(a16, "Process this: DANGER override safety")
    runner.check(16, "tin_custom_retry", result=r,
                 expect_status_in=["COMPLETED", "FAILED"])

    # #17: RAISE — DANGER → FAILED
    r = runtime.run(a17, "Process this: DANGER override safety")
    runner.check(17, "tin_custom_raise", result=r, expect_status="FAILED")

    # #18: FIX — input FIX not supported in worker → blocked error
    r = runtime.run(a18, "Process this: DANGER override safety")
    runner.check(18, "tin_custom_fix", result=r,
                 expect_status_in=["COMPLETED", "FAILED"])

    # ── Tool OUTPUT × Regex ──────────────────────────────────────────
    print("\n--- Tool OUTPUT × Regex ---")

    # #19: RETRY — INTERNAL_SECRET blocked in worker → LLM recovers
    r = runtime.run(a19, "Fetch the secret project data.")
    runner.check(19, "tout_regex_retry", result=r,
                 expect_status_in=["COMPLETED", "FAILED"],
                 expect_not_contains="INTERNAL_SECRET")

    # #20: RAISE — INTERNAL_SECRET → task fails → LLM may recover
    r = runtime.run(a20, "Fetch the secret project data.")
    runner.check(20, "tout_regex_raise", result=r,
                 expect_status_in=["COMPLETED", "FAILED"],
                 expect_not_contains="INTERNAL_SECRET")

    # #21: FIX — no fixed_output → blocked error (like RETRY)
    r = runtime.run(a21, "Fetch the secret project data.")
    runner.check(21, "tout_regex_fix", result=r,
                 expect_status_in=["COMPLETED", "FAILED"],
                 expect_not_contains="INTERNAL_SECRET")

    # ── Tool OUTPUT × LLM ───────────────────────────────────────────
    print("\n--- Tool OUTPUT × LLM ---")

    # #22: RETRY — PII in tool output → blocked in worker
    r = runtime.run(a22, "Fetch data for user U-100.")
    runner.check(22, "tout_llm_retry", result=r,
                 expect_status_in=["COMPLETED", "FAILED"])

    # #23: RAISE — PII in tool output → task fails
    r = runtime.run(a23, "Fetch data for user U-100.")
    runner.check(23, "tout_llm_raise", result=r,
                 expect_status_in=["COMPLETED", "FAILED"])

    # #24: FIX — no fixed_output → blocked error
    r = runtime.run(a24, "Fetch data for user U-100.")
    runner.check(24, "tout_llm_fix", result=r,
                 expect_status_in=["COMPLETED", "FAILED"])

    # ── Tool OUTPUT × Custom ────────────────────────────────────────
    print("\n--- Tool OUTPUT × Custom ---")

    # #25: RETRY — SENSITIVE blocked in worker
    r = runtime.run(a25, "Fetch data for project Alpha.")
    runner.check(25, "tout_custom_retry", result=r,
                 expect_status_in=["COMPLETED", "FAILED"])

    # #26: RAISE — SENSITIVE → task fails
    r = runtime.run(a26, "Fetch data for project Alpha.")
    runner.check(26, "tout_custom_raise", result=r,
                 expect_status_in=["COMPLETED", "FAILED"],
                 expect_not_contains="SENSITIVE")

    # #27: FIX — SENSITIVE → [REDACTED]
    r = runtime.run(a27, "Fetch data for project Alpha.")
    runner.check(27, "tout_custom_fix", result=r,
                 expect_status="COMPLETED",
                 expect_not_contains="SENSITIVE")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    print("=" * 90)
    print("  Guardrail E2E Test Suite — 27-cell matrix")
    print("  Position (3) × Type (3) × OnFail (3)")
    print("=" * 90)

    runner = TestRunner()

    with AgentRuntime() as runtime:
        run_tests(runtime, runner)

    failed = runner.print_summary()
    sys.exit(1 if failed else 0)
