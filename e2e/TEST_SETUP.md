# E2E Test Setup — Python & TypeScript SDKs

Both SDKs have 1:1 matching test suites with identical file naming, test coverage, and algorithmic validation.

## Prerequisites

- Agentspan server running (default: `http://localhost:6767`)
- Agentspan CLI built (`cli/agentspan`)
- Python SDK installed (`uv sync --extra testing`)
- TypeScript SDK built (`cd sdk/typescript && npm install && npm run build`)
- `mcp-testkit` running (default: `http://localhost:3001`, needed for Suites 1, 4, 5)
- Docker running (needed for Suite 10 Docker tests, skips if unavailable)
- LLM API keys:
  - `OPENAI_API_KEY` — required for agent execution (Suites 2–10)
  - `ANTHROPIC_API_KEY` — required for LLM-as-judge (Suite 1, default judge model is Claude Sonnet)
  - `GITHUB_TOKEN` — required for Suite 3 CLI tools test (gh CLI authentication)
  - `GOOGLE_AI_API_KEY` — optional, for Gemini image test in Suite 7
- `gh` CLI installed (only needed for Suite 3)

**Troubleshooting:** If you get `AEADBadTagException` on startup, the DB was encrypted with a different key. Delete the stale DB and restart:
```bash
rm -f agent-runtime.db* ~/.agentspan/master.key
```

## Rules

1. When adding e2e make sure not to use LLM for validation unless we are doing this for judging quality/output/evals
2. Write a test, then validate that the test is actually valid. Make it fail, assert that it did fail so we know it's correct (counterfactual testing)
3. All validation must be algorithmic and deterministic — no LLM output parsing
4. Python and TypeScript must have 1:1 parity including file names

## Test Suite Parity

Both SDKs implement identical test suites:

| Suite | File (Python) | File (TypeScript) | Tests | Duration |
|-------|--------------|-------------------|-------|----------|
| 1 — Basic Validation | `test_suite1_basic_validation.py` | `test_suite1_basic_validation.test.ts` | 8 | ~1s |
| 2 — Tool Calling | `test_suite2_tool_calling.py` | `test_suite2_tool_calling.test.ts` | 1 | ~3 min |
| 3 — CLI Tools | `test_suite3_cli_tools.py` | `test_suite3_cli_tools.test.ts` | 1 | skips w/o GITHUB_TOKEN |
| 4 — MCP Tools | `test_suite4_mcp_tools.py` | `test_suite4_mcp_tools.test.ts` | 1 | ~30s |
| 5 — HTTP Tools | `test_suite5_http_tools.py` | `test_suite5_http_tools.test.ts` | 2 | ~20s |
| 6 — PDF Tools | `test_suite6_pdf_tools.py` | `test_suite6_pdf_tools.test.ts` | 1 | ~10s |
| 7 — Media Tools | `test_suite7_media_tools.py` | `test_suite7_media_tools.test.ts` | 4 | ~2 min |
| 8 — Guardrails | `test_suite8_guardrails.py` | `test_suite8_guardrails.test.ts` | 7-8 | ~30s |
| 9 — Handoffs | `test_suite9_handoffs.py` | `test_suite9_handoffs.test.ts` | 8 | ~2 min |
| 10 — Code Execution | `test_suite10_code_execution.py` | `test_suite10_code_execution.test.ts` | 9 | ~40s |

## Running

### Python

```bash
# Full automated run (build + start services + test + report)
./e2e/orchestrator.sh

# Manual run (services already running)
cd sdk/python
export AGENTSPAN_SERVER_URL=http://localhost:6767/api
export AGENTSPAN_CLI_PATH=../../cli/agentspan

uv run pytest e2e/ -v                                    # all suites
uv run pytest e2e/test_suite1_basic_validation.py -v      # suite 1 only
uv run pytest e2e/test_suite2_tool_calling.py -v          # suite 2 only
uv run pytest e2e/test_suite3_cli_tools.py -v             # suite 3 only
uv run pytest e2e/test_suite4_mcp_tools.py -v             # suite 4 only
uv run pytest e2e/test_suite5_http_tools.py -v            # suite 5 only
uv run pytest e2e/test_suite6_pdf_tools.py -v             # suite 6 only
uv run pytest e2e/test_suite7_media_tools.py -v           # suite 7 only
uv run pytest e2e/test_suite8_guardrails.py -v            # suite 8 only
uv run pytest e2e/test_suite9_handoffs.py -v              # suite 9 only
uv run pytest e2e/test_suite10_code_execution.py -v       # suite 10 only
```

### TypeScript

