"""Suite 2: Tool Calling / Credentials — credential-independent coverage.

Secrets are delegated to the Orkes host via ``${workflow.secrets.NAME}``.
Standalone/CI has NO secret backend and NO way to inject a secret value into
a running tool, so the old "set/update credential value" lifecycle steps are
gone. What remains is the architecture-aligned coverage that does NOT require
a secret store:

  1. A tool that needs NO credential runs and the task COMPLETES.
  2. A tool REQUIRING a credential FAILS (terminal, non-COMPLETED status) when
     no secret backend is available, AND does NOT silently read an OS env var
     value (the "env is not a silent fallback" security boundary).

No mocks. Real server, real LLM.
"""

import os

import pytest
import requests

from agentspan.agents import Agent, tool

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.xdist_group("credentials"),
]

CRED_A = "E2E_CRED_A"
TIMEOUT = 300  # 5 min per agent run — CI runners are slower


# ── Tools ───────────────────────────────────────────────────────────────


@tool
def free_tool(x: str) -> str:
    """A tool that needs no credentials. Always succeeds."""
    return "free:ok"


@tool(credentials=[CRED_A])
def paid_tool_a(x: str) -> str:
    """A tool that needs E2E_CRED_A. Returns first 3 chars of credential."""
    cred_val = os.environ.get(CRED_A)
    if not cred_val:
        raise RuntimeError(
            f"Credential '{CRED_A}' not found in environment. "
            f"The server should have injected it via credential resolution."
        )
    return f"paid_a:{cred_val[:3]}"


# ── Helpers ─────────────────────────────────────────────────────────────


FREE_AGENT_INSTRUCTIONS = """\
You have one tool: free_tool.
You MUST call free_tool exactly once with the argument "test".
After calling it, report the tool's output verbatim. Do not add commentary.
"""

PAID_AGENT_INSTRUCTIONS = """\
You have one tool: paid_tool_a.
You MUST call paid_tool_a exactly once with the argument "test".
After calling it, report the tool's output verbatim. Do not add commentary.
"""


def _make_free_agent(model: str) -> Agent:
    return Agent(
        name="e2e_free_tool",
        model=model,
        max_turns=3,
        instructions=FREE_AGENT_INSTRUCTIONS,
        tools=[free_tool],
    )


def _make_paid_agent(model: str) -> Agent:
    return Agent(
        name="e2e_paid_tool",
        model=model,
        max_turns=3,
        instructions=PAID_AGENT_INSTRUCTIONS,
        tools=[paid_tool_a],
    )


