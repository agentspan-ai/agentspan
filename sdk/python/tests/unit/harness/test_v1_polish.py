"""Tests for harness pieces that survive the Conductor refactor:

  * WriteFile snapshot
  * PatchFile diff
  * UpdatePlan accepting plain strings
  * StructuredOutput 'output' alias
  * FileOutline / FindReferences
  * SharedStore round-trip + cross-runtime visibility
  * spawn_agent worktree isolation

Engine-loop tests (cycle detection, low-turns hint, session_start/stop hooks)
are deleted because the conversation loop now runs server-side as a
Conductor workflow — those concerns belong on Agent callbacks.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from typing import Any, Dict

import pytest

from agentspan.harness import HarnessConfig, HarnessRuntime
from agentspan.harness.sandbox import ChecksOnlySandbox
from agentspan.harness.tools.builtins import (
    FileOutline,
    FindReferences,
    PatchFile,
    SharedStoreList,
    SharedStoreRead,
    SharedStoreWrite,
    SpawnAgent,
    StructuredOutput,
    UpdatePlan,
    WriteFile,
)
from agentspan.harness.tools.contract import ToolUseContext


@pytest.fixture
def workdir():
    with tempfile.TemporaryDirectory() as td:
        yield td


def _ctx(rt: HarnessRuntime, cwd: str) -> ToolUseContext:
    return ToolUseContext(
        cwd=cwd, session_id=rt.session_id,
        abort=asyncio.Event(), store=rt.session_store,
    )


# ── Tools: WriteFile snapshot ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_write_file_snapshots_prior_version(workdir):
    sandbox = ChecksOnlySandbox(allowed_read_roots=[workdir],
                                allowed_write_roots=[workdir])
    rt = HarnessRuntime(HarnessConfig(model="fake/m", tools=[],
                                       cwd=workdir, sandbox=sandbox))
    target = os.path.join(workdir, "f.txt")
    with open(target, "w") as f:
        f.write("first")

    res = await WriteFile().call(
        {"path": "f.txt", "content": "second"}, _ctx(rt, workdir),
    )
    assert not res.is_error
    snap_dir = os.path.join(rt.session_store["content_dir"], "snapshots")
    snaps = os.listdir(snap_dir)
    assert snaps, "expected a snapshot file"
    with open(os.path.join(snap_dir, snaps[0])) as f:
        assert f.read() == "first"
    rt.close()


# ── Tools: PatchFile diff ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_file_returns_unified_diff(workdir):
    sandbox = ChecksOnlySandbox(allowed_read_roots=[workdir],
                                allowed_write_roots=[workdir])
    rt = HarnessRuntime(HarnessConfig(model="fake/m", tools=[],
                                       cwd=workdir, sandbox=sandbox))
    target = os.path.join(workdir, "f.py")
    with open(target, "w") as f:
        f.write("def add(a, b):\n    return a - b\n")

    res = await PatchFile().call(
        {"path": "f.py", "edits": [
            {"old_string": "return a - b", "new_string": "return a + b"},
        ]},
        _ctx(rt, workdir),
    )
    assert not res.is_error
    assert "@@" in res.content
    assert "-    return a - b" in res.content
    assert "+    return a + b" in res.content
    rt.close()


# ── Tools: UpdatePlan accepts strings ───────────────────────────────────


@pytest.mark.asyncio
async def test_update_plan_accepts_plain_string_steps(workdir):
    rt = HarnessRuntime(HarnessConfig(model="fake/m", tools=[], cwd=workdir))
    res = await UpdatePlan().call(
        {"steps": ["one", "two", "three"]}, _ctx(rt, workdir),
    )
    assert not res.is_error
    plan = rt.session_store["plan"]
    assert [s["description"] for s in plan] == ["one", "two", "three"]
    assert all(s["status"] == "pending" for s in plan)
    rt.close()


# ── Tools: StructuredOutput accepts 'output' alias ─────────────────────


@pytest.mark.asyncio
async def test_structured_output_accepts_output_alias(workdir):
    rt = HarnessRuntime(HarnessConfig(model="fake/m", tools=[], cwd=workdir))
    res = await StructuredOutput().call(
        {"output": {"status": "complete"}}, _ctx(rt, workdir),
    )
    assert not res.is_error
    assert rt.session_store["structured_output"] == {"status": "complete"}
    rt.close()


# ── Tools: FileOutline ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_file_outline_python(workdir):
    sandbox = ChecksOnlySandbox(allowed_read_roots=[workdir])
    rt = HarnessRuntime(HarnessConfig(model="fake/m", tools=[],
                                       cwd=workdir, sandbox=sandbox))
    src = "class Foo:\n    def bar(self):\n        pass\n\ndef baz():\n    return 1\n"
    target = os.path.join(workdir, "x.py")
    with open(target, "w") as f:
        f.write(src)

    res = await FileOutline().call({"path": "x.py"}, _ctx(rt, workdir))
    assert not res.is_error
    names = [e["name"] for e in res.output]
    assert "Foo" in names and "bar" in names and "baz" in names
    rt.close()


# ── Tools: FindReferences ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_references_word_boundary(workdir):
    sandbox = ChecksOnlySandbox(allowed_read_roots=[workdir])
    rt = HarnessRuntime(HarnessConfig(model="fake/m", tools=[],
                                       cwd=workdir, sandbox=sandbox))
    with open(os.path.join(workdir, "a.py"), "w") as f:
        f.write("x = my_func()\n# my_func_other should NOT match\n")
    with open(os.path.join(workdir, "b.py"), "w") as f:
        f.write("def my_func(): pass\n")

    res = await FindReferences().call({"symbol": "my_func"}, _ctx(rt, workdir))
    assert not res.is_error
    matches = res.output
    assert len(matches) == 2
    assert all("my_func" in m["match"] for m in matches)
    assert not any("my_func_other" in m["match"] for m in matches)
    rt.close()


# ── SharedStore ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_shared_store_round_trip(workdir):
    rt = HarnessRuntime(HarnessConfig(model="fake/m", tools=[], cwd=workdir))
    ctx = _ctx(rt, workdir)
    await SharedStoreWrite().call(
        {"key": "design", "value": {"approach": "X", "files": ["a.py"]}}, ctx,
    )
    res = await SharedStoreRead().call({"key": "design"}, ctx)
    assert res.output == {"approach": "X", "files": ["a.py"]}
    list_res = await SharedStoreList().call({}, ctx)
    assert "design" in list_res.output
    rt.close()


@pytest.mark.asyncio
async def test_shared_store_visible_across_runtimes(workdir):
    """Two HarnessRuntimes pointed at the same shared_store_dir see each
    other's writes — that's the whole point of SharedStore."""
    shared = os.path.join(workdir, "shared")
    rt_a = HarnessRuntime(HarnessConfig(model="fake/m", tools=[], cwd=workdir,
                                         shared_store_dir=shared))
    rt_b = HarnessRuntime(HarnessConfig(model="fake/m", tools=[], cwd=workdir,
                                         shared_store_dir=shared))
    rt_a.session_store["shared_store"].write("k", "v_from_a")
    assert rt_b.session_store["shared_store"].read("k") == "v_from_a"
    rt_a.close(); rt_b.close()


# ── Spawn agent worktree isolation ─────────────────────────────────────


def _make_repo() -> str:
    td = tempfile.mkdtemp()
    subprocess.check_call(["git", "init", "-q", "-b", "main"], cwd=td)
    subprocess.check_call(["git", "config", "user.email", "a@b.c"], cwd=td)
    subprocess.check_call(["git", "config", "user.name", "T"], cwd=td)
    with open(os.path.join(td, "f.txt"), "w") as f:
        f.write("hi\n")
    subprocess.check_call(["git", "add", "."], cwd=td)
    subprocess.check_call(["git", "commit", "-qm", "init"], cwd=td)
    return td


@pytest.mark.asyncio
async def test_spawn_agent_worktree_requires_manager(workdir):
    """Without worktree_repo on the parent, isolation='worktree' errors —
    the validity counter-test for worktree wiring."""
    rt = HarnessRuntime(HarnessConfig(model="fake/m", tools=[], cwd=workdir))
    assert "worktree_manager" not in rt.session_store

    def factory(ctx, input):
        raise AssertionError("should not be reached")

    sa = SpawnAgent(factory=factory)
    res = await sa.call(
        {"description": "x", "prompt": "y", "isolation": "worktree"},
        _ctx(rt, workdir),
    )
    assert res.is_error
    assert "worktree_manager" in res.content
    rt.close()


@pytest.mark.asyncio
async def test_spawn_agent_worktree_creates_isolated_path():
    """spawn_agent with isolation='worktree' creates a worktree and the
    factory receives the path."""
    repo = _make_repo()
    try:
        rt = HarnessRuntime(HarnessConfig(model="fake/m", tools=[], cwd=repo,
                                           worktree_repo=repo))
        assert "worktree_manager" in rt.session_store
        recorded: Dict[str, Any] = {}

        def factory(ctx, input):
            recorded["cwd"] = input.get("_worktree_path")
            recorded["branch"] = input.get("_worktree_branch")
            raise RuntimeError("stop here — we only want to verify worktree creation")

        sa = SpawnAgent(factory=factory)
        res = await sa.call(
            {"description": "test", "prompt": "hi", "isolation": "worktree"},
            _ctx(rt, repo),
        )
        # factory raised, so result is an error — but worktree was created first.
        assert res.is_error
        assert recorded["cwd"], "factory should have received a worktree path"
        assert recorded["branch"].startswith("agentspan/wt/")
        # Cleanup is best-effort by spawn_agent on factory failure; force here.
        await rt.session_store["worktree_manager"].cleanup(
            recorded["cwd"], force=True,
        )
        rt.close()
    finally:
        import shutil
        shutil.rmtree(repo, ignore_errors=True)
