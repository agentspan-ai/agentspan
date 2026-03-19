# E2E Validation: Multi-Run Example Runner

Runs SDK examples against configured models via TOML config. One run = one model, concurrent execution, cross-run LLM judge.

## Prerequisites

- Python 3.11+
- Agentspan server running
- For judging: `OPENAI_API_KEY` env var

## Install

```bash
uv sync --extra validation
```

## Quick Start

```bash
# Copy and edit the example config
cp validation/runs.toml.example validation/runs.toml

# Run all configured runs
python3 -m validation.scripts.run_examples --config validation/runs.toml

# Preview without executing
python3 -m validation.scripts.run_examples --config validation/runs.toml --dry-run

# Run specific runs
python3 -m validation.scripts.run_examples --config validation/runs.toml --run openai

# Run + judge in one command
python3 -m validation.scripts.run_examples --config validation/runs.toml --judge

# Cross-run judge on existing results
python3 -m validation.scripts.judge_results --run-dir validation/output/run_*/
```

## TOML Config

See `validation/runs.toml.example` for full reference. Key sections:

```toml
[defaults]       # merged into every run
timeout = 300
parallel = true
max_workers = 8

[judge]          # judge settings
baseline_run = "openai"
model = "gpt-4o-mini"

[runs.openai]
model = "openai/gpt-4o"
group = "SMOKE_TEST"

[runs.anthropic]
model = "anthropic/claude-sonnet-4-20250514"
group = "SMOKE_TEST"
```

## Example Groups

Defined in `validation/groups.py`. Set `group = "NAME"` in TOML run config:

| Group | Examples | Notes |
|-------|----------|-------|
| **SMOKE_TEST** | 8 examples | Quick sanity check (OpenAI + ADK) |
| **PASSING_EXAMPLES** | 40 examples | Fast, reliable |
| **SLOW_EXAMPLES** | 08, 13, 23, 31 | >2 min each |
| **HITL_EXAMPLES** | 02, 09, 09b, 09c | Stdin piped via HITL_STDIN |
| **KNOWN_FAILURES** | 14, 21, 22, 33_ext, 34, 39c | Server/config issues |
| **OPENAI_EXAMPLES** | 10 examples | Requires `openai-agents` package |
| **ADK_EXAMPLES** | 32 examples | Requires `google-adk` package |
| **LANGGRAPH_EXAMPLES** | 40 examples | Requires `langgraph` + `langchain-openai` |
| **LANGCHAIN_EXAMPLES** | 25 examples | Requires `langchain` + `langchain-openai` |
| **LC_SMOKE_TEST** | 6 examples | Quick sanity check (LangGraph + LangChain) |

## LangGraph and LangChain Validation

LangGraph and LangChain examples can be validated in two modes:

- **Agentspan mode** (default): the agent is translated server-side into a Conductor workflow. The LLM runs as an `AI_MODEL` task and each tool runs as a `SIMPLE` worker task.
- **Native mode** (`native = true`): the agent runs directly via LangGraph/LangChain SDK, bypassing Conductor. Used as the judge baseline to compare output quality.

### Prerequisites

```bash
uv sync --extra validation
# Requires OPENAI_API_KEY for the examples themselves
# Requires OPENAI_API_KEY for the judge (gpt-4o-mini by default)
```

### Quick smoke test (6 examples, ~2 min)

```bash
# Run both modes and judge them against each other
uv run python3 -m validation.scripts.run_examples \
  --config validation/runs.toml \
  --run lc-smoke-test,lc-smoke-test-native \
  --judge
```

### Full LangGraph suite (40 examples)

```bash
# Agentspan vs native, with judge
uv run python3 -m validation.scripts.run_examples \
  --config validation/runs.toml \
  --run langgraph,langgraph-native \
  --judge

# Agentspan only (no judge)
uv run python3 -m validation.scripts.run_examples \
  --config validation/runs.toml \
  --run langgraph
```

### Full LangChain suite (25 examples)

```bash
# Agentspan vs native, with judge
uv run python3 -m validation.scripts.run_examples \
  --config validation/runs.toml \
  --run langchain,langchain-native \
  --judge
```

### All LangGraph + LangChain at once

```bash
uv run python3 -m validation.scripts.run_examples \
  --config validation/runs.toml \
  --run langgraph,langgraph-native,langchain,langchain-native \
  --judge
```

### Preview without executing

```bash
uv run python3 -m validation.scripts.run_examples \
  --config validation/runs.toml \
  --run lc-smoke-test,lc-smoke-test-native \
  --dry-run
```

### Available run names

