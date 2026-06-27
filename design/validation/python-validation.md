# Python SDK — Validation & E2E

**Status:** Refreshed 2026-06-26

**Scope:** Canonical reference for the two validation surfaces of the Python SDK (PyPI `conductor-agent-sdk`, import namespace `conductor.ai.agents`): (1) the **deterministic E2E suites** under `sdk/python/e2e/`, which exercise real agents against a real server + real services with deterministic assertions; and (2) the **examples-quality validation framework** under `sdk/python/validation/`, which runs every SDK example across multiple models concurrently and scores output quality with an LLM judge. Cross-links: methodology / cross-cutting harness [`README.md`](README.md); implementation [`../sdk-design/languages/python-implementation.md`](../sdk-design/languages/python-implementation.md); SDK contract (env vars, CLI binary) [`../sdk-design.md`](../sdk-design.md).

---

## 1. Overview

| Surface | Location | Purpose | Judging |
|---------|----------|---------|---------|
| Deterministic E2E suites | `sdk/python/e2e/` | Verify feature correctness end-to-end (real agents, real server, real CLI/MCP/HTTP services, no mocks) | Deterministic assertions (JSON-path / workflow-task / Conductor-API checks). LLM only where the thing under test *is* output quality (e.g. one semantic judge call in Suite 1) — see [CLAUDE.md](../../CLAUDE.md) |
| Examples-quality framework | `sdk/python/validation/` | Run every published example across multiple models, compare outputs, surface quality regressions | LLM-as-judge by design (1–5 scoring + baseline comparison) |

The two are complementary: the E2E suites answer *"does the feature work?"* deterministically; the validation framework answers *"is the example's output good across models?"*. Both are driven by the cross-SDK orchestrator (`e2e/orchestrator.sh`) and CI (`.github/workflows/ci.yml`).

Both surfaces honour the SDK's intentional contracts from [`../sdk-design.md`](../sdk-design.md): the `AGENTSPAN_*` environment variables, the `agentspan` CLI binary (PyPI console-script entry point `conductor.ai.cli:main`), and `AGENTSPAN_AUTO_START_SERVER=false` to keep tests pointed at the orchestrator-managed server.

---

## 2. Deterministic E2E suites (`sdk/python/e2e/`)

### 2.1 Principles

- **No mocks** — real agents, real Conductor server, real CLI, real services (mcp-testkit for MCP/HTTP, Docker/Jupyter for code execution, provider APIs for media).
- **Deterministic assertions** — checks are made against compiled workflow JSON (`plan()`), individual workflow task status/output via the server REST API, or Conductor control-plane API state. LLM execution is used where the *behaviour* requires it (tool-calling, handoffs, guardrail runtime policies), but assertions target structural/observable facts, not free-text equality. The only LLM-as-judge call is the single semantic check in Suite 1 — consistent with the [CLAUDE.md](../../CLAUDE.md) rule (no LLM judging except when judging quality).
- **Credentials via CLI only** — managed exclusively through `agentspan credentials set/delete/list`; the SDK must never read credential values from env vars (Suite 2 explicitly asserts this isolation).

### 2.2 Harness (`conftest.py`)

Configuration is read from env vars exported by the orchestrator:

| Var | Default | Purpose |
|-----|---------|---------|
| `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api` | Server API URL (health, workflow inspection) |
| `AGENTSPAN_CLI_PATH` | `agentspan` | Absolute path to the built CLI binary used for credential ops |
| `MCP_TESTKIT_URL` | `http://localhost:3001` | mcp-testkit HTTP/MCP endpoint for tool suites |
| `AGENTSPAN_LLM_MODEL` | `openai/gpt-4o-mini` | Model for suites that execute agents |

Fixtures and behaviour:

