"""Suite 5: HTTP Tools — API discovery, execution, and authenticated access.

Tests HTTP/API tool integration end-to-end:
  1. Unauthenticated: discover all 65 tools via OpenAPI spec, execute 3
  2. Authenticated: credential-based access, same discovery and execution
  3. External OpenAPI spec: validate agent discovers startWorkflow operation

Manages its own mcp-testkit instance on a dedicated port.
Single sequential test with try/finally cleanup.
No mocks. Real server, real CLI, real LLM.
"""

import inspect
import os
import re
import subprocess
import time

import pytest
import requests

from agentspan.agents import Agent, api_tool, http_tool

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.xdist_group("credentials"),
]

# ── Configuration ────────────────────────────────────────────────────────

HTTP_PORT = 3003  # Dedicated port — avoids conflict with 3001 (orchestrator) / 3002 (Suite 4)
HTTP_BASE_URL = f"http://localhost:{HTTP_PORT}"
HTTP_SPEC_URL = f"{HTTP_BASE_URL}/api-docs"
HTTP_AUTH_KEY = "e2e-http-test-secret-key-67890"
CRED_NAME = "HTTP_AUTH_KEY"
TIMEOUT = 120

ORKES_SPEC_URL = "https://developer.orkescloud.com/api-docs"

# ── Expected tools (from mcp-testkit endpoint registry) ──────────────────


def _expected_tools_from_source():
    """Dynamically compute expected operation IDs from mcp-testkit API registry."""
    from mcp_test_server.api import ENDPOINTS

    return sorted(ep[2] for ep in ENDPOINTS)  # ep[2] is the tool_name / operationId


EXPECTED_TOOL_NAMES = _expected_tools_from_source()
EXPECTED_TOOL_COUNT = len(EXPECTED_TOOL_NAMES)  # 65

# 3 deterministic tools with verifiable outputs.
# Same tools as Suite 4 (MCP) — same deterministic results.
TEST_TOOL_NAMES = ["math_add", "string_reverse", "encoding_base64_encode"]
TEST_TOOL_EXPECTED = {
    "math_add": "7",  # 3 + 4
    "string_reverse": "olleh",  # reverse("hello")
    "encoding_base64_encode": "dGVzdA==",  # base64("test")
}


# ── Server Management ───────────────────────────────────────────────────


def _start_http_server(port, auth_key=None):
    """Start mcp-testkit in HTTP mode as a subprocess."""
    cmd = ["mcp-testkit", "--transport", "http", "--port", str(port)]
    if auth_key:
        cmd += ["--auth", auth_key]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    deadline = time.time() + 15
    while time.time() < deadline:
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            raise RuntimeError(
                f"mcp-testkit exited with code {proc.returncode}: {stderr}"
            )
        try:
            requests.get(f"http://localhost:{port}/api-docs", timeout=2)
            return proc  # OpenAPI spec responding means server is up
        except (requests.ConnectionError, requests.Timeout):
            time.sleep(0.5)

    proc.terminate()
    raise TimeoutError(f"mcp-testkit not ready on port {port} after 15s")


def _stop_http_server(proc):
    """Stop mcp-testkit subprocess."""
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


# ── OpenAPI Discovery ────────────────────────────────────────────────────


def _discover_tools_via_openapi(spec_url, auth_key=None):
    """Fetch OpenAPI spec and extract all operation IDs.

    Returns a sorted list of operation IDs (tool names).
    """
    headers = {}
    if auth_key:
        headers["Authorization"] = f"Bearer {auth_key}"
    resp = requests.get(spec_url, headers=headers, timeout=10)
    resp.raise_for_status()
    spec = resp.json()

    operations = []
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if isinstance(op, dict) and "operationId" in op:
                operations.append(op["operationId"])
    return sorted(operations)


# ── Agent Factories ──────────────────────────────────────────────────────

AGENT_INSTRUCTIONS = """\
You have access to HTTP API tools. Call exactly the tools specified in each prompt.
Report each tool's result verbatim. Do not skip any tool.
"""

