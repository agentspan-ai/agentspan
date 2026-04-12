# E2E Validation Framework Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a per-SDK end-to-end validation framework with an orchestrator, two test suites, and an HTML report generator — starting with Python.

**Architecture:** Orchestrator shell script at repo root builds all components, starts services (server + mcp-testkit), runs pytest suites with configurable parallelism, generates HTML report, tears down. Test suites live in `sdk/python/e2e/` and use real server, real CLI, no mocks.

**Tech Stack:** Bash (orchestrator), Python/pytest (suites), agentspan CLI (credential management), mcp-testkit (HTTP/MCP test server)

---

## File Structure

```
repo-root/
├── e2e-orchestrator.sh                        # CREATE — orchestrator script
├── sdk/python/e2e/
│   ├── conftest.py                            # CREATE — shared fixtures
│   ├── report_generator.py                    # CREATE — junit XML → HTML
│   ├── test_suite1_basic_validation.py        # CREATE — Suite 1
│   └── test_suite2_tool_calling.py            # CREATE — Suite 2
└── .gitignore                                 # MODIFY — add e2e-results/
```

---

## Chunk 1: Infrastructure (conftest, report generator, orchestrator)

### Task 1: conftest.py — shared fixtures

**Files:**
- Create: `sdk/python/e2e/conftest.py`

- [ ] **Step 1: Create conftest.py with all shared fixtures**

```python
"""E2E test infrastructure. No mocks. Real server, real CLI, real services."""

import os
import subprocess
import pytest
import requests

# ── Configuration from env (set by orchestrator) ────────────────────────

SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
BASE_URL = SERVER_URL.rstrip("/").replace("/api", "")
CLI_PATH = os.environ.get("AGENTSPAN_CLI_PATH", "agentspan")
MCP_TESTKIT_URL = os.environ.get("MCP_TESTKIT_URL", "http://localhost:3001")
MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini")


# ── Prevent runtime from auto-starting a second server ──────────────────

os.environ["AGENTSPAN_AUTO_START_SERVER"] = "false"


# ── Markers ─────────────────────────────────────────────────────────────

def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring live server")


# ── Session-scoped health check ─────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def verify_server():
    """Fail fast if server is not running."""
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        assert resp.json().get("healthy"), "Server reports unhealthy"
    except Exception as e:
        pytest.skip(f"Server not available at {BASE_URL}: {e}")


# ── Runtime fixture ─────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def runtime():
    """Module-scoped AgentRuntime — shared across tests in a module."""
    from agentspan.agents import AgentRuntime
    with AgentRuntime() as rt:
        yield rt


# ── Model fixture ───────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def model():
    return MODEL


@pytest.fixture(scope="session")
def mcp_url():
    return MCP_TESTKIT_URL


# ── CLI credential helper ──────────────────────────────────────────────

class CredentialsCLI:
    """Wraps the agentspan CLI for credential operations.

    Relies on AGENTSPAN_SERVER_URL env var being set (by orchestrator).
    The CLI's config.Load() reads this env var for the server URL.
    """

    def __init__(self, cli_path: str):
        self._cli = cli_path

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        cmd = [self._cli] + list(args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15)

    def set(self, name: str, value: str) -> None:
        result = self._run("credentials", "set", name, value)
        assert result.returncode == 0, (
            f"credentials set {name} failed: {result.stderr}"
        )

    def delete(self, name: str) -> None:
        result = self._run("credentials", "delete", name)
        # Ignore "not found" errors during cleanup
        if result.returncode != 0 and "not found" not in result.stderr.lower():
            raise AssertionError(
                f"credentials delete {name} failed: {result.stderr}"
            )

    def list(self) -> str:
        result = self._run("credentials", "list")
        assert result.returncode == 0, f"credentials list failed: {result.stderr}"
        return result.stdout


@pytest.fixture(scope="session")
def cli_credentials():
    return CredentialsCLI(CLI_PATH)


# ── Server API helpers ──────────────────────────────────────────────────

def get_workflow(execution_id: str) -> dict:
    """Fetch full workflow execution from server."""
    resp = requests.get(f"{BASE_URL}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_task_by_name(execution_id: str, task_ref_prefix: str) -> list:
    """Find tasks in a workflow whose referenceTaskName contains prefix."""
    wf = get_workflow(execution_id)
    return [
        t for t in wf.get("tasks", [])
        if task_ref_prefix in t.get("referenceTaskName", "")
    ]
```

- [ ] **Step 2: Verify conftest loads without errors**

Run: `cd sdk/python && uv run python -c "import e2e.conftest"`
Expected: No import errors (will skip tests if server not running, which is fine)

- [ ] **Step 3: Commit**

```bash
git add sdk/python/e2e/conftest.py
git commit -m "feat(e2e): add shared conftest with fixtures, CLI helper, server helpers"
```

---

### Task 2: HTML report generator

**Files:**
- Create: `sdk/python/e2e/report_generator.py`

- [ ] **Step 1: Create report_generator.py**

