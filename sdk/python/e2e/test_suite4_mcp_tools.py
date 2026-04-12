"""Suite 4: MCP Tools — discovery, execution, and authenticated access.

Tests MCP tool integration end-to-end:
  1. Unauthenticated: discover all 65 tools, execute 3 specific tools
  2. Authenticated: credential-based access, same discovery and execution

Manages its own mcp-testkit instance on a dedicated port.
Single sequential test with try/finally cleanup.
No mocks. Real server, real CLI, real LLM.
"""

import asyncio
import os
import re
import inspect
import subprocess
import time

import pytest
import requests

from agentspan.agents import Agent, mcp_tool

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.xdist_group("credentials"),
]

# ── Configuration ────────────────────────────────────────────────────────

MCP_PORT = 3002  # Dedicated port — avoids conflict with orchestrator's 3001
MCP_BASE_URL = f"http://localhost:{MCP_PORT}"
MCP_SERVER_URL = f"{MCP_BASE_URL}/mcp"
MCP_AUTH_KEY = "e2e-test-secret-key-12345"
CRED_NAME = "MCP_AUTH_KEY"
TIMEOUT = 120

# ── Expected tools (from mcp-testkit source) ─────────────────────────────

def _expected_tools_from_source():
    """Dynamically compute expected tool names from mcp-testkit source."""
    from mcp_test_server.tools import ALL_GROUPS

    tools = []
    for g in ALL_GROUPS:
        src = inspect.getsource(g.register)
        names = re.findall(r"def (\w+)\(", src)
        tools.extend(n for n in names if n != "register")
    return sorted(tools)


EXPECTED_TOOL_NAMES = _expected_tools_from_source()
EXPECTED_TOOL_COUNT = len(EXPECTED_TOOL_NAMES)  # 65

# 3 deterministic tools with verifiable outputs.
# Validated in workflow task output, NOT in LLM response text.
TEST_TOOL_NAMES = ["math_add", "string_reverse", "encoding_base64_encode"]
TEST_TOOL_EXPECTED = {
    "math_add": "7",  # 3 + 4
    "string_reverse": "olleh",  # reverse("hello")
    "encoding_base64_encode": "dGVzdA==",  # base64("test")
}


# ── MCP Server Management ───────────────────────────────────────────────


def _start_mcp_server(port, auth_key=None):
    """Start mcp-testkit as a subprocess. Returns Popen handle."""
    cmd = ["mcp-testkit", "--transport", "http", "--port", str(port)]
    if auth_key:
        cmd += ["--auth", auth_key]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Wait for server to accept connections
    deadline = time.time() + 15
    while time.time() < deadline:
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            raise RuntimeError(
                f"mcp-testkit exited with code {proc.returncode}: {stderr}"
            )
        try:
            requests.post(MCP_BASE_URL, json={}, timeout=2)
            return proc  # Any response means server is up
        except (requests.ConnectionError, requests.Timeout):
            time.sleep(0.5)

    proc.terminate()
    raise TimeoutError(f"mcp-testkit not ready on port {port} after 15s")


def _stop_mcp_server(proc):
    """Stop mcp-testkit subprocess."""
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


# ── MCP Tool Discovery ──────────────────────────────────────────────────


