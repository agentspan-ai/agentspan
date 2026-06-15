"""Safety invariant: the agent's tools only ever dispatch READ-ONLY commands.

A source-level guard so that if anyone later wires a mutating agent-handler command
into a tool, CI fails loudly. Deterministic, no network/LLM.
"""
import pathlib

_TOOLS_SRC = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src" / "oncall_agent" / "tools.py"
).read_text()

# Mutating / privileged agent-handler commands that must never appear in tools.py.
MUTATING_COMMANDS = [
    "DELETE_POD",
    "ROLLOUT_RESTART_DEPLOYMENT",
    "SCALE_DEPLOYMENT",
    "UPGRADE_DEPLOYMENT",
    "PATCH_DEPLOYMENT",
    "RUN_KUBECTL",
    "KUBECTL_UNRESTRICTED",
    "ADD_EKS_ADMIN",
    "UPDATE_API_KEY",
    "BACKUP_CONDUCTOR",
    "DEPLOY_DEBUGGER_POD",
    "DEPLOY_MCP_WORKER",
]


def test_no_mutating_commands_wired_into_tools():
    found = [c for c in MUTATING_COMMANDS if c in _TOOLS_SRC]
    assert not found, f"mutating command(s) wired into tools.py: {found}"


def test_sql_tool_goes_through_the_select_guard():
    # SQL must pass ensure_select before any dispatch — never raw to the DB.
    assert "ensure_select" in _TOOLS_SRC