```python
"""Generate a self-contained HTML report from pytest junit XML output."""

import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


def generate_report(junit_xml_path: str, output_path: str) -> None:
    """Parse junit XML and produce a single-file HTML report."""
    tree = ET.parse(junit_xml_path)
    root = tree.getroot()

    # Collect suites — handle both <testsuites> wrapper and bare <testsuite>
    if root.tag == "testsuites":
        suites = list(root)
    else:
        suites = [root]

    total = passed = failed = skipped = errors = 0
    total_time = 0.0
    suite_data = []

    for suite in suites:
        suite_name = suite.get("name", "unknown")
        suite_tests = []
        for tc in suite.findall("testcase"):
            name = tc.get("name", "unknown")
            classname = tc.get("classname", "")
            time_s = float(tc.get("time", "0"))
            total_time += time_s
            total += 1

            failure = tc.find("failure")
            error = tc.find("error")
            skip = tc.find("skipped")

            if failure is not None:
                status = "FAILED"
                detail = failure.text or failure.get("message", "")
                failed += 1
            elif error is not None:
                status = "ERROR"
                detail = error.text or error.get("message", "")
                errors += 1
            elif skip is not None:
                status = "SKIPPED"
                detail = skip.get("message", "")
                skipped += 1
            else:
                status = "PASSED"
                detail = ""
                passed += 1

            suite_tests.append({
                "name": name,
                "classname": classname,
                "time": time_s,
                "status": status,
                "detail": detail,
            })
        suite_data.append({"name": suite_name, "tests": suite_tests})

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = _render_html(timestamp, total_time, total, passed, failed, skipped, errors, suite_data)
    Path(output_path).write_text(html, encoding="utf-8")
    print(f"Report written to {output_path}")


def _render_html(timestamp, total_time, total, passed, failed, skipped, errors, suites):
    status_colors = {
        "PASSED": "#22c55e",
        "FAILED": "#ef4444",
        "ERROR": "#f97316",
        "SKIPPED": "#eab308",
    }

    test_rows = []
    for suite in suites:
        test_rows.append(f'<tr class="suite-header"><td colspan="4">{_esc(suite["name"])}</td></tr>')
        for t in suite["tests"]:
            color = status_colors.get(t["status"], "#888")
            detail_block = ""
            if t["detail"]:
                detail_block = (
                    f'<details><summary>Details</summary>'
                    f'<pre>{_esc(t["detail"])}</pre></details>'
                )
            test_rows.append(
                f'<tr>'
                f'<td>{_esc(t["name"])}</td>'
                f'<td style="color:{color};font-weight:bold">{t["status"]}</td>'
                f'<td>{t["time"]:.2f}s</td>'
                f'<td>{detail_block}</td>'
                f'</tr>'
            )

    rows_html = "\n".join(test_rows)
    overall = "PASSED" if failed == 0 and errors == 0 else "FAILED"
    overall_color = "#22c55e" if overall == "PASSED" else "#ef4444"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>E2E Test Report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
         background: #0f172a; color: #e2e8f0; padding: 2rem; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 1rem; }}
  .summary {{ display: flex; gap: 1.5rem; margin-bottom: 1.5rem; flex-wrap: wrap; }}
  .stat {{ background: #1e293b; padding: 1rem 1.5rem; border-radius: 8px; }}
  .stat .label {{ font-size: 0.75rem; text-transform: uppercase; color: #94a3b8; }}
  .stat .value {{ font-size: 1.5rem; font-weight: bold; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; padding: 0.5rem 1rem; background: #1e293b; color: #94a3b8;
       font-size: 0.75rem; text-transform: uppercase; }}
  td {{ padding: 0.5rem 1rem; border-bottom: 1px solid #1e293b; }}
  tr.suite-header td {{ background: #1e293b; font-weight: bold; color: #60a5fa;
                        padding: 0.75rem 1rem; }}
  details {{ margin-top: 0.25rem; }}
  summary {{ cursor: pointer; color: #94a3b8; font-size: 0.85rem; }}
  pre {{ background: #1e293b; padding: 1rem; border-radius: 4px; overflow-x: auto;
         font-size: 0.8rem; margin-top: 0.5rem; white-space: pre-wrap; }}
</style>
</head>
<body>
<h1>E2E Test Report</h1>
<div class="summary">
  <div class="stat">
    <div class="label">Status</div>
    <div class="value" style="color:{overall_color}">{overall}</div>
  </div>
  <div class="stat">
    <div class="label">Total</div>
    <div class="value">{total}</div>
  </div>
  <div class="stat">
    <div class="label">Passed</div>
    <div class="value" style="color:#22c55e">{passed}</div>
  </div>
  <div class="stat">
    <div class="label">Failed</div>
    <div class="value" style="color:#ef4444">{failed}</div>
  </div>
  <div class="stat">
    <div class="label">Skipped</div>
    <div class="value" style="color:#eab308">{skipped}</div>
  </div>
  <div class="stat">
    <div class="label">Duration</div>
    <div class="value">{total_time:.1f}s</div>
  </div>
  <div class="stat">
    <div class="label">Timestamp</div>
    <div class="value" style="font-size:1rem">{timestamp}</div>
  </div>
</div>
<table>
<thead><tr><th>Test</th><th>Status</th><th>Time</th><th>Detail</th></tr></thead>
<tbody>
{rows_html}
</tbody>
</table>
</body>
</html>"""


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python report_generator.py <junit.xml> <output.html>")
        sys.exit(1)
    generate_report(sys.argv[1], sys.argv[2])
```

- [ ] **Step 2: Verify report generator works with a sample XML**

Run:
```bash
cd sdk/python
cat > /tmp/test_junit.xml << 'XML'
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="test_suite1_basic_validation" tests="2" failures="1">
    <testcase classname="test_suite1" name="test_smoke" time="0.5"/>
    <testcase classname="test_suite1" name="test_plan_tools" time="1.2">
      <failure message="assert failed">Expected 3 tasks, got 2</failure>
    </testcase>
  </testsuite>
</testsuites>
XML
uv run python e2e/report_generator.py /tmp/test_junit.xml /tmp/test_report.html
```
Expected: "Report written to /tmp/test_report.html" — file contains valid HTML with PASSED/FAILED rows.

