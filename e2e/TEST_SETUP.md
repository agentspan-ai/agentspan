# E2E Test Setup — Python SDK

## Prerequisites

- Agentspan server running (default: `http://localhost:6767`)
- Agentspan CLI built (`cli/agentspan`)
- Python SDK installed (`uv sync --extra testing`)
- `mcp-testkit` running (default: `http://localhost:3001`, only needed for Suite 1 kitchen sink test)
- LLM API keys:
  - `OPENAI_API_KEY` — required for agent execution (Suites 2, 3) and stored in the server's credential store
  - `ANTHROPIC_API_KEY` — required for LLM-as-judge (Suite 1, default judge model is Claude Sonnet)
  - If using OpenAI as the judge instead, only `OPENAI_API_KEY` is needed (set `AGENTSPAN_JUDGE_MODEL=gpt-4o-mini`)
  - `GITHUB_TOKEN` — required for Suite 3 CLI tools test (gh CLI authentication)
- `gh` CLI installed (only needed for Suite 3)

### Server master key

The server encrypts credentials with AES-256-GCM using a master key. **You must set `AGENTSPAN_MASTER_KEY`** before starting the server, otherwise the server auto-generates a key that is lost on restart — causing HTTP 500 on all credential operations.

```bash
# Use a stable key for e2e (the orchestrator sets this automatically)
export AGENTSPAN_MASTER_KEY="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
java -jar server/build/libs/agentspan-runtime.jar --server.port=6767

# If you get AEADBadTagException on startup, the DB was encrypted with a different key.
# Delete the stale DB and restart:
rm -f agent-runtime.db* ~/.agentspan/master.key
```

## Rules of writing the tests
1. When adding e2e make sure not to use LLM for validation unless we are doing this for judging quality/output/evals
2. Write a test, then validate that the test is actually valid. make it fail, assert that it did fail so we know its corect

## Running

```bash
# Full automated run (build + start services + test + report)
./e2e/orchestrator.sh

# Manual run (services already running)
cd sdk/python
export AGENTSPAN_SERVER_URL=http://localhost:6767/api
export AGENTSPAN_CLI_PATH=../../cli/agentspan
export MCP_TESTKIT_URL=http://localhost:3001

uv run pytest e2e/ -v                           # all suites
uv run pytest e2e/test_suite1_basic_validation.py -v  # suite 1 only
uv run pytest e2e/test_suite2_tool_calling.py -v      # suite 2 only
uv run pytest e2e/test_suite3_cli_tools.py -v         # suite 3 only
uv run pytest e2e/test_suite4_mcp_tools.py -v         # suite 4 only
uv run pytest e2e/test_suite5_http_tools.py -v        # suite 5 only
uv run pytest e2e/test_suite6_pdf_tools.py -v         # suite 6 only
uv run pytest e2e/test_suite7_media_tools.py -v       # suite 7 only
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api` | Server API URL |
| `AGENTSPAN_CLI_PATH` | `agentspan` | Path to CLI binary |
| `AGENTSPAN_MASTER_KEY` | (auto-generated) | Master key for credential encryption. Set before starting the server. |
| `MCP_TESTKIT_URL` | `http://localhost:3001` | mcp-testkit URL for HTTP/MCP tool tests |
| `AGENTSPAN_LLM_MODEL` | `openai/gpt-4o-mini` | Model for agent execution (Suite 2) |
| `AGENTSPAN_JUDGE_MODEL` | `claude-sonnet-4-20250514` | Model for LLM-as-judge (Suite 1). Supports `claude-*` (Anthropic) and `gpt-*` / `o*` (OpenAI). |
| `ANTHROPIC_API_KEY` | — | Required when judge model is `claude-*` (default) |
| `OPENAI_API_KEY` | — | Required for agent execution and when judge model is `gpt-*` |
| `GITHUB_TOKEN` | — | Required for Suite 3 CLI tools test (`gh` CLI authentication). Test skips if not set. |