- `verify_server` (session, autouse) — polls `BASE_URL/health`; **skips** the whole session if the server is unreachable.
- `runtime` (module) — a shared `AgentRuntime` (`from conductor.ai.agents import AgentRuntime`).
- `model`, `mcp_url`, `cli_credentials` (session) — model string, mcp-testkit URL, and a `CredentialsCLI` helper wrapping the `agentspan` binary (`set`/`delete`/`list`; tolerant of "not found" on cleanup). The helper strips the `/api` suffix because the CLI appends it internally.
- `get_workflow()` / `get_task_by_name()` — REST helpers to fetch a completed workflow and locate tasks by `referenceTaskName`, used for deterministic per-task assertions.
- `conftest.py` sets `AGENTSPAN_AUTO_START_SERVER=false` at import time to prevent the runtime from launching a second server.
- **Auto-retry**: `pytest_collection_modifyitems` attaches `flaky(reruns=2, reruns_delay=5)` to every `e2e`-marked test. These suites drive a real server + real LLM, so individual tests flake on transient latency (workflow still `RUNNING` at timeout, a tool-call batch not returning, LLM phrasing variance). Two reruns let a one-off flake recover while a genuinely broken test still fails all three attempts. No-op unless `pytest-rerunfailures` (dev extra) is installed.

### 2.3 Suite layout

Suites 1–16 and 20–24 (17–19 do not exist). All carry `pytest.mark.e2e`; several add `pytest.mark.timeout`, `skipif` (Docker/Jupyter/provider keys), or `xfail`.

| Suite | File | Validates | Determinism |
|-------|------|-----------|-------------|
| 1 | `test_suite1_basic_validation.py` | `plan()` compilation — tools, guardrails, credentials, sub-agents, all 8 strategies, kitchen-sink agent reflected in workflow JSON | Deterministic (plan-only; + 1 semantic judge call) |
| 2 | `test_suite2_tool_calling.py` | Credential lifecycle: missing → env-isolation → add (CLI) → update; server injects creds into tool execution | LLM exec; deterministic task-output assertions |
| 3 | `test_suite3_cli_tools.py` | CLI tool credential isolation, command-whitelist enforcement | LLM exec; deterministic |
| 4 | `test_suite4_mcp_tools.py` | MCP tool discovery + execution, unauth → auth lifecycle (mcp-testkit) | LLM exec; deterministic tool outputs |
| 5 | `test_suite5_http_tools.py` | HTTP/OpenAPI tool discovery + execution, auth lifecycle, external-OpenAPI compile | LLM exec; deterministic tool outputs |
| 6 | `test_suite6_pdf_tools.py` | PDF generation from markdown, markitdown round-trip content survival | LLM gen; deterministic content checks |
| 7 | `test_suite7_media_tools.py` | Image (DALL·E, Gemini) + audio (TTS) generation; `skipif` no keys, one `xfail` | LLM/provider exec |
| 8 | `test_suite8_guardrails.py` | Guardrail compilation (types/positions/`on_fail`); runtime block/retry/fix/escalation | Deterministic compile + LLM runtime policies |
| 9 | `test_suite9_handoffs.py` | All 8 multi-agent strategies compile + execute; `>>` operator | LLM exec; deterministic tool outputs |
| 10 | `test_suite10_code_execution.py` | Local/Bash, timeout, language restriction, Docker isolation, Jupyter stateful | Deterministic config + LLM exec (`skipif` Docker/Jupyter) |
| 11 | `test_suite11_langgraph.py` | LangGraph detection/serialization (full/graph-structure/passthrough), schema, compile, runtime | Deterministic serialization + LLM runtime |
| 12 | `test_suite12_termination_gates.py` | `TextMentionTermination`, `MaxMessageTermination`, `TextGate` SWITCH compile, invalid-model rejection | Deterministic gate wiring + LLM runtime |
| 13 | `test_suite13_callbacks.py` | `CallbackHandler` compile (before/after tool/model/agent); runtime as worker tasks | Deterministic compile + LLM runtime |
| 14 | `test_suite14_stateful_domain.py` | Stateful agent domain propagation (tool + `stop_when` + swarm handoff + concurrent isolation); regression: non-stateful has no domain | LLM exec; deterministic via Conductor task domains |
| 15 | `test_suite15_skills.py` | Skill load/serialize, nested in `agent_tool`, script discovery, param injection, worker creation, plan compile | Deterministic load/serialize + LLM skill exec |
| 16 | `test_suite16_cli_skills.py` | CLI skill register/list/get/pull/delete; load/serve/run; script-worker polling; dep pinning | LLM run; deterministic script-worker checks |
| 20 | `test_suite20_plan_execute.py` | `PLAN_EXECUTE`: planner sub-agent, plan compile + execute, Refs across steps, PAC whitelist | LLM planner; deterministic ref/whitelist + wire-path checks |
| 21 | `test_suite21_scheduling.py` | Schedule create/reconcile/pause/resume/delete, `preview_next`, `run_now`, tri-state | Deterministic (Conductor scheduler API; no LLM) |
| 22 | `test_suite22_ocg.py` | OCG multi-instance binding isolation (per-tenant stub routing) | LLM exec; deterministic via HTTP request recording |
| 23 | `test_suite23_from_instance_and_event_hitl.py` | Event-targeted HITL (approve/reject/respond on streamed event); `Agent.from_instance` resolution/wiring | Deterministic targeting/wire + plan compile |
| 24 | `test_suite24_agent_client.py` | `AgentClient.run`/`.start`/`.join`/`.schedule` reconcile + list; surface consistency | Deterministic control-plane + LLM run on tool-less agent |