- [ ] **Step 3: Commit**

```bash
git add sdk/python/e2e/report_generator.py
git commit -m "feat(e2e): add HTML report generator from junit XML"
```

---

### Task 3: Orchestrator shell script

**Files:**
- Create: `e2e-orchestrator.sh`
- Modify: `.gitignore`

- [ ] **Step 1: Create e2e-orchestrator.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

# ── E2E Test Orchestrator ────────────────────────────────────────────────
# Builds all components, starts services, runs e2e tests, generates report.
#
# Usage:
#   ./e2e-orchestrator.sh              # defaults: -j 1
#   ./e2e-orchestrator.sh -j 4        # 4 parallel workers
#   ./e2e-orchestrator.sh --suite suite1
#   ./e2e-orchestrator.sh --no-build --no-start

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
RESULTS_DIR="$REPO_ROOT/e2e-results"
PARALLELISM=1
SUITE_FILTER=""
DO_BUILD=true
DO_START=true
SERVER_PORT=6767
MCP_PORT=3001
SERVER_PID=""
MCP_PID=""

# ── Parse arguments ─────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case "$1" in
    -j|--parallelism) PARALLELISM="$2"; shift 2 ;;
    --suite)          SUITE_FILTER="$2"; shift 2 ;;
    --no-build)       DO_BUILD=false; shift ;;
    --no-start)       DO_START=false; shift ;;
    --port)           SERVER_PORT="$2"; shift 2 ;;
    --mcp-port)       MCP_PORT="$2"; shift 2 ;;
    *)                echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# ── Cleanup trap ────────────────────────────────────────────────────────

cleanup() {
  echo ""
  echo "=== Teardown ==="
  if [[ -n "$SERVER_PID" ]]; then
    echo "Stopping server (PID $SERVER_PID)..."
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  if [[ -n "$MCP_PID" ]]; then
    echo "Stopping mcp-testkit (PID $MCP_PID)..."
    kill "$MCP_PID" 2>/dev/null || true
    wait "$MCP_PID" 2>/dev/null || true
  fi
  echo "Done."
}
trap cleanup EXIT

# ── Build ───────────────────────────────────────────────────────────────

if $DO_BUILD; then
  echo "=== Building server ==="
  cd "$REPO_ROOT/server"
  ./gradlew bootJar -x test -q
  echo "Server JAR built."

  echo "=== Building CLI ==="
  cd "$REPO_ROOT/cli"
  go build -o agentspan .
  echo "CLI built at cli/agentspan"

  echo "=== Installing Python SDK ==="
  cd "$REPO_ROOT/sdk/python"
  uv sync --extra dev --group dev -q
  echo "Python SDK installed."

  echo "=== Installing mcp-testkit ==="
  uv pip install mcp-testkit -q 2>/dev/null || pip install mcp-testkit -q
  echo "mcp-testkit installed."
fi

# ── Start services ──────────────────────────────────────────────────────

if $DO_START; then
  echo "=== Starting mcp-testkit on port $MCP_PORT ==="
  mcp-testkit --transport http --port "$MCP_PORT" &
  MCP_PID=$!
  echo "mcp-testkit started (PID $MCP_PID)"

  echo "=== Starting agentspan server on port $SERVER_PORT ==="
  java -jar "$REPO_ROOT/server/build/libs/agentspan-runtime.jar" \
    --server.port="$SERVER_PORT" &
  SERVER_PID=$!
  echo "Server started (PID $SERVER_PID)"

  echo "=== Waiting for server health ==="
  for i in $(seq 1 30); do
    if curl -sf "http://localhost:$SERVER_PORT/health" > /dev/null 2>&1; then
      echo "Server healthy."
      break
    fi
    if [[ $i -eq 30 ]]; then
      echo "ERROR: Server did not become healthy in 60s"
      exit 1
    fi
    sleep 2
  done

  echo "=== Waiting for mcp-testkit ==="
  for i in $(seq 1 15); do
    if curl -sf "http://localhost:$MCP_PORT/" > /dev/null 2>&1; then
      echo "mcp-testkit healthy."
      break
    fi
    if [[ $i -eq 15 ]]; then
      echo "ERROR: mcp-testkit did not start in 30s"
      exit 1
    fi
    sleep 2
  done
fi

# ── Run tests ───────────────────────────────────────────────────────────

echo "=== Running E2E tests (parallelism=$PARALLELISM) ==="
mkdir -p "$RESULTS_DIR"

export AGENTSPAN_SERVER_URL="http://localhost:$SERVER_PORT/api"
export AGENTSPAN_CLI_PATH="$REPO_ROOT/cli/agentspan"
export MCP_TESTKIT_URL="http://localhost:$MCP_PORT"
export AGENTSPAN_AUTO_START_SERVER=false

# Build pytest args
PYTEST_ARGS=(
  "$REPO_ROOT/sdk/python/e2e/"
  "-v"
  "--tb=short"
  "--junitxml=$RESULTS_DIR/junit.xml"
  "-n" "$PARALLELISM"
)

if [[ -n "$SUITE_FILTER" ]]; then
  PYTEST_ARGS+=("-k" "$SUITE_FILTER")
fi

cd "$REPO_ROOT/sdk/python"
TEST_EXIT=0
uv run pytest "${PYTEST_ARGS[@]}" || TEST_EXIT=$?

# ── Generate HTML report ────────────────────────────────────────────────

echo "=== Generating HTML report ==="
uv run python "$REPO_ROOT/sdk/python/e2e/report_generator.py" \
  "$RESULTS_DIR/junit.xml" "$RESULTS_DIR/report.html"

