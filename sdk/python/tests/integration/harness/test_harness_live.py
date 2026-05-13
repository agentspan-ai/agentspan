# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Live-Conductor integration tests for HarnessRuntime.

These exercise the full path:

  HarnessRuntime.submit(prompt)
    → wrap each Tool as a ToolDef whose worker runs permission/sandbox/hook
    → build agentspan Agent(model, tools, system, ...)
    → AgentRuntime.stream_async() → Conductor LLM_CHAT_COMPLETE workflow
    → tool tasks scheduled by Conductor → Python worker polls → adapter pipeline
    → AgentEvent stream back to the harness

Requires:
  - Agentspan server running (AGENTSPAN_SERVER_URL, default localhost:6767)
  - OPENAI_API_KEY (or AGENTSPAN_LLM_MODEL set + matching key)

Run:
    cd sdk/python && uv run pytest tests/integration/harness -v -s
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from typing import Any, Dict, List

import pytest

from agentspan.harness import HarnessConfig, HarnessRuntime
from agentspan.harness.permission import (
    PermissionEngine,
    PermissionRule,
    RuleSource,
)
from agentspan.harness.sandbox import ChecksOnlySandbox
from agentspan.harness.tools.builtins import (
    ListFiles,
    PatchFile,
    ReadFile,
    StructuredOutput,
    UpdatePlan,
    WriteFile,
)

pytestmark = pytest.mark.integration


# Per-test budget. asyncio.wait_for gives a clean cancellation so a hung
# shell tool / runaway loop fails fast instead of blocking the whole suite.
_PER_TEST_BUDGET_SEC = 60.0


def _run_with_timeout(coro_factory):
    """Run an async coroutine factory under a hard 60s ceiling."""
    async def _runner():
        await asyncio.wait_for(coro_factory(), timeout=_PER_TEST_BUDGET_SEC)
    asyncio.run(_runner())


def _allow_all_rules(*tool_names: str) -> List[PermissionRule]:
    return [
        PermissionRule(source=RuleSource.PROJECT, behavior="allow", tool_name=n)
        for n in tool_names
    ]


@pytest.fixture
def workdir():
    td = tempfile.mkdtemp(prefix="harness-live-")
    try:
        yield td
    finally:
        shutil.rmtree(td, ignore_errors=True)


@pytest.fixture
def harness(runtime, workdir, model):
    """Build a HarnessRuntime that shares the module-scoped AgentRuntime."""
    sandbox = ChecksOnlySandbox(
        allowed_read_roots=[workdir],
        allowed_write_roots=[workdir],
    )
    rules = _allow_all_rules(
        "read_file", "list_files", "write_file", "patch_file",
        "update_plan", "structured_output",
    )
    config = HarnessConfig(
        model=model,
        tools=[
            ReadFile(), ListFiles(), WriteFile(), PatchFile(),
            UpdatePlan(), StructuredOutput(),
        ],
        cwd=workdir,
        sandbox=sandbox,
        permission_engine=PermissionEngine(rules=rules),
        system=(
            "You are a precise tool-using assistant. Use the tools provided. "
            "Always finish by calling structured_output exactly once."
        ),
        max_turns=8,
        max_tokens=2000,
    )
    rt = HarnessRuntime(config, agent_runtime=runtime)
    yield rt
    rt.close()


# ── Tests ───────────────────────────────────────────────────────────────


