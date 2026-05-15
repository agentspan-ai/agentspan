# E2E Validation Framework — Design Spec

## Overview

Per-SDK end-to-end validation of agentspan features using real agents, real server, real services. No mocks. Starting with Python SDK.

## Components

### 1. Orchestrator (`e2e-orchestrator.sh`)

Standalone shell script at repo root. Responsibilities:

1. **Build**: server JAR (`./gradlew bootJar -x test`), CLI binary (`go build -o agentspan .`), Python SDK (`uv sync --extra dev`)
2. **Install mcp-testkit**: `pip install mcp-testkit` (not a SDK dependency — test infrastructure only)
3. **Start services**: mcp-testkit (`mcp-testkit --transport http`), agentspan server (`java -jar ...`)
4. **Health check**: poll both services until ready
5. **Run tests**: `pytest sdk/python/e2e/ -n <parallelism> --junitxml=...`
6. **Generate HTML report**: post-process junit XML into styled HTML
7. **Teardown**: kill all background processes (trap-based cleanup)

The orchestrator exports these env vars for the test process:
- `AGENTSPAN_SERVER_URL=http://localhost:6767/api`
- `AGENTSPAN_CLI_PATH=<repo-root>/cli/agentspan` (absolute path to built CLI binary)
- `MCP_TESTKIT_URL=http://localhost:3001`
- `AGENTSPAN_AUTO_START_SERVER=false` (prevent runtime from starting a second server)

Interface:
```bash
./e2e-orchestrator.sh              # defaults: -j 1
./e2e-orchestrator.sh -j 4        # 4 parallel workers
./e2e-orchestrator.sh --suite suite1
./e2e-orchestrator.sh --no-build --no-start  # skip build, services already running
```

Output: `e2e-results/report.html` + `e2e-results/junit.xml`

### 2. Test Suites (`sdk/python/e2e/`)

Brand new folder. Each suite is a separate test file.

#### `conftest.py`

Shared fixtures and configuration:
- `runtime` (module-scoped): `AgentRuntime` instance
- `cli_credentials`: helper class wrapping CLI binary (path from `AGENTSPAN_CLI_PATH` env var) for `set`, `delete`, `list` credential operations
- `server_url`: from `AGENTSPAN_SERVER_URL` or default `http://localhost:6767/api`
- `mcp_testkit_url`: from `MCP_TESTKIT_URL` or default `http://localhost:3001`
- `model`: from `AGENTSPAN_LLM_MODEL` or default `openai/gpt-4o-mini`
- Session-scoped health check fixture (skip all if server not available)
- Sets `AGENTSPAN_AUTO_START_SERVER=false` to prevent auto-start

Parallelism note: Suite 1 tests are independent and safe for parallel execution. Suite 2 mutates server credential state and must run serially. Use `@pytest.mark.xdist_group("credentials")` to isolate Suite 2 into a single worker when using `-n`.

#### Suite 1: Basic Validation (`test_suite1_basic_validation.py`)

All tests use `plan()` — no agent execution, no LLM calls beyond compile endpoint. All assertions are deterministic JSON path checks. Since `plan()` does not invoke the LLM, the `model` value can be any valid format string (e.g., `openai/gpt-4o-mini`); the server validates format only.

If `plan()` itself fails (server returns 4xx/5xx), `AgentRuntime.plan()` raises `AgentAPIError` which propagates as a test failure with the server error message.

| Test | Description |
|------|-------------|
| `test_smoke_simple_agent_plan` | Agent with 2 tools -> plan() succeeds, tasks contain both tool names |
| `test_plan_reflects_tools` | Agent with N tools -> every tool appears as a task in workflow |
| `test_plan_reflects_guardrails` | Agent with input + output guardrails -> guardrail tasks present |
| `test_plan_reflects_credentials` | Agent with credentialed tools -> credential refs in task config |
| `test_plan_sub_agent_produces_sub_workflow` | Agent with sub-agent -> at least one SUB_WORKFLOW task |
| `test_plan_sub_agent_references_correct_names` | Agent with 2 named sub-agents -> SUB_WORKFLOW tasks reference correct names |
| `test_kitchen_sink_compiles` | Agent with ALL tool types, guardrails, credentials, sub-agents (all strategies) -> plan() succeeds, all structural elements present |