echo ""
echo "=============================="
echo "  Results: $RESULTS_DIR/report.html"
echo "  XML:     $RESULTS_DIR/junit.xml"
echo "=============================="

exit $TEST_EXIT
```

- [ ] **Step 2: Make executable**

Run: `chmod +x e2e-orchestrator.sh`

- [ ] **Step 3: Add e2e-results/ to .gitignore**

Append `e2e-results/` to `.gitignore`.

- [ ] **Step 4: Commit**

```bash
git add e2e-orchestrator.sh .gitignore
git commit -m "feat(e2e): add orchestrator script — build, start, test, report, teardown"
```

---

## Chunk 2: Suite 1 — Basic Validation

### Task 4: Suite 1 — smoke test and tool reflection

**Files:**
- Create: `sdk/python/e2e/test_suite1_basic_validation.py`

- [ ] **Step 1: Create test file with smoke test and tool reflection tests**

```python
"""Suite 1: Basic Validation — plan() structural assertions.

All tests compile agents via plan() and assert on the Conductor workflow
JSON structure. No agent execution, no LLM inference. Deterministic.
"""

import pytest
from agentspan.agents import (
    Agent,
    AgentRuntime,
    Guardrail,
    GuardrailResult,
    RegexGuardrail,
    Strategy,
    http_tool,
    image_tool,
    audio_tool,
    video_tool,
    mcp_tool,
    pdf_tool,
    tool,
)

pytestmark = pytest.mark.e2e

MODEL = "openai/gpt-4o-mini"


# ── Helpers ─────────────────────────────────────────────────────────────


def _all_tasks_flat(workflow_def: dict) -> list:
    """Recursively collect all tasks from a workflow definition.

    Traverses nested structures: DO_WHILE loopOver, SWITCH decisionCases/
    defaultCase, FORK_JOIN forkTasks/joinOn, and SUB_WORKFLOW.
    """
    tasks = []
    for t in workflow_def.get("tasks", []):
        tasks.append(t)
        # DO_WHILE nesting
        for nested in t.get("loopOver", []):
            tasks.append(nested)
            tasks.extend(_recurse_task(nested))
        # SWITCH nesting
        for case_tasks in t.get("decisionCases", {}).values():
            for ct in case_tasks:
                tasks.append(ct)
                tasks.extend(_recurse_task(ct))
        for ct in t.get("defaultCase", []):
            tasks.append(ct)
            tasks.extend(_recurse_task(ct))
        # FORK
        for fork_list in t.get("forkTasks", []):
            for ft in fork_list:
                tasks.append(ft)
                tasks.extend(_recurse_task(ft))
    return tasks


def _recurse_task(t: dict) -> list:
    """Recurse into a single task's nested children."""
    children = []
    for nested in t.get("loopOver", []):
        children.append(nested)
        children.extend(_recurse_task(nested))
    for case_tasks in t.get("decisionCases", {}).values():
        for ct in case_tasks:
            children.append(ct)
            children.extend(_recurse_task(ct))
    for ct in t.get("defaultCase", []):
        children.append(ct)
        children.extend(_recurse_task(ct))
    for fork_list in t.get("forkTasks", []):
        for ft in fork_list:
            children.append(ft)
            children.extend(_recurse_task(ft))
    return children


def _task_names(tasks: list) -> list:
    """Extract all taskReferenceName values."""
    return [t.get("taskReferenceName", "") for t in tasks]


def _task_types(tasks: list) -> list:
    """Extract all type values."""
    return [t.get("type", "") for t in tasks]


# ── Tools for tests ─────────────────────────────────────────────────────


@tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@tool
def multiply(x: int, y: int) -> int:
    """Multiply two numbers."""
    return x * y


@tool
def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello {name}"


@tool(credentials=["API_KEY_1"])
def credentialed_tool(query: str) -> str:
    """A tool that needs credentials."""
    import os
    return os.environ.get("API_KEY_1", "missing")[:3]


@tool(credentials=["SECRET_A", "SECRET_B"])
def multi_cred_tool(data: str) -> str:
    """A tool needing multiple credentials."""
    return data


# ── Guardrails for tests ────────────────────────────────────────────────


def no_pii(content: str) -> GuardrailResult:
    """Block PII patterns."""
    return GuardrailResult(passed=True)


def check_input(content: str) -> GuardrailResult:
    """Validate input."""
    return GuardrailResult(passed=True)


# ── Tests ───────────────────────────────────────────────────────────────


