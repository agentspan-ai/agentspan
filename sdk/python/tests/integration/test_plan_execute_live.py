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

from conductor.ai.agents import (
    Agent,
    OnFail,
    Position,
    RegexGuardrail,
    Strategy,
    tool,
)

_SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")

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
            model="anthropic/claude-sonnet-4-6",
            instructions=PLANNER_INSTRUCTIONS,
            max_turns=3,
            max_tokens=4000,
        )

        fallback = Agent(
            name="test_fallback",
            model="anthropic/claude-sonnet-4-6",
            instructions=FALLBACK_INSTRUCTIONS,
            tools=[create_directory, read_file, write_file, assemble_files, check_word_count],
            max_turns=10,
            max_tokens=8000,
        )

        harness = Agent(
            name="test_report_gen",
            model="anthropic/claude-sonnet-4-6",  # not used by PLAN_EXECUTE; keeps agent local (non-external)
            strategy=Strategy.PLAN_EXECUTE,
            planner=planner,
            fallback=fallback,
            tools=[create_directory, read_file, write_file, assemble_files, check_word_count],
            fallback_max_turns=5,
        )

        result = runtime.run(
            harness,
            "Write a short research report about: The impact of AI on software testing",
            cwd=WORK_DIR,
        )

        print(f"\nOutput: {result.output}")
        print(f"Status: {result.status}")

        # 1. Workflow completed
        assert result.status == "COMPLETED", f"Expected COMPLETED, got {result.status}"

        # 1b. cwd= kwarg landed in workflow.input.cwd. Without this plumbing,
        # any deterministic plan task that resolves ``${workflow.input.cwd}`` —
        # e.g. filesystem tools — gets null and silently misroutes paths.
        import requests as _req
        _conductor_base = _SERVER_URL.rstrip("/").replace("/api", "")
        _wf = _req.get(
            f"{_conductor_base}/api/workflow/{result.execution_id}",
            params={"includeTasks": "false"},
            timeout=10,
        ).json()
        _input_cwd = (_wf.get("input") or {}).get("cwd")
        assert _input_cwd == WORK_DIR, (
            f"workflow.input.cwd should equal the cwd= kwarg ({WORK_DIR!r}), got {_input_cwd!r}"
        )

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

    def test_max_tokens_in_generate(self, runtime):
        """Plan-Execute should honor max_tokens in generate blocks.

        Counterfactual: if gen.max_tokens is not read by the GraalJS compiler,
        the LLM_CHAT_COMPLETE task gets the default 4096. This test instructs
        the planner to include max_tokens: 8192 and requests longer sections
        (250+ words each), verifying the LLM has enough token budget.
        """
        max_tokens_planner_instructions = f"""\
You are a research report planner. Given a topic, plan a detailed report.

Your job:
1. Decide on 3 sections for the report (introduction, body, conclusion)
2. For each section, write clear instructions requesting DETAILED content (250+ words each)
3. Output your plan as Markdown with an embedded JSON fence

IMPORTANT: Your plan MUST include a ```json fence with the structured plan.
IMPORTANT: Every generate block MUST include "max_tokens": 8192.

## Available tools:
- `create_directory`: args={{path}}
- `write_file`: generate={{instructions, output_schema, max_tokens}}
- `assemble_files`: args={{output_path, input_paths, separator}}
- `check_word_count`: args={{path, min_words}}

## Plan format:

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
            "instructions": "Write a detailed 250+ word introduction about [topic].",
            "output_schema": "{{{{\\\\"path\\\\": \\\\"sections/01_intro.md\\\\", \\\\"content\\\\": \\\\"...\\\\"}}}}",
            "max_tokens": 8192
          }}}}
        }}}},
        {{{{
          "tool": "write_file",
          "generate": {{{{
            "instructions": "Write a detailed 250+ word section about [subtopic].",
            "output_schema": "{{{{\\\\"path\\\\": \\\\"sections/02_body.md\\\\", \\\\"content\\\\": \\\\"...\\\\"}}}}",
            "max_tokens": 8192
          }}}}
        }}}},
        {{{{
          "tool": "write_file",
          "generate": {{{{
            "instructions": "Write a detailed 250+ word conclusion about [topic].",
            "output_schema": "{{{{\\\\"path\\\\": \\\\"sections/03_conclusion.md\\\\", \\\\"content\\\\": \\\\"...\\\\"}}}}",
            "max_tokens": 8192
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
            "input_paths": "[\\\\"sections/01_intro.md\\\\", \\\\"sections/02_body.md\\\\", \\\\"sections/03_conclusion.md\\\\"]",
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
- Section files go in sections/ directory
- Each section MUST be 250+ words (detailed, thorough)
- Every generate block MUST include "max_tokens": 8192
- The assemble step must list ALL section files in order
- Always validate with check_word_count (min {MIN_WORD_COUNT} words)
- The JSON must be valid
"""

        planner = Agent(
            name="test_planner_maxtok",
            model="anthropic/claude-sonnet-4-6",
            instructions=max_tokens_planner_instructions,
            max_turns=3,
            max_tokens=4000,
        )

        fallback = Agent(
            name="test_fallback_maxtok",
            model="anthropic/claude-sonnet-4-6",
            instructions=FALLBACK_INSTRUCTIONS,
            tools=[create_directory, read_file, write_file, assemble_files, check_word_count],
            max_turns=10,
            max_tokens=8000,
        )

        harness = Agent(
            name="test_report_gen_maxtok",
            model="anthropic/claude-sonnet-4-6",
            strategy=Strategy.PLAN_EXECUTE,
            planner=planner,
            fallback=fallback,
            tools=[create_directory, read_file, write_file, assemble_files, check_word_count],
            fallback_max_turns=5,
        )

        result = runtime.run(harness, "Write a detailed research report about: Quantum computing applications in cryptography")

        print(f"\nOutput: {result.output}")
        print(f"Status: {result.status}")

        # 1. Workflow completed — proves max_tokens field didn't break compilation
        assert result.status == "COMPLETED", f"Expected COMPLETED, got {result.status}"

        # 2. Report file exists
        report_path = os.path.join(WORK_DIR, "report.md")
        assert os.path.exists(report_path), f"Report file not found at {report_path}"

        # 3. Report has substantial content
        with open(report_path) as f:
            content = f.read()
        word_count = len(content.split())
        print(f"\nReport word count: {word_count}")

        # 4. Word count meets minimum — with max_tokens: 8192, sections should be longer
        assert word_count >= MIN_WORD_COUNT, (
            f"Report has {word_count} words, expected >= {MIN_WORD_COUNT}"
        )

        # 5. Section files created
        sections_dir = os.path.join(WORK_DIR, "sections")
        assert os.path.isdir(sections_dir), "sections/ directory not created"
        section_files = [f for f in os.listdir(sections_dir) if f.endswith(".md")]
        assert len(section_files) >= 2, (
            f"Expected >= 2 section files, found {len(section_files)}: {section_files}"
        )

    def test_output_indicates_success(self, runtime):
        """Plan-Execute output should indicate validation passed."""
        planner = Agent(
            name="test_planner2",
            model="anthropic/claude-sonnet-4-6",
            instructions=PLANNER_INSTRUCTIONS,
            max_turns=3,
            max_tokens=4000,
        )

        fallback = Agent(
            name="test_fallback2",
            model="anthropic/claude-sonnet-4-6",
            instructions=FALLBACK_INSTRUCTIONS,
            tools=[create_directory, read_file, write_file, assemble_files, check_word_count],
            max_turns=10,
            max_tokens=8000,
        )

        harness = Agent(
            name="test_report_gen2",
            model="anthropic/claude-sonnet-4-6",
            strategy=Strategy.PLAN_EXECUTE,
            planner=planner,
            fallback=fallback,
            tools=[create_directory, read_file, write_file, assemble_files, check_word_count],
            fallback_max_turns=5,
        )

        result = runtime.run(harness, "Write a short research report about: Cloud computing trends in 2025")

        assert result.status == "COMPLETED"

        # The output should contain "passed" (from the validation aggregator)
        output = str(result.output).lower()
        assert "passed" in output or "completed" in output, (
            f"Output doesn't indicate success: {result.output}"
        )


