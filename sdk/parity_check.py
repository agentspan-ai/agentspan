#!/usr/bin/env python3
"""SDK Parity Check — compares Java vs Python agent definition JSONs.

Runs each example pair, fetches the agentDef from Conductor, normalizes
away example-specific values, then diffs the structure to find SDK gaps.

Usage:
    python sdk/parity_check.py                   # run all examples
    python sdk/parity_check.py --example 01      # run only Example01
    python sdk/parity_check.py --example 03,07   # run specific examples
"""

import argparse
import copy
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

# ── Paths ────────────────────────────────────────────────────────────────────

SDK_DIR = Path(__file__).parent
JAVA_EXAMPLES_DIR = SDK_DIR / "java" / "examples"
PYTHON_SDK_DIR = SDK_DIR / "python"
CONFIG_FILE = SDK_DIR / "parity_examples.json"
REPORT_FILE = SDK_DIR / "java" / "PARITY_REPORT.md"
SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767")
LLM_MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini")

# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class Gap:
    path: str
    kind: str   # missing_in_java | missing_in_python | type_mismatch | value_mismatch | length_mismatch
    java_val: Any
    python_val: Any

    def __str__(self):
        if self.kind == "missing_in_java":
            return f"  MISSING IN JAVA  {self.path}  (Python has: {_short(self.python_val)})"
        if self.kind == "missing_in_python":
            return f"  MISSING IN PY    {self.path}  (Java has: {_short(self.java_val)})"
        if self.kind == "type_mismatch":
            return f"  TYPE MISMATCH    {self.path}  Java={self.java_val} Python={self.python_val}"
        if self.kind == "length_mismatch":
            return f"  LENGTH MISMATCH  {self.path}  Java={self.java_val} Python={self.python_val}"
        return f"  VALUE MISMATCH   {self.path}  Java={_short(self.java_val)} Python={_short(self.python_val)}"


def _short(v: Any, max_len: int = 80) -> str:
    s = json.dumps(v) if not isinstance(v, str) else v
    return s if len(s) <= max_len else s[:max_len] + "..."


# ── Config loading ────────────────────────────────────────────────────────────

def load_config() -> dict:
    with open(CONFIG_FILE) as f:
        return json.load(f)


def filter_examples(examples: list, ids: list[str]) -> list:
    if not ids:
        return examples
    return [e for e in examples if any(e["id"] == i or e["id"].lstrip("0") == i.lstrip("0") for i in ids)]


# ── Running examples ──────────────────────────────────────────────────────────

def run_java_example(java_class: str, timeout: int = 120) -> dict:
    env = {**os.environ, "AGENTSPAN_SERVER_URL": SERVER_URL, "AGENTSPAN_LLM_MODEL": LLM_MODEL}
    cmd = [
        "mvn", "-q", "exec:java",
        f"-Dexec.mainClass=dev.agentspan.examples.{java_class}",
        "-Dorg.slf4j.simpleLogger.defaultLogLevel=warn",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            timeout=timeout, cwd=JAVA_EXAMPLES_DIR, env=env)
    combined = result.stdout + result.stderr
    m = re.search(r"Workflow ID:\s*([0-9a-f-]{36})", combined)
    if not m:
        raise RuntimeError(f"No Workflow ID in Java output:\n{combined[:600]}")
    return fetch_agent_def(m.group(1))


def run_python_example(python_file: str, timeout: int = 120) -> dict:
    env = {**os.environ, "AGENTSPAN_SERVER_URL": SERVER_URL, "AGENTSPAN_LLM_MODEL": LLM_MODEL}
    cmd = ["bash", "-c",
           f"source .venv/bin/activate && python examples/{python_file}"]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            timeout=timeout, cwd=PYTHON_SDK_DIR, env=env)
    combined = result.stdout + result.stderr
    m = re.search(r"Execution ID:\s*([0-9a-f-]{36})", combined)
    if not m:
        raise RuntimeError(f"No Execution ID in Python output:\n{combined[:600]}")
    return fetch_agent_def(m.group(1))


def fetch_agent_def(workflow_id: str) -> dict:
    url = f"{SERVER_URL}/api/workflow/{workflow_id}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    wf = resp.json()
    raw = wf.get("workflowDefinition", {}).get("metadata", {}).get("agentDef", {})
    return json.loads(raw) if isinstance(raw, str) else raw


# ── Normalization ─────────────────────────────────────────────────────────────