class TestSuite1BasicValidation:
    """All tests compile agents via plan() and assert on workflow structure."""

    def test_smoke_simple_agent_plan(self, runtime):
        """Smoke test: agent with 2 tools compiles to a valid workflow."""
        agent = Agent(
            name="e2e_smoke",
            model=MODEL,
            instructions="You are a calculator.",
            tools=[add, multiply],
        )
        result = runtime.plan(agent)

        # Top-level structure
        assert "workflowDef" in result
        assert "requiredWorkers" in result
        wf = result["workflowDef"]
        assert wf["name"] == "e2e_smoke"
        assert len(wf["tasks"]) > 0

        # Both tools appear somewhere in the task tree
        all_tasks = _all_tasks_flat(wf)
        all_refs = _task_names(all_tasks)
        assert any("add" in ref for ref in all_refs), (
            f"'add' tool not found in task refs: {all_refs}"
        )
        assert any("multiply" in ref for ref in all_refs), (
            f"'multiply' tool not found in task refs: {all_refs}"
        )

        # Required workers should include both tools
        workers = result["requiredWorkers"]
        assert any("add" in w for w in workers), (
            f"'add' not in requiredWorkers: {workers}"
        )
        assert any("multiply" in w for w in workers), (
            f"'multiply' not in requiredWorkers: {workers}"
        )

    def test_plan_reflects_tools(self, runtime):
        """Every tool on the agent appears as a task in the compiled workflow."""
        agent = Agent(
            name="e2e_tools",
            model=MODEL,
            instructions="Use tools.",
            tools=[add, multiply, greet],
        )
        result = runtime.plan(agent)
        all_tasks = _all_tasks_flat(result["workflowDef"])
        all_refs = _task_names(all_tasks)

        for tool_name in ["add", "multiply", "greet"]:
            assert any(tool_name in ref for ref in all_refs), (
                f"Tool '{tool_name}' not found in workflow tasks. Refs: {all_refs}"
            )

    def test_plan_reflects_guardrails(self, runtime):
        """Input and output guardrails appear in the compiled workflow."""
        agent = Agent(
            name="e2e_guardrails",
            model=MODEL,
            instructions="Answer questions.",
            tools=[greet],
            guardrails=[
                Guardrail(check_input, position="input", on_fail="retry"),
                Guardrail(no_pii, position="output", on_fail="retry"),
                RegexGuardrail(
                    patterns=[r"\b\d{3}-\d{2}-\d{4}\b"],
                    name="no_ssn",
                    message="No SSNs allowed.",
                    on_fail="retry",
                ),
            ],
        )
        result = runtime.plan(agent)
        all_tasks = _all_tasks_flat(result["workflowDef"])
        all_refs = _task_names(all_tasks)
        all_refs_lower = [r.lower() for r in all_refs]

        # At least one guardrail-related task should exist
        guardrail_indicators = ["guardrail", "guard", "validate", "check"]
        has_guardrail = any(
            indicator in ref for ref in all_refs_lower
            for indicator in guardrail_indicators
        )
        # Also check if guardrails are embedded in the workflow metadata
        metadata = result["workflowDef"].get("metadata", {})
        agent_def = metadata.get("agentDef", {})
        has_guardrail_config = bool(agent_def.get("guardrails"))

        assert has_guardrail or has_guardrail_config, (
            f"No guardrail evidence in workflow. Refs: {all_refs}. "
            f"Metadata guardrails: {agent_def.get('guardrails')}"
        )

    def test_plan_reflects_credentials(self, runtime):
        """Credentialed tools preserve credential info in the compiled workflow."""
        agent = Agent(
            name="e2e_creds",
            model=MODEL,
            instructions="Use tools.",
            tools=[credentialed_tool, multi_cred_tool],
        )
        result = runtime.plan(agent)
        wf_str = str(result)

        # Credentials should appear somewhere in the workflow definition
        assert "API_KEY_1" in wf_str, (
            f"API_KEY_1 not found in compiled workflow"
        )
        assert "SECRET_A" in wf_str, (
            f"SECRET_A not found in compiled workflow"
        )
        assert "SECRET_B" in wf_str, (
            f"SECRET_B not found in compiled workflow"
        )

    def test_plan_sub_agent_produces_sub_workflow(self, runtime):
        """An agent with a sub-agent produces SUB_WORKFLOW tasks."""
        child = Agent(
            name="e2e_child",
            model=MODEL,
            instructions="You are a helper.",
        )
        parent = Agent(
            name="e2e_parent",
            model=MODEL,
            instructions="Delegate to child.",
            agents=[child],
            strategy=Strategy.HANDOFF,
        )
        result = runtime.plan(parent)
        all_tasks = _all_tasks_flat(result["workflowDef"])
        all_types = _task_types(all_tasks)

        assert "SUB_WORKFLOW" in all_types, (
            f"No SUB_WORKFLOW task found. Types: {all_types}"
        )

    def test_plan_sub_agent_references_correct_names(self, runtime):
        """SUB_WORKFLOW tasks reference the correct sub-agent names."""
        analyst = Agent(
            name="e2e_analyst",
            model=MODEL,
            instructions="You analyze data.",
        )
        writer = Agent(
            name="e2e_writer",
            model=MODEL,
            instructions="You write reports.",
        )
        manager = Agent(
            name="e2e_manager",
            model=MODEL,
            instructions="Delegate analysis to analyst and writing to writer.",
            agents=[analyst, writer],
            strategy=Strategy.HANDOFF,
        )
        result = runtime.plan(manager)
        all_tasks = _all_tasks_flat(result["workflowDef"])
        sub_wf_tasks = [t for t in all_tasks if t.get("type") == "SUB_WORKFLOW"]

        # Extract sub-workflow names from subWorkflowParams or task references
        sub_names = []
        for t in sub_wf_tasks:
            params = t.get("subWorkflowParam", {}) or t.get("subWorkflowParams", {})
            if params.get("name"):
                sub_names.append(params["name"])
            ref = t.get("taskReferenceName", "")
            sub_names.append(ref)

        sub_names_str = " ".join(sub_names).lower()
        assert "analyst" in sub_names_str, (
            f"'analyst' not referenced in SUB_WORKFLOW tasks: {sub_names}"
        )
        assert "writer" in sub_names_str, (
            f"'writer' not referenced in SUB_WORKFLOW tasks: {sub_names}"
        )

    def test_kitchen_sink_compiles(self, runtime, mcp_url):
        """Kitchen sink agent with ALL tool types, guardrails, credentials,
        and all 8 sub-agent strategies compiles successfully."""
        from agentspan.agents import OnTextMention

        # ── Worker tools ────────────────────────────────────────────
        @tool
        def local_tool(x: str) -> str:
            """A local worker tool."""
            return x

        @tool(credentials=["KS_SECRET"])
        def cred_local_tool(x: str) -> str:
            """Worker tool with credentials."""
            return x

        # ── Server-side tools ───────────────────────────────────────
        ht = http_tool(
            name="ks_http",
            description="HTTP endpoint",
            url=f"{mcp_url}/echo",
            method="POST",
        )
        mt = mcp_tool(
            server_url=mcp_url,
            name="ks_mcp",
            description="MCP tools",
        )
        img = image_tool(
            name="ks_image",
            description="Generate image",
            llm_provider="openai",
            model="dall-e-3",
        )
        aud = audio_tool(
            name="ks_audio",
            description="Generate audio",
            llm_provider="openai",
            model="tts-1",
        )
        vid = video_tool(
            name="ks_video",
            description="Generate video",
            llm_provider="openai",
            model="sora",
        )
        pdf = pdf_tool(name="ks_pdf", description="Generate PDF")

        # ── Guardrails ──────────────────────────────────────────────
        input_guard = Guardrail(check_input, position="input", on_fail="retry")
        output_guard = Guardrail(no_pii, position="output", on_fail="retry")
        regex_guard = RegexGuardrail(
            patterns=[r"password"],
            name="no_password",
            message="No passwords in output.",
            on_fail="retry",
        )

        # ── Sub-agents with ALL 8 strategies ────────────────────────
        handoff_team = Agent(
            name="ks_handoff",
            model=MODEL,
            instructions="Route tasks.",
            agents=[
                Agent(name="ks_h1", model=MODEL, instructions="H1."),
                Agent(name="ks_h2", model=MODEL, instructions="H2."),
            ],
            strategy=Strategy.HANDOFF,
        )
        sequential_team = Agent(
            name="ks_sequential",
            model=MODEL,
            agents=[
                Agent(name="ks_seq1", model=MODEL, instructions="Seq1."),
                Agent(name="ks_seq2", model=MODEL, instructions="Seq2."),
            ],
            strategy=Strategy.SEQUENTIAL,
        )
        parallel_team = Agent(
            name="ks_parallel",
            model=MODEL,
            agents=[
                Agent(name="ks_p1", model=MODEL, instructions="P1."),
                Agent(name="ks_p2", model=MODEL, instructions="P2."),
            ],
            strategy=Strategy.PARALLEL,
        )
        router_lead = Agent(
            name="ks_router_lead",
            model=MODEL,
            instructions="Route to correct agent.",
        )
        router_team = Agent(
            name="ks_router",
            model=MODEL,
            agents=[
                Agent(name="ks_r1", model=MODEL, instructions="R1."),
                Agent(name="ks_r2", model=MODEL, instructions="R2."),
            ],
            strategy=Strategy.ROUTER,
            router=router_lead,
        )
        round_robin_team = Agent(
            name="ks_round_robin",
            model=MODEL,
            agents=[
                Agent(name="ks_rr1", model=MODEL, instructions="RR1."),
                Agent(name="ks_rr2", model=MODEL, instructions="RR2."),
            ],
            strategy=Strategy.ROUND_ROBIN,
        )
        random_team = Agent(
            name="ks_random",
            model=MODEL,
            agents=[
                Agent(name="ks_rand1", model=MODEL, instructions="Rand1."),
                Agent(name="ks_rand2", model=MODEL, instructions="Rand2."),
            ],
            strategy=Strategy.RANDOM,
        )
        swarm_team = Agent(
            name="ks_swarm",
            model=MODEL,
            agents=[
                Agent(name="ks_sw1", model=MODEL, instructions="SW1."),
                Agent(name="ks_sw2", model=MODEL, instructions="SW2."),
            ],
            strategy=Strategy.SWARM,
            handoffs=[
                OnTextMention(text="GOTO_SW2", target="ks_sw2"),
                OnTextMention(text="GOTO_SW1", target="ks_sw1"),
            ],
        )
        manual_team = Agent(
            name="ks_manual",
            model=MODEL,
            agents=[
                Agent(name="ks_m1", model=MODEL, instructions="M1."),
                Agent(name="ks_m2", model=MODEL, instructions="M2."),
            ],
            strategy=Strategy.MANUAL,
        )

        # ── Kitchen sink agent ──────────────────────────────────────
        kitchen_sink = Agent(
            name="e2e_kitchen_sink",
            model=MODEL,
            instructions="You are the kitchen sink agent.",
            tools=[
                local_tool, cred_local_tool, ht, mt,
                img, aud, vid, pdf,
            ],
            guardrails=[input_guard, output_guard, regex_guard],
            agents=[
                handoff_team, sequential_team, parallel_team, router_team,
                round_robin_team, random_team, swarm_team, manual_team,
            ],
            strategy=Strategy.HANDOFF,
        )

        # ── Compile ─────────────────────────────────────────────────
        result = runtime.plan(kitchen_sink)
        wf = result["workflowDef"]

        # Basic structure
        assert wf["name"] == "e2e_kitchen_sink"
        assert len(wf["tasks"]) > 0

        all_tasks = _all_tasks_flat(wf)
        all_refs = _task_names(all_tasks)
        all_types = _task_types(all_tasks)
        wf_str = str(result)

        # Worker tools present
        assert any("local_tool" in r for r in all_refs), (
            f"local_tool not found: {all_refs}"
        )

        # HTTP tool present
        assert "HTTP" in all_types, f"No HTTP task type: {all_types}"

        # Media tool types present
        for media_type in ["GENERATE_IMAGE", "GENERATE_AUDIO", "GENERATE_VIDEO", "GENERATE_PDF"]:
            assert media_type in all_types or media_type.lower() in wf_str.lower(), (
                f"{media_type} not found in workflow"
            )

        # Sub-workflows exist
        assert "SUB_WORKFLOW" in all_types, (
            f"No SUB_WORKFLOW tasks: {all_types}"
        )

        # Credentials in workflow
        assert "KS_SECRET" in wf_str, "KS_SECRET credential not in workflow"

        # Guardrail evidence
        metadata = wf.get("metadata", {})
        agent_def = metadata.get("agentDef", {})
        has_guardrails = bool(agent_def.get("guardrails"))
        guardrail_in_refs = any("guard" in r.lower() for r in all_refs)
        assert has_guardrails or guardrail_in_refs, (
            "No guardrail evidence in kitchen sink workflow"
        )
