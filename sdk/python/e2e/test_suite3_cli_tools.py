"""Suite 3: CLI Tools — command whitelist and credential lifecycle.

Tests CLI tool execution with credential isolation:
  1. ls and mktemp succeed without credentials
  2. gh fails without server credential (env vars NOT used)
  3. gh succeeds after credential added to server
  4. Commands outside whitelist are rejected (cd)

Single sequential test with try/finally cleanup.
No mocks. Real server, real CLI, real LLM.
"""

import os
import re
import subprocess

import pytest
import requests

from agentspan.agents import Agent, tool
from agentspan.agents.cli_config import _validate_cli_command

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.xdist_group("credentials"),
]

CRED_NAME = "GITHUB_TOKEN"
TIMEOUT = 120


# ── Tools ───────────────────────────────────────────────────────────────


@tool
def cli_ls(path: str = ".") -> str:
    """List directory contents using the ls command."""
    result = subprocess.run(["ls", path], capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        return f"ls_error:{result.stderr.strip()[:200]}"
    return f"ls_ok:{result.stdout.strip()[:200]}"


@tool
def cli_mktemp() -> str:
    """Create a temporary file and return its path."""
    result = subprocess.run(["mktemp"], capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        return f"mktemp_error:{result.stderr.strip()[:200]}"
    return f"mktemp_ok:{result.stdout.strip()}"


@tool(credentials=[CRED_NAME])
def cli_gh(subcommand: str, args: str = "") -> str:
    """Run a gh CLI command. Requires GITHUB_TOKEN credential.
    Example: subcommand="repo list", args="--limit 3"
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN not found in environment. "
            "The server should have injected it via credential resolution."
        )
    cmd = ["gh"] + subcommand.split()
    if args:
        cmd += args.split()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return f"gh_error:{result.stderr.strip()[:200]}"
    return f"gh_ok:{result.stdout.strip()[:200]}"


# ── Helpers ─────────────────────────────────────────────────────────────


AGENT_INSTRUCTIONS = """\
You have three tools: cli_ls, cli_mktemp, and cli_gh.
You MUST call each tool exactly once as directed and report the output verbatim.
Do not skip any tool. Do not add commentary beyond the results.
"""

PROMPT_ALL_THREE = """\
Call all three tools:
1. cli_ls with path="/tmp"
2. cli_mktemp (no arguments)
3. cli_gh with subcommand="repo list" and args="--limit 3"
Report each result in this format:
  cli_ls: <output>
  cli_mktemp: <output>
  cli_gh: <output>
"""

PROMPT_CD = """\
You MUST call the run_command tool with command="cd" and args=["/etc"].
Report the exact output or error message verbatim.
"""


def _make_agent(model: str) -> Agent:
    """Agent with custom CLI tools for credential testing."""
    return Agent(
        name="e2e_cli_tools",
        model=model,
        instructions=AGENT_INSTRUCTIONS,
        tools=[cli_ls, cli_mktemp, cli_gh],
    )


def _make_whitelist_agent(model: str) -> Agent:
    """Agent with CLI whitelist for command filtering testing."""
    return Agent(
        name="e2e_cli_whitelist",
        model=model,
        instructions=(
            "You have a run_command tool that executes CLI commands. "
            "Always call the tool as instructed and report the exact output."
        ),
        cli_commands=True,
        cli_allowed_commands=["ls", "mktemp", "gh"],
    )


def _get_output_text(result) -> str:
    """Extract the text output from a run result.

    The result.output is typically a dict with a 'result' key containing
    a list of streaming tokens/chunks.
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


def _run_diagnostic(result) -> str:
    """Build a diagnostic string from a run result for error messages."""
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
        out_str = str(output)
        if len(out_str) > 200:
            out_str = out_str[:200] + "..."
        parts.append(f"output={out_str}")
    return " | ".join(parts)


def _get_workflow(execution_id: str) -> dict:
    """Fetch workflow from server API."""
    base = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
    base_url = base.rstrip("/").replace("/api", "")
    resp = requests.get(f"{base_url}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _tool_diagnostics(execution_id: str, tool_names: set[str]) -> str:
    """Fetch workflow tasks and report tool-related task statuses."""
    try:
        wf = _get_workflow(execution_id)
    except Exception as e:
        return f"(could not fetch workflow: {e})"

    tool_tasks = []
    for task in wf.get("tasks", []):
        ref = task.get("referenceTaskName", "")
        status = task.get("status", "")
        reason = task.get("reasonForIncompletion", "")
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
        wf_status = wf.get("status", "unknown")
        wf_reason = wf.get("reasonForIncompletion", "")
        summary = f"No tool tasks found in workflow. workflow_status={wf_status}"
        if wf_reason:
            summary += f" reason={wf_reason}"
        return summary

    return "\n  ".join(["Tool tasks:"] + tool_tasks)


def _assert_run_completed(result, step_name: str):
    """Assert a run completed successfully with actionable diagnostics."""
    diag = _run_diagnostic(result)

    assert result.execution_id, f"[{step_name}] No execution_id returned. {diag}"

    output = result.output
    if isinstance(output, dict) and output.get("finishReason") == "TOOL_CALLS":
        tool_diag = _tool_diagnostics(
            result.execution_id, {"cli_ls", "cli_mktemp", "cli_gh"}
        )
        pytest.fail(
            f"[{step_name}] Run stalled at tool-calling stage — tools were "
            f"requested but did not return results.\n"
            f"  {diag}\n"
            f"  {tool_diag}"
        )

    assert result.status == "COMPLETED", (
        f"[{step_name}] Run did not complete. {diag}\n"
        f"  {_tool_diagnostics(result.execution_id, {'cli_ls', 'cli_mktemp', 'cli_gh'})}"
    )


# ── Test ────────────────────────────────────────────────────────────────


@pytest.mark.timeout(600)
class TestSuite3CliTools:
    """CLI tools: credential lifecycle + command whitelist."""

    def test_cli_credential_lifecycle(self, runtime, cli_credentials, model):
        """Full CLI credential lifecycle — sequential steps with cleanup."""
        real_token = os.environ.get("GITHUB_TOKEN")
        if not real_token:
            pytest.skip(
                "GITHUB_TOKEN not set in environment — "
                "required for Suite 3 CLI tools test"
            )

        # Verify gh CLI is installed
        try:
            subprocess.run(
                ["gh", "--version"], capture_output=True, text=True, timeout=5
            )
        except FileNotFoundError:
            pytest.skip("gh CLI not installed — required for Suite 3 CLI tools test")

        try:
            self._run_lifecycle(runtime, cli_credentials, model, real_token)
        finally:
            cli_credentials.delete(CRED_NAME)
            os.environ.pop(CRED_NAME, None)

    def _run_lifecycle(self, runtime, cli_credentials, model, real_token):
        agent = _make_agent(model)

        # ── Step 1: Clean slate — remove credential from server ─────
        cli_credentials.delete(CRED_NAME)

        # ── Step 2: Export GITHUB_TOKEN to env ──────────────────────
        # This validates the SDK does NOT read credentials from env.
        # The real token is in the env but NOT in the server store.
        os.environ["GITHUB_TOKEN"] = real_token

        # ── Step 3: Run agent — ls/mktemp succeed, gh fails ────────
        result = runtime.run(agent, PROMPT_ALL_THREE, timeout=TIMEOUT)

        assert result.execution_id, (
            f"[Step 3: No credential] No execution_id. "
            f"{_run_diagnostic(result)}"
        )
        assert result.status in ("COMPLETED", "FAILED", "TERMINATED"), (
            f"[Step 3: No credential] Expected terminal status, "
            f"got '{result.status}'. The agent should complete or fail "
            f"when gh credential is missing.\n"
            f"  {_run_diagnostic(result)}\n"
            f"  {_tool_diagnostics(result.execution_id, {'cli_ls', 'cli_mktemp', 'cli_gh'})}"
        )

        output = _get_output_text(result)

        # ls and mktemp should succeed (no credentials needed)
        assert "ls_ok" in output, (
            f"[Step 3: No credential] cli_ls should succeed — it needs no "
            f"credentials.\n"
            f"  output={output[:500]}\n"
            f"  {_run_diagnostic(result)}\n"
            f"  {_tool_diagnostics(result.execution_id, {'cli_ls', 'cli_mktemp', 'cli_gh'})}"
        )
        assert "mktemp_ok" in output, (
            f"[Step 3: No credential] cli_mktemp should succeed — it needs "
            f"no credentials.\n"
            f"  output={output[:500]}\n"
            f"  {_run_diagnostic(result)}"
        )

        # gh should fail — credential not in server, env must NOT be used
        assert "gh_ok" not in output, (
            f"[Step 3: No credential] SECURITY: cli_gh should NOT succeed — "
            f"GITHUB_TOKEN is in env but NOT in the server credential store. "
            f"If it succeeded, env vars are leaking through credential "
            f"isolation.\n"
            f"  output={output[:500]}"
        )

        # ── Step 4: Add credential via CLI ──────────────────────────
        cli_credentials.set(CRED_NAME, real_token)

        # ── Step 5: Run agent — all three should succeed ────────────
        result = runtime.run(agent, PROMPT_ALL_THREE, timeout=TIMEOUT)
        _assert_run_completed(result, "Step 5: With credential")

        output = _get_output_text(result)

        assert "ls_ok" in output, (
            f"[Step 5: With credential] cli_ls should succeed.\n"
            f"  output={output[:500]}\n"
            f"  {_run_diagnostic(result)}"
        )
        assert "mktemp_ok" in output, (
            f"[Step 5: With credential] cli_mktemp should succeed.\n"
            f"  output={output[:500]}\n"
            f"  {_run_diagnostic(result)}"
        )
        assert "gh_ok" in output, (
            f"[Step 5: With credential] cli_gh should succeed — "
            f"GITHUB_TOKEN was added to server credential store.\n"
            f"  output={output[:500]}\n"
            f"  {_run_diagnostic(result)}\n"
            f"  {_tool_diagnostics(result.execution_id, {'cli_ls', 'cli_mktemp', 'cli_gh'})}"
        )

        # ── Step 6: cd command — not allowed ─────────────────────────
        # All validation is algorithmic — no LLM output parsing.

        EXPECTED_ALLOWED = ["ls", "mktemp", "gh"]
        whitelist_agent = _make_whitelist_agent(model)

        # 6a. Validate whitelist via plan() — the compiled tool description
        #     must list exactly the expected allowed commands.
        plan = runtime.plan(whitelist_agent)
        ad = plan["workflowDef"]["metadata"]["agentDef"]
        cli_tool = next(
            (t for t in ad.get("tools", []) if "run_command" in t["name"]),
            None,
        )
        assert cli_tool is not None, (
            f"[Step 6: cd blocked] No run_command tool in compiled agent. "
            f"Tools: {[t['name'] for t in ad.get('tools', [])]}"
        )
        # Parse the exact allowed commands from the tool description.
        # Format: "... Allowed commands: gh, ls, mktemp. ..."
        tool_desc = cli_tool.get("description", "")
        match = re.search(r"Allowed commands:\s*(.+?)\.", tool_desc)
        assert match, (
            f"[Step 6: cd blocked] Could not find 'Allowed commands:' in "
            f"compiled run_command tool description.\n"
            f"  description={tool_desc}"
        )
        actual_commands = sorted(c.strip() for c in match.group(1).split(","))
        assert actual_commands == sorted(EXPECTED_ALLOWED), (
            f"[Step 6: cd blocked] Allowed commands mismatch.\n"
            f"  expected={sorted(EXPECTED_ALLOWED)}\n"
            f"  actual={actual_commands}"
        )

        # 6b. Validate cd rejection directly — call the validation function
        #     and assert it raises ValueError with the correct message.
        with pytest.raises(ValueError, match="not allowed") as exc_info:
            _validate_cli_command("cd", EXPECTED_ALLOWED)

        error_msg = str(exc_info.value)
        for cmd in EXPECTED_ALLOWED:
            assert cmd in error_msg, (
                f"[Step 6: cd blocked] Rejection error must list '{cmd}' "
                f"as an allowed command.\n"
                f"  error_msg={error_msg}"
            )

        # 6c. Run the agent to verify it reaches terminal status.
        result_cd = runtime.run(whitelist_agent, PROMPT_CD, timeout=TIMEOUT)

        assert result_cd.execution_id, (
            f"[Step 6: cd blocked] No execution_id. "
            f"{_run_diagnostic(result_cd)}"
        )
        assert result_cd.status in ("COMPLETED", "FAILED", "TERMINATED"), (
            f"[Step 6: cd blocked] Expected terminal status, "
            f"got '{result_cd.status}'.\n"
            f"  {_run_diagnostic(result_cd)}"
        )