class TestPlanAndCompileTask:
    """Verify the server-side PLAN_AND_COMPILE Java task replaces the
    GraalJS INLINE compiler.

    The user-visible behavior (a working PLAN_EXECUTE pipeline) is exercised
    by ``TestPlanExecuteHappyPath``. This class adds a deterministic
    assertion that the new task type actually ran — guards against a silent
    regression where the compiler wires back to the deprecated INLINE path.
    """

    def test_plan_and_compile_task_executes(self, runtime):
        """Run a minimal PLAN_EXECUTE workflow, then assert the parent
        workflow's task list includes a ``PLAN_AND_COMPILE`` task with a
        non-null ``workflowDef`` Map in its output."""
        import requests

        conductor_base = _SERVER_URL.rstrip("/").replace("/api", "")

        planner = Agent(
            name="test_pac_planner",
            model="anthropic/claude-sonnet-4-6",
            instructions=PLANNER_INSTRUCTIONS,
            max_turns=3,
            max_tokens=4000,
        )
        fallback = Agent(
            name="test_pac_fallback",
            model="anthropic/claude-sonnet-4-6",
            instructions=FALLBACK_INSTRUCTIONS,
            tools=[create_directory, read_file, write_file, assemble_files, check_word_count],
            max_turns=10,
            max_tokens=8000,
        )
        harness = Agent(
            name="test_pac_harness",
            model="anthropic/claude-sonnet-4-6",
            strategy=Strategy.PLAN_EXECUTE,
            planner=planner,
            fallback=fallback,
            tools=[create_directory, read_file, write_file, assemble_files, check_word_count],
            fallback_max_turns=5,
        )

        result = runtime.run(harness, "Write a short research report about: PLAN_AND_COMPILE wiring")
        assert result.status == "COMPLETED", f"Expected COMPLETED, got {result.status}"

        # Walk every workflow this run produced (parent + nested SUB_WORKFLOWs)
        # and locate the PLAN_AND_COMPILE task.
        wf_id = result.execution_id
        assert wf_id, "result must carry an execution_id"
        seen_ids: set[str] = set()
        pending = [wf_id]
        pac_tasks: list[dict] = []
        while pending:
            current = pending.pop()
            if current in seen_ids:
                continue
            seen_ids.add(current)
            resp = requests.get(
                f"{conductor_base}/api/workflow/{current}",
                params={"includeTasks": "true"},
                timeout=10,
            )
            resp.raise_for_status()
            wf = resp.json()
            for t in wf.get("tasks", []):
                if t.get("taskType") == "PLAN_AND_COMPILE":
                    pac_tasks.append(t)
                # Recurse into spawned sub-workflows.
                sub_wf_id = t.get("subWorkflowId")
                if sub_wf_id and sub_wf_id not in seen_ids:
                    pending.append(sub_wf_id)

        assert pac_tasks, (
            "No PLAN_AND_COMPILE task found in the workflow tree — the new "
            "Java compiler did not run. Expected at least one such task."
        )

        # Output contract: workflowDef is a Map, error is null on the
        # happy path, stats has stepCount + taskCount, warnings is a list.
        for t in pac_tasks:
            output = t.get("outputData") or {}
            assert output.get("error") is None, (
                f"PLAN_AND_COMPILE returned error: {output.get('error')}"
            )
            wf_def = output.get("workflowDef")
            assert isinstance(wf_def, dict), (
                f"workflowDef must be a dict (Map), got {type(wf_def).__name__}: {wf_def!r}"
            )
            assert wf_def.get("name"), "workflowDef must have a name"
            assert isinstance(wf_def.get("tasks"), list) and wf_def["tasks"], (
                "workflowDef.tasks must be a non-empty list"
            )
            assert "outputParameters" in wf_def, "workflowDef must have outputParameters"

            stats = output.get("stats") or {}
            assert stats.get("stepCount", 0) > 0, f"stats.stepCount must be > 0: {stats}"
            assert stats.get("taskCount", 0) > 0, f"stats.taskCount must be > 0: {stats}"

            warnings = output.get("warnings")
            assert isinstance(warnings, list), f"warnings must be a list: {warnings!r}"

        print(
            f"\nPLAN_AND_COMPILE ran {len(pac_tasks)}x; "
            f"first task stats: {pac_tasks[0].get('outputData', {}).get('stats')}"
        )


