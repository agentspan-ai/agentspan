"""Suite 1: Basic Validation — plan() structural assertions.

All tests compile agents via plan() and assert on the Conductor workflow
JSON structure. No agent execution. Deterministic — except the LLM-as-judge
test which makes a single LLM call to validate the compiled workflow.
"""

import json
import os

import pytest

from agentspan.agents import (
    Agent,
    Guardrail,
    GuardrailResult,
    OnTextMention,
    RegexGuardrail,
    Strategy,
    audio_tool,
    http_tool,
    image_tool,
    mcp_tool,
    pdf_tool,
    tool,
    video_tool,
)

pytestmark = pytest.mark.e2e

MODEL = "openai/gpt-4o-mini"


# ── Helpers ─────────────────────────────────────────────────────────────


def _agent_def(result: dict) -> dict:
    """Extract metadata.agentDef from a plan() result.

    Fails with a clear message if the expected path is missing.
    """
    wf = result.get("workflowDef")
    assert wf is not None, (
        f"plan() result missing 'workflowDef'. "
        f"Top-level keys: {list(result.keys())}"
    )
    metadata = wf.get("metadata")
    assert metadata is not None, (
        f"workflowDef missing 'metadata'. "
        f"workflowDef keys: {list(wf.keys())}"
    )
    agent_def = metadata.get("agentDef")
    assert agent_def is not None, (
        f"workflowDef.metadata missing 'agentDef'. "
        f"metadata keys: {list(metadata.keys())}"
    )
    return agent_def


def _tool_names(agent_def: dict) -> list[str]:
    """Extract tool names from agentDef.tools."""
    return [t["name"] for t in agent_def.get("tools", [])]


def _tool_types(agent_def: dict) -> dict[str, str]:
    """Map tool name -> toolType from agentDef.tools."""
    return {t["name"]: t.get("toolType", "") for t in agent_def.get("tools", [])}


def _tool_credentials(agent_def: dict) -> dict[str, list[str]]:
    """Map tool name -> credentials list from agentDef.tools[].config.credentials."""
    result = {}
    for t in agent_def.get("tools", []):
        creds = t.get("config", {}).get("credentials", [])
        if creds:
            result[t["name"]] = creds
    return result


def _guardrail_names(agent_def: dict) -> list[str]:
    """Extract guardrail names from agentDef.guardrails."""
    return [g["name"] for g in agent_def.get("guardrails", [])]


def _guardrail_by_name(agent_def: dict, name: str) -> dict:
    """Find a guardrail by name in agentDef.guardrails. Fails if not found."""
    for g in agent_def.get("guardrails", []):
        if g["name"] == name:
            return g
    all_names = _guardrail_names(agent_def)
    pytest.fail(
        f"Guardrail '{name}' not found in agentDef.guardrails. "
        f"Available: {all_names}"
    )


def _sub_agent_names(agent_def: dict) -> list[str]:
    """Extract sub-agent names from agentDef.agents."""
    return [a["name"] for a in agent_def.get("agents", [])]


def _all_tasks_flat(workflow_def: dict) -> list:
    """Recursively collect all tasks from a workflow definition.

    Traverses nested structures: DO_WHILE loopOver, SWITCH decisionCases/
    defaultCase, FORK_JOIN forkTasks, and SUB_WORKFLOW.
    """
    tasks = []
    for t in workflow_def.get("tasks", []):
        tasks.append(t)
        tasks.extend(_recurse_task(t))
    return tasks


def _recurse_task(t: dict) -> list:
    """Recurse into a single task's nested children."""
    children = []
    for nested in t.get("loopOver", []):
        children.append(nested)
        children.extend(_recurse_task(nested))
    for case_tasks in t.get("decisionCases", {}).values():
        for ct in case_tasks:
            children.append(ct)
            children.extend(_recurse_task(ct))
    for ct in t.get("defaultCase", []):
        children.append(ct)
        children.extend(_recurse_task(ct))
    for fork_list in t.get("forkTasks", []):
        for ft in fork_list:
            children.append(ft)
            children.extend(_recurse_task(ft))
    return children


def _task_type_set(tasks: list) -> set[str]:
    """Collect unique task type values."""
    return {t.get("type", "") for t in tasks}


def _sub_workflow_names(tasks: list) -> list[str]:
    """Extract subWorkflowParam.name from SUB_WORKFLOW tasks."""
    names = []
    for t in tasks:
        if t.get("type") == "SUB_WORKFLOW":
            params = t.get("subWorkflowParam", {}) or t.get("subWorkflowParams", {})
            if params.get("name"):
                names.append(params["name"])
    return names