def _discover_tools_via_mcp(server_url, auth_key=None):
    """Discover tools directly from MCP server using the official MCP client.

    Returns a sorted list of tool names.
    """
    from mcp.client.streamable_http import streamablehttp_client
    from mcp import ClientSession

    async def _inner():
        headers = {}
        if auth_key:
            headers["Authorization"] = f"Bearer {auth_key}"

        async with streamablehttp_client(
            server_url, headers=headers
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return sorted(t.name for t in result.tools)

    return asyncio.run(_inner())


# ── Agent Factories ──────────────────────────────────────────────────────

AGENT_INSTRUCTIONS = """\
You have access to MCP tools. Call exactly the tools specified in each prompt.
Report each tool's result verbatim. Do not skip any tool.
"""

PROMPT_USE_3_TOOLS = """\
Call exactly these three tools with these exact arguments:
1. math_add with a=3 and b=4
2. string_reverse with text="hello"
3. encoding_base64_encode with text="test"
Report each result.
"""


def _make_agent(model, server_url):
    """Agent with unauthenticated MCP tools."""
    mt = mcp_tool(
        server_url=server_url,
        name="test_mcp",
        description="Deterministic test tools via MCP",
    )
    return Agent(
        name="e2e_mcp_unauth",
        model=model,
        instructions=AGENT_INSTRUCTIONS,
        tools=[mt],
    )


def _make_auth_agent(model, server_url, cred_name):
    """Agent with authenticated MCP tools (credential in headers)."""
    mt = mcp_tool(
        server_url=server_url,
        name="test_mcp_auth",
        description="Authenticated MCP test tools",
        headers={"Authorization": f"Bearer ${{{cred_name}}}"},
        credentials=[cred_name],
    )
    return Agent(
        name="e2e_mcp_auth",
        model=model,
        instructions=AGENT_INSTRUCTIONS,
        tools=[mt],
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


def _find_mcp_tool_tasks(execution_id, tool_names):
    """Find MCP tool tasks in the workflow by tool name.

    MCP tool tasks store the tool name in `taskDefName` (or `taskType`),
    NOT in `referenceTaskName` (which holds the LLM's call ID).

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
        all_tasks.append(f"{ref}[def={task_def},type={task_type}]")

        # For CALL_MCP_TOOL system tasks, the tool name is in inputData
        if task_type == "CALL_MCP_TOOL":
            input_data = task.get("inputData", {})
            tool_name = input_data.get("toolName", input_data.get("tool_name", ""))
            for name in tool_names:
                if name in results:
                    continue
                if name == tool_name or name in str(input_data):
                    results[name] = {
                        "status": task.get("status", ""),
                        "output": task.get("outputData", {}),
                        "input": input_data,
                        "ref": ref,
                        "taskDef": task_def,
                        "reason": task.get("reasonForIncompletion", ""),
                    }
        else:
            # For regular tool tasks, check taskDefName and referenceTaskName
            for name in tool_names:
                if name in results:
                    continue
                if name == task_def or name == task_type or name in ref:
                    results[name] = {
                        "status": task.get("status", ""),
                        "output": task.get("outputData", {}),
                        "ref": ref,
                        "taskDef": task_def,
                        "reason": task.get("reasonForIncompletion", ""),
                    }
    return results, all_tasks


def _dump_mcp_tasks(execution_id):
    """Dump full details of CALL_MCP_TOOL tasks for debugging."""
    try:
        wf = _get_workflow(execution_id)
    except Exception as e:
        return f"(could not fetch workflow: {e})"

    mcp_tasks = []
    for task in wf.get("tasks", []):
        if task.get("taskType") == "CALL_MCP_TOOL":
            input_str = str(task.get("inputData", {}))
            output_str = str(task.get("outputData", {}))
            if len(input_str) > 300:
                input_str = input_str[:300] + "..."
            if len(output_str) > 300:
                output_str = output_str[:300] + "..."
            mcp_tasks.append(
                f"ref={task.get('referenceTaskName', '')} "
                f"status={task.get('status', '')} "
                f"input={input_str} "
                f"output={output_str}"
            )
    return "\n    ".join(mcp_tasks) if mcp_tasks else "(no CALL_MCP_TOOL tasks)"


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

    tool_tasks, all_refs = _find_mcp_tool_tasks(
        result.execution_id, TEST_TOOL_NAMES
    )

    # Dump CALL_MCP_TOOL tasks for diagnostics if tools not found
    mcp_task_dump = _dump_mcp_tasks(result.execution_id)

    for name in TEST_TOOL_NAMES:
        assert name in tool_tasks, (
            f"[{step_name}] Tool '{name}' not found in workflow tasks.\n"
            f"  Found tools: {list(tool_tasks.keys())}\n"
            f"  All task refs: {all_refs}\n"
            f"  MCP task details: {mcp_task_dump}"
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
class TestSuite4McpTools:
    """MCP tools: discovery, execution, and authenticated access."""

    def test_mcp_lifecycle(self, runtime, cli_credentials, model):
        """Full MCP lifecycle — unauthenticated → authenticated."""
        # Verify mcp-testkit is installed
        try:
            subprocess.run(
                ["mcp-testkit", "--help"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except FileNotFoundError:
            pytest.skip(
                "mcp-testkit not installed — required for Suite 4 MCP tools test"
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

            # Step d: Start MCP server without auth
            server_proc = _start_mcp_server(MCP_PORT)

            # Step e: Discover tools, validate all are present
            discovered = _discover_tools_via_mcp(MCP_SERVER_URL)
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
            agent = _make_agent(model, MCP_SERVER_URL)
            result = runtime.run(agent, PROMPT_USE_3_TOOLS, timeout=TIMEOUT)
            _validate_tool_execution(result, "Phase 1: Unauthenticated execution")

            # ── Phase 2: Authenticated ────────────────────────────────

            # Step g: Stop server, restart with auth
            _stop_mcp_server(server_proc)
            server_proc = None
            time.sleep(1)  # Let port release
            server_proc = _start_mcp_server(MCP_PORT, auth_key=MCP_AUTH_KEY)

            # Verify auth is enforced — unauthenticated call should fail
            with pytest.raises(Exception):
                _discover_tools_via_mcp(MCP_SERVER_URL)

            # Step h: Create auth agent with credential placeholder
            auth_agent = _make_auth_agent(model, MCP_SERVER_URL, CRED_NAME)

            # Step i: Set credential via CLI
            cli_credentials.set(CRED_NAME, MCP_AUTH_KEY)

            # Step j: Discover tools with auth, validate all present
            discovered_auth = _discover_tools_via_mcp(
                MCP_SERVER_URL, auth_key=MCP_AUTH_KEY
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
                _stop_mcp_server(server_proc)