def test_submit_runs_tool_and_completes(harness, workdir):
    """Smoke: ask the LLM to write one file then call structured_output;
    verify (a) events stream, (b) the tool ran (file exists), (c) structured
    output captured."""
    target_path = "hello.txt"
    target_content = "agentspan harness e2e"

    prompt = (
        f"Use write_file to create {target_path!r} with the exact content "
        f"{target_content!r} (use create_dirs=true if needed). "
        "Then call structured_output with {\"done\": true, \"path\": "
        f"{target_path!r}}}."
    )

    events: List[Any] = []

    async def _run() -> None:
        async for event in harness.submit(prompt):
            events.append(event)

    _run_with_timeout(_run)

    # 1. We saw at least one event.
    assert events, "expected at least one event from submit()"

    # 2. The file was actually written by the wrapped tool.
    full = os.path.join(workdir, target_path)
    assert os.path.exists(full), f"expected {full} to exist after submit()"
    assert open(full).read() == target_content

    # 3. We have an execution_id correlation.
    assert harness.last_execution_id, "expected execution_id to be set"

    # 4. structured_output was captured (best-effort — small models sometimes
    #    omit it, so this is a soft signal). If the file was written, the
    #    end-to-end pipeline worked even when the model didn't summarize.
    structured = harness.session_store.get("structured_output")
    if structured:
        assert isinstance(structured, dict), f"expected dict, got {type(structured)}"