def _find_llm_tasks(tasks: list) -> list[dict]:
    """Find all LLM_CHAT_COMPLETE tasks recursively (including inside DO_WHILE)."""
    found = []
    for t in tasks:
        if t.get("type") == "LLM_CHAT_COMPLETE":
            found.append(t)
        # Recurse into DO_WHILE loopOver tasks
        for inner in t.get("loopOver", []):
            if inner.get("type") == "LLM_CHAT_COMPLETE":
                found.append(inner)
    return found


def _assert_plan_structure(result: dict, expected_name: str) -> dict:
    """Validate top-level plan() result structure. Returns workflowDef."""
    assert "workflowDef" in result, (
        f"plan() result missing 'workflowDef'. "
        f"Got keys: {list(result.keys())}. "
        f"The server may have returned an error: {json.dumps(result)[:500]}"
    )
    assert "requiredWorkers" in result, (
        f"plan() result missing 'requiredWorkers'. "
        f"Got keys: {list(result.keys())}"
    )
    wf = result["workflowDef"]
    assert wf.get("name") == expected_name, (
        f"workflowDef.name is '{wf.get('name')}', expected '{expected_name}'. "
        f"The compiled workflow name should match the agent name."
    )
    assert len(wf.get("tasks", [])) > 0, (
        f"workflowDef.tasks is empty. The compiler produced no tasks for "
        f"agent '{expected_name}'. This likely means the server's "
        f"AgentCompiler failed silently."
    )
    return wf


def _assert_tool_in_agent_def(
    ad: dict, tool_name: str, expected_type: str
) -> None:
    """Assert a tool exists in agentDef.tools with the correct toolType."""
    compiled_tools = _tool_names(ad)
    assert tool_name in compiled_tools, (
        f"Tool '{tool_name}' not found in agentDef.tools. "
        f"Compiled tools: {compiled_tools}. "
        f"Check that the tool was passed to Agent(tools=[...])."
    )
    actual_type = _tool_types(ad).get(tool_name, "")
    assert actual_type == expected_type, (
        f"Tool '{tool_name}' has toolType '{actual_type}', "
        f"expected '{expected_type}'. "
        f"This means the SDK serialized the tool with the wrong type."
    )


# ── LLM Judge ──────────────────────────────────────────────────────────


JUDGE_MODEL = os.environ.get("AGENTSPAN_JUDGE_MODEL", "claude-sonnet-4-20250514")

JUDGE_SYSTEM_PROMPT = """\
You are a strict validation judge for a workflow compilation system.

You will receive a SIDE-BY-SIDE COMPARISON of what the developer specified \
(EXPECTED) versus what the compiler produced (ACTUAL) for each element.

Your job: go through each comparison item and check if EXPECTED matches ACTUAL.

Rules:
- A tool is NOT a sub-agent. They are in separate lists. Do not confuse them.
- Compare values exactly as written. "regex" matches "regex", not "custom".
- If EXPECTED and ACTUAL match for all items, set "pass" to true.

Respond with ONLY a JSON object:
{
  "pass": true or false,
  "missing": ["list items where EXPECTED does not match ACTUAL"],
  "explanation": "brief explanation"
}
"""


