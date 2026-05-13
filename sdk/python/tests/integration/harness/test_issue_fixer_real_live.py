"""Live integration tests for the production issue-fixer pipeline (102).

Strategy: avoid hitting real GitHub by pre-populating the parent's
SharedStore with a fixture ``issue_pr`` payload AND skipping ``setup_repo``
by initializing a small local git repo in the workspace. Each test
focuses on one stage's adapter wiring rather than the whole pipeline:

  - The new tools (ReadSymbol, MultiEdit, WebFetch) execute live as
    Conductor SIMPLE tasks under a HarnessRuntime+Agent.
  - HarnessConfig.stop_condition fires (an Agent's stop_when call
    short-circuits the loop).
  - SharedStore round-trips between parent and a child harness sharing
    the same shared_store_dir.

We don't drive the full 4-stage pipeline against a real LLM here — too
expensive and flaky. Phase D will add a proper end-to-end smoke once a
fixture repo is committed to the test corpus.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
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
    MultiEdit,
    ReadSymbol,
    SharedStoreRead,
    SharedStoreWrite,
    StructuredOutput,
)


pytestmark = pytest.mark.integration


_PER_TEST_BUDGET_SEC = 50.0


def _run_with_timeout(factory):
    async def runner():
        await asyncio.wait_for(factory(), timeout=_PER_TEST_BUDGET_SEC)
    asyncio.run(runner())


def _allow(*names: str) -> List[PermissionRule]:
    return [
        PermissionRule(source=RuleSource.PROJECT, behavior="allow", tool_name=n)
        for n in names
    ]


@pytest.fixture
def repo():
    td = tempfile.mkdtemp(prefix="issuefixer-live-")
    subprocess.check_call(["git", "init", "-q", "-b", "main"], cwd=td)
    subprocess.check_call(["git", "config", "user.email", "a@b.c"], cwd=td)
    subprocess.check_call(["git", "config", "user.name", "T"], cwd=td)
    src = os.path.join(td, "lib.py")
    with open(src, "w") as f:
        f.write(
            "def add(a, b):\n"
            "    return a - b  # bug\n"
            "\n"
            "def sub(a, b):\n"
            "    return a - b\n"
            "\n"
            "VERSION = '0.1.0'\n"
        )
    subprocess.check_call(["git", "add", "."], cwd=td)
    subprocess.check_call(["git", "commit", "-qm", "init"], cwd=td)
    yield td
    import shutil
    shutil.rmtree(td, ignore_errors=True)


def _workflow_tasks(execution_id: str) -> List[Dict[str, Any]]:
    import requests
    url = (os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
           .rstrip("/").replace("/api", ""))
    resp = requests.get(f"{url}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    return resp.json().get("tasks", []) or []


# ── Live: ReadSymbol via Conductor ──────────────────────────────────────


def test_live_read_symbol_under_conductor(runtime, repo, model):
    """The model is told to call read_symbol on a known function and
    structured_output the result. Confirms the new tool works end-to-end
    through the Conductor adapter with the dynamic-signature builder."""
    sandbox = ChecksOnlySandbox(allowed_read_roots=[repo])
    rt = HarnessRuntime(HarnessConfig(
        model=model,
        tools=[ReadSymbol(), StructuredOutput()],
        cwd=repo,
        sandbox=sandbox,
        permission_engine=PermissionEngine(rules=_allow("read_symbol", "structured_output")),
        system=(
            "Use read_symbol to read the 'add' function from 'lib.py'. "
            "Then call structured_output with {\"saw_bug\": <bool>} where "
            "saw_bug is true iff the function body contains 'a - b'."
        ),
        max_turns=6, max_tokens=1500,
    ), agent_runtime=runtime)

    async def go():
        async for _ in rt.submit("Read the add function and report."):
            pass

    try:
        _run_with_timeout(go)
    finally:
        rt.close()

    # Algorithmic: at least one read_symbol task ran and returned the body.
    tasks = _workflow_tasks(rt.last_execution_id or "")
    rs = [t for t in tasks if t.get("taskType") == "read_symbol"]
    assert rs, f"expected read_symbol task, got types={[t.get('taskType') for t in tasks]}"
    out = rs[0].get("outputData", {})
    assert not out.get("is_error"), out
    assert "a - b" in str(out.get("result", "")), out


# ── Live: MultiEdit via Conductor ───────────────────────────────────────


def test_live_multi_edit_under_conductor(runtime, repo, model):
    """Two edits across two files in one tool call."""
    other = os.path.join(repo, "VERSION.txt")
    with open(other, "w") as f:
        f.write("0.1.0\n")
    subprocess.check_call(["git", "add", "VERSION.txt"], cwd=repo)
    subprocess.check_call(["git", "commit", "-qm", "version"], cwd=repo)

    sandbox = ChecksOnlySandbox(
        allowed_read_roots=[repo], allowed_write_roots=[repo],
    )
    rt = HarnessRuntime(HarnessConfig(
        model=model,
        tools=[MultiEdit(), StructuredOutput()],
        cwd=repo,
        sandbox=sandbox,
        permission_engine=PermissionEngine(rules=_allow("multi_edit", "structured_output")),
        system=(
            "Use multi_edit ONCE to make two changes:\n"
            " 1. In 'lib.py' replace 'return a - b  # bug' with 'return a + b'\n"
            " 2. In 'VERSION.txt' replace '0.1.0' with '0.2.0'\n"
            "Then call structured_output."
        ),
        max_turns=4, max_tokens=1500,
    ), agent_runtime=runtime)

    async def go():
        async for _ in rt.submit("Make the changes."):
            pass

    try:
        _run_with_timeout(go)
    finally:
        rt.close()

    with open(os.path.join(repo, "lib.py")) as f:
        body = f.read()
    assert "return a + b" in body, body
    with open(other) as f:
        assert "0.2.0" in f.read()


# ── stop_condition fires ───────────────────────────────────────────────


def test_live_stop_condition_short_circuits(runtime, repo, model):
    """A child harness whose stop_condition is True from the start
    terminates immediately (no LLM tool calls). Confirms the
    stop_condition plumbing into Agent.stop_when."""
    sandbox = ChecksOnlySandbox(allowed_read_roots=[repo])
    rt = HarnessRuntime(HarnessConfig(
        model=model,
        tools=[StructuredOutput()],
        cwd=repo,
        sandbox=sandbox,
        permission_engine=PermissionEngine(rules=_allow("structured_output")),
        system="If the stop condition is already satisfied you should never run.",
        max_turns=20, max_tokens=200,
        stop_condition=lambda *a, **k: True,
    ), agent_runtime=runtime)

    async def go():
        async for _ in rt.submit("Should stop immediately."):
            pass

    try:
        _run_with_timeout(go)
    finally:
        rt.close()

    # The workflow may have completed in 0 or 1 LLM turn — but it must
    # have terminated, not hit max_turns.
    tasks = _workflow_tasks(rt.last_execution_id or "")
    llm_calls = [t for t in tasks if t.get("taskType") == "LLM_CHAT_COMPLETE"]
    # Expect <= 1 LLM call given the stop condition is true from t=0.
    assert len(llm_calls) <= 1, (
        f"expected stop_condition to short-circuit; saw {len(llm_calls)} LLM calls"
    )


# ── SharedStore visibility across parent/child via shared_store_dir ─────


def test_live_shared_store_visible_to_child(runtime, repo, model):
    """A parent harness writes to its SharedStore. A child harness with
    the same shared_store_dir reads the same value via shared_store_read."""
    parent = HarnessRuntime(HarnessConfig(
        model=model, tools=[], cwd=repo,
        sandbox=ChecksOnlySandbox(allowed_read_roots=[repo]),
    ), agent_runtime=runtime)

    parent.session_store["shared_store"].write("from_parent", {"hello": "world"})
    shared_dir = parent.session_store["shared_store_dir"]

    child = HarnessRuntime(HarnessConfig(
        model=model,
        tools=[SharedStoreRead(), StructuredOutput()],
        cwd=repo,
        sandbox=ChecksOnlySandbox(allowed_read_roots=[repo]),
        permission_engine=PermissionEngine(rules=_allow("shared_store_read", "structured_output")),
        system=(
            "Call shared_store_read with key='from_parent'. Then call "
            "structured_output with the value you got."
        ),
        max_turns=4, max_tokens=500,
        shared_store_dir=shared_dir,
    ), agent_runtime=runtime)

    async def go():
        async for _ in child.submit("Look up the key."):
            pass

    try:
        _run_with_timeout(go)
    finally:
        child.close()
        parent.close()

    # Algorithmic: at least one shared_store_read task with the right key.
    tasks = _workflow_tasks(child.last_execution_id or "")
    sr = [t for t in tasks if t.get("taskType") == "shared_store_read"]
    assert sr, f"expected shared_store_read tasks; got {[t.get('taskType') for t in tasks]}"
    matched = [t for t in sr if t.get("inputData", {}).get("key") == "from_parent"]
    assert matched, f"expected read with key=from_parent; saw {[t.get('inputData') for t in sr]}"
    out = matched[0].get("outputData", {})
    assert not out.get("is_error"), out
    # Value travels through the wrapper's `result` field.
    assert "world" in str(out.get("result", "")), out
