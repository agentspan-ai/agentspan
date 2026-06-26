"""Suite 3: CLI Tools — command whitelist enforcement.

Tests CLI tool execution with command filtering:
  1. The compiled run_command tool advertises exactly the allowed commands
  2. Commands outside the whitelist are rejected (cd)

The credential-lifecycle coverage (gh requires a server-stored token, env
vars NOT used) has been removed: secrets are delegated to the Orkes host via
``${workflow.secrets.NAME}`` and standalone/CI has no secret backend to inject
a credential value into a running tool.

No mocks. Real server, real CLI, real LLM.
"""

import re

import pytest

from agentspan.agents import Agent
from agentspan.agents.cli_config import _validate_cli_command

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.xdist_group("credentials"),
]

TIMEOUT = 120


# ── Helpers ─────────────────────────────────────────────────────────────


PROMPT_CD = """\
You MUST call the run_command tool with command="cd" and args=["/etc"].
Report the exact output or error message verbatim.
"""


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


# ── Test ────────────────────────────────────────────────────────────────


@pytest.mark.timeout(600)
class TestSuite3CliTools:
    """CLI tools: command whitelist enforcement."""

    def test_cli_command_whitelist(self, runtime, model):
        """Command whitelist enforcement — cd is rejected, allowed list matches.

        All validation is algorithmic — no LLM output parsing.
        """
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
            f"[Step 6: cd blocked] No execution_id. {_run_diagnostic(result_cd)}"
        )
        assert result_cd.status in ("COMPLETED", "FAILED", "TERMINATED"), (
            f"[Step 6: cd blocked] Expected terminal status, "
            f"got '{result_cd.status}'.\n"
            f"  {_run_diagnostic(result_cd)}"
        )