def _build_judge_comparison(agent_spec: dict, result: dict) -> str:
    """Build a side-by-side EXPECTED vs ACTUAL comparison for the LLM judge.

    agent_spec is a structured dict describing what the developer specified.
    result is the plan() output containing the compiled workflow.
    """
    wf = result["workflowDef"]
    ad = wf.get("metadata", {}).get("agentDef", {})

    # Index compiled data for lookup
    compiled_tools = {t["name"]: t for t in ad.get("tools", [])}
    compiled_guardrails = {g["name"]: g for g in ad.get("guardrails", [])}
    compiled_agents = {a["name"]: a for a in ad.get("agents", [])}
    all_tasks = _all_tasks_flat(wf)
    task_types = sorted(_task_type_set(all_tasks))

    lines = []

    # Tools comparison
    lines.append("=== TOOLS ===")
    for t in agent_spec["tools"]:
        name = t["name"]
        ct = compiled_tools.get(name)
        if ct:
            creds = ct.get("config", {}).get("credentials", [])
            actual = f"toolType={ct.get('toolType', '?')}"
            if t.get("credentials"):
                actual += f", credentials={creds}"
        else:
            actual = "NOT FOUND"
        expected = f"toolType={t['type']}"
        if t.get("credentials"):
            expected += f", credentials={t['credentials']}"
        lines.append(f"  {name}: EXPECTED({expected}) ACTUAL({actual})")

    # Guardrails comparison
    lines.append("\n=== GUARDRAILS ===")
    for g in agent_spec["guardrails"]:
        name = g["name"]
        cg = compiled_guardrails.get(name)
        if cg:
            actual = (
                f"guardrailType={cg.get('guardrailType', '?')}, "
                f"position={cg.get('position', '?')}, "
                f"onFail={cg.get('onFail', '?')}"
            )
            if g.get("patterns"):
                actual += f", patterns={cg.get('patterns', [])}"
        else:
            actual = "NOT FOUND"
        expected = (
            f"guardrailType={g['guardrailType']}, "
            f"position={g['position']}, onFail={g['onFail']}"
        )
        if g.get("patterns"):
            expected += f", patterns={g['patterns']}"
        lines.append(f"  {name}: EXPECTED({expected}) ACTUAL({actual})")

    # Sub-agents comparison
    lines.append("\n=== SUB-AGENTS ===")
    for a in agent_spec["agents"]:
        name = a["name"]
        ca = compiled_agents.get(name)
        if ca:
            actual = f"strategy={ca.get('strategy', '?')}"
        else:
            actual = "NOT FOUND"
        expected = f"strategy={a['strategy']}"
        lines.append(f"  {name}: EXPECTED({expected}) ACTUAL({actual})")

    # Parent strategy
    lines.append("\n=== PARENT STRATEGY ===")
    lines.append(
        f"  EXPECTED({agent_spec['strategy']}) "
        f"ACTUAL({ad.get('strategy', 'not set')})"
    )

    # Task types
    has_sub_wf = "SUB_WORKFLOW" in task_types
    lines.append("\n=== TASK TYPES ===")
    lines.append(
        f"  SUB_WORKFLOW: EXPECTED(present) "
        f"ACTUAL({'present' if has_sub_wf else 'NOT FOUND'})"
    )

    return "\n".join(lines)


# Structured spec for the kitchen sink agent (used by the judge comparison builder)
KITCHEN_SINK_SPEC_STRUCTURED = {
    "tools": [
        {"name": "local_tool", "type": "worker"},
        {"name": "cred_local_tool", "type": "worker", "credentials": ["KS_SECRET"]},
        {"name": "ks_http", "type": "http"},
        {"name": "ks_mcp", "type": "mcp"},
        {"name": "ks_image", "type": "generate_image"},
        {"name": "ks_audio", "type": "generate_audio"},
        {"name": "ks_video", "type": "generate_video"},
        {"name": "ks_pdf", "type": "generate_pdf"},
    ],
    "guardrails": [
        {"name": "check_input", "guardrailType": "custom", "position": "input", "onFail": "retry"},
        {"name": "no_pii", "guardrailType": "custom", "position": "output", "onFail": "retry"},
        {"name": "no_password", "guardrailType": "regex", "position": "output", "onFail": "retry", "patterns": ["password"]},
    ],
    "agents": [
        {"name": "ks_handoff", "strategy": "handoff"},
        {"name": "ks_sequential", "strategy": "sequential"},
        {"name": "ks_parallel", "strategy": "parallel"},
        {"name": "ks_router", "strategy": "router"},
        {"name": "ks_round_robin", "strategy": "round_robin"},
        {"name": "ks_random", "strategy": "random"},
        {"name": "ks_swarm", "strategy": "swarm"},
        {"name": "ks_manual", "strategy": "manual"},
    ],
    "strategy": "handoff",
}


def _judge_call_anthropic(model: str, system: str, user: str) -> str:
    """Call Anthropic API. Returns raw text response."""
    try:
        import anthropic
    except ImportError:
        pytest.skip(
            "anthropic package required for Claude judge. "
            "Install with: pip install anthropic (or uv sync --extra testing)"
        )

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
        temperature=0,
    )
    return response.content[0].text.strip()


def _judge_call_openai(model: str, system: str, user: str) -> str:
    """Call OpenAI API. Returns raw text response."""
    try:
        import openai
    except ImportError:
        pytest.skip(
            "openai package required for OpenAI judge. "
            "Install with: pip install openai (or uv sync --extra testing)"
        )

    client = openai.OpenAI()  # reads OPENAI_API_KEY from env
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0,
    )
    return response.choices[0].message.content.strip()


