#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Plan-Execute Harness — deterministic execution of LLM-generated plans.

Demonstrates Strategy.PLAN_EXECUTE: a planner agent produces a structured plan
(DAG of operations), which is compiled into a Conductor workflow and executed
deterministically. LLM is only invoked per-operation where it adds value
(generating content, writing code). Orchestration is pure Conductor.

This example builds a research report generator:
    planner → plan_executor (deterministic) → fallback (if validation fails)

The planner:
    - Takes a topic and decides what sections to research/write
    - Outputs a Markdown plan with an embedded JSON fence
    - The JSON describes a DAG: research (parallel) → write sections (parallel) → assemble

The executor (compiled from JSON plan):
    - Static operations (create dirs, assemble files) run as direct tool calls
    - Generated operations (write sections) get parallel LLM calls
    - Validation checks the report exists and meets word count

If validation fails, the fallback agent gets the plan + errors and fixes things.

Architecture:
    planner (agentic LLM)
      ↓ writes plan with JSON fence
    plan_executor (deterministic Conductor workflow)
      ├── step: setup (static: create output dir)
      ├── step: write_sections (parallel: LLM generates each section)
      ├── step: assemble (static: concatenate sections)
      └── validation: check word count
      ↓ on failure
    fallback (agentic LLM, bounded)

Usage:
    python 85_plan_execute_harness.py "The impact of AI agents on software development"
    python 85_plan_execute_harness.py "Climate change mitigation strategies for 2030"

Requirements:
    - Agentspan server with PLAN_EXECUTE strategy support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-4o-mini)
"""

import json
import os
import sys
import tempfile

from conductor.ai.agents import AgentRuntime, plan_execute, tool
from settings import settings

# ── Configuration ────────────────────────────────────────────────
WORK_DIR = os.path.join(tempfile.gettempdir(), "plan-execute-report")
MIN_WORD_COUNT = 500


# ── Tools ────────────────────────────────────────────────────────


@tool
def create_directory(path: str) -> str:
    """Create a directory (and parents) if it doesn't exist.

    Args:
        path: Directory path to create (relative to working dir).
    """
    full = os.path.join(WORK_DIR, path)
    os.makedirs(full, exist_ok=True)
    return f"Created directory: {full}"


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories if needed.

    Args:
        path: File path (relative to working dir).
        content: Full file content to write.
    """
    full = os.path.join(WORK_DIR, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)
    return f"Wrote {len(content)} bytes to {full}"


@tool
def read_file(path: str) -> str:
    """Read the contents of a file.

    Args:
        path: File path (relative to working dir).
    """
    full = os.path.join(WORK_DIR, path)
    if not os.path.exists(full):
        return f"ERROR: File not found: {full}"
    with open(full) as f:
        return f.read()


@tool
def assemble_files(output_path: str, input_paths: str, separator: str = "\n\n---\n\n") -> str:
    """Concatenate multiple files into one, with a separator between them.

    Args:
        output_path: Output file path (relative to working dir).
        input_paths: JSON array of input file paths (relative to working dir).
        separator: Text to insert between file contents.
    """
    paths = json.loads(input_paths)
    parts = []
    for p in paths:
        full = os.path.join(WORK_DIR, p)
        if os.path.exists(full):
            with open(full) as f:
                parts.append(f.read())
        else:
            parts.append(f"[Missing: {p}]")

    combined = separator.join(parts)
    out_full = os.path.join(WORK_DIR, output_path)
    os.makedirs(os.path.dirname(out_full), exist_ok=True)
    with open(out_full, "w") as f:
        f.write(combined)
    return f"Assembled {len(paths)} files into {out_full} ({len(combined)} bytes)"


@tool
def check_word_count(path: str, min_words: int) -> str:
    """Check that a file meets a minimum word count.

    Args:
        path: File path (relative to working dir).
        min_words: Minimum number of words required.
    """
    full = os.path.join(WORK_DIR, path)
    if not os.path.exists(full):
        return json.dumps({"passed": False, "error": f"File not found: {path}", "word_count": 0})
    with open(full) as f:
        content = f.read()
    count = len(content.split())
    passed = count >= min_words
    return json.dumps({"passed": passed, "word_count": count, "min_words": min_words})


# ── Agents ───────────────────────────────────────────────────────

# Domain-level guidance only. The server auto-appends ``## Available tools``
# and ``## Plan schema`` blocks to the planner's prompt at compile time —
# no need to hand-write tool listings or JSON schema examples here.
PLANNER_INSTRUCTIONS = f"""\
You are a research report planner. Given a topic, plan a structured report.

Your plan should:
1. Use 3-5 sections (introduction, 2-3 body sections, conclusion).
2. Put section files under ``sections/`` (e.g. ``sections/01_intro.md``).
3. Run section writes in parallel after a setup step that creates the directory.
4. Assemble the sections into ``report.md`` once writes complete.
5. Validate the result with ``check_word_count`` (min {MIN_WORD_COUNT} words).

Each section should be 150-300 words. Use the ``generate`` block on
``write_file`` ops so the LLM produces content at run time; static args for
``create_directory`` and ``assemble_files``.
"""

FALLBACK_INSTRUCTIONS = f"""\
You are fixing a report that failed validation. The plan was already partially \
executed but something went wrong (missing sections, word count too low, etc.).

Review the error output, figure out what's missing or broken, and fix it.
You have access to read_file, write_file, assemble_files, and check_word_count.

Working directory: {WORK_DIR}
"""

# ── Harness ──────────────────────────────────────────────────────
#
# ``plan_execute()`` collapses the planner+fallback+harness boilerplate
# into one call. ``tools`` is the canonical plan-executable set: every
# ``op.tool`` in the planner's JSON is validated against this list, and
# each tool's guardrails (none here) propagate into the compiled plan.
report_harness = plan_execute(
    name="report_generator",
    tools=[create_directory, read_file, write_file, assemble_files, check_word_count],
    planner_instructions=PLANNER_INSTRUCTIONS,
    fallback_instructions=FALLBACK_INSTRUCTIONS,
    model=settings.llm_model,
    fallback_max_turns=5,
)


# ── Main ─────────────────────────────────────────────────────────

def main():
    topic = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "The impact of AI agents on software development in 2025"

    os.makedirs(WORK_DIR, exist_ok=True)
    print(f"Topic: {topic}")
    print(f"Working directory: {WORK_DIR}")
    print(f"Strategy: PLAN_EXECUTE")
    print()

    with AgentRuntime() as rt:
        result = rt.run(report_harness, f"Write a research report about: {topic}")
        result.print_result()

        report_path = os.path.join(WORK_DIR, "report.md")
        if os.path.exists(report_path):
            with open(report_path) as f:
                content = f.read()
            word_count = len(content.split())
            print(f"\nReport: {report_path}")
            print(f"Word count: {word_count}")
            print(f"Preview:\n{content[:500]}...")


if __name__ == "__main__":
    main()