PROMPT_USE_3_TOOLS = """\
Call exactly these three tools with these exact arguments:
1. math_add with a=3 and b=4
2. string_reverse with text="hello"
3. encoding_base64_encode with text="test"
Report each result.
"""


def _make_http_tools(base_url, headers=None, credentials=None):
    """Create 3 http_tool instances for the test endpoints."""
    math_add = http_tool(
        name="math_add",
        description="Add two numbers (a + b)",
        url=f"{base_url}/api/math/add",
        method="GET",
        headers=headers,
        credentials=credentials,
        input_schema={
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"},
            },
            "required": ["a", "b"],
        },
    )
    string_reverse = http_tool(
        name="string_reverse",
        description="Reverse a string",
        url=f"{base_url}/api/string/reverse",
        method="POST",
        headers=headers,
        credentials=credentials,
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to reverse"},
            },
            "required": ["text"],
        },
    )
    base64_encode = http_tool(
        name="encoding_base64_encode",
        description="Base64-encode a string",
        url=f"{base_url}/api/encoding/base64-encode",
        method="POST",
        headers=headers,
        credentials=credentials,
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to encode"},
            },
            "required": ["text"],
        },
    )
    return [math_add, string_reverse, base64_encode]


def _make_agent(model, base_url):
    """Agent with unauthenticated HTTP tools."""
    return Agent(
        name="e2e_http_unauth",
        model=model,
        instructions=AGENT_INSTRUCTIONS,
        tools=_make_http_tools(base_url),
    )


def _make_auth_agent(model, base_url, cred_name):
    """Agent with authenticated HTTP tools (credential in headers)."""
    headers = {"Authorization": f"Bearer ${{{cred_name}}}"}
    return Agent(
        name="e2e_http_auth",
        model=model,
        instructions=AGENT_INSTRUCTIONS,
        tools=_make_http_tools(base_url, headers=headers, credentials=[cred_name]),
    )


def _make_orkes_agent(model):
    """Agent with Orkes Cloud API tools for external OpenAPI test."""
    at = api_tool(
        url=ORKES_SPEC_URL,
        name="orkes_api",
        description="Orkes Conductor API",
        tool_names=["startWorkflow"],
    )
    return Agent(
        name="e2e_orkes_api",
        model=model,
        instructions=(
            "You have access to the Orkes Conductor API tools. "
            "Answer questions about available API operations."
        ),
        tools=[at],
    )


# ── Helpers ──────────────────────────────────────────────────────────────