def _judge_compiled_workflow(comparison_text: str) -> dict:
    """Call LLM to judge whether compiled workflow matches agent spec.

    Uses Anthropic (claude-*) or OpenAI (gpt-*) based on model name.
    Defaults to Claude Sonnet. Configure via AGENTSPAN_JUDGE_MODEL env var.

    Returns dict with keys: pass (bool), missing (list), explanation (str).
    """
    model = JUDGE_MODEL

    if model.startswith("claude"):
        raw = _judge_call_anthropic(model, JUDGE_SYSTEM_PROMPT, comparison_text)
    elif model.startswith("gpt") or model.startswith("o"):
        raw = _judge_call_openai(model, JUDGE_SYSTEM_PROMPT, comparison_text)
    else:
        pytest.fail(
            f"Unknown judge model '{model}'. "
            f"Set AGENTSPAN_JUDGE_MODEL to a claude-* or gpt-* model."
        )

    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        raw = "\n".join(lines)

    try:
        verdict = json.loads(raw)
    except json.JSONDecodeError:
        pytest.fail(
            f"LLM judge returned unparseable response.\n"
            f"Raw response: {raw[:500]}"
        )

    return {
        "pass": bool(verdict.get("pass", False)),
        "missing": verdict.get("missing", []),
        "explanation": verdict.get("explanation", ""),
    }


# ── Kitchen Sink Agent Builder ─────────────────────────────────────────


def _make_kitchen_sink_agent(mcp_url: str) -> Agent:
    """Build the kitchen sink agent with all tool types, guardrails,
    credentials, and all 8 sub-agent strategies."""

    @tool
    def local_tool(x: str) -> str:
        """A local worker tool."""
        return x

    @tool(credentials=["KS_SECRET"])
    def cred_local_tool(x: str) -> str:
        """Worker tool with credentials."""
        return x

    ht = http_tool(
        name="ks_http",
        description="HTTP endpoint",
        url=f"{mcp_url}/echo",
        method="POST",
    )
    mt = mcp_tool(
        server_url=mcp_url,
        name="ks_mcp",
        description="MCP tools",
    )
    img = image_tool(
        name="ks_image",
        description="Generate image",
        llm_provider="openai",
        model="dall-e-3",
    )
    aud = audio_tool(
        name="ks_audio",
        description="Generate audio",
        llm_provider="openai",
        model="tts-1",
    )
    vid = video_tool(
        name="ks_video",
        description="Generate video",
        llm_provider="openai",
        model="sora",
    )
    pdf = pdf_tool(name="ks_pdf", description="Generate PDF")

    input_guard = Guardrail(check_input, position="input", on_fail="retry")
    output_guard = Guardrail(no_pii, position="output", on_fail="retry")
    regex_guard = RegexGuardrail(
        patterns=[r"password"],
        name="no_password",
        message="No passwords in output.",
        on_fail="retry",
    )

    router_lead = Agent(
        name="ks_router_lead",
        model=MODEL,
        instructions="Route to correct agent.",
    )

    return Agent(
        name="e2e_kitchen_sink",
        model=MODEL,
        instructions="You are the kitchen sink agent.",
        tools=[local_tool, cred_local_tool, ht, mt, img, aud, vid, pdf],
        guardrails=[input_guard, output_guard, regex_guard],
        agents=[
            Agent(
                name="ks_handoff",
                model=MODEL,
                instructions="Route tasks.",
                agents=[
                    Agent(name="ks_h1", model=MODEL, instructions="H1."),
                    Agent(name="ks_h2", model=MODEL, instructions="H2."),
                ],
                strategy=Strategy.HANDOFF,
            ),
            Agent(
                name="ks_sequential",
                model=MODEL,
                agents=[
                    Agent(name="ks_seq1", model=MODEL, instructions="Seq1."),
                    Agent(name="ks_seq2", model=MODEL, instructions="Seq2."),
                ],
                strategy=Strategy.SEQUENTIAL,
            ),
            Agent(
                name="ks_parallel",
                model=MODEL,
                agents=[
                    Agent(name="ks_p1", model=MODEL, instructions="P1."),
                    Agent(name="ks_p2", model=MODEL, instructions="P2."),
                ],
                strategy=Strategy.PARALLEL,
            ),
            Agent(
                name="ks_router",
                model=MODEL,
                agents=[
                    Agent(name="ks_r1", model=MODEL, instructions="R1."),
                    Agent(name="ks_r2", model=MODEL, instructions="R2."),
                ],
                strategy=Strategy.ROUTER,
                router=router_lead,
            ),
            Agent(
                name="ks_round_robin",
                model=MODEL,
                agents=[
                    Agent(name="ks_rr1", model=MODEL, instructions="RR1."),
                    Agent(name="ks_rr2", model=MODEL, instructions="RR2."),
                ],
                strategy=Strategy.ROUND_ROBIN,
            ),
            Agent(
                name="ks_random",
                model=MODEL,
                agents=[
                    Agent(name="ks_rand1", model=MODEL, instructions="Rand1."),
                    Agent(name="ks_rand2", model=MODEL, instructions="Rand2."),
                ],
                strategy=Strategy.RANDOM,
            ),
            Agent(
                name="ks_swarm",
                model=MODEL,
                agents=[
                    Agent(name="ks_sw1", model=MODEL, instructions="SW1."),
                    Agent(name="ks_sw2", model=MODEL, instructions="SW2."),
                ],
                strategy=Strategy.SWARM,
                handoffs=[
                    OnTextMention(text="GOTO_SW2", target="ks_sw2"),
                    OnTextMention(text="GOTO_SW1", target="ks_sw1"),
                ],
            ),
            Agent(
                name="ks_manual",
                model=MODEL,
                agents=[
                    Agent(name="ks_m1", model=MODEL, instructions="M1."),
                    Agent(name="ks_m2", model=MODEL, instructions="M2."),
                ],
                strategy=Strategy.MANUAL,
            ),
        ],
        strategy=Strategy.HANDOFF,
    )