### 2.4 Serial / stateful suites

Suites that mutate shared server state run serially via `pytest.mark.xdist_group`, so parallel workers (`-n`) keep them on one worker:

- `xdist_group("credentials")` — Suites 2, 3, 4, 5 (credential set/delete is global server state).
- `xdist_group("cli-skills")` — Suite 16.
- `xdist_group("ocg")` — Suite 22.

CI runs with `--dist=loadgroup` so these groups are honoured. Suites mutating state use `try/finally` cleanup to avoid leaking state on failure.

### 2.5 How to run

Driven by the cross-SDK orchestrator `e2e/orchestrator.sh` (Python is the default `--sdk`). It builds the server JAR + CLI, `uv sync`s the SDK, installs mcp-testkit, starts services, health-checks, runs pytest, then renders the HTML report:

```bash
./e2e/orchestrator.sh                 # build + start + run all Python suites (-j 1)
./e2e/orchestrator.sh -j 4            # 4 parallel xdist workers
./e2e/orchestrator.sh --suite suite1  # pytest -k suite1
./e2e/orchestrator.sh --no-build --no-start   # services already running
```

The orchestrator exports `AGENTSPAN_SERVER_URL=http://localhost:6767/api`, `AGENTSPAN_CLI_PATH=<repo>/cli/agentspan`, `MCP_TESTKIT_URL=http://localhost:3001`, `AGENTSPAN_AUTO_START_SERVER=false`, then invokes pytest from `sdk/python` and writes `e2e-results/junit.xml` + `e2e-results/report.html`.

To run pytest directly against an already-running server (skips build/service management):

```bash
cd sdk/python
export AGENTSPAN_SERVER_URL=http://localhost:6767/api
export AGENTSPAN_CLI_PATH="$PWD/../../cli/agentspan"
export MCP_TESTKIT_URL=http://localhost:3001
uv run pytest e2e/ -v --tb=short -n 3 --dist=loadgroup
```

> Note: there is no `e2e-orchestrator.sh` at the repo root — the orchestrator lives at `e2e/orchestrator.sh`.

### 2.6 HTML report (`report_generator.py`)

Post-processes the pytest junit XML into a single self-contained HTML file: parses the `testsuites/testsuite` structure, groups tests by suite file, derives human-readable suite names (`test_suite1_basic_validation` → "Suite 1: Basic Validation"), and renders collapsible per-suite sections with a pass/fail/skip/error summary, color-coded statuses, and expandable error tracebacks (inline CSS, dark mode, no external deps). Invoked as `python e2e/report_generator.py <junit.xml> <report.html>`.

### 2.7 CI