## Shared Fixtures (`conftest.py`)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `verify_server` | session | Health check — skips all tests if server is down |
| `runtime` | module | `AgentRuntime` instance connected to the server |
| `model` | session | LLM model string (default: `openai/gpt-4o-mini`) |
| `mcp_url` | session | mcp-testkit URL for HTTP/MCP tool tests |
| `cli_credentials` | session | `CredentialsCLI` wrapper — manages credentials via the CLI binary |

## Suite 1: Basic Validation

**File:** `sdk/python/e2e/test_suite1_basic_validation.py`
**LLM calls:** One — the LLM-as-judge test makes a single LLM call via the Anthropic or OpenAI API (not agent execution). All other tests use `runtime.plan()` only.
**Duration:** ~5s total (mostly the LLM judge call).
**Dependencies:** `uv sync --extra testing` (installs `anthropic` and `openai` SDKs).

Compiles agents via `plan()` and asserts on the Conductor workflow JSON at exact paths in `workflowDef.metadata.agentDef`.

### Spec coverage

| Spec item | Test(s) |
|-----------|---------|
| **2a** — plan reflects agent structure (tools, guardrails, credentials) | `test_plan_reflects_tools`, `test_plan_reflects_guardrails`, `test_plan_reflects_credentials` |
| **2b** — LLM as judge validates compiled graph contains all structural info | `test_llm_judge_validates_compiled_workflow` |
| **2c** — sub-agent references in compiled graph | `test_plan_sub_agent_produces_sub_workflow`, `test_plan_sub_agent_references_correct_names` |
| **2d** — kitchen sink with all tool types, guardrails, sub-agent strategies | `test_kitchen_sink_compiles` |
| **2e** — smoke test with simple agent + tools | `test_smoke_simple_agent_plan` |

### Test details

| Test | What it validates |
|------|-------------------|
| `test_smoke_simple_agent_plan` | Agent with 2 tools compiles. `workflowDef` and `requiredWorkers` present. Tools appear in `agentDef.tools` with `toolType=worker`. |
| `test_plan_reflects_tools` | Every tool passed to `Agent(tools=[...])` appears in `agentDef.tools[]` with correct `name` and `toolType`. |
| `test_plan_reflects_guardrails` | All 3 guardrails (custom input, custom output, regex) appear in `agentDef.guardrails[]` with correct `name`, `position`, `guardrailType`, `onFail`, and `patterns`. |
| `test_plan_reflects_credentials` | Credential names from `@tool(credentials=[...])` appear at `agentDef.tools[].config.credentials`. Validates single-credential and multi-credential tools. |
| `test_plan_sub_agent_produces_sub_workflow` | Agent with a child agent: child appears in `agentDef.agents[]`, parent strategy is `handoff`, compiled workflow contains `SUB_WORKFLOW` task type. |
| `test_plan_sub_agent_references_correct_names` | Multi-child agent: both children in `agentDef.agents[]` and both referenced in `subWorkflowParam.name` of compiled `SUB_WORKFLOW` tasks. |
| `test_kitchen_sink_compiles` | All 8 tool types (worker, http, mcp, image, audio, video, pdf + credentialed worker), 3 guardrails, 8 sub-agent strategies (handoff, sequential, parallel, router, round_robin, random, swarm, manual) compile. Validates every tool name + `toolType`, credential at correct config path, guardrail names + types, sub-agent names + strategies, parent strategy, and `SUB_WORKFLOW` task presence. |
| `test_llm_judge_validates_compiled_workflow` | **LLM-as-judge.** Compiles the kitchen sink agent, extracts a structured side-by-side comparison (EXPECTED vs ACTUAL for each tool, guardrail, sub-agent, strategy, and task type), and sends it to an LLM for validation. The judge verifies every structural element matches. Default model: Claude Sonnet (`claude-sonnet-4-20250514`). Override with `AGENTSPAN_JUDGE_MODEL` env var — supports `claude-*` (uses `anthropic` SDK, requires `ANTHROPIC_API_KEY`) and `gpt-*`/`o*` (uses `openai` SDK, requires `OPENAI_API_KEY`). |

### Assertion paths

All Suite 1 structural assertions check exact JSON paths, never `str(result)`:

- **Tools:** `workflowDef.metadata.agentDef.tools[].name`, `.toolType`
- **Credentials:** `workflowDef.metadata.agentDef.tools[].config.credentials`
- **Guardrails:** `workflowDef.metadata.agentDef.guardrails[].name`, `.position`, `.guardrailType`, `.onFail`, `.patterns`
- **Sub-agents:** `workflowDef.metadata.agentDef.agents[].name`, `.strategy`
- **Compiled tasks:** `workflowDef.tasks[]` (recursive) `.type`, `.subWorkflowParam.name`

## Suite 2: Tool Calling / Credential Lifecycle

**File:** `sdk/python/e2e/test_suite2_tool_calling.py`
**LLM calls:** Yes — 4 real agent executions per run.
**Duration:** ~3-4 minutes total.
**Parallel safety:** `xdist_group("credentials")` — runs serially to avoid credential conflicts.

Runs a single sequential test (`test_credential_lifecycle`) that exercises the full credential pipeline with 3 tools:

- `free_tool` — no credentials, always returns `"free:ok"`
- `paid_tool_a` — requires `E2E_CRED_A`, returns first 3 chars of the credential value
- `paid_tool_b` — requires `E2E_CRED_B`, returns first 3 chars of the credential value

Both paid tools raise `RuntimeError` if the expected credential is not injected into the environment by the server. This ensures credential resolution failures surface immediately at the tool level rather than producing silent empty output.

### Spec coverage

| Spec item | Step |
|-----------|------|
| **3a** — 3 tools, 2 require credentials | Agent definition: `free_tool`, `paid_tool_a` (needs `E2E_CRED_A`), `paid_tool_b` (needs `E2E_CRED_B`) |
| **3b** — start with no credentials | Step 1: deletes both credentials via CLI |
| **3c** — prompt calls all 3 tools | Agent instructions: "call all three tools exactly once each" |
| **3d** — tools needing creds report error | Step 2: paid tools raise `RuntimeError` when credential not in env, agent reaches terminal status |
| **3e** — export env vars to ensure NOT read | Step 3: sets `E2E_CRED_A`/`E2E_CRED_B` as local env vars |
| **3f** — validate env vars ignored, free tool OK | Step 3: asserts `"fro"` (prefix of `"from-env-..."`) is NOT in output |
| **3g** — add creds via CLI, validate first 3 chars | Step 4: adds creds, validates `"free"` in output + `"sec"` (first 3 chars of `"secret-aaa-value"`) |
| **3h** — change cred value, validate new first 3 chars | Step 5: updates creds, validates `"new"` (first 3 chars of `"newval-xxx-updated"`) |

### Step details

| Step | What it validates |
|------|-------------------|
| **Step 1: Clean slate** | Deletes `E2E_CRED_A` and `E2E_CRED_B` via CLI. |
| **Step 2: No credentials** | Runs agent. Paid tools should raise `RuntimeError` (credential not in env). Agent reaches terminal status (`COMPLETED` or `FAILED`). |
| **Step 3: Env vars ignored** | Sets `E2E_CRED_A` and `E2E_CRED_B` as local env vars, runs agent. Asserts `"fro"` (prefix of `"from-env-..."`) is NOT in output — the SDK must not read credentials from the environment. |
| **Step 4: Credentials added** | Sets credentials via CLI (`agentspan credentials set`), runs agent. Asserts: run completes, output contains `"free"` from `free_tool`, output contains `"sec"` (first 3 chars of `"secret-aaa-value"`) from `paid_tool_a`. |
| **Step 5: Credentials updated** | Updates credentials via CLI, runs agent. Asserts output contains `"new"` (first 3 chars of `"newval-xxx-updated"`) — proves the update propagated. |

### Diagnostics on failure

When a test fails, the error message includes:

- **Step label:** `[Step 4: With credentials]` — which lifecycle phase failed
- **Run diagnostic:** status, execution_id, finishReason, result count
- **Tool diagnostics:** Per-tool task status and failure reason from the workflow API
- **Credential audit:** Cross-references each tool's declared credentials against the server's credential store, reports `FOUND`/`NOT FOUND` for each, and lists all missing credentials

