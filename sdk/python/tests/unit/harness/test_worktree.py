"""Unit tests for the WorktreeManager."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile

import pytest

from agentspan.harness.worktree import WorktreeManager


def _git(cwd: str, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=cwd, stderr=subprocess.STDOUT
    ).decode()


@pytest.fixture
def repo():
    td = tempfile.mkdtemp()
    try:
        _git(td, "init", "-q", "-b", "main")
        _git(td, "config", "user.email", "a@b.c")
        _git(td, "config", "user.name", "T")
        with open(os.path.join(td, "f.txt"), "w") as f:
            f.write("hi\n")
        _git(td, "add", ".")
        _git(td, "commit", "-q", "-m", "init")
        yield td
    finally:
        shutil.rmtree(td, ignore_errors=True)


@pytest.mark.asyncio
async def test_create_returns_path_under_root(repo):
    mgr = WorktreeManager(repo)
    info = await mgr.create()
    try:
        assert os.path.isdir(info.path)
        assert info.path.startswith(mgr.root + os.sep)
        assert info.branch.startswith("agentspan/wt/")
    finally:
        await mgr.cleanup(info.path, force=True)


@pytest.mark.asyncio
async def test_has_changes_false_after_create(repo):
    mgr = WorktreeManager(repo)
    info = await mgr.create()
    try:
        assert not await mgr.has_changes(info.path)
    finally:
        await mgr.cleanup(info.path, force=True)


@pytest.mark.asyncio
async def test_has_changes_true_after_edit(repo):
    mgr = WorktreeManager(repo)
    info = await mgr.create()
    try:
        with open(os.path.join(info.path, "new.txt"), "w") as f:
            f.write("x")
        assert await mgr.has_changes(info.path)
    finally:
        await mgr.cleanup(info.path, force=True)


@pytest.mark.asyncio
async def test_cleanup_keeps_dirty_worktree(repo):
    mgr = WorktreeManager(repo)
    info = await mgr.create()
    try:
        with open(os.path.join(info.path, "x"), "w") as f:
            f.write("y")
        ok = await mgr.cleanup(info.path)  # force=False
        assert ok is False
        assert os.path.isdir(info.path)
    finally:
        await mgr.cleanup(info.path, force=True)


@pytest.mark.asyncio
async def test_cleanup_idempotent(repo):
    mgr = WorktreeManager(repo)
    info = await mgr.create()
    assert await mgr.cleanup(info.path, force=True) is True
    # Second call should not raise.
    assert await mgr.cleanup(info.path, force=True) is True


@pytest.mark.asyncio
async def test_refuses_paths_outside_root(repo):
    mgr = WorktreeManager(repo)
    # Cleanup of a path outside the managed root is a no-op (returns False).
    other = tempfile.mkdtemp()
    try:
        ok = await mgr.cleanup(other, force=True)
        assert ok is False
        assert os.path.isdir(other)  # untouched
    finally:
        shutil.rmtree(other, ignore_errors=True)
