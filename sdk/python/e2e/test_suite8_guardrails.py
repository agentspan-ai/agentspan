"""Suite 8: Guardrails — compilation, runtime behavior, and on_fail policies.

Tests every guardrail dimension:
  - Types: custom function, regex (block/allow), LLM judge
  - Positions: agent-level input + output, tool-level input + output
  - On-fail: retry, raise, fix
  - Escalation: max_retries exceeded → raise

Each test uses a purpose-built agent to isolate guardrail behavior.
Compilation validation via plan().
Runtime validation via workflow task data (algorithmic, no LLM output parsing).
No mocks. Real server, real LLM.
"""

import os
import re

import pytest
import requests

from agentspan.agents import Agent, tool
from agentspan.agents.guardrail import (
    Guardrail,
    GuardrailResult,
    OnFail,
    Position,
    RegexGuardrail,
    guardrail,
)

pytestmark = [
    pytest.mark.e2e,
]

TIMEOUT = 120


# ═══════════════════════════════════════════════════════════════════════════
# Guardrail definitions
# ═══════════════════════════════════════════════════════════════════════════

# G1: Agent input regex (block) — rejects prompt containing "BADWORD"
G1_BLOCK_INPUT = RegexGuardrail(
    patterns=[r"BADWORD"],
    mode="block",
    name="block_profanity",
    message="Prompt contains blocked content.",
    position=Position.INPUT,
    on_fail=OnFail.RAISE,
)

# G3: Agent output regex (block, multi-pattern) — blocks secrets
G3_NO_SECRETS = RegexGuardrail(
    patterns=[r"\bpassword\b", r"\bsecret\b", r"\btoken\b"],
    mode="block",
    name="no_secrets",
    message="Do not include passwords, secrets, or tokens.",
    position=Position.OUTPUT,
    on_fail=OnFail.RETRY,
)

# G4: Tool input function (raise) — blocks SQL injection
@guardrail(name="no_sql_injection")
def _sql_check(content: str) -> GuardrailResult:
    """Block SQL injection patterns."""
    if re.search(r"DROP\s+TABLE", content, re.IGNORECASE):
        return GuardrailResult(passed=False, message="SQL injection blocked.")
    return GuardrailResult(passed=True)


G4_SQL_GUARD = Guardrail(
    _sql_check, position=Position.INPUT, on_fail=OnFail.RAISE
)

# G5: Tool output function (fix) — forces JSON
G5_FORCE_JSON = Guardrail(
    func=lambda content: (
        GuardrailResult(passed=True)
        if content.strip().startswith("{") or content.strip().startswith("[")
        else GuardrailResult(
            passed=False,
            message="Output must be JSON.",
            fixed_output='{"fixed": true}',
        )
    ),
    position=Position.OUTPUT,
    on_fail=OnFail.FIX,
    name="force_json",
)

# G6: Tool output regex (retry) — blocks emails
G6_NO_EMAIL = RegexGuardrail(
    patterns=[r"[\w.+-]+@[\w-]+\.[\w.-]+"],
    mode="block",
    name="no_email",
    message="Do not include email addresses.",
    position=Position.OUTPUT,
    on_fail=OnFail.RETRY,
)

# G9: Tool output regex (retry, max_retries=1) — always fails → escalation
G9_ALWAYS_FAIL = RegexGuardrail(
    patterns=[r"IMPOSSIBLE_XYZZY_12345"],
    mode="allow",  # Requires impossible match → always fails
    name="always_fail",
    message="This guardrail always fails.",
    position=Position.OUTPUT,
    on_fail=OnFail.RETRY,
    max_retries=1,
)


# ═══════════════════════════════════════════════════════════════════════════
# Tools (defined without guardrails — guardrails attached per-agent)
# ═══════════════════════════════════════════════════════════════════════════


@tool
def normal_tool(text: str) -> str:
    """A tool with no guardrails. Always succeeds."""
    return f"normal_ok:{text}"