Example failure output:
```
[Step 4: With credentials] Run stalled at tool-calling stage — tools were
requested but did not return results.
  status=COMPLETED | finishReason=TOOL_CALLS | result_count=0
  Credential audit (tool requirements vs server store):
    free_tool: no credentials required
    paid_tool_a: requires [E2E_CRED_A] — E2E_CRED_A: FOUND
    paid_tool_b: requires [WRONG_NAME] — WRONG_NAME: NOT FOUND
    MISSING: WRONG_NAME (needed by paid_tool_b)
```

## Suite 3: CLI Tools / Credential Isolation

**File:** `sdk/python/e2e/test_suite3_cli_tools.py`
**LLM calls:** Yes — 3 real agent executions per run.
**Duration:** ~3-5 minutes total.
**Parallel safety:** `xdist_group("credentials")` — runs serially to avoid credential conflicts.
**Dependencies:** `gh` CLI installed, `GITHUB_TOKEN` env var set.

Runs a single sequential test (`test_cli_credential_lifecycle`) that exercises CLI tools with credential isolation and command whitelisting.

3 custom tools:
- `cli_ls` — no credentials, runs `ls`, returns `"ls_ok:<output>"`
- `cli_mktemp` — no credentials, runs `mktemp`, returns `"mktemp_ok:<path>"`
- `cli_gh` — requires `GITHUB_TOKEN`, runs `gh` CLI, returns `"gh_ok:<output>"`

Plus a whitelist agent with `cli_commands=True, cli_allowed_commands=["ls", "mktemp", "gh"]` for command restriction testing.

### Spec coverage

| Spec item | Step |
|-----------|------|
| **4a** — agent with CLI commands (ls, mktemp, gh) | Agent definition with 3 custom `@tool` functions |
| **4b** — gh requires GITHUB_TOKEN credential | `@tool(credentials=["GITHUB_TOKEN"])` on `cli_gh` |
| **4c** — remove GITHUB_TOKEN from server | Step 1: deletes GITHUB_TOKEN via CLI |
| **4d** — export GITHUB_TOKEN to env (not used) | Step 2: sets real `GITHUB_TOKEN` in `os.environ` |
| **4e** — prompt uses all three commands | Agent instructions: "call cli_ls, cli_mktemp, cli_gh" |
| **4f** — ls/mktemp succeed, gh fails (missing token) | Step 3: asserts `"ls_ok"` and `"mktemp_ok"` in output, `"gh_ok"` NOT in output |
| **4g** — add GITHUB_TOKEN credential via CLI | Step 4: `agentspan credentials set GITHUB_TOKEN <value>` |
| **4h** — re-run, all three succeed, gh lists repos | Step 5: asserts `"ls_ok"`, `"mktemp_ok"`, `"gh_ok"` all in output |
| **4i** — cd command rejected (not in whitelist) | Step 6: whitelist agent, `run_command("cd")` → "not allowed" |

### Step details

| Step | What it validates |
|------|-------------------|
| **Step 1: Clean slate** | Deletes `GITHUB_TOKEN` from server credential store via CLI. |
| **Step 2: Export to env** | Sets real `GITHUB_TOKEN` in `os.environ` — the SDK must NOT read this. |
| **Step 3: No credential** | Runs agent. `cli_ls` and `cli_mktemp` succeed (no creds needed). `cli_gh` fails — server has no GITHUB_TOKEN, even though it's in env. |
| **Step 4: Add credential** | Adds `GITHUB_TOKEN` to server via CLI. |
| **Step 5: With credential** | Runs agent. All three tools succeed. `gh repo list` returns repos. |
| **Step 6: cd blocked** | Whitelist agent with `cli_allowed_commands=["ls", "mktemp", "gh"]`. Prompt asks to run `cd /etc`. Tool rejects with "Command 'cd' is not allowed. Allowed commands: gh, ls, mktemp". |

## Suite 4: MCP Tools / Authenticated Access

**File:** `sdk/python/e2e/test_suite4_mcp_tools.py`
**LLM calls:** Yes — 2 real agent executions per run.
**Duration:** ~3-5 minutes total.
**Parallel safety:** `xdist_group("credentials")` — runs serially to avoid credential conflicts.
**Dependencies:** `mcp-testkit` installed (pip install mcp-testkit).

