"""Safety invariant: the agent's tools only ever dispatch READ-ONLY commands.

A source-level guard so that if anyone later wires a mutating agent-handler command
into a tool, CI fails loudly. Deterministic, no network/LLM.
"""
import pathlib

_TOOLS_SRC = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src" / "oncall_agent" / "tools.py"
).read_text()

# Mutating / privileged / heavy agent-handler commands that must never appear in
# tools.py. Names match the AgentHandlerCommand enum in orkes-saas exactly, so the
# guard actually catches them (the earlier list had non-existent names like
# ROLLOUT_RESTART_DEPLOYMENT / RUN_KUBECTL that could never match).
MUTATING_COMMANDS = [
    "DELETE_POD",
    "ROLLOUT_RESTART",
    "SCALE_DEPLOYMENT",
    "UPGRADE_DEPLOYMENT",
    "ROLLBACK_DEPLOYMENT",
    "UPDATE_DEPLOYMENT_MEMORY",
    "PATCH_DEPLOYMENT",
    "KUBECTL_UNRESTRICTED",
    "ADD_EKS_ADMIN",
    "UPDATE_API_KEY",
    "BACKUP_CONDUCTOR",
    "DEPLOY_DEBUGGER_POD",
    "DEPLOY_MCP_WORKER",
    # heavy / disruptive read commands — out of scope for advisory triage.
    # (DOWNLOAD_HEAP_DUMP was moved to the allowed set by explicit team decision,
    # 2026-07-22: the agent captures the dump itself for heap alerts — one pod,
    # once per incident — instead of telling the engineer to. See
    # tools.download_heap_dump and the playbook HEAP NEXT-STEP RULE.)
    "DOWNLOAD_THREAD_DUMP",
    "DOWNLOAD_ALL_POD_LOGS",
]


def test_no_mutating_commands_wired_into_tools():
    found = [c for c in MUTATING_COMMANDS if c in _TOOLS_SRC]
    assert not found, f"mutating command(s) wired into tools.py: {found}"


def test_sql_tool_goes_through_the_select_guard():
    # SQL must pass ensure_select before any dispatch — never raw to the DB.
    assert "ensure_select" in _TOOLS_SRC