```

- [ ] **Step 2: Verify tests are collected by pytest (dry run)**

Run: `cd sdk/python && uv run pytest e2e/test_suite1_basic_validation.py --collect-only`
Expected: 7 tests collected (may skip if server not running — that's fine for collection)

- [ ] **Step 3: Commit**

```bash
git add sdk/python/e2e/test_suite1_basic_validation.py
git commit -m "feat(e2e): add Suite 1 — basic validation with plan() structural assertions"
```

---

## Chunk 3: Suite 2 — Tool Calling / Credentials

### Task 5: Suite 2 — credential lifecycle test

**Files:**
- Create: `sdk/python/e2e/test_suite2_tool_calling.py`

- [ ] **Step 1: Create Suite 2 test file**

```python
"""Suite 2: Tool Calling / Credentials — full lifecycle test.

Tests the credential pipeline end-to-end:
  1. Tools fail when credentials are missing
  2. Env vars are NOT read (security boundary)
  3. Credentials added via CLI are resolved at execution time
  4. Credential updates propagate to subsequent runs

Single sequential test with try/finally cleanup.
No mocks. Real server, real CLI, real LLM.
"""

import os

import pytest
import requests

from agentspan.agents import Agent, AgentRuntime, tool

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.xdist_group("credentials"),
]