Manages its own mcp-testkit instance on port 3002 (avoids conflict with orchestrator's port 3001). Runs a single sequential test (`test_mcp_lifecycle`) that exercises MCP tool discovery, execution, and authenticated access.

### Spec coverage

| Spec item | Step |
|-----------|------|
| **5a** — local mcp server, 65 tools, auth support | mcp-testkit with `--auth` flag, managed by test |
| **5b** — agent using MCP server | `mcp_tool(server_url="http://localhost:3002/mcp")` |
| **5c** — prompt using 3 tools | `math_add`, `string_reverse`, `encoding_base64_encode` |
| **5d** — start server unauthenticated | Phase 1: `_start_mcp_server(port=3002)` |
| **5e** — list tools, validate all 65 | Phase 1: `_discover_tools_via_mcp()` + exact set comparison |
| **5f** — use 3 tools, validate success | Phase 1: workflow task validation (COMPLETED status + output) |
| **5g** — stop server, restart with auth | Phase 2: `_stop_mcp_server()` then `_start_mcp_server(auth_key=...)` |
| **5h** — agent with credentials for MCP | Phase 2: `mcp_tool(headers={"Authorization": "Bearer ${MCP_AUTH_KEY}"}, credentials=["MCP_AUTH_KEY"])` |
| **5i** — set credentials via CLI | Phase 2: `agentspan credentials set MCP_AUTH_KEY <value>` |
| **5j** — list tools with auth, validate all 65 | Phase 2: `_discover_tools_via_mcp(auth_key=...)` + exact set comparison |
| **5k** — use 3 tools with auth, validate success | Phase 2: workflow task validation (same as 5f) |

### Step details

| Step | What it validates |
|------|-------------------|
| **Phase 1: Unauthenticated** | |
| Start server | mcp-testkit on port 3002, no auth. |
| Discovery | Direct MCP protocol call via `mcp` client library. Asserts exact tool count (65) and exact tool name set match against mcp-testkit source. |
| Execution | Agent calls `math_add(3,4)`, `string_reverse("hello")`, `encoding_base64_encode("test")`. Workflow tasks checked for COMPLETED status and expected output values (`7`, `olleh`, `dGVzdA==`). |
| **Phase 2: Authenticated** | |
| Server restart | Stop unauthenticated server, start with `--auth e2e-test-secret-key-12345`. |
| Auth enforcement | Unauthenticated discovery call must raise exception. |
| Credential setup | `MCP_AUTH_KEY` stored via CLI. Agent uses `headers={"Authorization": "Bearer ${MCP_AUTH_KEY}"}`. |
| Discovery + Execution | Same validation as Phase 1 — full tool set, 3 tools execute correctly. |

### Validation approach

All validation is algorithmic — no LLM output parsing:

- **Tool discovery**: Direct MCP protocol call using `mcp` Python client library. Compares discovered tool names against expected set (computed from mcp-testkit source).
- **Tool execution**: Workflow task data from server API. Each tool task checked for `COMPLETED` status and expected deterministic output value.
- **Auth enforcement**: `pytest.raises(Exception)` on unauthenticated call to authenticated server.

## Suite 5: HTTP Tools / External OpenAPI

**File:** `sdk/python/e2e/test_suite5_http_tools.py`
**LLM calls:** Yes — 3 real agent executions per run (2 lifecycle + 1 external).
**Duration:** ~30s total.
**Parallel safety:** `xdist_group("credentials")` — runs serially.
**Dependencies:** `mcp-testkit` installed, internet access for external OpenAPI test.

Two tests: `test_http_lifecycle` (local server, steps a-k) and `test_external_openapi_spec` (Orkes Cloud, steps l-n).

### Spec coverage

| Spec item | Step |
|-----------|------|
| **6a** — local HTTP server, 65 tools, auth support | mcp-testkit with `--transport http`, REST at `/api/*` |
| **6b** — agent using HTTP server | `http_tool()` for 3 specific endpoints |
| **6c** — prompt using 3 tools | `math_add`, `string_reverse`, `encoding_base64_encode` |
| **6d** — start server unauthenticated | `_start_http_server(port=3003)` |
| **6e** — list tools, validate all 65 | Direct HTTP fetch of `/api-docs` OpenAPI spec + exact set comparison |
| **6f** — use 3 tools, validate success | Workflow task validation (COMPLETED status + output) |
| **6g** — stop server, restart with auth | `_stop_http_server()` then `_start_http_server(auth_key=...)` |
| **6h** — agent with credentials for HTTP | `http_tool(headers={"Authorization": "Bearer ${HTTP_AUTH_KEY}"}, credentials=["HTTP_AUTH_KEY"])` |
| **6i** — set credentials via CLI | `agentspan credentials set HTTP_AUTH_KEY <value>` |
| **6j** — list tools with auth, validate all 65 | OpenAPI spec fetch with auth header + exact set comparison |
| **6k** — use 3 tools with auth, validate success | Workflow task validation (same as 6f) |
| **6l** — agent with Orkes Cloud API | `api_tool(url="https://developer.orkescloud.com/api-docs", tool_names=["startWorkflow"])` |
| **6m** — find start workflow API | Algorithmic: fetch spec, verify `startWorkflow` exists at `/api/workflow` |
| **6n** — validate operationId | Compile agent (`plan()`), verify API tool present; run agent (best-effort) |

### Validation approach

All validation is algorithmic:

- **Tool discovery**: Direct HTTP GET to `/api-docs`, parse OpenAPI 3.0 JSON, extract all `operationId` values. Compare against expected set (from mcp-testkit source `ENDPOINTS` registry).
- **Tool execution**: Workflow task data from server API. Each HTTP task checked for `COMPLETED` status and expected output value.
- **Auth enforcement**: Direct HTTP GET without auth header → assert 401/403.
- **External spec (steps l-n)**: Fetch spec, parse JSON for `startWorkflow` at `/api/workflow` path. Compile agent with `plan()`. Run agent with lenient status check (accepts COMPLETED/FAILED).

## Suite 6: PDF Tools

**File:** `sdk/python/e2e/test_suite6_pdf_tools.py`
**LLM calls:** Yes — 1 agent execution.
**Duration:** ~10s.

Generates a PDF from sample markdown via `pdf_tool()`, then validates the round-trip using `markitdown` to extract text from the generated PDF.

| Step | What it validates |
|------|-------------------|
| PDF generation | Agent calls `generate_pdf` tool with sample markdown. GENERATE_PDF task completes. |
| Round-trip | Downloads generated PDF, extracts text with markitdown, verifies key phrases survived (headings, metrics, features). Allows ≤2 missing phrases (PDF conversion is lossy). |

Skips round-trip validation if PDF URL cannot be extracted from task output.

## Suite 7: Media Tools (Image, Audio, Video)

**File:** `sdk/python/e2e/test_suite7_media_tools.py`
**LLM calls:** Yes — 1 per test (up to 4 tests).
**Duration:** ~2-4 minutes total.
**Dependencies:** `OPENAI_API_KEY` (required), `GOOGLE_AI_API_KEY` (optional, for Gemini image).

| Test | Provider | Model | What it validates |
|------|----------|-------|-------------------|
| `test_image_openai` | OpenAI | dall-e-3 | GENERATE_IMAGE task completes with output |
| `test_image_gemini` | Google Gemini | imagen-3.0-generate-002 | Same (skips if no `GOOGLE_AI_API_KEY`) |
| `test_audio_openai` | OpenAI | tts-1 | GENERATE_AUDIO task completes with output |
| `test_video_openai` | OpenAI | sora-2 | GENERATE_VIDEO task completes with output |

Media API errors (400, quota limits, generation failures) cause skip, not failure — these are provider issues, not test bugs.

## Report

After running, an HTML report is generated at `e2e-results/report.html`:

- Tests grouped by suite (Suite 1: Basic Validation, Suite 2: Tool Calling, Suite 3: CLI Tools)
- Failed tests show error summary and file:line immediately (no expanding needed)
- Full traceback available in collapsible section
- Summary header with pass/fail/skip counts and duration