```bash
# Manual run (server already running)
cd sdk/typescript
export AGENTSPAN_SERVER_URL=http://localhost:6767/api
export AGENTSPAN_CLI_PATH=../../cli/agentspan

npx vitest run tests/e2e/                                          # all suites
npx vitest run tests/e2e/test_suite1_basic_validation.test.ts      # suite 1 only
npx vitest run tests/e2e/test_suite2_tool_calling.test.ts          # suite 2 only
npx vitest run tests/e2e/test_suite3_cli_tools.test.ts             # suite 3 only
npx vitest run tests/e2e/test_suite4_mcp_tools.test.ts             # suite 4 only
npx vitest run tests/e2e/test_suite5_http_tools.test.ts            # suite 5 only
npx vitest run tests/e2e/test_suite6_pdf_tools.test.ts             # suite 6 only
npx vitest run tests/e2e/test_suite7_media_tools.test.ts           # suite 7 only
npx vitest run tests/e2e/test_suite8_guardrails.test.ts            # suite 8 only
npx vitest run tests/e2e/test_suite9_handoffs.test.ts              # suite 9 only
npx vitest run tests/e2e/test_suite10_code_execution.test.ts       # suite 10 only
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api` | Server API URL |
| `AGENTSPAN_CLI_PATH` | `agentspan` | Path to CLI binary |
| `MCP_TESTKIT_URL` | `http://localhost:3001` | mcp-testkit URL for HTTP/MCP tool tests |
| `AGENTSPAN_LLM_MODEL` | `openai/gpt-4o-mini` | Model for agent execution |
| `AGENTSPAN_JUDGE_MODEL` | `claude-sonnet-4-20250514` | Model for LLM-as-judge (Suite 1) |
| `ANTHROPIC_API_KEY` | — | Required when judge model is `claude-*` (default) |
| `OPENAI_API_KEY` | — | Required for agent execution and when judge model is `gpt-*` |
| `GITHUB_TOKEN` | — | Required for Suite 3 CLI tools test. Skips if not set. |
| `GOOGLE_AI_API_KEY` | — | Optional, for Gemini image test in Suite 7 |

## Suite Details

### Suite 1: Basic Validation
Compiles agents via `plan()` and asserts on Conductor workflow JSON. No agent execution except the LLM judge test. Validates tools, guardrails, credentials, sub-agents, and all 8 strategy types compile correctly.

### Suite 2: Tool Calling / Credential Lifecycle
Full credential pipeline: missing → env vars ignored → add via CLI → update via CLI. Validates via workflow task data (tool task status + output), not LLM prose.

### Suite 3: CLI Tools / Credential Isolation
CLI command execution with credential isolation and command whitelisting. Validates `ls`/`mktemp` succeed without credentials, `gh` fails without server credential, succeeds after adding. Command whitelist validated via plan compilation + direct `_validate_cli_command()` call.

### Suite 4: MCP Tools
MCP tool discovery (65 tools via MCP protocol), execution (3 deterministic tools), and authenticated access. Manages its own mcp-testkit instance on port 3002.

### Suite 5: HTTP Tools / External OpenAPI
HTTP tool execution via `http_tool()`, OpenAPI spec discovery (65 operations), authenticated access. External OpenAPI test validates `startWorkflow` operation at Orkes Cloud API. Manages its own mcp-testkit instance on port 3003.

### Suite 6: PDF Tools
Markdown → PDF generation via `pdf_tool()`. Validates GENERATE_PDF task completes. Round-trip validation with markitdown (extracts text from PDF, checks key phrases survived).

### Suite 7: Media Tools
Image (OpenAI DALL-E 3 + Gemini Imagen 3), audio (OpenAI TTS-1), and video (OpenAI Sora-2) generation. Plan compilation validates correct model in tool config. Runtime validates GENERATE_* task completes. Video failures skip (Sora is unreliable).

### Suite 8: Guardrails
Compilation: all guardrail types (regex block/allow, custom function, LLM) with correct properties. Runtime: tool input raise (SQL injection), tool output regex retry (email blocked), agent output secrets blocked, max_retries escalation (always-fail → FAILED).

### Suite 9: Agent Handoffs
All 8 multi-agent strategies compile correctly. Runtime: sequential (both sub-workflows complete in order), parallel (FORK task + both complete), handoff (LLM delegates), router (correct agent selected), swarm (OnTextMention triggers handoff), pipe operator (>> / .pipe()). All validated via SUB_WORKFLOW task status in workflow data.

### Suite 10: Code Execution
Compilation: `codeExecution` config in plan, tool naming avoids collisions. Runtime: local Python (42*73=3066), local Bash (17+29=46), language restriction (plan-only — bash not in allowedLanguages), timeout (maxTurns=2, 3s executor timeout), Docker Python (container execution), Docker network disabled (connection error). Jupyter stateful (variable persists across calls, skips if not installed).

## Reports

After running:
- **Python**: `e2e-results/report.html` (generated by `e2e/report_generator.py`)
- **TypeScript**: `e2e-results/report-ts.html` (generated by `tests/e2e/generate-report.ts`)

Both use the same dark-themed format with collapsible suites, error summaries, file:line locations, and full tracebacks.

## CI

Both e2e jobs in `.github/workflows/ci.yml`:
- Build CLI + install mcp-testkit + start services
- Run existing e2e tests, then new suites 1-10
- Generate HTML reports (uploaded as artifacts, 14-day retention)
- 45-minute timeout per job