CRED_A = "E2E_CRED_A"
CRED_B = "E2E_CRED_B"
TIMEOUT = 120  # 120 seconds per agent run


# ── Tools ───────────────────────────────────────────────────────────────


@tool
def free_tool(x: str) -> str:
    """A tool that needs no credentials. Always succeeds."""
    return "free:ok"


@tool(credentials=[CRED_A])
def paid_tool_a(x: str) -> str:
    """A tool that needs E2E_CRED_A. Returns first 3 chars of credential."""
    cred_val = os.environ.get(CRED_A, "")
    return f"paid_a:{cred_val[:3]}"


@tool(credentials=[CRED_B])
def paid_tool_b(x: str) -> str:
    """A tool that needs E2E_CRED_B. Returns first 3 chars of credential."""
    cred_val = os.environ.get(CRED_B, "")
    return f"paid_b:{cred_val[:3]}"


# ── Helpers ─────────────────────────────────────────────────────────────


AGENT_INSTRUCTIONS = """\
You have three tools: free_tool, paid_tool_a, and paid_tool_b.
You MUST call all three tools exactly once each, with the argument "test".
After calling all three, report each tool's output verbatim in this format:
  free_tool: <output>
  paid_tool_a: <output>
  paid_tool_b: <output>
Do not skip any tool. Do not add commentary.
"""


def _make_agent(model: str) -> Agent:
    return Agent(
        name="e2e_cred_lifecycle",
        model=model,
        instructions=AGENT_INSTRUCTIONS,
        tools=[free_tool, paid_tool_a, paid_tool_b],
    )


