"""Unit tests for Phase-A additions: ReadSymbol, MultiEdit, WebFetch,
HarnessConfig.stop_condition.

These tools fill the production-readiness gaps identified in the
issue-fixer harness review: symbol-level navigation, batch editing
across files, and reading external docs.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any, Dict
from unittest.mock import patch

import pytest

from agentspan.harness import HarnessConfig, HarnessRuntime
from agentspan.harness.sandbox import ChecksOnlySandbox
from agentspan.harness.tools.builtins import MultiEdit, ReadSymbol, WebFetch
from agentspan.harness.tools.contract import ToolUseContext


@pytest.fixture
def workdir():
    with tempfile.TemporaryDirectory() as td:
        yield td


def _runtime(workdir: str, *, sandbox: ChecksOnlySandbox = None) -> HarnessRuntime:
    sb = sandbox or ChecksOnlySandbox(
        allowed_read_roots=[workdir], allowed_write_roots=[workdir],
    )
    return HarnessRuntime(HarnessConfig(model="fake/m", tools=[],
                                         cwd=workdir, sandbox=sb))


def _ctx(rt: HarnessRuntime, cwd: str) -> ToolUseContext:
    return ToolUseContext(
        cwd=cwd, session_id=rt.session_id,
        abort=asyncio.Event(), store=rt.session_store,
    )


# ── ReadSymbol ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_symbol_python_function(workdir):
    src = (
        "def alpha():\n"
        "    return 1\n"
        "\n"
        "def beta(x):\n"
        "    # multi line\n"
        "    return x + 1\n"
        "\n"
        "def gamma():\n"
        "    return 'g'\n"
    )
    p = os.path.join(workdir, "x.py")
    with open(p, "w") as f:
        f.write(src)
    rt = _runtime(workdir)
    res = await ReadSymbol().call({"path": "x.py", "name": "beta"}, _ctx(rt, workdir))
    assert not res.is_error, res.content
    # Body must include `x + 1`, must NOT include `gamma`.
    assert "x + 1" in res.content
    assert "gamma" not in res.content
    assert res.output["start_line"] >= 1
    rt.close()


@pytest.mark.asyncio
async def test_read_symbol_python_class_with_methods(workdir):
    src = (
        "class Foo:\n"
        "    def a(self):\n"
        "        return 1\n"
        "    def b(self):\n"
        "        return 2\n"
        "\n"
        "class Bar:\n"
        "    pass\n"
    )
    p = os.path.join(workdir, "x.py")
    with open(p, "w") as f:
        f.write(src)
    rt = _runtime(workdir)
    res = await ReadSymbol().call({"path": "x.py", "name": "Foo"}, _ctx(rt, workdir))
    assert not res.is_error, res.content
    assert "def a" in res.content and "def b" in res.content
    assert "class Bar" not in res.content
    rt.close()


@pytest.mark.asyncio
async def test_read_symbol_typescript_class(workdir):
    src = (
        "export interface Other { x: number }\n"
        "export class Target {\n"
        "  constructor(private n: number) {}\n"
        "  greet(): string { return 'hi'; }\n"
        "}\n"
        "export function helper() { return 1; }\n"
    )
    p = os.path.join(workdir, "x.ts")
    with open(p, "w") as f:
        f.write(src)
    rt = _runtime(workdir)
    res = await ReadSymbol().call({"path": "x.ts", "name": "Target"}, _ctx(rt, workdir))
    assert not res.is_error, res.content
    assert "constructor" in res.content
    assert "greet" in res.content
    assert "helper" not in res.content
    rt.close()


@pytest.mark.asyncio
async def test_read_symbol_missing_returns_error(workdir):
    p = os.path.join(workdir, "x.py")
    with open(p, "w") as f:
        f.write("def known(): pass\n")
    rt = _runtime(workdir)
    res = await ReadSymbol().call(
        {"path": "x.py", "name": "absent"}, _ctx(rt, workdir),
    )
    assert res.is_error
    assert "not found" in res.content
    rt.close()


@pytest.mark.asyncio
async def test_read_symbol_unsupported_extension(workdir):
    p = os.path.join(workdir, "x.rs")
    with open(p, "w") as f:
        f.write("fn main() {}\n")
    rt = _runtime(workdir)
    res = await ReadSymbol().call(
        {"path": "x.rs", "name": "main"}, _ctx(rt, workdir),
    )
    assert res.is_error
    assert ".rs" in res.content
    rt.close()


# ── MultiEdit ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multi_edit_applies_all_files(workdir):
    a = os.path.join(workdir, "a.py")
    b = os.path.join(workdir, "b.py")
    with open(a, "w") as f:
        f.write("VERSION = '1.0.0'\n")
    with open(b, "w") as f:
        f.write("# old comment\nx = 1\n")
    rt = _runtime(workdir)
    res = await MultiEdit().call({
        "files": [
            {"path": "a.py", "edits": [{"old_string": "1.0.0", "new_string": "1.1.0"}]},
            {"path": "b.py", "edits": [{"old_string": "old comment", "new_string": "new comment"}]},
        ]
    }, _ctx(rt, workdir))
    assert not res.is_error, res.content
    with open(a) as f:
        assert "1.1.0" in f.read()
    with open(b) as f:
        assert "new comment" in f.read()
    rt.close()


@pytest.mark.asyncio
async def test_multi_edit_stops_on_first_failure_keeps_prior(workdir):
    a = os.path.join(workdir, "a.py")
    b = os.path.join(workdir, "b.py")
    c = os.path.join(workdir, "c.py")
    for p, body in [(a, "AAA\n"), (b, "BBB\n"), (c, "CCC\n")]:
        with open(p, "w") as f:
            f.write(body)
    rt = _runtime(workdir)
    res = await MultiEdit().call({
        "files": [
            {"path": "a.py", "edits": [{"old_string": "AAA", "new_string": "A2A"}]},
            {"path": "b.py", "edits": [{"old_string": "ZZZ", "new_string": "X"}]},
            {"path": "c.py", "edits": [{"old_string": "CCC", "new_string": "C2C"}]},
        ]
    }, _ctx(rt, workdir))
    # Failure recorded but we stopped before c.py.
    assert res.is_error
    with open(a) as f:
        assert "A2A" in f.read()  # applied
    with open(b) as f:
        assert "BBB" in f.read()  # untouched
    with open(c) as f:
        assert "CCC" in f.read()  # not reached
    rt.close()


@pytest.mark.asyncio
async def test_multi_edit_rejects_ambiguous_match(workdir):
    """old_string with multiple matches per CLAUDE.md should reject."""
    a = os.path.join(workdir, "a.py")
    with open(a, "w") as f:
        f.write("x = 1\nx = 1\n")
    rt = _runtime(workdir)
    res = await MultiEdit().call({
        "files": [
            {"path": "a.py", "edits": [{"old_string": "x = 1", "new_string": "x = 2"}]},
        ]
    }, _ctx(rt, workdir))
    assert res.is_error
    assert "matches 2 places" in res.content
    rt.close()


# ── WebFetch ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_web_fetch_blocks_private_network(workdir):
    sb = ChecksOnlySandbox(
        allowed_read_roots=[workdir], allowed_write_roots=[workdir],
        block_private_networks=True,
    )
    rt = _runtime(workdir, sandbox=sb)
    res = await WebFetch().call(
        {"url": "http://localhost:8080/admin"}, _ctx(rt, workdir),
    )
    assert res.is_error
    assert "sandbox" in res.content.lower()
    rt.close()


@pytest.mark.asyncio
async def test_web_fetch_html_to_text(workdir):
    rt = _runtime(workdir)
    fake_html = b"<html><body><h1>Hello</h1><script>alert(1)</script><p>World</p></body></html>"

    def _fake_fetch(url):
        return (fake_html.decode(), "text/html; charset=utf-8", 200)

    with patch("agentspan.harness.tools.builtins.web_fetch._fetch", _fake_fetch):
        res = await WebFetch().call(
            {"url": "https://example.com/hello"}, _ctx(rt, workdir),
        )
    assert not res.is_error, res.content
    assert "Hello" in res.content
    assert "World" in res.content
    assert "alert(1)" not in res.content  # script content stripped
    assert res.output["status"] == 200
    rt.close()


@pytest.mark.asyncio
async def test_web_fetch_truncates_large_pages(workdir):
    from agentspan.harness.tools.builtins import web_fetch as wf_mod

    big = "A" * (wf_mod.MAX_CHARS + 10_000)

    def _fake_fetch(url):
        return (big, "text/plain", 200)

    rt = _runtime(workdir)
    with patch("agentspan.harness.tools.builtins.web_fetch._fetch", _fake_fetch):
        res = await WebFetch().call(
            {"url": "https://example.com/big"}, _ctx(rt, workdir),
        )
    assert not res.is_error
    assert res.output["truncated"] is True
    assert "[truncated" in res.content
    rt.close()


# ── HarnessConfig.stop_condition plumbing ───────────────────────────────


def test_harness_config_stop_condition_field_exists():
    """The HarnessConfig dataclass exposes stop_condition as a field that
    forwards to the agentspan Agent's stop_when. Validity counter-test:
    a config without stop_condition has it as None (not omitted)."""
    cfg = HarnessConfig(model="fake/m", tools=[])
    assert cfg.stop_condition is None
    cfg2 = HarnessConfig(
        model="fake/m", tools=[], stop_condition=lambda ctx, **kw: True,
    )
    assert callable(cfg2.stop_condition)


def test_build_agent_propagates_stop_condition(workdir):
    """The conductor adapter's build_agent must put the harness's
    stop_condition into the Agent's stop_when kwarg."""
    from agentspan.harness.conductor_adapter import build_agent

    sentinel = lambda ctx, **kw: False  # noqa: E731
    rt = HarnessRuntime(HarnessConfig(
        model="fake/m", tools=[], cwd=workdir, stop_condition=sentinel,
    ))
    agent = build_agent(harness=rt, name="probe")
    assert getattr(agent, "stop_when", None) is sentinel
    rt.close()


def test_build_agent_omits_stop_when_when_unset(workdir):
    """Counter-test: when stop_condition is None, Agent's stop_when remains
    its default (None) — confirms the propagation only fires when set."""
    from agentspan.harness.conductor_adapter import build_agent

    rt = HarnessRuntime(HarnessConfig(model="fake/m", tools=[], cwd=workdir))
    agent = build_agent(harness=rt, name="probe2")
    assert getattr(agent, "stop_when", None) is None
    rt.close()
