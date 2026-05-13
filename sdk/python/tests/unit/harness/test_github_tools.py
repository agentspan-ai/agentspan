"""Unit tests for the GitHub primitives (setup_repo, fetch_issue, fetch_pr,
open_pr).

These tools shell out to ``gh``, so for unit testing we either:
  (a) Verify the schema is OpenAI-strict-mode compatible (no untyped
      arrays, every field has a type, required is consistent).
  (b) Inject a fake ``gh`` on PATH that returns canned JSON, so we can
      walk the tool's ``call()`` without real network/auth.
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
import tempfile
from typing import Any, Dict

import pytest

from agentspan.harness import HarnessConfig, HarnessRuntime
from agentspan.harness.tools.builtins import (
    FetchIssue,
    FetchPR,
    OpenPR,
    SetupRepo,
)
from agentspan.harness.tools.contract import ToolUseContext


# ── Schema validation (catches OpenAI strict-mode rejections offline) ──


def _walk_schema_arrays(schema: Dict[str, Any]) -> None:
    """Walk a JSON Schema and assert every ``type:"array"`` declares ``items``.

    OpenAI's Responses API rejects tool definitions with arrays that don't
    declare an item type. We pre-fixed the others (patch_file, update_plan,
    find_references, spawn_agent) — verify the GitHub tools too.
    """
    if not isinstance(schema, dict):
        return
    if schema.get("type") == "array":
        assert "items" in schema, f"array schema missing 'items': {schema}"
    for k in ("properties", "items", "additionalProperties"):
        if k in schema:
            v = schema[k]
            if isinstance(v, dict):
                if k == "properties":
                    for prop in v.values():
                        _walk_schema_arrays(prop)
                else:
                    _walk_schema_arrays(v)


@pytest.mark.parametrize("tool_cls", [SetupRepo, FetchIssue, FetchPR, OpenPR])
def test_github_tool_schema_is_openai_strict_compatible(tool_cls):
    """Every array property in the GitHub tools' schemas declares 'items'."""
    tool = tool_cls()
    _walk_schema_arrays(tool.input_schema)


@pytest.mark.parametrize("tool_cls,required", [
    (SetupRepo, {"repo", "directory"}),
    (FetchIssue, {"repo", "issue_number"}),
    (FetchPR, {"repo", "pr_number"}),
    (OpenPR, {"title", "body"}),
])
def test_github_tool_required_fields(tool_cls, required):
    """The required-field set is what we expect — guards against accidental
    schema regressions that would let the LLM call with missing args."""
    tool = tool_cls()
    schema = tool.input_schema
    assert set(schema.get("required", [])) == required


# ── Tool execution with a fake gh on PATH ──────────────────────────────


@pytest.fixture
def fake_gh_dir():
    """Create a directory containing a fake ``gh`` and ``git`` that print
    canned output. Yield the directory; PATH gets prepended in tests."""
    with tempfile.TemporaryDirectory() as td:
        yield td


def _make_fake_binary(dir: str, name: str, script: str) -> str:
    path = os.path.join(dir, name)
    with open(path, "w") as fp:
        fp.write("#!/bin/sh\n" + script + "\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.fixture
def harness(monkeypatch, fake_gh_dir):
    monkeypatch.setenv("PATH", fake_gh_dir + os.pathsep + os.environ.get("PATH", ""))
    rt = HarnessRuntime(HarnessConfig(model="fake/m", tools=[]))
    yield rt
    rt.close()


def _ctx(rt: HarnessRuntime) -> ToolUseContext:
    return ToolUseContext(
        cwd=rt.cwd, session_id=rt.session_id,
        abort=asyncio.Event(), store=rt.session_store,
    )


@pytest.mark.asyncio
async def test_fetch_issue_parses_gh_json(harness, fake_gh_dir):
    payload = {
        "title": "Allow retry on @tool",
        "body": "decorator should accept retry_count and retry_delay_seconds",
        "labels": [{"name": "feature"}],
        "comments": [],
        "state": "OPEN",
        "url": "https://github.com/o/r/issues/167",
        "author": {"login": "user"},
    }
    _make_fake_binary(fake_gh_dir, "gh",
                       f"echo {json.dumps(json.dumps(payload))!s}")
    res = await FetchIssue().call(
        {"repo": "o/r", "issue_number": 167}, _ctx(harness),
    )
    assert not res.is_error, res.content
    assert res.output["title"] == "Allow retry on @tool"
    assert "decorator should accept retry_count" in res.content


@pytest.mark.asyncio
async def test_fetch_issue_surfaces_gh_failure(harness, fake_gh_dir):
    """gh nonzero exit → tool returns error result (not exception)."""
    _make_fake_binary(fake_gh_dir, "gh",
                       'echo "auth required" >&2; exit 1')
    res = await FetchIssue().call(
        {"repo": "o/r", "issue_number": 1}, _ctx(harness),
    )
    assert res.is_error
    assert "auth required" in res.content or "gh issue view failed" in res.content


@pytest.mark.asyncio
async def test_fetch_issue_handles_non_json_output(harness, fake_gh_dir):
    """gh returns garbage → tool reports parse error, not an exception."""
    _make_fake_binary(fake_gh_dir, "gh", 'echo "not json"')
    res = await FetchIssue().call(
        {"repo": "o/r", "issue_number": 1}, _ctx(harness),
    )
    assert res.is_error
    assert "non-JSON" in res.content or "JSON" in res.content


@pytest.mark.asyncio
async def test_fetch_pr_parses_pr_json(harness, fake_gh_dir):
    payload = {
        "title": "fix retry decorator",
        "body": "wires retry_count through",
        "state": "OPEN",
        "headRefName": "fix/167",
        "baseRefName": "main",
        "url": "https://github.com/o/r/pull/200",
        "files": [],
        "comments": [],
        "reviews": [],
    }
    _make_fake_binary(fake_gh_dir, "gh",
                       f"echo {json.dumps(json.dumps(payload))!s}")
    res = await FetchPR().call(
        {"repo": "o/r", "pr_number": 200}, _ctx(harness),
    )
    assert not res.is_error, res.content
    assert res.output["headRefName"] == "fix/167"


@pytest.mark.asyncio
async def test_setup_repo_requires_gh_and_git_on_path(monkeypatch, fake_gh_dir):
    """If gh/git aren't on PATH, SetupRepo errors cleanly."""
    # Replace PATH with only an empty dir so gh/git aren't reachable.
    monkeypatch.setenv("PATH", fake_gh_dir)
    rt = HarnessRuntime(HarnessConfig(model="fake/m", tools=[]))
    try:
        res = await SetupRepo().call(
            {"repo": "o/r", "directory": "/tmp/nope"}, _ctx(rt),
        )
        assert res.is_error
        assert "gh and git CLIs must be on PATH" in res.content
    finally:
        rt.close()