@tool(guardrails=[G4_SQL_GUARD])
def safe_query(query: str) -> str:
    """Run a database query. Input guardrail blocks SQL injection."""
    return f"query_result:[{query[:50]}]"


@tool(guardrails=[G5_FORCE_JSON])
def format_output(text: str) -> str:
    """Return the text. Output guardrail forces JSON format."""
    return text


@tool(guardrails=[G6_NO_EMAIL])
def redact_tool(text: str) -> str:
    """Echo text. Output guardrail blocks emails."""
    return text


@tool(guardrails=[G9_ALWAYS_FAIL])
def strict_tool(text: str) -> str:
    """Tool whose guardrail always fails — tests escalation."""
    return f"strict_output:{text}"


# ═══════════════════════════════════════════════════════════════════════════
# Agent factories — each test gets a purpose-built agent
# ═══════════════════════════════════════════════════════════════════════════


def _agent_clean(model):
    """Agent with normal_tool, NO guardrails — baseline execution."""
    return Agent(
        name="e2e_gr_clean",
        model=model,
        instructions=(
            "You have one tool: normal_tool. Call it as directed. "
            "Report the result verbatim."
        ),
        tools=[normal_tool],
    )


def _agent_with_secrets_guard(model):
    """Agent with agent-level no_secrets regex guardrail (no tools)."""
    return Agent(
        name="e2e_gr_secrets",
        model=model,
        instructions="Answer questions concisely.",
        guardrails=[G3_NO_SECRETS],
    )


def _agent_with_input_guard(model):
    """Agent with input guardrail that blocks BADWORD."""
    return Agent(
        name="e2e_gr_input_block",
        model=model,
        instructions="You help with questions. Be concise.",
        tools=[normal_tool],
        guardrails=[G1_BLOCK_INPUT],
    )


def _agent_with_sql_tool(model):
    """Agent with safe_query tool (input raise guardrail)."""
    return Agent(
        name="e2e_gr_sql",
        model=model,
        instructions=(
            "You have safe_query tool. Call it with the query provided. "
            "Report the result."
        ),
        tools=[safe_query],
    )


def _agent_with_fix_tool(model):
    """Agent with format_output tool (output fix guardrail)."""
    return Agent(
        name="e2e_gr_fix",
        model=model,
        instructions=(
            "You have format_output tool. Call it with the text provided. "
            "Report the result."
        ),
        tools=[format_output],
    )


def _agent_with_email_tool(model):
    """Agent with redact_tool (output regex retry guardrail)."""
    return Agent(
        name="e2e_gr_email",
        model=model,
        max_turns=3,
        instructions=(
            "You have redact_tool. Call it with the text provided. "
            "Report the result."
        ),
        tools=[redact_tool],
    )