# ── Tools for tests ─────────────────────────────────────────────────────


@tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@tool
def multiply(x: int, y: int) -> int:
    """Multiply two numbers."""
    return x * y


@tool
def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello {name}"


@tool(credentials=["API_KEY_1"])
def credentialed_tool(query: str) -> str:
    """A tool that needs credentials."""
    import os

    return os.environ.get("API_KEY_1", "missing")[:3]


@tool(credentials=["SECRET_A", "SECRET_B"])
def multi_cred_tool(data: str) -> str:
    """A tool needing multiple credentials."""
    return data


# ── Guardrails for tests ────────────────────────────────────────────────


def no_pii(content: str) -> GuardrailResult:
    """Block PII patterns."""
    return GuardrailResult(passed=True)


def check_input(content: str) -> GuardrailResult:
    """Validate input."""
    return GuardrailResult(passed=True)


# ── Tests ───────────────────────────────────────────────────────────────


class TestSuite1BasicValidation:
    """All tests compile agents via plan() and assert on workflow structure."""

    def test_smoke_simple_agent_plan(self, runtime):
        """Smoke test: agent with 2 tools compiles to a valid workflow."""
        agent = Agent(
            name="e2e_smoke",
            model=MODEL,
            instructions="You are a calculator.",
            tools=[add, multiply],
        )
        result = runtime.plan(agent)

        _assert_plan_structure(result, "e2e_smoke")

        ad = _agent_def(result)
        _assert_tool_in_agent_def(ad, "add", "worker")
        _assert_tool_in_agent_def(ad, "multiply", "worker")

    def test_plan_reflects_tools(self, runtime):
        """Every tool on the agent appears in agentDef.tools with correct type."""
        agent = Agent(
            name="e2e_tools",
            model=MODEL,
            instructions="Use tools.",
            tools=[add, multiply, greet],
        )
        result = runtime.plan(agent)
        ad = _agent_def(result)

        for name in ["add", "multiply", "greet"]:
            _assert_tool_in_agent_def(ad, name, "worker")

    def test_plan_reflects_guardrails(self, runtime):
        """Guardrails appear in agentDef.guardrails with correct position/type/onFail."""
        agent = Agent(
            name="e2e_guardrails",
            model=MODEL,
            instructions="Answer questions.",
            tools=[greet],
            guardrails=[
                Guardrail(check_input, position="input", on_fail="retry"),
                Guardrail(no_pii, position="output", on_fail="retry"),
                RegexGuardrail(
                    patterns=[r"\b\d{3}-\d{2}-\d{4}\b"],
                    name="no_ssn",
                    message="No SSNs allowed.",
                    on_fail="retry",
                ),
            ],
        )
        result = runtime.plan(agent)
        ad = _agent_def(result)
        guardrails = ad.get("guardrails", [])
        guard_names = _guardrail_names(ad)

        assert len(guardrails) == 3, (
            f"Expected 3 guardrails in agentDef.guardrails, got {len(guardrails)}. "
            f"Names found: {guard_names}. "
            f"Check that all guardrails passed to Agent(guardrails=[...]) "
            f"are serialized by the SDK."
        )

        # Custom guardrails by function name
        for name in ["check_input", "no_pii", "no_ssn"]:
            assert name in guard_names, (
                f"Guardrail '{name}' not in agentDef.guardrails. "
                f"Found: {guard_names}"
            )

        # Verify positions
        check_input_g = _guardrail_by_name(ad, "check_input")
        assert check_input_g["position"] == "input", (
            f"Guardrail 'check_input' has position '{check_input_g['position']}', "
            f"expected 'input'. Guardrail was created with position='input'."
        )
        no_pii_g = _guardrail_by_name(ad, "no_pii")
        assert no_pii_g["position"] == "output", (
            f"Guardrail 'no_pii' has position '{no_pii_g['position']}', "
            f"expected 'output'. Guardrail was created with position='output'."
        )

        # Regex guardrail type and patterns
        no_ssn_g = _guardrail_by_name(ad, "no_ssn")
        assert no_ssn_g["guardrailType"] == "regex", (
            f"Guardrail 'no_ssn' has guardrailType '{no_ssn_g.get('guardrailType')}', "
            f"expected 'regex'. RegexGuardrail should serialize as type 'regex'."
        )
        assert r"\b\d{3}-\d{2}-\d{4}\b" in no_ssn_g.get("patterns", []), (
            f"SSN regex pattern not found in 'no_ssn' guardrail. "
            f"patterns: {no_ssn_g.get('patterns')}. "
            f"The pattern should be preserved verbatim during serialization."
        )

        # All guardrails have onFail = retry
        for g in guardrails:
            assert g.get("onFail") == "retry", (
                f"Guardrail '{g['name']}' has onFail='{g.get('onFail')}', "
                f"expected 'retry'. All guardrails in this test use on_fail='retry'."
            )

    def test_plan_reflects_credentials(self, runtime):
        """Credentials appear in agentDef.tools[].config.credentials."""
        agent = Agent(
            name="e2e_creds",
            model=MODEL,
            instructions="Use tools.",
            tools=[credentialed_tool, multi_cred_tool],
        )
        result = runtime.plan(agent)
        ad = _agent_def(result)
        cred_map = _tool_credentials(ad)

        # credentialed_tool has API_KEY_1
        assert "credentialed_tool" in cred_map, (
            f"'credentialed_tool' has no credentials in agentDef.tools[].config.credentials. "
            f"Tools with credentials: {cred_map}. "
            f"The @tool(credentials=['API_KEY_1']) decorator should serialize "
            f"credentials into the tool's config."
        )
        assert cred_map["credentialed_tool"] == ["API_KEY_1"], (
            f"'credentialed_tool' credentials are {cred_map['credentialed_tool']}, "
            f"expected ['API_KEY_1']. "
            f"Check config_serializer.py credential serialization."
        )

        # multi_cred_tool has SECRET_A and SECRET_B
        assert "multi_cred_tool" in cred_map, (
            f"'multi_cred_tool' has no credentials in agentDef.tools[].config.credentials. "
            f"Tools with credentials: {cred_map}. "
            f"The @tool(credentials=['SECRET_A', 'SECRET_B']) decorator should "
            f"serialize both credential names."
        )
        assert set(cred_map["multi_cred_tool"]) == {"SECRET_A", "SECRET_B"}, (
            f"'multi_cred_tool' credentials are {cred_map['multi_cred_tool']}, "
            f"expected {{'SECRET_A', 'SECRET_B'}}."
        )

    def test_plan_sub_agent_produces_sub_workflow(self, runtime):
        """An agent with a sub-agent produces SUB_WORKFLOW tasks
        and sub-agents appear in agentDef.agents."""
        child = Agent(
            name="e2e_child",
            model=MODEL,
            instructions="You are a helper.",
        )
        parent = Agent(
            name="e2e_parent",
            model=MODEL,
            instructions="Delegate to child.",
            agents=[child],
            strategy=Strategy.HANDOFF,
        )
        result = runtime.plan(parent)

        # agentDef.agents contains the child
        ad = _agent_def(result)
        sub_names = _sub_agent_names(ad)
        assert "e2e_child" in sub_names, (
            f"Sub-agent 'e2e_child' not in agentDef.agents. "
            f"Found: {sub_names}. "
            f"The child agent passed to Agent(agents=[child]) should appear "
            f"in the compiled agentDef."
        )

        # Strategy is set
        assert ad.get("strategy") == "handoff", (
            f"agentDef.strategy is '{ad.get('strategy')}', expected 'handoff'. "
            f"Agent was created with strategy=Strategy.HANDOFF."
        )

        # SUB_WORKFLOW task exists in compiled workflow
        all_tasks = _all_tasks_flat(result["workflowDef"])
        task_types = _task_type_set(all_tasks)
        assert "SUB_WORKFLOW" in task_types, (
            f"No SUB_WORKFLOW task in compiled workflow. "
            f"Task types found: {task_types}. "
            f"An agent with sub-agents should compile to SUB_WORKFLOW tasks."
        )

    def test_plan_sub_agent_references_correct_names(self, runtime):
        """SUB_WORKFLOW tasks reference the correct sub-agent names
        both in agentDef and in subWorkflowParam."""
        analyst = Agent(
            name="e2e_analyst",
            model=MODEL,
            instructions="You analyze data.",
        )
        writer = Agent(
            name="e2e_writer",
            model=MODEL,
            instructions="You write reports.",
        )
        manager = Agent(
            name="e2e_manager",
            model=MODEL,
            instructions="Delegate analysis to analyst and writing to writer.",
            agents=[analyst, writer],
            strategy=Strategy.HANDOFF,
        )
        result = runtime.plan(manager)

        # agentDef.agents has both sub-agents
        ad = _agent_def(result)
        sub_names = _sub_agent_names(ad)
        for name in ["e2e_analyst", "e2e_writer"]:
            assert name in sub_names, (
                f"Sub-agent '{name}' not in agentDef.agents. "
                f"Found: {sub_names}"
            )

        # SUB_WORKFLOW tasks reference the correct names
        all_tasks = _all_tasks_flat(result["workflowDef"])
        sw_names = _sub_workflow_names(all_tasks)
        assert any("analyst" in n for n in sw_names), (
            f"No SUB_WORKFLOW task references 'analyst'. "
            f"subWorkflowParam.name values: {sw_names}. "
            f"The compiler should create a SUB_WORKFLOW for 'e2e_analyst'."
        )
        assert any("writer" in n for n in sw_names), (
            f"No SUB_WORKFLOW task references 'writer'. "
            f"subWorkflowParam.name values: {sw_names}. "
            f"The compiler should create a SUB_WORKFLOW for 'e2e_writer'."
        )

    def test_kitchen_sink_compiles(self, runtime, mcp_url):
        """Kitchen sink agent with ALL tool types, guardrails, credentials,
        and all 8 sub-agent strategies compiles successfully."""

        kitchen_sink = _make_kitchen_sink_agent(mcp_url)

        # ── Compile ─────────────────────────────────────────────────
        result = runtime.plan(kitchen_sink)
        wf = _assert_plan_structure(result, "e2e_kitchen_sink")
        ad = _agent_def(result)

        # ── Tools: every tool present with correct toolType ─────────
        expected_tools = {
            "local_tool": "worker",
            "cred_local_tool": "worker",
            "ks_http": "http",
            "ks_mcp": "mcp",
            "ks_image": "generate_image",
            "ks_audio": "generate_audio",
            "ks_video": "generate_video",
            "ks_pdf": "generate_pdf",
        }
        for tool_name, expected_type in expected_tools.items():
            _assert_tool_in_agent_def(ad, tool_name, expected_type)

        # ── Credentials: at correct path in tool config ─────────────
        cred_map = _tool_credentials(ad)
        assert "cred_local_tool" in cred_map, (
            f"'cred_local_tool' has no credentials in agentDef.tools[].config.credentials. "
            f"Tools with credentials: {cred_map}. "
            f"Expected ['KS_SECRET'] from @tool(credentials=['KS_SECRET'])."
        )
        assert cred_map["cred_local_tool"] == ["KS_SECRET"], (
            f"'cred_local_tool' credentials are {cred_map['cred_local_tool']}, "
            f"expected ['KS_SECRET']."
        )

        # ── Guardrails: all 3 in agentDef.guardrails ───────────────
        guardrails = ad.get("guardrails", [])
        guard_names = _guardrail_names(ad)
        assert len(guardrails) == 3, (
            f"Expected 3 guardrails, got {len(guardrails)}. "
            f"Names found: {guard_names}"
        )
        for name in ["check_input", "no_pii", "no_password"]:
            assert name in guard_names, (
                f"Guardrail '{name}' not in agentDef.guardrails. "
                f"Found: {guard_names}"
            )

        no_pw = _guardrail_by_name(ad, "no_password")
        assert no_pw["guardrailType"] == "regex", (
            f"Guardrail 'no_password' has guardrailType '{no_pw.get('guardrailType')}', "
            f"expected 'regex'."
        )
        assert "password" in no_pw.get("patterns", []), (
            f"Pattern 'password' not in 'no_password' guardrail. "
            f"patterns: {no_pw.get('patterns')}"
        )

        # ── Sub-agents: all 8 strategy teams in agentDef.agents ─────
        sub_names = _sub_agent_names(ad)
        expected_subs = [
            "ks_handoff",
            "ks_sequential",
            "ks_parallel",
            "ks_router",
            "ks_round_robin",
            "ks_random",
            "ks_swarm",
            "ks_manual",
        ]
        for name in expected_subs:
            assert name in sub_names, (
                f"Sub-agent '{name}' not in agentDef.agents. "
                f"Found: {sub_names}"
            )

        # Verify each sub-agent has the correct strategy
        sub_agent_map = {a["name"]: a for a in ad["agents"]}
        expected_strategies = {
            "ks_handoff": "handoff",
            "ks_sequential": "sequential",
            "ks_parallel": "parallel",
            "ks_router": "router",
            "ks_round_robin": "round_robin",
            "ks_random": "random",
            "ks_swarm": "swarm",
            "ks_manual": "manual",
        }
        for name, expected_strat in expected_strategies.items():
            actual = sub_agent_map[name].get("strategy")
            assert actual == expected_strat, (
                f"Sub-agent '{name}' has strategy '{actual}', "
                f"expected '{expected_strat}'. "
                f"Agent was created with strategy=Strategy.{expected_strat.upper()}."
            )

        # ── Parent strategy ─────────────────────────────────────────
        assert ad.get("strategy") == "handoff", (
            f"Parent agentDef.strategy is '{ad.get('strategy')}', "
            f"expected 'handoff'."
        )

        # ── Compiled task types: SUB_WORKFLOW exists ────────────────
        all_tasks = _all_tasks_flat(wf)
        task_types = _task_type_set(all_tasks)
        assert "SUB_WORKFLOW" in task_types, (
            f"No SUB_WORKFLOW task in compiled workflow. "
            f"Task types: {task_types}. "
            f"Agent has 8 sub-agent teams — at least one should produce "
            f"a SUB_WORKFLOW task."
        )

        # ── requiredWorkers present ─────────────────────────────────
        assert "requiredWorkers" in result, (
            f"plan() result missing 'requiredWorkers'. "
            f"Got keys: {list(result.keys())}"
        )

    def test_llm_judge_validates_compiled_workflow(self, runtime, mcp_url):
        """LLM-as-judge: give the agent structure and compiled workflow
        to an LLM, have it verify the workflow contains all structural info.

        This catches semantic mismatches that exact-path assertions might miss.
        Makes one LLM call for judging (not agent execution).
        """
        kitchen_sink = _make_kitchen_sink_agent(mcp_url)
        result = runtime.plan(kitchen_sink)

        # Sanity check — compilation succeeded
        assert "workflowDef" in result, (
            f"plan() result missing 'workflowDef'. "
            f"Got keys: {list(result.keys())}. "
            f"Cannot run LLM judge without a compiled workflow."
        )

        comparison = _build_judge_comparison(KITCHEN_SINK_SPEC_STRUCTURED, result)

        verdict = _judge_compiled_workflow(comparison)

        assert verdict["pass"], (
            f"LLM judge found structural mismatches between agent definition "
            f"and compiled workflow.\n"
            f"  Missing items: {verdict['missing']}\n"
            f"  Explanation: {verdict['explanation']}\n"
            f"  Judge model: {JUDGE_MODEL}\n"
            f"  To debug: inspect the workflowDef JSON returned by "
            f"runtime.plan() and compare against the agent spec."
        )