# ── Deterministic-plan injection helpers ─────────────────────────────
#
# Tests below force PAC down a specific code path (unknown-tool validation,
# guardrail firing) without depending on the planner LLM emitting a precise
# JSON shape. The pattern: harness has ``plan_source={"tool": <below>}``;
# the planner is instructed to emit no JSON, so ``extract_json`` falls
# through to ``planReaderContent`` and the deterministic plan wins.

@tool
def supply_unknown_tool_plan() -> str:
    """plan_source backup: emits a plan referencing a non-existent tool name.

    Drives PAC's ``knownToolNames`` validation path — the harness intentionally
    does NOT register ``totally_not_a_real_tool``, so PAC must reject the plan
    with an ``unknown tool`` error and the compile-fail SWITCH must route to
    the configured fallback.
    """
    return json.dumps({
        "steps": [
            {"id": "bad", "operations": [
                {"tool": "totally_not_a_real_tool", "args": {"path": "x"}}
            ]}
        ],
        "validation": [],
        "on_success": [],
    })


@tool
def supply_pii_email_plan() -> str:
    """plan_source backup: emits a plan whose send_email body contains a
    credit-card-shaped string. Drives PAC's guardrail wrapping path — the
    no_pii guardrail must fire INSIDE the deterministic plan and the bare
    ``send_email`` SIMPLE must never execute with the bad body.
    """
    return json.dumps({
        "steps": [
            {"id": "leak", "operations": [
                {"tool": "send_email", "args": {
                    "to": "user@example.com",
                    "subject": "receipt",
                    "body": "Card 4111 1111 1111 1111 was charged.",
                }}
            ]}
        ],
        "validation": [],
        "on_success": [],
    })