def normalize(agent: dict) -> dict:
    """Deep-copy and normalize away all example-specific values."""
    return _norm_agent(copy.deepcopy(agent))


def _norm_agent(a: dict) -> dict:
    a["name"] = "__AGENT__"
    if "model" in a:
        a["model"] = "__MODEL__"
    if "instructions" in a:
        if isinstance(a["instructions"], str):
            a["instructions"] = "__INSTRUCTIONS__"
        elif isinstance(a["instructions"], dict):
            a["instructions"]["name"] = "__PROMPT_TEMPLATE__"
            a["instructions"].pop("variables", None)

    if "tools" in a:
        a["tools"] = [_norm_tool(t) for t in a["tools"]]

    if "guardrails" in a:
        a["guardrails"] = [_norm_guardrail(g) for g in a["guardrails"]]

    if "agents" in a:
        a["agents"] = [_norm_agent(sa) for sa in a["agents"]]

    if isinstance(a.get("router"), dict):
        a["router"] = _norm_agent(a["router"])

    if "callbacks" in a:
        for cb in a["callbacks"]:
            cb["taskName"] = "__CALLBACK_TASK__"

    if "outputType" in a:
        ot = a["outputType"]
        ot["className"] = "__OUTPUT_CLASS__"
        if "schema" in ot:
            ot["schema"] = _strip_titles(ot["schema"])

    if "stopWhen" in a:
        a["stopWhen"]["taskName"] = "__STOP_WHEN_TASK__"

    if "handoffs" in a:
        for h in a["handoffs"]:
            h["target"] = "__TARGET__"
            if "taskName" in h:
                h["taskName"] = "__HANDOFF_TASK__"
            if "text" in h:
                h["text"] = "__TEXT__"

    # Strip fields that are always emitted by one SDK but not the other
    # when the value is the "empty/default" value — not structural gaps.
    if a.get("timeoutSeconds") == 0:
        a.pop("timeoutSeconds", None)
    if a.get("external") is False:
        a.pop("external", None)

    return a


def _norm_tool(t: dict) -> dict:
    t["name"] = "__TOOL__"
    t["description"] = "__TOOL_DESC__"
    if "inputSchema" in t:
        t["inputSchema"] = _anon_schema(t["inputSchema"])
    if "outputSchema" in t:
        t["outputSchema"] = _anon_schema(t["outputSchema"])
    if "config" in t:
        cfg = t["config"]
        if "credentials" in cfg:
            cfg["credentials"] = ["__CRED__"] * len(cfg["credentials"])
        # Normalize URL/server values
        for key in ("url", "serverUrl", "mcpServer"):
            if key in cfg:
                cfg[key] = "__URL__"
    if "guardrails" in t:
        t["guardrails"] = [_norm_guardrail(g) for g in t["guardrails"]]
    return t


def _norm_guardrail(g: dict) -> dict:
    g["name"] = "__GUARDRAIL__"
    if "taskName" in g:
        g["taskName"] = "__GUARDRAIL_TASK__"
    if "patterns" in g:
        g["patterns"] = ["__PATTERN__"] * len(g["patterns"])
    if "policy" in g:
        g["policy"] = "__POLICY__"
    if "model" in g:
        g["model"] = "__MODEL__"
    return g


def _anon_schema(schema: dict) -> dict:
    """Anonymize property names but keep types and structure."""
    if "properties" not in schema:
        return schema
    sorted_props = sorted(schema["properties"].items())
    schema["properties"] = {
        f"__P{i}__": v for i, (_, v) in enumerate(sorted_props)
    }
    if "required" in schema:
        schema["required"] = sorted([f"__P{i}__" for i in range(len(schema["required"]))])
    return schema


def _strip_titles(schema: dict) -> dict:
    """Remove Pydantic-generated title fields — known gap, reported separately."""
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        if isinstance(prop, dict):
            _strip_titles(prop)
    return schema


# ── Diffing ───────────────────────────────────────────────────────────────────

def diff_agent(java: dict, py: dict) -> list[Gap]:
    return _diff_dicts(java, py, "root")


def _diff_dicts(a: dict, b: dict, path: str) -> list[Gap]:
    gaps = []
    for k in sorted(set(a) | set(b)):
        child = f"{path}.{k}"
        if k not in a:
            gaps.append(Gap(child, "missing_in_java", None, b[k]))
        elif k not in b:
            gaps.append(Gap(child, "missing_in_python", a[k], None))
        else:
            gaps.extend(_diff_vals(a[k], b[k], child))
    return gaps