The `python-e2e` job in `.github/workflows/ci.yml` (needs `build-server` + `python-unit-tests`, 45-min timeout): downloads the server JAR artifact, builds the CLI (`go build -o agentspan .`), `uv sync --extra dev --extra testing`, installs + starts mcp-testkit, starts the server and polls `/health`, then:

```bash
uv run pytest e2e/ -v --tb=short \
  --junitxml=../../e2e-results/junit.xml \
  --reruns 2 --reruns-delay 5 \
  -n 3 --dist=loadgroup
```

It always generates and uploads `e2e-results/` (junit + HTML), retained 14 days. `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` come from secrets; env vars match the harness contract (`AGENTSPAN_SERVER_URL`, `AGENTSPAN_CLI_PATH`, `AGENTSPAN_AUTO_START_SERVER=false`).

---

## 3. Examples-quality validation framework (`sdk/python/validation/`)

Runs every published SDK example across one-or-more models concurrently, parses each example's output, and (optionally) scores quality with an LLM judge against a baseline model. Install with `uv sync --extra validation`.

### 3.1 Architecture

TOML config defines named runs (one model each). Runs execute concurrently via the orchestrator. A multi-run LLM judge compares outputs against a baseline.

```
runs.toml → load_toml_config() → resolve_runs() → run_all()
                                                       │
                                              ThreadPoolExecutor
                                               ┌───────┼───────┐
                                               ▼       ▼       ▼
                                          run_single  run_single  run_single
                                          (sub-dir)   (sub-dir)   (sub-dir)
                                               │       │       │
                                               └───────┼───────┘
                                                       ▼
                                               judge_across_runs()
                                                (judge/ sub-dir)
```

### 3.2 Config structure

```toml
[defaults]
timeout = 300          # per-example timeout (seconds)
parallel = true        # run examples within a run concurrently
max_workers = 8        # max concurrent examples per run
retries = 0
server_url = "http://localhost:6767/api"

[env]                  # global env, applied to all runs (shell wins via setdefault)
# AGENTSPAN_AUTH_KEY = "<key>"

[judge]
baseline_run = "openai"
model = "gpt-4o-mini"
max_output_chars = 3000
max_tokens = 300
rate_limit = 0.5       # seconds between judge calls
max_calls = 0          # 0 = unlimited

[runs.openai]
group = "OPENAI_EXAMPLES"
model = "openai/gpt-4o"

[runs.anthropic]
group = "OPENAI_EXAMPLES"
model = "anthropic/claude-sonnet-4-20250514"

[runs.anthropic.env]   # per-run env, never touches os.environ
# ANTHROPIC_API_KEY = "<key>"
```

`[defaults]` values merge into every `[runs.*]` (run-level overrides win). Live config is `validation/runs.toml` (gitignored); template is `validation/runs.toml.example`. Run-config keys: `name` (auto), `group`, `model`, `secondary_model`, `parallel`, `max_workers`, `timeout`, `retries`, `server_url`.

### 3.3 Example groups

Groups are defined in `validation/groups.py` and selected per run via `group = "NAME"`. Notable groups: `PASSING_EXAMPLES` (the core SDK examples), `SMOKE_TEST` (small fast subset), `OPENAI_EXAMPLES` / `ADK_EXAMPLES` / `LANGGRAPH_EXAMPLES` / `LANGCHAIN_EXAMPLES` (per-framework, gated on dep availability via `SUBDIRS` in `config.py`), `HITL_EXAMPLES` (driven by the `HITL_STDIN` map), `SLOW_EXAMPLES`, and `KNOWN_FAILURES`. Discovery scans `examples/` plus framework subdirs and skips subdirs whose framework dependency is not installed. `--list-groups` prints all groups.

### 3.4 Execution

Each `run_single()`:
1. Discovers examples for the run's group.
2. Starts the server pool.
3. Calls `run_examples()` — single model, concurrent examples via `ThreadPoolExecutor` (`max_workers`).
4. Writes `run_results.json`, `outputs/`, `meta.json`, `report.json` into the run sub-dir.