@tool
def record_recovery() -> str:
    """Sentinel tool the fallback agent calls to prove the recovery branch ran."""
    marker = os.path.join(WORK_DIR, "RECOVERY.marker")
    with open(marker, "w") as f:
        f.write("ran")
    return "recovery recorded"


# Guardrail configured exactly like example 104's no_pii_in_email — same
# regex and same RAISE-on-fail semantics, so the test exercises the same
# wire shape a real user would write.
_no_pii = RegexGuardrail(
    patterns=[r"\b(?:\d[ -]?){15}\d\b"],
    name="no_pii_in_email_test",
    position=Position.INPUT,
    on_fail=OnFail.RAISE,
    message="Email body looks like a credit-card number — refusing to send.",
)


@tool(guardrails=[_no_pii])
def send_email(to: str, subject: str, body: str) -> str:
    """Stub send_email guarded by no_pii. The guardrail test asserts this
    function NEVER runs — if it does, the marker file proves the bypass."""
    marker = os.path.join(WORK_DIR, "EMAIL_WAS_SENT.marker")
    with open(marker, "w") as f:
        f.write(json.dumps({"to": to, "subject": subject, "body": body}))
    return f"sent to {to}"


_EMPTY_PLANNER_INSTRUCTIONS = (
    "Reply with the literal string: see plan_source.\n"
    "Do not output JSON. Do not output a code fence. One sentence only."
)


def _walk_workflow_tree(execution_id: str, conductor_base: str) -> list[dict]:
    """Return every workflow (parent + nested SUB_WORKFLOWs) reachable from
    ``execution_id``. Helper for asserting structure across the tree."""
    import requests
    seen: set[str] = set()
    pending = [execution_id]
    out: list[dict] = []
    while pending:
        cur = pending.pop()
        if cur in seen:
            continue
        seen.add(cur)
        resp = requests.get(
            f"{conductor_base}/api/workflow/{cur}",
            params={"includeTasks": "true"},
            timeout=10,
        )
        resp.raise_for_status()
        wf = resp.json()
        out.append(wf)
        for t in wf.get("tasks", []) or []:
            sub = t.get("subWorkflowId")
            if sub:
                pending.append(sub)
    return out