# ── Suite 1.x: Base URL tests ─────────────────────────────────────────


class TestBaseUrl:
    """Verify base_url flows through compilation to LLM task inputParameters."""

    def test_base_url_in_compiled_workflow(self, runtime):
        """Per-agent base_url appears in LLM_CHAT_COMPLETE task inputParameters."""
        agent = Agent(
            name="e2e_base_url",
            model=MODEL,
            instructions="Say hello.",
            base_url="https://my-custom-proxy.example.com/v1",
        )
        result = runtime.plan(agent)
        wf = _assert_plan_structure(result, "e2e_base_url")
        tasks = wf.get("tasks", [])
        llm_tasks = _find_llm_tasks(tasks)

        assert llm_tasks, "No LLM_CHAT_COMPLETE task found in workflow"
        llm_input_params = llm_tasks[0].get("inputParameters", {})
        assert llm_input_params.get("baseUrl") == "https://my-custom-proxy.example.com/v1", (
            f"Expected baseUrl='https://my-custom-proxy.example.com/v1' in LLM task "
            f"inputParameters, got: {llm_input_params.get('baseUrl')}"
        )

    def test_no_base_url_when_omitted(self, runtime):
        """When base_url is not set, no baseUrl key appears in LLM task inputParameters."""
        agent = Agent(
            name="e2e_no_base_url",
            model=MODEL,
            instructions="Say hello.",
        )
        result = runtime.plan(agent)
        wf = _assert_plan_structure(result, "e2e_no_base_url")
        tasks = wf.get("tasks", [])
        llm_tasks = _find_llm_tasks(tasks)

        assert llm_tasks, "No LLM_CHAT_COMPLETE task found in workflow"
        llm_input_params = llm_tasks[0].get("inputParameters", {})
        assert "baseUrl" not in llm_input_params, (
            f"baseUrl should NOT be present when not set on Agent, "
            f"but found: {llm_input_params.get('baseUrl')}"
        )
