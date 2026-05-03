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

from agentspan.agents import Agent, AgentRuntime, Strategy, tool
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

PLANNER_INSTRUCTIONS = f"""\
You are a research report planner. Given a topic, plan a structured report.

Your job:
1. Decide on 3-5 sections for the report (introduction, 2-3 body sections, conclusion)
2. For each section, write clear instructions on what content to include
3. Output your plan as Markdown with an embedded JSON fence

IMPORTANT: Your plan MUST include a ```json fence with the structured plan.
The JSON plan uses the Plan-Execute schema with steps, validation, and on_success.

## Available tools for operations:
- `create_directory`: args={{path}} — create a directory
- `write_file`: generate={{instructions, output_schema}} — LLM writes content
- `assemble_files`: args={{output_path, input_paths, separator}} — concatenate files
- `check_word_count`: args={{path, min_words}} — validate word count

## Plan format:

Your output MUST end with a JSON fence like this example:

```json
{{
  "steps": [
    {{
      "id": "setup",
      "parallel": false,
      "operations": [
        {{"tool": "create_directory", "args": {{"path": "sections"}}}}
      ]
    }},
    {{
      "id": "write_sections",
      "depends_on": ["setup"],
      "parallel": true,
      "operations": [
        {{
          "tool": "write_file",
          "generate": {{
            "instructions": "Write a 200-word introduction about [topic]. Cover [key points].",
            "output_schema": "{{\\"path\\": \\"sections/01_intro.md\\", \\"content\\": \\"...\\"}}"
          }}
        }},
        {{
          "tool": "write_file",
          "generate": {{
            "instructions": "Write a 200-word section about [subtopic]. Cover [details].",
            "output_schema": "{{\\"path\\": \\"sections/02_body.md\\", \\"content\\": \\"...\\"}}"
          }}
        }}
      ]
    }},
    {{
      "id": "assemble",
      "depends_on": ["write_sections"],
      "parallel": false,
      "operations": [
        {{
          "tool": "assemble_files",
          "args": {{
            "output_path": "report.md",
            "input_paths": "[\\"sections/01_intro.md\\", \\"sections/02_body.md\\"]",
            "separator": "\\n\\n---\\n\\n"
          }}
        }}
      ]
    }}
  ],
  "validation": [
    {{"tool": "check_word_count", "args": {{"path": "report.md", "min_words": {MIN_WORD_COUNT}}}}}
  ],
  "on_success": []
}}
```

## Rules:
- Section files go in sections/ directory (01_intro.md, 02_body.md, etc.)
- Each section should be 150-300 words
- The assemble step must list ALL section files in order
- Always validate with check_word_count (min {MIN_WORD_COUNT} words)
- The JSON must be valid — double-check bracket matching
"""

FALLBACK_INSTRUCTIONS = f"""\
You are fixing a report that failed validation. The plan was already partially \
executed but something went wrong (missing sections, word count too low, etc.).

Review the error output, figure out what's missing or broken, and fix it.
You have access to read_file, write_file, assemble_files, and check_word_count.

Working directory: {WORK_DIR}
"""

planner = Agent(
    name="report_planner",
    model=settings.llm_model,
    instructions=PLANNER_INSTRUCTIONS,
    max_turns=3,
    max_tokens=4000,
)

fallback = Agent(
    name="report_fallback",
    model=settings.llm_model,
    instructions=FALLBACK_INSTRUCTIONS,
    tools=[create_directory, read_file, write_file, assemble_files, check_word_count],
    max_turns=10,
    max_tokens=8000,
)

# ── Harness ──────────────────────────────────────────────────────

report_harness = Agent(
    name="report_generator",
    model=settings.llm_model,
    agents=[planner, fallback],
    strategy=Strategy.PLAN_EXECUTE,
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