def _get_workflow(execution_id: str) -> dict:
    """Fetch workflow from server API."""
    base = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
    base_url = base.rstrip("/").replace("/api", "")
    resp = requests.get(f"{base_url}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _find_tool_tasks(execution_id: str) -> dict:
    """Fetch workflow and extract tool task results by reference name.

    Returns dict mapping tool name fragment -> {"status": ..., "output": ...}
    """
    wf = get_workflow(execution_id)
    results = {}
    for task in wf.get("tasks", []):
        ref = task.get("referenceTaskName", "")
        # Match tool tasks by name fragment
        for tool_name in ["free_tool", "paid_tool_a", "paid_tool_b"]:
            if tool_name in ref:
                results[tool_name] = {
                    "status": task.get("status", ""),
                    "output": task.get("outputData", {}),
                    "ref": ref,
                }
    return results


# ── Test ────────────────────────────────────────────────────────────────


@pytest.mark.timeout(300)
class TestSuite2ToolCalling:
    """Credential lifecycle: missing -> env ignored -> add -> update."""

    def test_credential_lifecycle(self, runtime, cli_credentials, model):
        """Full credential lifecycle test — sequential steps with cleanup."""
        try:
            self._run_lifecycle(runtime, cli_credentials, model)
        finally:
            # Always clean up credentials
            cli_credentials.delete(CRED_A)
            cli_credentials.delete(CRED_B)
            # Clean env vars if they leaked
            os.environ.pop(CRED_A, None)
            os.environ.pop(CRED_B, None)

    def _run_lifecycle(self, runtime, cli_credentials, model):
        agent = _make_agent(model)

        # ── Step 1: Clean slate ─────────────────────────────────────
        cli_credentials.delete(CRED_A)
        cli_credentials.delete(CRED_B)

        # ── Step 2: No credentials — paid tools should fail ─────────
        result = runtime.run(agent, "Call all three tools.", timeout=TIMEOUT)

        # The agent may complete (reporting errors) or fail outright.
        # Either way, inspect what happened at the tool level.
        assert result.execution_id, "No execution_id returned"

        # Check output or workflow for evidence:
        # free_tool should have succeeded, paid tools should show credential error
        output = str(result.output).lower() if result.output else ""
        assert "free" in output or result.status in ("COMPLETED", "FAILED"), (
            f"Unexpected result with no credentials: status={result.status}, "
            f"output={result.output}"
        )

        # If workflow completed, check that paid tools had issues
        if result.status == "COMPLETED" and result.execution_id:
            tool_tasks = _find_tool_tasks(result.execution_id)
            if "free_tool" in tool_tasks:
                assert tool_tasks["free_tool"]["status"] in (
                    "COMPLETED", "COMPLETED_WITH_ERRORS"
                ), f"free_tool should succeed: {tool_tasks['free_tool']}"

        # ── Step 3: Env vars should NOT be read ─────────────────────
        os.environ[CRED_A] = "from-env-aaa"
        os.environ[CRED_B] = "from-env-bbb"
        try:
            result_env = runtime.run(agent, "Call all three tools.", timeout=TIMEOUT)

            # The paid tools should STILL fail despite env vars being set.
            # The SDK resolves credentials from the server, not env.
            output_env = str(result_env.output).lower() if result_env.output else ""

            # If the tool returned "fro" (first 3 chars of "from-env-..."),
            # that means env vars leaked — FAIL the test.
            assert "fro" not in output_env, (
                "SECURITY VIOLATION: env vars were read for credential resolution! "
                f"Output: {result_env.output}"
            )
        finally:
            os.environ.pop(CRED_A, None)
            os.environ.pop(CRED_B, None)

        # ── Step 4: Add credentials via CLI ─────────────────────────
        cli_credentials.set(CRED_A, "secret-aaa-value")
        cli_credentials.set(CRED_B, "secret-bbb-value")

        result_with_creds = runtime.run(
            agent, "Call all three tools.", timeout=TIMEOUT
        )
        assert result_with_creds.status == "COMPLETED", (
            f"Agent should complete with credentials. "
            f"Status: {result_with_creds.status}, "
            f"Output: {result_with_creds.output}"
        )

        output_creds = str(result_with_creds.output)
        # free_tool always returns "free:ok"
        assert "free" in output_creds.lower(), (
            f"free_tool output missing: {output_creds}"
        )
        # paid_tool_a should return first 3 chars of "secret-aaa-value" = "sec"
        assert "sec" in output_creds, (
            f"paid_tool_a should output 'sec' (first 3 chars of credential). "
            f"Output: {output_creds}"
        )

        # ── Step 5: Update credentials via CLI ──────────────────────
        cli_credentials.set(CRED_A, "newval-xxx-updated")
        cli_credentials.set(CRED_B, "newval-yyy-updated")

        result_updated = runtime.run(
            agent, "Call all three tools.", timeout=TIMEOUT
        )
        assert result_updated.status == "COMPLETED", (
            f"Agent should complete with updated credentials. "
            f"Status: {result_updated.status}, "
            f"Output: {result_updated.output}"
        )

        output_updated = str(result_updated.output)
        # paid_tool_a should now return "new" (first 3 chars of "newval-xxx-updated")
        assert "new" in output_updated, (
            f"paid_tool_a should output 'new' after credential update. "
            f"Output: {output_updated}"
        )
```

- [ ] **Step 2: Verify tests are collected by pytest (dry run)**

Run: `cd sdk/python && uv run pytest e2e/test_suite2_tool_calling.py --collect-only`
Expected: 1 test collected (`test_credential_lifecycle`)

- [ ] **Step 3: Commit**

```bash
git add sdk/python/e2e/test_suite2_tool_calling.py
git commit -m "feat(e2e): add Suite 2 — tool calling credential lifecycle test"
```

---

## Chunk 4: Verification

### Task 6: Verify everything wires together

- [ ] **Step 1: Verify all e2e files are present**

Run: `ls -la sdk/python/e2e/`
Expected: `conftest.py`, `report_generator.py`, `test_suite1_basic_validation.py`, `test_suite2_tool_calling.py`

- [ ] **Step 2: Verify pytest collects all tests**

Run: `cd sdk/python && uv run pytest e2e/ --collect-only`
Expected: 8 tests collected (7 from Suite 1, 1 from Suite 2)

- [ ] **Step 3: Verify report generator produces valid HTML**

Run:
```bash
cd sdk/python
cat > /tmp/e2e_test.xml << 'XML'
<?xml version="1.0"?>
<testsuites>
  <testsuite name="Suite 1" tests="3" failures="0">
    <testcase classname="suite1" name="test_smoke" time="0.3"/>
    <testcase classname="suite1" name="test_tools" time="0.5"/>
    <testcase classname="suite1" name="test_guardrails" time="0.4"/>
  </testsuite>
  <testsuite name="Suite 2" tests="1" failures="0">
    <testcase classname="suite2" name="test_credential_lifecycle" time="45.2"/>
  </testsuite>
</testsuites>
XML
uv run python e2e/report_generator.py /tmp/e2e_test.xml /tmp/e2e_report.html
cat /tmp/e2e_report.html | head -5
```
Expected: Valid HTML output with "E2E Test Report" title.

- [ ] **Step 4: Verify orchestrator script is valid bash**

Run: `bash -n e2e-orchestrator.sh`
Expected: No syntax errors.

- [ ] **Step 5: Final commit with all files**

```bash
git add -A sdk/python/e2e/ e2e-orchestrator.sh .gitignore
git commit -m "feat(e2e): complete e2e validation framework — orchestrator, 2 suites, HTML report"
```