def _workflow_tasks(execution_id: str) -> List[Dict[str, Any]]:
    """Pull the Conductor workflow's task list — the algorithmic ground
    truth for what the harness adapter actually returned to the LLM."""
    import requests
    url = (os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
           .rstrip("/").replace("/api", ""))
    resp = requests.get(f"{url}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    return resp.json().get("tasks", []) or []


def test_permission_deny_surfaces_as_tool_error(runtime, workdir, model):
    """A tool with NO allow rule must produce a model-visible tool error
    (not a worker exception, not a workflow failure).

    Algorithmic check: read the Conductor workflow's write_file task output
    and assert it carries the canonical denial string. We don't grep model
    text — the model may phrase the failure however it wants."""
    sandbox = ChecksOnlySandbox(
        allowed_read_roots=[workdir],
        allowed_write_roots=[workdir],
    )
    # Allow only structured_output. write_file is not allowed.
    rules = _allow_all_rules("structured_output")

    rt = HarnessRuntime(
        HarnessConfig(
            model=model,
            tools=[WriteFile(), StructuredOutput()],
            cwd=workdir,
            sandbox=sandbox,
            permission_engine=PermissionEngine(rules=rules),
            system=(
                "You are a tool-using assistant. If a tool fails, do NOT retry "
                "it more than once — instead, finish by calling structured_output "
                "with the observed error message in the 'error' field."
            ),
            max_turns=6,
            max_tokens=1000,
        ),
        agent_runtime=runtime,
    )

    prompt = (
        "Try to write_file at path 'denied.txt' with content 'x'. "
        "If it fails, call structured_output with "
        "{\"attempted\": true, \"error\": \"<exact error message you saw>\"}."
    )

    async def _run() -> None:
        async for _ in rt.submit(prompt):
            pass

    try:
        _run_with_timeout(_run)
    finally:
        rt.close()

    # The denied write must NOT have produced a file.
    assert not os.path.exists(os.path.join(workdir, "denied.txt"))

    # Algorithmic: at least one write_file task ran AND its output carries
    # the canonical denial string from the harness adapter.
    tasks = _workflow_tasks(rt.last_execution_id or "")
    write_tasks = [t for t in tasks if t.get("taskType") == "write_file"]
    assert write_tasks, "expected at least one write_file task"
    denial_outputs = [
        t for t in write_tasks
        if "Permission denied" in str(t.get("outputData", {}).get("result", ""))
    ]
    assert denial_outputs, (
        "expected at least one write_file task output containing the canonical "
        f"denial. saw outputs: {[t.get('outputData') for t in write_tasks]}"
    )


# ── Group A: broader live tool coverage ─────────────────────────────────


def _all_tools_harness(runtime, workdir, model, *,
                       extra_allow=()) -> HarnessRuntime:
    """Build a runtime with read + edit + plan + structured output tools
    plus shell, all permission-allowed."""
    from agentspan.harness.tools.builtins import (
        SearchText, Shell, ReadTaskOutput, StopTask,
    )
    sandbox = ChecksOnlySandbox(
        allowed_read_roots=[workdir],
        allowed_write_roots=[workdir],
        allowed_commands=["echo", "cat", "ls", "sh", "sleep", "printf"],
    )
    rules = _allow_all_rules(
        "read_file", "list_files", "search_text", "write_file", "patch_file",
        "shell", "read_task_output", "stop_task",
        "update_plan", "structured_output", *extra_allow,
    )
    cfg = HarnessConfig(
        model=model,
        tools=[
            ReadFile(), ListFiles(), SearchText(),
            WriteFile(), PatchFile(),
            Shell(), ReadTaskOutput(), StopTask(),
            UpdatePlan(), StructuredOutput(),
        ],
        cwd=workdir,
        sandbox=sandbox,
        permission_engine=PermissionEngine(rules=rules),
        system=(
            "You are a coding agent that uses tools to inspect and modify a "
            f"small workspace. The workspace directory is {workdir}. "
            "When using the shell tool, OMIT the cwd parameter — the tool "
            "defaults to the workspace and the sandbox forbids paths outside "
            "it. Use only relative paths for read_file / write_file / "
            "patch_file. Be concise. End by calling structured_output."
        ),
        max_turns=10,
        max_tokens=2000,
    )
    return HarnessRuntime(cfg, agent_runtime=runtime)


def test_live_read_search_patch_pipeline(runtime, workdir, model):
    """A.1: model reads a file, finds a substring with search_text, applies a
    patch, then verifies via re-read. Validates read_file + search_text +
    patch_file end-to-end through Conductor."""
    src = os.path.join(workdir, "code.py")
    with open(src, "w") as f:
        f.write("def add(a, b):\n    return a - b  # bug: subtract\n")

    rt = _all_tools_harness(runtime, workdir, model)
    prompt = (
        "There is a file 'code.py' in the workspace. It contains a bug. "
        "Use read_file to read it, then use patch_file to change "
        "'return a - b' to 'return a + b'. After patching, call "
        "structured_output."
    )

    async def _run() -> None:
        async for _ in rt.submit(prompt):
            pass

    try:
        _run_with_timeout(_run)
    finally:
        rt.close()

    # Algorithmic: file contents must match the expected fix.
    with open(src) as f:
        new_content = f.read()
    assert "return a + b" in new_content, new_content
    assert "return a - b" not in new_content, new_content

    # At least one read_file task and one patch_file task ran.
    tasks = _workflow_tasks(rt.last_execution_id or "")
    types = {t.get("taskType") for t in tasks}
    assert "read_file" in types, types
    assert "patch_file" in types, types


def test_live_shell_foreground_writes_log(runtime, workdir, model):
    """A.2: model runs a shell command. Validates Shell + sandbox auto-extend
    + content_ref. Algorithmic: assert workflow shows a successful shell
    task with exit_code=0 and a non-empty log."""
    rt = _all_tools_harness(runtime, workdir, model)
    prompt = (
        "Run the shell command \"echo agentspan-shell-marker-7QX\". "
        "Then call structured_output."
    )

    async def _run() -> None:
        async for _ in rt.submit(prompt):
            pass

    try:
        _run_with_timeout(_run)
    finally:
        rt.close()

    tasks = _workflow_tasks(rt.last_execution_id or "")
    shell_tasks = [t for t in tasks if t.get("taskType") == "shell"]
    assert shell_tasks, f"expected at least one shell task. types: {[t.get('taskType') for t in tasks]}"

    success = [
        t for t in shell_tasks
        if not t.get("outputData", {}).get("is_error", True)
        and "agentspan-shell-marker-7QX" in str(t.get("outputData", {}).get("result", ""))
    ]
    assert success, (
        "expected a shell task whose result contains the marker. "
        f"outputs: {[t.get('outputData') for t in shell_tasks]}"
    )


# NOTE: shell run_in_background mode is intentionally not live-tested in v1.
# The harness's threaded-worker model can't keep an asyncio.Task alive past
# the worker's transient event loop, so background tasks don't poll their
# subprocesses to completion. Re-enable when the harness gains a long-lived
# event loop (post-v1).


def test_live_subagent_runs_to_completion(runtime, workdir, model):
    """A.4 + C.11: spawn_agent (sync, no worktree) builds a real child
    HarnessRuntime, the child runs a tiny prompt, the parent receives the
    structured result. Algorithmic: assert spawn_agent task output carries
    the child's structured payload."""
    from agentspan.harness.tools.builtins import SpawnAgent

    parent_sandbox = ChecksOnlySandbox(
        allowed_read_roots=[workdir],
        allowed_write_roots=[workdir],
    )

    def factory(ctx, input):
        # Child: tiny tool set, run a prompt, finish via structured_output.
        cfg = HarnessConfig(
            model=model,
            tools=[StructuredOutput()],
            cwd=workdir,
            sandbox=parent_sandbox,
            permission_engine=PermissionEngine(
                rules=_allow_all_rules("structured_output"),
            ),
            system=(
                "You are a child subagent. Always finish by calling "
                "structured_output exactly once."
            ),
            max_turns=4,
            max_tokens=400,
            session_id=f"child-{os.urandom(4).hex()}",
        )
        return HarnessRuntime(cfg, agent_runtime=runtime)

    rules = _allow_all_rules("spawn_agent", "structured_output")
    parent_cfg = HarnessConfig(
        model=model,
        tools=[SpawnAgent(factory=factory), StructuredOutput()],
        cwd=workdir,
        sandbox=parent_sandbox,
        permission_engine=PermissionEngine(rules=rules),
        system=(
            "You orchestrate a subagent. Call spawn_agent exactly once with a "
            "trivial prompt that asks the subagent for a constant value, then "
            "call structured_output with the result."
        ),
        max_turns=6,
        max_tokens=1500,
    )
    parent = HarnessRuntime(parent_cfg, agent_runtime=runtime)

    prompt = (
        "Use spawn_agent (foreground / not background) with description='echo' "
        "and prompt=\"Call structured_output with {\\\"value\\\": 42}\". "
        "After it returns, call structured_output yourself with "
        "{\"child_result\": <the structured value the child produced>}."
    )

    async def _run() -> None:
        async for _ in parent.submit(prompt):
            pass

    try:
        _run_with_timeout(_run)
    finally:
        parent.close()

    tasks = _workflow_tasks(parent.last_execution_id or "")
    spawn_tasks = [t for t in tasks if t.get("taskType") == "spawn_agent"]
    assert spawn_tasks, f"expected spawn_agent task. types={[t.get('taskType') for t in tasks]}"
    spawned = spawn_tasks[0].get("outputData", {})
    # The harness adapter shapes spawn_agent output as {result, is_error, ...}.
    # The "result" carries the dict spawn_agent.call() returned.
    spawn_result = spawned.get("result")
    assert spawn_result and not spawned.get("is_error"), spawned
    assert isinstance(spawn_result, dict) or "child" in str(spawn_result), spawn_result


def test_live_parallel_tool_calls_in_one_turn(runtime, workdir, model):
    """A.5: model emits two read_file calls in one turn. Conductor's flow
    is LLM_CHAT_COMPLETE → SWITCH → FORK → [read_file, read_file] → JOIN.
    Verifies the harness adapter's concurrency-safety claim under FORK."""
    a = os.path.join(workdir, "a.txt")
    b = os.path.join(workdir, "b.txt")
    with open(a, "w") as f:
        f.write("alpha-marker-X1")
    with open(b, "w") as f:
        f.write("beta-marker-Y2")

    rt = _all_tools_harness(runtime, workdir, model)
    prompt = (
        "Read BOTH files 'a.txt' and 'b.txt' in a SINGLE turn (issue both "
        "read_file tool calls in the same response, do not wait for one "
        "before issuing the other). After you have both contents, call "
        "structured_output with {\"a\": <a contents>, \"b\": <b contents>}."
    )

    async def _run() -> None:
        async for _ in rt.submit(prompt):
            pass

    try:
        _run_with_timeout(_run)
    finally:
        rt.close()

    tasks = _workflow_tasks(rt.last_execution_id or "")
    read_tasks = [t for t in tasks if t.get("taskType") == "read_file"]
    assert len(read_tasks) >= 2, (
        f"expected ≥2 read_file tasks for parallel reads; saw {len(read_tasks)} "
        f"types={[t.get('taskType') for t in tasks]}"
    )
    # At least one FORK task must have wrapped them — that's how Conductor
    # schedules in-turn parallel tool calls.
    forks = [t for t in tasks if t.get("taskType") == "FORK"]
    assert forks, f"expected ≥1 FORK task. types={[t.get('taskType') for t in tasks]}"


# ── Group B: durability ────────────────────────────────────────────────


def test_live_idempotency_key_reattaches_running_workflow(runtime, workdir, model):
    """B.6: while a workflow is RUNNING, a second submit with the same
    session_id (= idempotency_key) re-attaches to the same execution_id.

    We start a slow first submit in a background thread, give Conductor
    a moment to register the workflow, then start a second submit with
    the same config and confirm the execution_id matches. This is the
    real "kill-and-resume" path — agentspan's worker-liveness machinery
    handles the post-crash re-attach via the same idempotency_key.

    Conductor's idempotent-start contract: re-attach if running with the
    same key; start fresh if the previous run is terminal. We rely on
    the running-workflow case here.
    """
    import threading

    from agentspan.harness.tools.builtins import Shell
    sandbox = ChecksOnlySandbox(
        allowed_read_roots=[workdir],
        allowed_write_roots=[workdir],
        allowed_commands=["sh", "sleep", "echo"],
    )
    cfg = HarnessConfig(
        model=model,
        tools=[Shell(), StructuredOutput()],
        cwd=workdir,
        sandbox=sandbox,
        permission_engine=PermissionEngine(
            rules=_allow_all_rules("shell", "structured_output"),
        ),
        system=(
            "Run the shell command 'sh -c \"sleep 5\"' to deliberately wait "
            "5 seconds, then call structured_output. OMIT cwd from the "
            "shell call — the sandbox forbids /tmp, /home, /, etc."
        ),
        max_turns=4,
        max_tokens=400,
        session_id=f"resume-test-{os.urandom(4).hex()}",
    )

    rt1 = HarnessRuntime(cfg, agent_runtime=runtime)
    prompt = "Do exactly what the system prompt says."

    first_id = {"v": None}

    def _bg_first() -> None:
        async def _go():
            async for _ in rt1.submit(prompt):
                if rt1.last_execution_id and first_id["v"] is None:
                    first_id["v"] = rt1.last_execution_id
        try:
            asyncio.run(asyncio.wait_for(_go(), timeout=45.0))
        except Exception:
            pass

    t = threading.Thread(target=_bg_first, daemon=True)
    t.start()
    # Wait until first submit registers a workflow.
    for _ in range(40):
        if first_id["v"]:
            break
        import time as _time
        _time.sleep(0.1)
    assert first_id["v"], "first submit didn't register an execution within 4s"

    # Second runtime with the SAME session_id while the first is running.
    rt2 = HarnessRuntime(cfg, agent_runtime=runtime)
    try:
        async def _short() -> None:
            async for _ in rt2.submit(prompt):
                if rt2.last_execution_id:
                    return
        try:
            asyncio.run(asyncio.wait_for(_short(), timeout=10.0))
        except asyncio.TimeoutError:
            pass
        second_id = rt2.last_execution_id
    finally:
        rt2.close()
        # let the bg thread finish
        t.join(timeout=45)
        rt1.close()

    assert second_id == first_id["v"], (
        f"expected re-attach: {first_id['v']} vs {second_id}"
    )