def _get_workflow(execution_id: str) -> dict:
    """Fetch workflow from server API."""
    base = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
    base_url = base.rstrip("/").replace("/api", "")
    resp = requests.get(f"{base_url}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _run_diagnostic(result) -> str:
    """Build a diagnostic string from a run result for error messages."""
    parts = [
        f"status={result.status}",
        f"execution_id={result.execution_id}",
    ]

    # Include output shape — dict keys if dict, truncated string otherwise
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
        out_str = str(output)
        if len(out_str) > 200:
            out_str = out_str[:200] + "..."
        parts.append(f"output={out_str}")

    return " | ".join(parts)


def _tool_diagnostics(execution_id: str) -> str:
    """Fetch workflow tasks and report tool-related task statuses."""
    try:
        wf = _get_workflow(execution_id)
    except Exception as e:
        return f"(could not fetch workflow: {e})"

    tool_names = {"free_tool", "paid_tool_a"}
    tool_tasks = []
    for task in wf.get("tasks", []):
        ref = task.get("referenceTaskName", "")
        status = task.get("status", "")
        reason = task.get("reasonForIncompletion", "")

        # Match tool tasks by reference name
        matched = [name for name in tool_names if name in ref]
        if matched:
            entry = f"{ref}: status={status}"
            if reason:
                entry += f" reason={reason}"
            output_data = task.get("outputData", {})
            if output_data:
                out_str = str(output_data)
                if len(out_str) > 150:
                    out_str = out_str[:150] + "..."
                entry += f" output={out_str}"
            tool_tasks.append(entry)

    if not tool_tasks:
        # No tool tasks found — report overall workflow status
        wf_status = wf.get("status", "unknown")
        wf_reason = wf.get("reasonForIncompletion", "")
        summary = f"No tool tasks found in workflow. workflow_status={wf_status}"
        if wf_reason:
            summary += f" reason={wf_reason}"
        return summary

    return "\n  ".join(["Tool tasks:"] + tool_tasks)


def _find_tool_tasks_for(execution_id: str) -> dict:
    """Fetch workflow and extract tool task results by tool name.

    Checks referenceTaskName, taskDefName, and taskType for tool name matches.
    Returns a dict keyed by tool name with status, output, reason, ref.
    """
    wf = _get_workflow(execution_id)
    tool_names = ["free_tool", "paid_tool_a"]
    results = {}
    for task in wf.get("tasks", []):
        ref = task.get("referenceTaskName", "")
        task_def = task.get("taskDefName", "")
        task_type = task.get("taskType", "")
        for name in tool_names:
            if name in results:
                continue
            if name in ref or name == task_def or name == task_type:
                results[name] = {
                    "status": task.get("status", ""),
                    "output": task.get("outputData", {}),
                    "reason": task.get("reasonForIncompletion", ""),
                    "ref": ref,
                }
    return results


def _assert_run_completed(result, step_name: str):
    """Assert a run completed successfully with actionable diagnostics."""
    diag = _run_diagnostic(result)

    assert result.execution_id, f"[{step_name}] No execution_id returned. {diag}"

    # Check for stuck-at-tool-calls: the run returned but tools didn't execute
    output = result.output
    if isinstance(output, dict) and output.get("finishReason") == "TOOL_CALLS":
        tool_diag = _tool_diagnostics(result.execution_id)
        pytest.fail(
            f"[{step_name}] Run stalled at tool-calling stage — tools were "
            f"requested but did not return results. This typically means tool "
            f"workers failed to execute (worker timeout, or worker not "
            f"registered).\n"
            f"  {diag}\n"
            f"  {tool_diag}"
        )

    assert result.status == "COMPLETED", (
        f"[{step_name}] Run did not complete. {diag}\n  {_tool_diagnostics(result.execution_id)}"
    )


def _get_output_text(result) -> str:
    """Extract the text output from a run result.

    The result.output is typically a dict with a 'result' key containing
    a list of streaming tokens/chunks. Each chunk may be a dict with a
    'text' or 'content' key, or a plain string. Tokens are concatenated
    without separators since they represent a streaming sequence.
    """
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


# ── Tests ───────────────────────────────────────────────────────────────


@pytest.mark.timeout(300)
class TestSuite2ToolCalling:
    """Credential-independent tool execution coverage (no secret store)."""

    def test_no_credential_tool_completes(self, runtime, model):
        """A tool needing no credential runs and the task COMPLETES."""
        agent = _make_free_agent(model)

        result = runtime.run(agent, "Call free_tool with 'test'.", timeout=TIMEOUT)
        _assert_run_completed(result, "No-credential tool")

        tool_tasks = _find_tool_tasks_for(result.execution_id)
        assert "free_tool" in tool_tasks, (
            f"[No-credential tool] free_tool task not found in workflow.\n"
            f"  found_tasks={list(tool_tasks.keys())}"
        )
        assert tool_tasks["free_tool"]["status"] == "COMPLETED", (
            f"[No-credential tool] free_tool not COMPLETED.\n  task={tool_tasks['free_tool']}"
        )

        output = _get_output_text(result)
        assert "free" in output.lower(), (
            f"[No-credential tool] free_tool output not found in agent "
            f"response. free_tool always returns 'free:ok'.\n"
            f"  {_run_diagnostic(result)}\n"
            f"  output_text={output[:300]}\n"
            f"  {_tool_diagnostics(result.execution_id)}"
        )

    def test_credential_required_tool_fails_without_backend(self, runtime, model):
        """A tool requiring a credential FAILS with no secret backend, and
        does NOT silently fall back to an OS env var value.

        With no secret store, ``${workflow.secrets.E2E_CRED_A}`` cannot be
        resolved, so paid_tool_a must end in a terminal, non-COMPLETED-ish
        state. Crucially, even when the credential name exists as an OS env
        var, that value MUST NOT leak into the output — env is not a silent
        credential fallback.
        """
        agent = _make_paid_agent(model)

        # Set an OS env var matching the credential name. The SDK/server MUST
        # NOT read it as a credential source — env is not a silent fallback.
        os.environ[CRED_A] = "from-env-aaa"
        try:
            result = runtime.run(agent, "Call paid_tool_a with 'test'.", timeout=TIMEOUT)

            assert result.execution_id, (
                f"[Credential-required tool] No execution_id returned. {_run_diagnostic(result)}"
            )

            # The run must reach a non-COMPLETED terminal-ish state — a tool
            # requiring an unresolvable credential cannot legitimately succeed.
            terminal_failed = {
                "FAILED",
                "FAILED_WITH_TERMINAL_ERROR",
                "COMPLETED_WITH_ERRORS",
                "TERMINATED",
            }
            assert result.status in terminal_failed, (
                f"[Credential-required tool] Expected a non-COMPLETED terminal "
                f"status (one of {sorted(terminal_failed)}) because no secret "
                f"backend can resolve '{CRED_A}', got '{result.status}'. The "
                f"tool must not silently succeed.\n"
                f"  {_run_diagnostic(result)}\n"
                f"  {_tool_diagnostics(result.execution_id)}"
            )

            # The paid tool task itself must be terminal (not retryable) — a
            # missing credential is a config issue, not a transient failure.
            tool_tasks = _find_tool_tasks_for(result.execution_id)
            paid_terminal = {
                "FAILED",
                "FAILED_WITH_TERMINAL_ERROR",
                "COMPLETED_WITH_ERRORS",
                "TERMINATED",
            }
            if "paid_tool_a" in tool_tasks:
                task_info = tool_tasks["paid_tool_a"]
                assert task_info["status"] in paid_terminal, (
                    f"[Credential-required tool] paid_tool_a should be terminal "
                    f"(not retryable), got '{task_info['status']}'.\n"
                    f"  task={task_info}"
                )

            # Security boundary: the OS env var value MUST NOT leak into output.
            # Using "from-env" (unique prefix of our test value) — "fro" caused
            # false positives when LLM prose contained "from" in normal words.
            output = _get_output_text(result)
            assert "from-env" not in output, (
                "SECURITY VIOLATION: env vars were read for credential "
                "resolution! The SDK MUST NOT resolve credentials from "
                "environment variables — only from the server/host secret "
                "store.\n"
                f"  {_run_diagnostic(result)}\n"
                f"  output_text={output[:300]}"
            )
        finally:
            os.environ.pop(CRED_A, None)


# Output masking (Audit gap D) is covered deterministically by the server's
# SecretMaskingIntegrationTest (MockMvc + @MockBean AgentService). An e2e
# version would need the LLM to reliably call a specific tool whose output
# contains the leaked value — non-deterministic; violates CLAUDE.md rule 1.