Kitchen sink agent includes:
- Tool types: `@tool`, `http_tool`, `mcp_tool`, `image_tool`, `audio_tool`, `video_tool`, `pdf_tool`
- Guardrails: `RegexGuardrail` (output), custom function guardrail (input), custom function guardrail (output)
- Credentials: tools with declared credentials
- Sub-agents: all 8 strategies — HANDOFF, SEQUENTIAL, PARALLEL, ROUTER, ROUND_ROBIN, RANDOM, SWARM, MANUAL

#### Suite 2: Tool Calling / Credentials (`test_suite2_tool_calling.py`)

Single sequential test function with `try/finally` cleanup. Uses real agent execution with LLM. Timeout: 120s per agent run, 300s for the full test.

Tools:
- `free_tool(x: str) -> str`: no credentials, returns `"free:ok"`
- `paid_tool_a(x: str) -> str`: needs `E2E_CRED_A`, returns `f"paid_a:{cred[:3]}"`
- `paid_tool_b(x: str) -> str`: needs `E2E_CRED_B`, returns `f"paid_b:{cred[:3]}"`

Steps:
1. **Clean slate**: delete E2E_CRED_A, E2E_CRED_B via CLI (ignore if not found)
2. **No creds**: run agent -> free_tool succeeds, paid tools fail with credential error. Assert by inspecting workflow tasks via server API (task status FAILED, output contains credential error).
3. **Env var isolation**: set `os.environ["E2E_CRED_A"]` and `E2E_CRED_B`, run agent -> SAME failures (SDK must NOT read env vars). Clean env vars.
4. **Add creds**: `agentspan credentials set E2E_CRED_A secret-aaa`, same for E2E_CRED_B. Run agent -> all 3 succeed. Assert paid_tool_a output contains `"sec"`, paid_tool_b output contains `"sec"`.
5. **Update creds**: `agentspan credentials set E2E_CRED_A newval-xxx`, same for E2E_CRED_B. Run agent -> all 3 succeed. Assert outputs contain `"new"`.
6. **Cleanup** (in `finally`): delete E2E_CRED_A, E2E_CRED_B via CLI.

Agent prompt: explicit instruction to call all three tools and report each tool's output verbatim.

Validation approach for tool results:
- Primary: fetch completed workflow via server REST API (`GET /api/workflow/<execution_id>`), inspect individual task outputs by task name
- Secondary: inspect `result.output` (final agent output) for tool output strings
- For failed tools: check task output contains credential-related error text

### 3. HTML Report (`report_generator.py`)

Post-processing of pytest junit XML into a self-contained HTML file.

Structure:
- Header: timestamp, total duration, pass/fail/skip/error counts
- Per-suite collapsible section
- Each test: name, status (color-coded green/red/yellow), duration
- Failed tests: full error message + traceback in expandable block
- Single-file, no external dependencies (inline CSS)

## Constraints

- No mocks anywhere — real agents, real server, real services
- Credentials managed exclusively via CLI (`agentspan credentials set/delete`)
- All Suite 1 assertions are deterministic (JSON structure checks)
- Suite 2 uses LLM but with explicit prompts to minimize non-determinism
- mcp-testkit provides HTTP and MCP endpoints for tool tests
- Tests use `pytest.mark.e2e` marker
- Suite 2 uses `@pytest.mark.xdist_group("credentials")` for serial execution under parallel mode
- Suite 2 uses `try/finally` for credential cleanup to prevent state leakage on failure

## Directory Layout

```
repo-root/
├── e2e-orchestrator.sh
├── e2e-results/              # gitignored
│   ├── report.html
│   └── junit.xml
└── sdk/python/
    └── e2e/
        ├── conftest.py
        ├── test_suite1_basic_validation.py
        ├── test_suite2_tool_calling.py
        └── report_generator.py   # junit XML -> HTML
```