| Run name | Group | Mode |
|----------|-------|------|
| `lc-smoke-test` | LC_SMOKE_TEST | Agentspan (Conductor) |
| `lc-smoke-test-native` | LC_SMOKE_TEST | Native (direct SDK) |
| `langgraph` | LANGGRAPH_EXAMPLES | Agentspan (Conductor) |
| `langgraph-native` | LANGGRAPH_EXAMPLES | Native (direct SDK) |
| `langchain` | LANGCHAIN_EXAMPLES | Agentspan (Conductor) |
| `langchain-native` | LANGCHAIN_EXAMPLES | Native (direct SDK) |

### How native mode works

The native runner monkey-patches `AgentRuntime` to bypass Conductor:

- **LangGraph** (`CompiledStateGraph`): calls `.invoke({"messages": [...]})` directly. For graphs with a `MemorySaver` checkpointer, passes `config={"configurable": {"thread_id": session_id}}`. For graphs without a checkpointer, maintains full message history in-memory.
- **LangChain** (`AgentExecutor`): calls `.invoke({"input": prompt, "chat_history": history})` directly. Maintains turn history in-memory for multi-turn sessions.

Token usage is extracted from `response_metadata.token_usage` on `AIMessage` objects.

### Parallel runner (without judge)

For a faster pass/fail check across all 65 examples, use the dedicated parallel runner:

```bash
uv run python examples/run_lc.py                     # all 65 examples, 6 workers
uv run python examples/run_lc.py --only langgraph    # LangGraph only
uv run python examples/run_lc.py --only langchain    # LangChain only
uv run python examples/run_lc.py --filter 01,07,22  # specific example numbers
uv run python examples/run_lc.py --workers 8 --timeout 180
```

The parallel runner auto-approves HITL tasks (polls Conductor for IN_PROGRESS HUMAN tasks and calls `POST /api/agent/{id}/respond {"approved": true}`).

## CLI Reference

### run_examples.py

```
python3 -m validation.scripts.run_examples [options]

Required:
  --config PATH         Path to TOML multi-run config

Options:
  --run NAMES           Comma-separated run names to execute
  --judge               Run cross-run judge after execution
  --output-dir DIR      Output directory (default: validation/output/)
  --dry-run             Show plan without executing
  --resume [RUN_DIR]    Resume, skipping completed examples
  --retry-failed [DIR]  Re-run only failed examples
  --list-groups         List available groups and exit
```

### judge_results.py

```
python3 -m validation.scripts.judge_results [options]

Required:
  --run-dir PATH        Multi-run parent directory

Options:
  --judge-model MODEL   Override judge model (default: from config)
```

## View Results

Each run creates `validation/output/run_{timestamp}_{id}/` containing:
- Per-run sub-directories with `results.csv` + `outputs/`
- `judge/report.html` — interactive dashboard with score heatmap, side-by-side outputs
- `judge/results.csv` — per-run scores + baseline comparison
- `judge/report.md` — markdown summary
- `meta.json` — timing and run metadata

## Environment

| Variable | Used by | Default | Purpose |
|----------|---------|---------|---------|
| `OPENAI_API_KEY` | examples + judge | — | LangGraph/LangChain examples (ChatOpenAI) and judge API calls |
| `ANTHROPIC_API_KEY` | examples | — | Examples using ChatAnthropic |
| `GOOGLE_API_KEY` | examples | — | ADK examples |
| `AGENTSPAN_SERVER_URL` | runner | `http://localhost:8080/api` | Conductor server |
| `AGENTSPAN_AUTH_KEY` | runner | — | Conductor auth key (if required) |
| `AGENTSPAN_AUTH_SECRET` | runner | — | Conductor auth secret (if required) |
| `JUDGE_LLM_MODEL` | judge | `gpt-4o-mini` | Judge model |
| `JUDGE_MAX_OUTPUT_CHARS` | judge | 3000 | Truncate before judging |
| `JUDGE_MAX_TOKENS` | judge | 300 | Max tokens for judge response |
| `JUDGE_MAX_CALLS` | judge | 0 (unlimited) | Budget cap |
| `JUDGE_RATE_LIMIT` | judge | 0.5 | Seconds between calls |


## Wishlist

- Validates end to end state of workflow creation by LLM Model is correct

### Judge Quality TODOs

- Multi-judge consensus (2-3 calls, median score)
- Judge model comparison (gpt-4o vs gpt-4o-mini consistency)
- Custom rubrics per example
- Retry on transient API failures (429/500 + backoff)
- Parallel judging (ThreadPoolExecutor + semaphore rate limiter)
