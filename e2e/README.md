# E2E Validation

End-to-end tests for agentspan. Real agents, real server, real services. No mocks.

## Quick Start

```bash
# Full run: build everything, start services, run tests, generate report
./e2e/orchestrator.sh

# Run with 4 parallel workers
./e2e/orchestrator.sh -j 4

# Run a specific suite
./e2e/orchestrator.sh --suite suite1
./e2e/orchestrator.sh --suite suite2
```

## Prerequisites

- Java 21 (for server)
- Go 1.23+ (for CLI)
- Python 3.10+ with `uv`
- `mcp-testkit` (`pip install mcp-testkit`)

The orchestrator handles building and starting everything. If you want to skip the build or service startup (e.g., server already running):

```bash
# Skip build, skip service startup
./e2e/orchestrator.sh --no-build --no-start

# Skip build only (services will still start)
./e2e/orchestrator.sh --no-build
```

## Orchestrator Options

| Flag | Default | Description |
|------|---------|-------------|
| `-j`, `--parallelism` | `1` | Number of parallel pytest workers |
| `--suite` | (all) | Run only matching suite (`suite1`, `suite2`) |
| `--no-build` | | Skip building server, CLI, and SDK |
| `--no-start` | | Skip starting server and mcp-testkit |
| `--port` | `6767` | Server port |
| `--mcp-port` | `3001` | mcp-testkit port |

## Environment Variables

Set these when using `--no-start` (services already running):

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api` | Server API URL |
| `AGENTSPAN_CLI_PATH` | `agentspan` | Path to CLI binary |
| `MCP_TESTKIT_URL` | `http://localhost:3001` | mcp-testkit URL |
| `AGENTSPAN_LLM_MODEL` | `openai/gpt-4o-mini` | LLM model for execution tests |

## Output

Results are written to `e2e-results/` (gitignored):

- `e2e-results/report.html` — styled HTML report with pass/fail summary
- `e2e-results/junit.xml` — standard junit XML for CI integration

## Test Suites

### Suite 1: Basic Validation (`sdk/python/e2e/test_suite1_basic_validation.py`)

Compiles agents via `plan()` and asserts on the Conductor workflow JSON. No agent execution, no LLM calls. All assertions are deterministic.

- Smoke test — simple agent with tools compiles
- Tool reflection — every tool appears in workflow tasks
- Guardrail reflection — guardrails appear in compiled workflow
- Credential reflection — credential references preserved
- Sub-agent structure — SUB_WORKFLOW tasks with correct names
- Kitchen sink — all tool types, all 8 strategies, guardrails, credentials

### Suite 2: Tool Calling (`sdk/python/e2e/test_suite2_tool_calling.py`)

Full credential lifecycle with real agent execution:

1. No credentials stored — credentialed tools fail, free tools succeed
2. Env vars set — still fails (SDK must not read env vars)
3. Credentials added via CLI — all tools succeed, output contains credential prefix
4. Credentials updated via CLI — output reflects new values

## Running Tests Manually

If the server and mcp-testkit are already running:

```bash
cd sdk/python

export AGENTSPAN_SERVER_URL=http://localhost:6767/api
export AGENTSPAN_CLI_PATH=../../cli/agentspan
export MCP_TESTKIT_URL=http://localhost:3001

# Run all e2e tests
uv run pytest e2e/ -v

# Run a specific suite
uv run pytest e2e/test_suite1_basic_validation.py -v

# Run with junit output
uv run pytest e2e/ -v --junitxml=../../e2e-results/junit.xml
```

## Adding New Suites

1. Create `sdk/python/e2e/test_suite<N>_<name>.py`
2. Use `pytestmark = pytest.mark.e2e`
3. Use the `runtime`, `model`, `mcp_url`, and `cli_credentials` fixtures from `conftest.py`
4. For tests that mutate server state, add `pytest.mark.xdist_group("<group>")` for parallel safety