def _diff_vals(a: Any, b: Any, path: str) -> list[Gap]:
    if type(a) != type(b):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if a != b:
                return [Gap(path, "value_mismatch", a, b)]
            return []
        return [Gap(path, "type_mismatch", type(a).__name__, type(b).__name__)]
    if isinstance(a, dict):
        return _diff_dicts(a, b, path)
    if isinstance(a, list):
        return _diff_lists(a, b, path)
    if a != b:
        return [Gap(path, "value_mismatch", a, b)]
    return []


def _diff_lists(a: list, b: list, path: str) -> list[Gap]:
    gaps = []
    if len(a) != len(b):
        gaps.append(Gap(path, "length_mismatch", len(a), len(b)))
    for i, (ai, bi) in enumerate(zip(a, b)):
        gaps.extend(_diff_vals(ai, bi, f"{path}[{i}]"))
    return gaps


# ── Reporting ─────────────────────────────────────────────────────────────────

def write_report(results: list[dict]):
    lines = ["# Java SDK Parity Report\n",
             "_Auto-generated by sdk/parity_check.py_\n\n",
             "## Summary\n\n",
             "| Example | Java Class | Python File | Gaps |\n",
             "|---------|------------|-------------|------|\n"]

    for r in results:
        status = "✅ PASS" if not r["gaps"] else f"❌ {len(r['gaps'])} gap(s)"
        lines.append(f"| {r['id']} | {r['java_class']} | {r['python_file']} | {status} |\n")

    lines.append("\n---\n\n## Details\n\n")

    for r in results:
        lines.append(f"### Example{r['id']}: {r['java_class']}\n\n")
        if r.get("error"):
            lines.append(f"⚠️ **Error**: `{r['error']}`\n\n")
            continue
        if not r["gaps"]:
            lines.append("✅ No SDK gaps found.\n\n")
            continue
        lines.append(f"**{len(r['gaps'])} gap(s) found:**\n\n")
        lines.append("| Path | Kind | Java | Python |\n")
        lines.append("|------|------|------|--------|\n")
        for g in r["gaps"]:
            j = _short(g.java_val) if g.java_val is not None else "—"
            p = _short(g.python_val) if g.python_val is not None else "—"
            lines.append(f"| `{g.path}` | {g.kind} | `{j}` | `{p}` |\n")
        lines.append("\n")

    REPORT_FILE.write_text("".join(lines))
    print(f"\nReport written to {REPORT_FILE}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Compare Java vs Python agent definitions")
    parser.add_argument("--example", help="Comma-separated example IDs to run (e.g. 01,03)")
    parser.add_argument("--timeout", type=int, default=120, help="Per-example timeout in seconds")
    args = parser.parse_args()

    config = load_config()
    ids = [i.strip() for i in args.example.split(",")] if args.example else []
    examples = filter_examples(config["examples"], ids)

    if not examples:
        print("No examples matched.")
        sys.exit(1)

    print(f"Running parity check for {len(examples)} example(s)...\n")

    results = []
    for ex in examples:
        print(f"[{ex['id']}] {ex['java_class']} ↔ {ex['python_file']}")
        result = {"id": ex["id"], "java_class": ex["java_class"],
                  "python_file": ex["python_file"], "gaps": [], "error": None}

        try:
            ex_timeout = ex.get("timeout", args.timeout)
            print(f"      Running Java...")
            java_def = run_java_example(ex["java_class"], timeout=ex_timeout)

            print(f"      Running Python...")
            py_def = run_python_example(ex["python_file"], timeout=ex_timeout)

            java_norm = normalize(java_def)
            py_norm = normalize(py_def)

            gaps = diff_agent(java_norm, py_norm)
            result["gaps"] = gaps

            if gaps:
                print(f"      ❌ {len(gaps)} gap(s):")
                for g in gaps:
                    print(f"        {g}")
            else:
                print(f"      ✅ No gaps")

        except Exception as e:
            result["error"] = str(e)
            print(f"      ⚠️  Error: {e}")

        results.append(result)
        print()

    total_gaps = sum(len(r["gaps"]) for r in results)
    errors = sum(1 for r in results if r.get("error"))
    print(f"{'='*60}")
    print(f"Results: {len(results)} examples, {total_gaps} gap(s), {errors} error(s)")

    write_report(results)

    sys.exit(1 if total_gaps > 0 or errors > 0 else 0)


if __name__ == "__main__":
    main()
