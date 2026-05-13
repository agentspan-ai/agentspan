"""Verify the regex-based ``file_outline`` extracts symbols from each
declared language (Python / JS / TS / Java / Go).

The README claim is "supports Python, JS/TS, Java, Go". Without these tests
the regexes are aspirational — a refactor could break Java extraction
silently. One fixture per language; assert that a representative class
and a representative function are picked up.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from agentspan.harness import HarnessConfig, HarnessRuntime
from agentspan.harness.sandbox import ChecksOnlySandbox
from agentspan.harness.tools.builtins import FileOutline
from agentspan.harness.tools.contract import ToolUseContext


@pytest.fixture
def workdir():
    with tempfile.TemporaryDirectory() as td:
        yield td


def _ctx(rt: HarnessRuntime, workdir: str) -> ToolUseContext:
    return ToolUseContext(
        cwd=workdir, session_id=rt.session_id,
        abort=asyncio.Event(), store=rt.session_store,
    )


def _runtime(workdir: str) -> HarnessRuntime:
    return HarnessRuntime(HarnessConfig(
        model="fake/m", tools=[], cwd=workdir,
        sandbox=ChecksOnlySandbox(allowed_read_roots=[workdir]),
    ))


def _names_at(out, kind: str | None = None) -> list[str]:
    if kind is None:
        return [e["name"] for e in out]
    return [e["name"] for e in out if e["kind"] == kind]


@pytest.mark.asyncio
async def test_outline_javascript(workdir):
    src = (
        "export function alpha() {\n"
        "  return 1;\n"
        "}\n\n"
        "export class Beta {\n"
        "  m() {}\n"
        "}\n\n"
        "export const gamma = 5;\n"
    )
    p = os.path.join(workdir, "x.js")
    with open(p, "w") as f:
        f.write(src)
    rt = _runtime(workdir)
    res = await FileOutline().call({"path": "x.js"}, _ctx(rt, workdir))
    assert not res.is_error, res.content
    names = _names_at(res.output)
    assert "alpha" in names and "Beta" in names and "gamma" in names
    rt.close()


@pytest.mark.asyncio
async def test_outline_typescript(workdir):
    src = (
        "export interface Foo { x: number }\n"
        "export type Bar = string;\n"
        "export enum Baz { A, B }\n"
        "export class Qux {\n"
        "  greet(): void { }\n"
        "}\n"
        "export async function quux() { return 1; }\n"
    )
    p = os.path.join(workdir, "x.ts")
    with open(p, "w") as f:
        f.write(src)
    rt = _runtime(workdir)
    res = await FileOutline().call({"path": "x.ts"}, _ctx(rt, workdir))
    assert not res.is_error, res.content
    names = _names_at(res.output)
    for expected in ("Foo", "Bar", "Baz", "Qux", "quux"):
        assert expected in names, f"missing {expected} in {names}"
    rt.close()


@pytest.mark.asyncio
async def test_outline_java(workdir):
    src = (
        "package x;\n"
        "public class Foo {\n"
        "    public void doIt() { }\n"
        "    private static int compute(int a) { return a; }\n"
        "}\n"
        "interface Bar { void m(); }\n"
    )
    p = os.path.join(workdir, "X.java")
    with open(p, "w") as f:
        f.write(src)
    rt = _runtime(workdir)
    res = await FileOutline().call({"path": "X.java"}, _ctx(rt, workdir))
    assert not res.is_error, res.content
    names = _names_at(res.output)
    assert "Foo" in names
    assert "Bar" in names
    # at least one method captured
    methods = _names_at(res.output, "method")
    assert methods, f"no methods extracted: {res.output}"
    rt.close()


@pytest.mark.asyncio
async def test_outline_go(workdir):
    src = (
        "package x\n"
        "type Foo struct { name string }\n"
        "type Bar interface { M() }\n"
        "func (f *Foo) Hello() string { return f.name }\n"
        "func Top() {}\n"
    )
    p = os.path.join(workdir, "x.go")
    with open(p, "w") as f:
        f.write(src)
    rt = _runtime(workdir)
    res = await FileOutline().call({"path": "x.go"}, _ctx(rt, workdir))
    assert not res.is_error, res.content
    names = _names_at(res.output)
    assert "Foo" in names and "Bar" in names
    funcs = _names_at(res.output, "func")
    assert "Hello" in funcs and "Top" in funcs
    rt.close()


@pytest.mark.asyncio
async def test_outline_rejects_unsupported_extension(workdir):
    p = os.path.join(workdir, "x.rs")
    with open(p, "w") as f:
        f.write("fn main() {}\n")
    rt = _runtime(workdir)
    res = await FileOutline().call({"path": "x.rs"}, _ctx(rt, workdir))
    assert res.is_error
    assert ".rs" in res.content
    rt.close()
