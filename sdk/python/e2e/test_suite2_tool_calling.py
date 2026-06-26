"""Suite 2: Tool Calling / Credentials — OSS-trim contract.

Secrets are delegated to the host via ``${workflow.secrets.NAME}`` and resolved
ONLY by Orkes-Conductor. The standalone server embeds OSS Conductor, which has
no secret store: a ``${workflow.secrets.X}`` reference resolves to ``null`` and,
in standalone mode, agentspan does not even stamp the reference. Either way the
secret is **trimmed** — it never reaches the worker tool. This is intentional:
standalone/OSS is non-secure by design.

There is therefore no way to inject a secret value into a running tool here, and
these tests do not try to. They validate the OSS-trim contract directly:

  1. A tool that needs NO credential runs and the task COMPLETES.
  2. A tool REQUIRING a credential FAILS because the secret is trimmed — and
     this **expected failure is the assertion**. We further prove the secret was
     genuinely not delivered (the tool's success output never appears), and that
     an OS env var of the same name is NOT a silent fallback: the tool reads via
     ``get_secret`` (the injected credential context), which never consults
     ``os.environ``.

No mocks. Real server, real LLM.
"""

import os

import pytest
import requests

from agentspan.agents import Agent, get_secret, tool

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
    """A tool that needs E2E_CRED_A. Returns first 3 chars of the credential.

    Reads via ``get_secret`` (the injected credential context), NOT ``os.environ``
    — so when the secret is trimmed (OSS/standalone) this raises and the task
    fails, and an OS env var of the same name can never be a silent fallback.
    """
    cred_val = get_secret(CRED_A)  # raises CredentialNotFoundError when trimmed
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
    # Agent name must NOT contain a tool name as a substring: tool tasks are
    # matched by substring on the reference name, and an agent named after the
    # tool (e.g. "e2e_free_tool") would make orchestration tasks like
    # "<agent>_ctx_resolve" falsely match "free_tool".
    return Agent(
        name="e2e_nocred_agent",
        model=model,
        max_turns=3,
        instructions=FREE_AGENT_INSTRUCTIONS,
        tools=[free_tool],
    )


def _make_paid_agent(model: str) -> Agent:
    return Agent(
        name="e2e_reqcred_agent",
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

        # Assert on the tool TASK output (deterministic) rather than the agent's
        # free-form text (whose shape varies and is unreliable to parse).
        task_output = str(tool_tasks["free_tool"]["output"]).lower()
        assert "free" in task_output, (
            f"[No-credential tool] free_tool task output missing its return "
            f"value 'free:ok'.\n  task={tool_tasks['free_tool']}"
        )

    def test_credential_required_tool_is_trimmed_and_fails(self, runtime, model):
        """The secret is trimmed in OSS/standalone, so a credential-requiring
        tool FAILS — and that expected failure is what we assert.

        ``get_secret(E2E_CRED_A)`` finds nothing in the injected credential
        context (no secret store; the reference is never resolved), raises, and
        paid_tool_a's task ends in a failure state. We prove the secret was
        genuinely not delivered (the success marker ``paid_a:`` never appears),
        and — by setting an OS env var of the same name — that env is NOT a
        silent fallback (``get_secret`` never reads ``os.environ``).
        """
        agent = _make_paid_agent(model)

        # Set an OS env var matching the credential name. get_secret() reads the
        # injected credential context, never os.environ — so this must NOT make
        # the tool succeed or leak into the output.
        os.environ[CRED_A] = "from-env-aaa"
        try:
            result = runtime.run(agent, "Call paid_tool_a with 'test'.", timeout=TIMEOUT)

            assert result.execution_id, (
                f"[Trimmed credential] No execution_id returned. {_run_diagnostic(result)}"
            )

            # The paid tool task must exist and be in a failure state — the
            # trimmed secret makes a successful run impossible. 'FAILED' is
            # accepted alongside the terminal variants: with no in-process
            # credential machinery, a missing credential surfaces as an ordinary
            # tool exception, which is the correct, expected outcome here.
            tool_tasks = _find_tool_tasks_for(result.execution_id)
            assert "paid_tool_a" in tool_tasks, (
                f"[Trimmed credential] paid_tool_a task not found — the agent "
                f"must call it so we can observe the expected failure.\n"
                f"  found_tasks={list(tool_tasks.keys())}\n"
                f"  {_run_diagnostic(result)}\n  {_tool_diagnostics(result.execution_id)}"
            )
            failure_states = {
                "FAILED",
                "FAILED_WITH_TERMINAL_ERROR",
                "COMPLETED_WITH_ERRORS",
                "TERMINATED",
            }
            task_info = tool_tasks["paid_tool_a"]
            assert task_info["status"] in failure_states, (
                f"[Trimmed credential] paid_tool_a must FAIL (secret is trimmed "
                f"in OSS), got '{task_info['status']}'. The tool must not "
                f"succeed without a delivered credential.\n  task={task_info}"
            )

            # Prove the secret was genuinely not delivered: the success marker
            # 'paid_a:' (returned only when a real value is read) must be absent.
            task_out = str(task_info["output"])
            assert "paid_a:" not in task_out, (
                f"[Trimmed credential] paid_tool_a produced its success output — "
                f"the secret was NOT trimmed as expected.\n  task={task_info}"
            )

            # Env is not a silent fallback: the OS env var value must not appear.
            # 'from-env' is the unique prefix of our test value ('fro' caused
            # false positives when LLM prose contained 'from').
            assert "from-env" not in task_out and "from-env" not in _get_output_text(result), (
                "SECURITY VIOLATION: an OS env var was used as a credential "
                "fallback. get_secret() must only read the injected credential "
                "context, never os.environ.\n"
                f"  {_run_diagnostic(result)}\n  task={task_info}"
            )
        finally:
            os.environ.pop(CRED_A, None)


# Output masking (Audit gap D) is covered deterministically by the server's
# SecretMaskingIntegrationTest (MockMvc + @MockBean AgentService). An e2e
# version would need the LLM to reliably call a specific tool whose output
# contains the leaked value — non-deterministic; violates CLAUDE.md rule 1.