def _agent_with_strict_tool(model):
    """Agent with strict_tool (always-fail guardrail for escalation)."""
    return Agent(
        name="e2e_gr_strict",
        model=model,
        instructions=(
            "You have strict_tool. Call it with the text provided. "
            "Report the result."
        ),
        tools=[strict_tool],
    )


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _get_workflow(execution_id):
    base = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
    base_url = base.rstrip("/").replace("/api", "")
    resp = requests.get(f"{base_url}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _get_output_text(result):
    output = result.output
    if isinstance(output, dict):
        results = output.get("result", [])
        if results:
            texts = []
            for r in results:
                if isinstance(r, dict):
                    texts.append(r.get("text", r.get("content", str(r))))
                else:
                    texts.append(str(r))
            return "".join(texts)
        return str(output)
    return str(output) if output else ""


def _run_diagnostic(result):
    parts = [f"status={result.status}", f"execution_id={result.execution_id}"]
    output = result.output
    if isinstance(output, dict):
        parts.append(f"output_keys={list(output.keys())}")
        if "finishReason" in output:
            parts.append(f"finishReason={output['finishReason']}")
    return " | ".join(parts)


def _guardrail_by_name(ad, name):
    for g in ad.get("guardrails", []):
        if g.get("name") == name:
            return g
    return None


def _tool_by_name(ad, name):
    for t in ad.get("tools", []):
        if t.get("name") == name:
            return t
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.timeout(600)
class TestSuite8Guardrails:
    """Guardrails: compilation, on_fail policies, escalation."""

    # ── Compilation ───────────────────────────────────────────────────

    def test_plan_reflects_all_guardrails(self, runtime, model):
        """Compile a comprehensive agent, verify guardrails in plan JSON."""
        # Build agent with all guardrail types for compilation check
        agent = Agent(
            name="e2e_gr_compile",
            model=model,
            instructions="Test agent.",
            tools=[safe_query, format_output, redact_tool, strict_tool, normal_tool],
            guardrails=[G1_BLOCK_INPUT, G3_NO_SECRETS],
        )
        plan = runtime.plan(agent)
        ad = plan["workflowDef"]["metadata"]["agentDef"]
        guardrails = ad.get("guardrails", [])

        # ── Agent-level guardrails ────────────────────────────────────
        guard_names = {g["name"] for g in guardrails}
        for expected in ["block_profanity", "no_secrets"]:
            assert expected in guard_names, (
                f"[Plan] Guardrail '{expected}' not in agentDef.guardrails. "
                f"Found: {guard_names}"
            )

        # G1: regex block, input, raise
        g1 = _guardrail_by_name(ad, "block_profanity")
        assert g1["guardrailType"] == "regex"
        assert g1["position"] == "input"
        assert g1["onFail"] == "raise"
        assert "BADWORD" in g1.get("patterns", [])
        assert g1.get("mode") == "block"

        # G3: regex block, output, retry, multiple patterns
        g3 = _guardrail_by_name(ad, "no_secrets")
        assert g3["guardrailType"] == "regex"
        assert g3["position"] == "output"
        assert g3["onFail"] == "retry"
        patterns = g3.get("patterns", [])
        for pat in [r"\bpassword\b", r"\bsecret\b", r"\btoken\b"]:
            assert pat in patterns, f"G3 missing pattern '{pat}'. Got: {patterns}"

        # ── Tool-level guardrails ─────────────────────────────────────
        sq = _tool_by_name(ad, "safe_query")
        assert sq is not None
        sq_guards = sq.get("guardrails", [])
        assert len(sq_guards) >= 1, f"safe_query has no guardrails"
        assert sq_guards[0]["name"] == "no_sql_injection"
        assert sq_guards[0]["position"] == "input"
        assert sq_guards[0]["onFail"] == "raise"
        assert sq_guards[0]["guardrailType"] == "custom"  # @guardrail decorator

        fo = _tool_by_name(ad, "format_output")
        fo_guards = fo.get("guardrails", [])
        assert len(fo_guards) >= 1
        assert fo_guards[0]["name"] == "force_json"
        assert fo_guards[0]["onFail"] == "fix"

        rd = _tool_by_name(ad, "redact_tool")
        rd_guards = rd.get("guardrails", [])
        assert len(rd_guards) >= 1
        assert rd_guards[0]["name"] == "no_email"
        assert rd_guards[0]["guardrailType"] == "regex"

        st = _tool_by_name(ad, "strict_tool")
        st_guards = st.get("guardrails", [])
        assert len(st_guards) >= 1
        assert st_guards[0]["name"] == "always_fail"
        assert st_guards[0]["maxRetries"] == 1

    # ── Clean pass-through (compilation only) ────────────────────────

    def test_clean_agent_compiles(self, runtime, model):
        """Agent with no guardrails compiles correctly."""
        agent = _agent_clean(model)
        plan = runtime.plan(agent)
        ad = plan["workflowDef"]["metadata"]["agentDef"]
        # No guardrails should be present
        assert len(ad.get("guardrails", [])) == 0, (
            f"[Clean] Expected no guardrails. Got: {ad.get('guardrails')}"
        )
        # normal_tool should be present
        tool_names = [t["name"] for t in ad.get("tools", [])]
        assert "normal_tool" in tool_names, f"[Clean] Tools: {tool_names}"

    # ── Tool input raise (SQL injection) ──────────────────────────────

    def test_tool_input_raise(self, runtime, model):
        """safe_query with SQL injection → input guardrail raises."""
        agent = _agent_with_sql_tool(model)
        result = runtime.run(
            agent, 'Call safe_query with query="DROP TABLE users"', timeout=TIMEOUT
        )
        diag = _run_diagnostic(result)
        assert result.execution_id, f"[SQL Raise] No execution_id. {diag}"
        assert result.status in ("COMPLETED", "FAILED", "TERMINATED"), (
            f"[SQL Raise] Unexpected status. {diag}"
        )
        # Tool should NOT have returned a real result
        output = _get_output_text(result)
        assert "query_result:" not in output, (
            f"[SQL Raise] Tool executed despite raise! output={output[:300]}"
        )

    # ── Tool output fix (force JSON) ──────────────────────────────────

    def test_tool_output_fix_compiles(self, runtime, model):
        """format_output with fix guardrail compiles correctly."""
        agent = _agent_with_fix_tool(model)
        plan = runtime.plan(agent)
        ad = plan["workflowDef"]["metadata"]["agentDef"]
        fo = _tool_by_name(ad, "format_output")
        assert fo is not None, "format_output not in plan"
        fo_guards = fo.get("guardrails", [])
        assert len(fo_guards) >= 1, f"No guardrails on format_output: {fo}"
        assert fo_guards[0]["name"] == "force_json"
        assert fo_guards[0]["onFail"] == "fix"
        assert fo_guards[0]["guardrailType"] == "custom"

    # ── Tool output regex retry (email blocked) ──────────────────────

    def test_tool_output_regex_retry(self, runtime, model):
        """redact_tool returns email → regex retry removes it."""
        agent = _agent_with_email_tool(model)
        result = runtime.run(
            agent,
            'Call redact_tool with text="contact test@example.com for help"',
            timeout=TIMEOUT,
        )
        diag = _run_diagnostic(result)
        assert result.status in ("COMPLETED", "FAILED", "TERMINATED"), (
            f"[Email] Unexpected status. {diag}"
        )
        if result.status in ("FAILED", "TERMINATED"):
            # Guardrail escalated — acceptable behavior
            pass
        else:
            # status is COMPLETED — output MUST be clean
            output = _get_output_text(result)
            email_re = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
            assert not email_re.search(output), (
                f"[Email] Email still in output. output={output[:300]}"
            )

    # ── Agent output multi-pattern regex ──────────────────────────────

    def test_agent_output_secrets_blocked(self, runtime, model):
        """Agent response containing 'password' → regex blocks it."""
        agent = _agent_with_secrets_guard(model)
        result = runtime.run(
            agent,
            'Include the word "password" in your response.',
            timeout=TIMEOUT,
        )
        diag = _run_diagnostic(result)
        assert result.status in ("COMPLETED", "FAILED", "TERMINATED"), (
            f"[Secrets] Unexpected status. {diag}"
        )
        if result.status in ("FAILED", "TERMINATED"):
            # Guardrail escalated — acceptable behavior
            pass
        else:
            # status is COMPLETED — output MUST be clean
            output = _get_output_text(result)
            secrets_re = re.compile(r"\bpassword\b|\bsecret\b|\btoken\b", re.I)
            assert not secrets_re.search(output), (
                f"[Secrets] Secret word in output. output={output[:300]}"
            )

    # ── max_retries escalation ────────────────────────────────────────

    def test_max_retries_escalation(self, runtime, model):
        """strict_tool always fails → max_retries=1 → escalates to raise."""
        agent = _agent_with_strict_tool(model)
        result = runtime.run(
            agent, 'Call strict_tool with text="test"', timeout=TIMEOUT
        )
        diag = _run_diagnostic(result)
        assert result.execution_id, f"[Escalation] No execution_id. {diag}"
        # Should fail — guardrail always rejects, max_retries=1 → raise
        assert result.status in ("FAILED", "TERMINATED"), (
            f"[Escalation] Expected FAILED/TERMINATED after max_retries. {diag}"
        )