`run_example()` runs each example as a subprocess (`python <script>`), setting `AGENTSPAN_LLM_MODEL` (and `AGENTSPAN_SERVER_URL` / `AGENTSPAN_SECONDARY_LLM_MODEL` as configured), then parses stdout/stderr into a `RunResult`. Env is built per-run by `build_resolved_env()` (`execution/runner.py`), which never mutates `os.environ` — each call returns an isolated dict (shell → global `[env]` → run `[runs.X.env]` → computed model/URL vars). HITL examples receive scripted stdin from `HITL_STDIN`.

**Concurrency:** runs execute concurrently (one `ThreadPoolExecutor` per orchestrator); within each run, examples execute concurrently. Examples are scheduled slowest-first (from `report.json` history) for load balancing. `report.json` updates are thread-safe (locks + atomic replace). SIGINT triggers a graceful abort that writes partial results.

**Resumption:** `--resume` skips already-completed examples (by output file); `--retry-failed` re-runs only ERROR/TIMEOUT/FAILED examples.

**Output parsing / status** (from `AgentResult.print_result()` stdout): extracts Execution ID, tool-call count, token usage, and agent output text. Status is `FAILED` if `execution FAILED` appears or exit code is non-zero, `TIMEOUT` on subprocess timeout, `COMPLETED` on clean exit, else `ERROR`.

### 3.5 Multi-run LLM judge

When `--judge` is passed (or `judge_results.py` is run later), `judge_across_runs()` scores each completed run:

- **Individual scoring** — one judge call per run per example, 1–5 against the original prompt (1 = wrong/empty … 5 = excellent). The prompt is extracted from the example source via regex on `run(...)`/`stream(...)` calls.
- **Baseline comparison** — each non-baseline run is compared against `baseline_run`, judging task-correctness rather than surface similarity.
- **Output-hash caching** — outputs are SHA-256 hashed; an unchanged hash reuses the prior score (skips the API call).
- Judge settings come from `[judge]` (or `JUDGE_LLM_MODEL` / `JUDGE_MAX_OUTPUT_CHARS` / `JUDGE_MAX_TOKENS` / `JUDGE_MAX_CALLS` / `JUDGE_RATE_LIMIT` env). The judge requires `OPENAI_API_KEY` (shell or `[judge.env]`).

### 3.6 Output files

```
validation/output/run_{timestamp}_{id}/
├── meta.json
├── openai/                     ← run sub-dir
│   ├── run_results.json        ← all example results + history
│   ├── meta.json / report.json
│   └── outputs/*.txt
├── anthropic/ …
└── judge/
    ├── judge_results.json      ← per-run scores, reasons, output hashes (+ cache)
    ├── report.md
    ├── report.html             ← cross-run interactive dashboard (heatmap, side-by-side, filters, dark mode)
    └── meta.json
```

---

## 4. Running locally + CI integration

### 4.1 E2E suites

```bash
# Full managed run (build + services + tests + report)
./e2e/orchestrator.sh -j 4

# Against an already-running server
cd sdk/python && uv run pytest e2e/ -v -n 3 --dist=loadgroup
```

CI: `python-e2e` job in `.github/workflows/ci.yml` (see §2.7) — builds CLI + downloads server JAR, starts mcp-testkit + server, runs `pytest e2e/` with reruns and `--dist=loadgroup`, uploads `e2e-results/`.

### 4.2 Examples-quality framework

```bash
cd sdk/python
uv sync --extra validation
cp validation/runs.toml.example validation/runs.toml   # then edit models/groups

# Plan only
uv run python3 -m validation.scripts.run_examples --config runs.toml --dry-run
# Run all configured runs
uv run python3 -m validation.scripts.run_examples --config runs.toml
# Subset of runs + judge in one pass
uv run python3 -m validation.scripts.run_examples --config runs.toml --run openai,anthropic --judge
# Cross-run judge on an existing output dir
uv run python3 -m validation.scripts.judge_results --run-dir validation/output/run_*/
```

This framework runs ad hoc / on demand (model comparison, example-quality regression sweeps) rather than on every CI commit; the deterministic E2E suites are the per-commit gate.
