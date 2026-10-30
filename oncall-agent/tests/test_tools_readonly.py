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
    # KUBECTL_UNRESTRICTED is allowed ONLY behind the deterministic read-only
    # guard (kubectl_guard.ensure_readonly_kubectl) — see run_kubectl_read and
    # test_run_kubectl_read_rejects_mutations_before_dispatch.
    "ADD_EKS_ADMIN",
    "UPDATE_API_KEY",
    "BACKUP_CONDUCTOR",
    "DEPLOY_DEBUGGER_POD",
    "DEPLOY_MCP_WORKER",
    # heavy / disruptive read commands — out of scope for advisory triage.
    # (DOWNLOAD_HEAP_DUMP and DOWNLOAD_THREAD_DUMP were moved to the allowed set
    # by explicit team decision, 2026-07-22: the agent captures dumps itself —
    # heap dumps only for memory alerts, one pod, once per incident (jmap is
    # stop-the-world); thread dumps for CPU/hot-loop triage (jstack, cheap).
    # See tools.download_heap_dump / download_thread_dump and the playbook.)
    "DOWNLOAD_ALL_POD_LOGS",
]


def test_no_mutating_commands_wired_into_tools():
    found = [c for c in MUTATING_COMMANDS if c in _TOOLS_SRC]
    assert not found, f"mutating command(s) wired into tools.py: {found}"


def test_sql_tool_goes_through_the_select_guard():
    # SQL must pass ensure_select before any dispatch — never raw to the DB.
    assert "ensure_select" in _TOOLS_SRC


def test_kubectl_tool_goes_through_the_readonly_guard():
    # kubectl must pass ensure_readonly_kubectl before any dispatch.
    assert "ensure_readonly_kubectl" in _TOOLS_SRC