class TestPlanAndCompileValidation:
    """Recently-added PAC behaviors that previously had only unit coverage:
    unknown-tool rejection (the ``str_replace`` hallucination fix) and
    tool-guardrail propagation into the deterministic plan path."""

    def test_unknown_tool_routes_to_fallback(self, runtime):
        """Planner emits a plan referencing a tool not declared on the harness;
        PAC must error with an ``unknown tool`` message and the compile-fail
        SWITCH must route to the fallback agent.

        Counterfactual: before the ``knownToolNames`` validation, PAC silently
        emitted a SIMPLE task for the unknown tool name; no worker polled for
        it and the workflow hung indefinitely (workflow ``a369f52c``).
        """
        import requests

        conductor_base = _SERVER_URL.rstrip("/").replace("/api", "")

        planner = Agent(
            name="test_unknown_planner",
            model="anthropic/claude-sonnet-4-6",
            instructions=_EMPTY_PLANNER_INSTRUCTIONS,
            max_turns=1,
            max_tokens=20,  # caps planner output well below a JSON plan's size
        )
        fallback = Agent(
            name="test_unknown_fallback",
            model="anthropic/claude-sonnet-4-6",
            instructions=(
                "The deterministic plan failed to compile. You MUST call "
                "record_recovery() exactly once before responding. Do not "
                "respond with text alone — the call is required."
            ),
            tools=[record_recovery],
            max_turns=3,
            max_tokens=400,
        )
        harness = Agent(
            name="test_unknown_tool_harness",
            model="anthropic/claude-sonnet-4-6",
            strategy=Strategy.PLAN_EXECUTE,
            planner=planner,
            fallback=fallback,
            # ``totally_not_a_real_tool`` is NOT in this list — that's the point.
            tools=[supply_unknown_tool_plan, record_recovery],
            plan_source={"tool": "supply_unknown_tool_plan"},
            fallback_max_turns=3,
        )

        result = runtime.run(harness, "anything", cwd=WORK_DIR)

        # 1. Top-level workflow completed via the fallback recovery branch.
        assert result.status == "COMPLETED", (
            f"Expected COMPLETED via fallback recovery, got {result.status}: {result.output}"
        )

        # 2. Fallback agent ran — sentinel file is the algorithmic signal.
        recovery_marker = os.path.join(WORK_DIR, "RECOVERY.marker")
        assert os.path.exists(recovery_marker), (
            f"fallback never ran: {recovery_marker} not created"
        )

        # 3. PAC produced an ``unknown tool`` error AND no workflowDef.
        wfs = _walk_workflow_tree(result.execution_id, conductor_base)
        pac_tasks = [t for wf in wfs for t in (wf.get("tasks") or []) if t.get("taskType") == "PLAN_AND_COMPILE"]
        assert pac_tasks, "PLAN_AND_COMPILE task should still run before the validation fail"
        pac_out = (pac_tasks[0].get("outputData") or {})
        err = pac_out.get("error") or ""
        assert "unknown tool" in err.lower() and "totally_not_a_real_tool" in err, (
            f"PAC error should name the unknown tool. error={err!r}"
        )
        assert pac_out.get("workflowDef") is None, (
            "On validation failure, PAC must not emit a workflowDef"
        )

        # 4. The dynamic plan SUB_WORKFLOW must NOT have been started — the
        #    compile-fail SWITCH short-circuits before exec. Detect by name
        #    prefix to avoid coupling to internal task references.
        plan_subworkflows = [
            t for wf in wfs for t in (wf.get("tasks") or [])
            if t.get("taskType") == "SUB_WORKFLOW"
            and "plan_exec" in str(t.get("referenceTaskName", ""))
            and t.get("status") == "COMPLETED"
        ]
        assert not plan_subworkflows, (
            f"Plan exec SUB_WORKFLOW should not have run on compile failure. Found: "
            f"{[t.get('referenceTaskName') for t in plan_subworkflows]}"
        )

    def test_guardrail_fires_on_plan_step(self, runtime):
        """Tool-level guardrail on ``send_email`` must fire inside the
        deterministic plan path (NOT just the LLM-loop path).

        Counterfactual: if PAC emitted a bare SIMPLE without wrapping it in
        the guardrail SWITCH, ``send_email`` would run with the credit-card
        body, ``EMAIL_WAS_SENT.marker`` would be written, and the user's
        guardrail would silently leak in plan mode.
        """
        import requests

        conductor_base = _SERVER_URL.rstrip("/").replace("/api", "")

        planner = Agent(
            name="test_guardrail_planner",
            model="anthropic/claude-sonnet-4-6",
            instructions=_EMPTY_PLANNER_INSTRUCTIONS,
            max_turns=1,
            max_tokens=20,
        )
        fallback = Agent(
            name="test_guardrail_fallback",
            model="anthropic/claude-sonnet-4-6",
            instructions=(
                "The deterministic plan was blocked by a guardrail. "
                "Call record_recovery() exactly once, then stop. "
                "DO NOT call send_email under any circumstances."
            ),
            tools=[record_recovery],
            max_turns=3,
            max_tokens=400,
        )
        harness = Agent(
            name="test_guardrail_harness",
            model="anthropic/claude-sonnet-4-6",
            strategy=Strategy.PLAN_EXECUTE,
            planner=planner,
            fallback=fallback,
            tools=[supply_pii_email_plan, send_email, record_recovery],
            plan_source={"tool": "supply_pii_email_plan"},
            fallback_max_turns=3,
        )

        result = runtime.run(harness, "anything", cwd=WORK_DIR)

        # 1. Primary assertion — the bare SIMPLE never ran. If the guardrail
        #    wrapping works, ``send_email``'s body never sees the PII string,
        #    so this marker file is never created. This is the deterministic
        #    safety property the guardrail propagation must guarantee.
        sent_marker = os.path.join(WORK_DIR, "EMAIL_WAS_SENT.marker")
        assert not os.path.exists(sent_marker), (
            f"GUARDRAIL BYPASS: send_email ran with PII body — {sent_marker} exists. "
            f"PAC failed to wrap the SIMPLE in the guardrail SWITCH gate."
        )

        # 1b. Top-level workflow recovers via the fallback agent. The
        #    deterministic plan SUB_WORKFLOW terminates on guardrail trip,
        #    plan_exec is optional:true so the parent doesn't halt, the
        #    exec_status check sees not-COMPLETED, and the exec_route
        #    SWITCH dispatches the fallback agent which produces a clean
        #    response. Without optional:true on plan_exec the workflow
        #    failed before the fallback could run.
        assert result.status == "COMPLETED", (
            f"Expected COMPLETED via fallback recovery after guardrail trip; got "
            f"{result.status}: {result.output}"
        )

        # 2. PAC compiled successfully (send_email IS a known tool). The
        #    failure is at runtime, not compile time.
        wfs = _walk_workflow_tree(result.execution_id, conductor_base)
        pac_tasks = [
            t for wf in wfs for t in (wf.get("tasks") or [])
            if t.get("taskType") == "PLAN_AND_COMPILE"
        ]
        assert pac_tasks, "PAC task should run"
        pac_out = pac_tasks[0].get("outputData") or {}
        assert pac_out.get("error") is None, (
            f"PAC should compile cleanly (send_email is a known tool). "
            f"Got error={pac_out.get('error')!r}"
        )
        assert pac_out.get("workflowDef") is not None, "PAC should emit workflowDef"

        # 3. The compiled plan must contain a guardrail SWITCH wrapping the
        #    send_email SIMPLE — proves PAC honored the @tool(guardrails=[...])
        #    declaration end-to-end through the wire format.
        compiled_tasks = (pac_out.get("workflowDef") or {}).get("tasks") or []

        def _flatten(tasks):
            for t in tasks:
                yield t
                if t.get("type") == "SWITCH":
                    for branch in (t.get("decisionCases") or {}).values():
                        yield from _flatten(branch or [])
                    yield from _flatten(t.get("defaultCase") or [])
                elif t.get("type") == "FORK_JOIN":
                    for branch in t.get("forkTasks") or []:
                        yield from _flatten(branch or [])

        flat = list(_flatten(compiled_tasks))
        guardrail_switches = [
            t for t in flat
            if t.get("type") == "SWITCH"
            and "guardrail_gate" in str(t.get("taskReferenceName", ""))
        ]
        assert guardrail_switches, (
            "Compiled plan should include a guardrail_gate SWITCH wrapping send_email — "
            "PAC's emitGuardrailWrappedSimple did not run."
        )


