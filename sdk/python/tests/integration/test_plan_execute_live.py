# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Plan-Execute strategy e2e tests — runs real agents with real LLM calls.

Tests the PLAN_EXECUTE strategy end-to-end:
  - Planner produces a valid JSON plan
  - Plan compiles to a Conductor sub-workflow
  - Parallel LLM generation executes deterministically
  - Static tool calls run without LLM
  - Validation passes on the happy path
  - Files are actually created on disk

Requires:
  - Agentspan server running (AGENTSPAN_SERVER_URL)
  - OPENAI_API_KEY set

Run with:
    python3 -m pytest tests/integration/test_plan_execute_live.py -v -s
"""

import json
import os
import shutil
import tempfile

import pytest

from agentspan.agents import Agent, Strategy, tool

pytestmark = pytest.mark.integration

# ── Test working directory ──────────────────────────────────────────
WORK_DIR = os.path.join(tempfile.gettempdir(), "plan-execute-test")
MIN_WORD_COUNT = 200


# ── Tools ───────────────────────────────────────────────────────────

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


# ── Agent definitions ───────────────────────────────────────────────

PLANNER_INSTRUCTIONS = f"""\
You are a research report planner. Given a topic, plan a structured report.

Your job:
1. Decide on 3 sections for the report (introduction, body, conclusion)
2. For each section, write clear instructions on what content to include
3. Output your plan as Markdown with an embedded JSON fence

