# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""CLI tool with guardrails — safe command execution.

Demonstrates tool-level guardrails on CLI commands. The agent can run
whitelisted commands, but a RegexGuardrail blocks dangerous patterns
(e.g. ``rm -rf``, ``sudo``) *before* the command executes.

Guardrails are compiled into Conductor workflow tasks that run between
the LLM's tool-call decision and the actual fork-join execution.
If a guardrail fails:

- ``on_fail="raise"`` terminates the workflow immediately
- ``on_fail="retry"`` feeds the rejection back to the LLM so it
  can generate a safer command
- ``on_fail="human"`` pauses for human approval via HITL

This example uses two guardrails:

1. **block_destructive** — ``on_fail="raise"``: hard-blocks ``rm -rf``,
   ``mkfs``, and ``dd`` patterns. No retry, no negotiation.
2. **review_sudo** — ``on_fail="retry"``: rejects ``sudo`` commands and
   asks the LLM to try without elevated privileges.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, CliConfig, OnFail, RegexGuardrail
from settings import settings

# ── Guardrails ────────────────────────────────────────────────────────

block_destructive = RegexGuardrail(
    patterns=[
        r"rm\s+-rf\s+/",       # rm -rf /
        r"mkfs\.",              # mkfs.ext4, mkfs.xfs, ...
        r"\bdd\s+if=",         # dd if=/dev/zero ...
    ],
    mode="block",
    name="block_destructive",
    message="Destructive system commands are not allowed.",
    on_fail=OnFail.RAISE,      # hard stop — no retry
)

review_sudo = RegexGuardrail(
    patterns=[r"\bsudo\b"],
    mode="block",
    name="review_sudo",
    message=(
        "Commands requiring sudo are not permitted. "
        "Rewrite the command without elevated privileges."
    ),
    on_fail=OnFail.RETRY,      # LLM gets another chance
    max_retries=2,
)

# ── Agent ─────────────────────────────────────────────────────────────

ops_agent = Agent(
    name="ops_agent",
    model=settings.llm_model,
    instructions=(
        "You are a DevOps assistant. Use the run_command tool to help "
        "the user inspect and manage their system. You can list files, "
        "check disk usage, read logs, and run git commands.\n\n"
        "IMPORTANT: Never use sudo or destructive commands like rm -rf."
    ),
    cli_config=CliConfig(
        allowed_commands=["ls", "cat", "df", "du", "git", "ps", "uname", "wc"],
        timeout=15,
        guardrails=[block_destructive, review_sudo],
    ),
)

# ── Run ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    prompt = "Show me the disk usage summary and list files in the current directory."

    print("=" * 60)
    print("  CLI Tool with Guardrails")
    print("  Allowed: ls, cat, df, du, git, ps, uname, wc")
    print("  Blocked: rm -rf, sudo, mkfs, dd")
    print("=" * 60)
    print(f"\nPrompt: {prompt}\n")


    with AgentRuntime() as runtime:
        result = runtime.run(ops_agent, prompt)
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(ops_agent)
        # CLI alternative:
        # agentspan deploy --package examples.62_cli_tool_guardrails
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(ops_agent)