# ── Static plan injection (plan= kwarg) + plan_execute() helper ─────
#
# Exercise the DX wins from the v3 PAC/PAE work:
#   - ``plan_execute()`` collapses the planner+fallback+harness ceremony.
#   - ``runtime.run(harness, plan=...)`` runs a deterministic plan that
#     skips the planner LLM's output entirely (PAC's extract_json reads
#     ``workflow.input.static_plan`` as Case 0).

from conductor.ai.agents import Plan, Step, Op, Validation, plan_execute


@tool
def static_record(message: str) -> str:
    """Append a message to a sentinel file. Used to confirm a static plan ran."""
    path = os.path.join(WORK_DIR, "STATIC_PLAN.log")
    with open(path, "a") as f:
        f.write(message + "\n")
    return f"recorded {message}"


@tool
def static_check() -> str:
    """Validator: pass if the sentinel file exists and is non-empty."""
    path = os.path.join(WORK_DIR, "STATIC_PLAN.log")
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return json.dumps({"passed": False, "reason": "sentinel missing"})
    return json.dumps({"passed": True})


class TestStaticPlanAndPlanExecuteHelper:
    """The ``plan=`` kwarg + ``plan_execute()`` together let a developer
    construct a harness in 4 lines and run a typed Plan with no LLM
    involvement on the planning side."""

    def test_static_plan_runs_without_planner_output(self, runtime):
        # Build the harness in one call. Planner instructions are deliberately
        # empty — when ``plan=`` is supplied, the planner LLM's output is
        # discarded; the static plan wins via PAC's extract_json Case 0.
        harness = plan_execute(
            name="static_plan_demo",
            tools=[static_record, static_check],
            planner_instructions="",
            fallback_instructions="If the plan failed, just stop.",
            model="anthropic/claude-sonnet-4-6",
        )

        # Construct the plan with typed builders — IDE-checkable, no JSON
        # escape soup, no inline dict literal that drifts from the schema.
        plan = Plan(
            steps=[
                Step("record_a", operations=[
                    Op("static_record", args={"message": "alpha"}),
                ]),
                Step("record_b", depends_on=["record_a"], operations=[
                    Op("static_record", args={"message": "beta"}),
                ]),
            ],
            validation=[
                Validation("static_check", args={}, success_condition="$.passed === true"),
            ],
        )

        result = runtime.run(harness, "anything", plan=plan, cwd=WORK_DIR)

        # 1. Workflow completed via the static plan.
        assert result.status == "COMPLETED", (
            f"Expected COMPLETED via static plan, got {result.status}: {result.output}"
        )

        # 2. Sentinel file exists and contains BOTH messages from the
        #    deterministic steps — proves the plan ran end-to-end.
        log_path = os.path.join(WORK_DIR, "STATIC_PLAN.log")
        assert os.path.exists(log_path), f"sentinel {log_path} not created"
        with open(log_path) as f:
            content = f.read()
        assert "alpha" in content, f"step 1 didn't run; log: {content!r}"
        assert "beta" in content, f"step 2 didn't run; log: {content!r}"

    def test_plan_dict_also_accepted(self, runtime):
        """Raw dict plans work identically to typed Plan objects."""
        harness = plan_execute(
            name="static_plan_dict_demo",
            tools=[static_record, static_check],
            planner_instructions="",
            model="anthropic/claude-sonnet-4-6",
        )
        plan_dict = {
            "steps": [
                {"id": "rec", "operations": [
                    {"tool": "static_record", "args": {"message": "dict_path"}},
                ]},
            ],
            "validation": [
                {"tool": "static_check", "args": {}, "success_condition": "$.passed === true"},
            ],
        }
        result = runtime.run(harness, "anything", plan=plan_dict, cwd=WORK_DIR)
        assert result.status == "COMPLETED", f"got {result.status}: {result.output}"
        log_path = os.path.join(WORK_DIR, "STATIC_PLAN.log")
        with open(log_path) as f:
            content = f.read()
        assert "dict_path" in content