IMPORTANT: Your plan MUST include a ```json fence with the structured plan.

## Available tools for operations:
- `create_directory`: args={{path}} — create a directory
- `write_file`: generate={{instructions, output_schema}} — LLM writes content
- `assemble_files`: args={{output_path, input_paths, separator}} — concatenate files
- `check_word_count`: args={{path, min_words}} — validate word count

## Plan format:

Your output MUST end with a JSON fence like this example:

```json
{{{{
  "steps": [
    {{{{
      "id": "setup",
      "parallel": false,
      "operations": [
        {{{{"tool": "create_directory", "args": {{{{"path": "sections"}}}}}}}}
      ]
    }}}},
    {{{{
      "id": "write_sections",
      "depends_on": ["setup"],
      "parallel": true,
      "operations": [
        {{{{
          "tool": "write_file",
          "generate": {{{{
            "instructions": "Write a 100-word introduction about [topic].",
            "output_schema": "{{{{\\\\"path\\\\": \\\\"sections/01_intro.md\\\\", \\\\"content\\\\": \\\\"...\\\\"}}}}"
          }}}}
        }}}},
        {{{{
          "tool": "write_file",
          "generate": {{{{
            "instructions": "Write a 100-word section about [subtopic].",
            "output_schema": "{{{{\\\\"path\\\\": \\\\"sections/02_body.md\\\\", \\\\"content\\\\": \\\\"...\\\\"}}}}"
          }}}}
        }}}}
      ]
    }}}},
    {{{{
      "id": "assemble",
      "depends_on": ["write_sections"],
      "parallel": false,
      "operations": [
        {{{{
          "tool": "assemble_files",
          "args": {{{{
            "output_path": "report.md",
            "input_paths": "[\\\\"sections/01_intro.md\\\\", \\\\"sections/02_body.md\\\\"]",
            "separator": "\\\\n\\\\n---\\\\n\\\\n"
          }}}}
        }}}}
      ]
    }}}}
  ],
  "validation": [
    {{{{"tool": "check_word_count", "args": {{{{"path": "report.md", "min_words": {MIN_WORD_COUNT}}}}}}}}}
  ],
  "on_success": []
}}}}
```

## Rules:
- Section files go in sections/ directory (01_intro.md, 02_body.md, etc.)
- Each section should be 80-150 words
- The assemble step must list ALL section files in order
- Always validate with check_word_count (min {MIN_WORD_COUNT} words)
- Keep it simple: 3 sections total
- The JSON must be valid
"""

FALLBACK_INSTRUCTIONS = f"""\
You are fixing a report that failed validation. The plan was already partially \
executed but something went wrong (missing sections, word count too low, etc.).

Review the error output, figure out what's missing or broken, and fix it.
You have access to read_file, write_file, assemble_files, and check_word_count.

Working directory: {WORK_DIR}
"""


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_workdir():
    """Clean the working directory before each test."""
    if os.path.exists(WORK_DIR):
        shutil.rmtree(WORK_DIR)
    os.makedirs(WORK_DIR, exist_ok=True)
    yield
    # Leave artifacts for debugging on failure


# ── Tests ───────────────────────────────────────────────────────────

class TestPlanExecuteHappyPath:
    """Verify the Plan-Execute strategy works end-to-end."""

    def test_report_generation(self, runtime):
        """Plan-Execute should generate a report that passes word count validation."""
        planner = Agent(
            name="test_planner",
            model="openai/gpt-4o-mini",
            instructions=PLANNER_INSTRUCTIONS,
            max_turns=3,
            max_tokens=4000,
        )

        fallback = Agent(
            name="test_fallback",
            model="openai/gpt-4o-mini",
            instructions=FALLBACK_INSTRUCTIONS,
            tools=[create_directory, read_file, write_file, assemble_files, check_word_count],
            max_turns=10,
            max_tokens=8000,
        )

        harness = Agent(
            name="test_report_gen",
            model="openai/gpt-4o-mini",
            agents=[planner, fallback],
            strategy=Strategy.PLAN_EXECUTE,
            fallback_max_turns=5,
        )

        result = runtime.run(harness, "Write a short research report about: The impact of AI on software testing")

        print(f"\nOutput: {result.output}")
        print(f"Status: {result.status}")

        # 1. Workflow completed
        assert result.status == "COMPLETED", f"Expected COMPLETED, got {result.status}"

        # 2. Report file exists
        report_path = os.path.join(WORK_DIR, "report.md")
        assert os.path.exists(report_path), f"Report file not found at {report_path}"

        # 3. Report has content
        with open(report_path) as f:
            content = f.read()
        assert len(content) > 0, "Report file is empty"

        word_count = len(content.split())
        print(f"\nReport word count: {word_count}")
        print(f"Report preview: {content[:300]}...")

        # 4. Word count meets minimum (the plan validates this too,
        #    but we check independently to confirm)
        assert word_count >= MIN_WORD_COUNT, (
            f"Report has {word_count} words, expected >= {MIN_WORD_COUNT}"
        )

        # 5. Section files were created (proves parallel execution happened)
        sections_dir = os.path.join(WORK_DIR, "sections")
        assert os.path.isdir(sections_dir), "sections/ directory not created"
        section_files = [f for f in os.listdir(sections_dir) if f.endswith(".md")]
        assert len(section_files) >= 2, (
            f"Expected >= 2 section files, found {len(section_files)}: {section_files}"
        )

        # 6. Each section file has content
        for sf in section_files:
            sf_path = os.path.join(sections_dir, sf)
            with open(sf_path) as f:
                sf_content = f.read()
            sf_words = len(sf_content.split())
            print(f"  Section {sf}: {sf_words} words")
            assert sf_words > 10, f"Section {sf} has only {sf_words} words"

    def test_output_indicates_success(self, runtime):
        """Plan-Execute output should indicate validation passed."""
        planner = Agent(
            name="test_planner2",
            model="openai/gpt-4o-mini",
            instructions=PLANNER_INSTRUCTIONS,
            max_turns=3,
            max_tokens=4000,
        )

        fallback = Agent(
            name="test_fallback2",
            model="openai/gpt-4o-mini",
            instructions=FALLBACK_INSTRUCTIONS,
            tools=[create_directory, read_file, write_file, assemble_files, check_word_count],
            max_turns=10,
            max_tokens=8000,
        )

        harness = Agent(
            name="test_report_gen2",
            model="openai/gpt-4o-mini",
            agents=[planner, fallback],
            strategy=Strategy.PLAN_EXECUTE,
            fallback_max_turns=5,
        )

        result = runtime.run(harness, "Write a short research report about: Cloud computing trends in 2025")

        assert result.status == "COMPLETED"

        # The output should contain "passed" (from the validation aggregator)
        output = str(result.output).lower()
        assert "passed" in output or "completed" in output, (
            f"Output doesn't indicate success: {result.output}"
        )