def _get_workflow(execution_id):
    """Fetch workflow from server API."""
    base = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
    base_url = base.rstrip("/").replace("/api", "")
    resp = requests.get(f"{base_url}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _get_output_text(result):
    """Extract text output from a run result."""
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
    """Build diagnostic string from a run result."""
    parts = [
        f"status={result.status}",
        f"execution_id={result.execution_id}",
    ]
    output = result.output
    if isinstance(output, dict):
        parts.append(f"output_keys={list(output.keys())}")
        if "finishReason" in output:
            parts.append(f"finishReason={output['finishReason']}")
        if output.get("result") is not None:
            parts.append(f"result_count={len(output.get('result', []))}")
        if output.get("rejectionReason"):
            parts.append(f"rejectionReason={output['rejectionReason']}")
    else:
        out_str = str(output)[:200]
        parts.append(f"output={out_str}")
    return " | ".join(parts)


# Task types that are NOT tool executions — skip these when searching inputData
_SYSTEM_TASK_TYPES = {
    "LLM_CHAT_COMPLETE",
    "SWITCH",
    "DO_WHILE",
    "INLINE",
    "SET_VARIABLE",
    "FORK",
    "FORK_JOIN_DYNAMIC",
    "JOIN",
    "SUB_WORKFLOW",
    "TERMINATE",
    "WAIT",
    "EVENT",
    "DECISION",
}


def _find_http_tool_tasks(execution_id, tool_names):
    """Find HTTP tool tasks in the workflow by tool name.

    HTTP tool tasks have taskType=HTTP. The tool name or URL appears in
    inputData. Only searches inputData for tool execution tasks (HTTP,
    CALL_MCP_TOOL, SIMPLE) — never for LLM or system tasks.

    Returns (results_dict, all_task_descriptions) for diagnostics.
    """
    try:
        wf = _get_workflow(execution_id)
    except Exception as e:
        return {}, [f"(could not fetch workflow: {e})"]

    results = {}
    all_tasks = []
    for task in wf.get("tasks", []):
        ref = task.get("referenceTaskName", "")
        task_def = task.get("taskDefName", "")
        task_type = task.get("taskType", "")
        input_data = task.get("inputData", {})
        all_tasks.append(f"{ref}[def={task_def},type={task_type}]")

        for name in tool_names:
            if name in results:
                continue
            # Exact match on taskDefName or taskType
            if name == task_def or name == task_type:
                results[name] = {
                    "status": task.get("status", ""),
                    "output": task.get("outputData", {}),
                    "input": input_data,
                    "ref": ref,
                    "taskDef": task_def,
                    "reason": task.get("reasonForIncompletion", ""),
                }
            # Substring match in referenceTaskName
            elif name in ref:
                results[name] = {
                    "status": task.get("status", ""),
                    "output": task.get("outputData", {}),
                    "input": input_data,
                    "ref": ref,
                    "taskDef": task_def,
                    "reason": task.get("reasonForIncompletion", ""),
                }
            # Substring match in inputData — ONLY for tool execution tasks
            elif task_type not in _SYSTEM_TASK_TYPES and name in str(input_data):
                results[name] = {
                    "status": task.get("status", ""),
                    "output": task.get("outputData", {}),
                    "input": input_data,
                    "ref": ref,
                    "taskDef": task_def,
                    "reason": task.get("reasonForIncompletion", ""),
                }
    return results, all_tasks


def _dump_http_tasks(execution_id):
    """Dump full details of HTTP-related tasks for debugging."""
    try:
        wf = _get_workflow(execution_id)
    except Exception as e:
        return f"(could not fetch workflow: {e})"

    http_tasks = []
    for task in wf.get("tasks", []):
        task_type = task.get("taskType", "")
        if task_type in ("HTTP", "CALL_MCP_TOOL") or task_type not in (
            "INLINE",
            "SET_VARIABLE",
            "DO_WHILE",
            "LLM_CHAT_COMPLETE",
            "SWITCH",
            "FORK",
            "JOIN",
        ):
            input_str = str(task.get("inputData", {}))
            output_str = str(task.get("outputData", {}))
            if len(input_str) > 300:
                input_str = input_str[:300] + "..."
            if len(output_str) > 300:
                output_str = output_str[:300] + "..."
            http_tasks.append(
                f"ref={task.get('referenceTaskName', '')} "
                f"type={task_type} "
                f"status={task.get('status', '')} "
                f"input={input_str} "
                f"output={output_str}"
            )
    return "\n    ".join(http_tasks) if http_tasks else "(no HTTP tasks)"


def _assert_run_completed(result, step_name):
    """Assert a run completed successfully with actionable diagnostics."""
    diag = _run_diagnostic(result)

    assert result.execution_id, f"[{step_name}] No execution_id. {diag}"

    output = result.output
    if isinstance(output, dict) and output.get("finishReason") == "TOOL_CALLS":
        pytest.fail(
            f"[{step_name}] Run stalled at tool-calling stage — tools were "
            f"requested but did not return results.\n"
            f"  {diag}"
        )

    assert result.status == "COMPLETED", (
        f"[{step_name}] Run did not complete. {diag}"
    )


def _validate_tool_execution(result, step_name):
    """Validate that the 3 test tools executed successfully via workflow tasks."""
    _assert_run_completed(result, step_name)

    tool_tasks, all_refs = _find_http_tool_tasks(
        result.execution_id, TEST_TOOL_NAMES
    )

    # Dump HTTP tasks for diagnostics if tools not found
    http_task_dump = _dump_http_tasks(result.execution_id)

    for name in TEST_TOOL_NAMES:
        assert name in tool_tasks, (
            f"[{step_name}] Tool '{name}' not found in workflow tasks.\n"
            f"  Found tools: {list(tool_tasks.keys())}\n"
            f"  All task refs: {all_refs}\n"
            f"  HTTP task details: {http_task_dump}"
        )
        task = tool_tasks[name]
        assert task["status"] == "COMPLETED", (
            f"[{step_name}] Tool '{name}' did not complete.\n"
            f"  status={task['status']} reason={task['reason']}\n"
            f"  ref={task['ref']}"
        )
        # Check for expected deterministic output value
        expected = TEST_TOOL_EXPECTED[name]
        output_str = str(task["output"])
        assert expected in output_str, (
            f"[{step_name}] Tool '{name}' output does not contain "
            f"expected value '{expected}'.\n"
            f"  output={output_str[:300]}"
        )


# ── Test ─────────────────────────────────────────────────────────────────


@pytest.mark.timeout(600)
class TestSuite5HttpTools:
    """HTTP tools: API discovery, execution, and authenticated access."""

    def test_http_lifecycle(self, runtime, cli_credentials, model):
        """Full HTTP lifecycle — unauthenticated → authenticated."""
        try:
            subprocess.run(
                ["mcp-testkit", "--help"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except FileNotFoundError:
            pytest.skip(
                "mcp-testkit not installed — required for Suite 5 HTTP tools test"
            )

        server_proc = None
        try:
            self._run_lifecycle(runtime, cli_credentials, model)
        finally:
            cli_credentials.delete(CRED_NAME)

    def _run_lifecycle(self, runtime, cli_credentials, model):
        server_proc = None
        try:
            # ── Phase 1: Unauthenticated ──────────────────────────────

            # Step d: Start HTTP server without auth
            server_proc = _start_http_server(HTTP_PORT)

            # Step e: Discover tools via OpenAPI spec, validate all present
            discovered = _discover_tools_via_openapi(HTTP_SPEC_URL)
            assert len(discovered) == EXPECTED_TOOL_COUNT, (
                f"[Phase 1: Discovery] Expected {EXPECTED_TOOL_COUNT} tools, "
                f"discovered {len(discovered)}.\n"
                f"  Missing: {sorted(set(EXPECTED_TOOL_NAMES) - set(discovered))}\n"
                f"  Extra: {sorted(set(discovered) - set(EXPECTED_TOOL_NAMES))}"
            )
            assert set(discovered) == set(EXPECTED_TOOL_NAMES), (
                f"[Phase 1: Discovery] Tool names mismatch.\n"
                f"  Missing: {sorted(set(EXPECTED_TOOL_NAMES) - set(discovered))}\n"
                f"  Extra: {sorted(set(discovered) - set(EXPECTED_TOOL_NAMES))}"
            )

            # Steps b+c+f: Create agent, run with 3 tools, validate
            agent = _make_agent(model, HTTP_BASE_URL)
            result = runtime.run(agent, PROMPT_USE_3_TOOLS, timeout=TIMEOUT)
            _validate_tool_execution(result, "Phase 1: Unauthenticated execution")

            # ── Phase 2: Authenticated ────────────────────────────────

            # Step g: Stop server, restart with auth
            _stop_http_server(server_proc)
            server_proc = None
            time.sleep(1)  # Let port release
            server_proc = _start_http_server(HTTP_PORT, auth_key=HTTP_AUTH_KEY)

            # Verify auth is enforced — unauthenticated spec fetch should fail
            unauth_resp = requests.get(HTTP_SPEC_URL, timeout=5)
            assert unauth_resp.status_code in (401, 403), (
                f"[Phase 2: Auth check] Expected 401/403 without auth, "
                f"got {unauth_resp.status_code}"
            )

            # Step h: Create auth agent with credential placeholder
            auth_agent = _make_auth_agent(model, HTTP_BASE_URL, CRED_NAME)

            # Step i: Set credential via CLI
            cli_credentials.set(CRED_NAME, HTTP_AUTH_KEY)

            # Step j: Discover tools with auth, validate all present
            discovered_auth = _discover_tools_via_openapi(
                HTTP_SPEC_URL, auth_key=HTTP_AUTH_KEY
            )
            assert len(discovered_auth) == EXPECTED_TOOL_COUNT, (
                f"[Phase 2: Auth Discovery] Expected {EXPECTED_TOOL_COUNT} tools, "
                f"discovered {len(discovered_auth)}."
            )
            assert set(discovered_auth) == set(EXPECTED_TOOL_NAMES), (
                f"[Phase 2: Auth Discovery] Tool names mismatch.\n"
                f"  Missing: {sorted(set(EXPECTED_TOOL_NAMES) - set(discovered_auth))}\n"
                f"  Extra: {sorted(set(discovered_auth) - set(EXPECTED_TOOL_NAMES))}"
            )

            # Step k: Execute and validate
            result_auth = runtime.run(
                auth_agent, PROMPT_USE_3_TOOLS, timeout=TIMEOUT
            )
            _validate_tool_execution(
                result_auth, "Phase 2: Authenticated execution"
            )

        finally:
            if server_proc:
                _stop_http_server(server_proc)

    def test_external_openapi_spec(self, runtime, model):
        """External OpenAPI spec — validate startWorkflow discovery (steps l-n).

        Validates algorithmically:
        1. Fetch Orkes spec directly, confirm startWorkflow at /api/workflow
        2. Compile agent with api_tool pointing to the spec
        3. Run agent, verify it completes and references the correct operation
        """
        # ── Step l: Verify external spec is reachable ─────────────────
        try:
            spec_resp = requests.get(ORKES_SPEC_URL, timeout=10)
            spec_resp.raise_for_status()
            spec = spec_resp.json()
        except Exception as e:
            pytest.skip(
                f"Orkes API spec not reachable at {ORKES_SPEC_URL}: {e}"
            )

        # ── Algorithmic validation: startWorkflow exists at /api/workflow
        found = False
        for path, methods in spec.get("paths", {}).items():
            for method, op in methods.items():
                if isinstance(op, dict) and op.get("operationId") == "startWorkflow":
                    assert "/workflow" in path, (
                        f"[External OpenAPI] startWorkflow found but at "
                        f"unexpected path: {path}"
                    )
                    found = True
        assert found, (
            "[External OpenAPI] operationId 'startWorkflow' not found in spec. "
            f"Total operations: {sum(1 for p in spec.get('paths', {}).values() for m, o in p.items() if isinstance(o, dict) and 'operationId' in o)}"
        )

        # ── Step m: Compile agent — verify API tool present ─────────
        agent = _make_orkes_agent(model)

        plan = runtime.plan(agent)
        ad = plan["workflowDef"]["metadata"]["agentDef"]
        api_tools = [t for t in ad.get("tools", []) if t.get("toolType") == "api"]
        assert len(api_tools) >= 1, (
            f"[External OpenAPI] No API tools in compiled agent. "
            f"Tools: {[t.get('name') for t in ad.get('tools', [])]}"
        )
        assert "orkescloud" in str(api_tools[0].get("config", {})), (
            f"[External OpenAPI] API tool config does not reference Orkes. "
            f"config={api_tools[0].get('config', {})}"
        )

        # ── Step n: Run agent — verify it references startWorkflow ──
        result = runtime.run(
            agent,
            "What is the API endpoint to start a new workflow? "
            "Give me the HTTP method, path, and operationId.",
            timeout=TIMEOUT,
        )

        assert result.execution_id, (
            f"[External OpenAPI] No execution_id. {_run_diagnostic(result)}"
        )
        # Accept any terminal status — agent may fail without Orkes credentials
        assert result.status in ("COMPLETED", "FAILED", "TERMINATED"), (
            f"[External OpenAPI] Expected terminal status, "
            f"got '{result.status}'. {_run_diagnostic(result)}"
        )

        # If completed, verify output mentions the correct operation
        if result.status == "COMPLETED":
            output = _get_output_text(result)
            assert "startWorkflow" in output, (
                f"[External OpenAPI] Agent output does not contain "
                f"'startWorkflow'.\n"
                f"  output={output[:500]}\n"
                f"  {_run_diagnostic(result)}"
            )
            assert "/api/workflow" in output, (
                f"[External OpenAPI] Agent output does not contain "
                f"'/api/workflow'.\n"
                f"  output={output[:500]}\n"
                f"  {_run_diagnostic(result)}"
            )
