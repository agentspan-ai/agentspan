# Validation: Multi-Run Example Runner

Run SDK examples against multiple models, compare outputs with an LLM judge.

---

## 30-Second Quick Start

```bash
# 1. Install
cd sdk/python && uv sync --extra validation

# 2. Copy config
cp validation/runs.toml.example validation/runs.toml

# 3. Run smoke test (7 examples, ~2 min)
uv run python3 -m validation.scripts.run_examples \
  --config validation/runs.toml \
  --run smoke-test-openai-agentspan
```

That's it. Results in `validation/output/run_*/`.

---

## Prerequisites

- Python 3.11+
- Agentspan server running at `http://localhost:8080`
- `OPENAI_API_KEY` set (required for OpenAI/LangGraph/LangChain examples and judge)
- `ANTHROPIC_API_KEY` for Anthropic runs
- `GOOGLE_API_KEY` for ADK runs

---

## Common Recipes

### Smoke tests — fastest sanity check

```bash
# OpenAI (7 examples)
uv run python3 -m validation.scripts.run_examples --config validation/runs.toml --run smoke-test-openai-agentspan

# Anthropic Claude
uv run python3 -m validation.scripts.run_examples --config validation/runs.toml --run smoke-test-anthropic-agentspan

# Claude Sonnet 4.6
uv run python3 -m validation.scripts.run_examples --config validation/runs.toml --run smoke-test-claude-sonnet-4-6-agentspan

# All three + judge comparison
uv run python3 -m validation.scripts.run_examples --config validation/runs.toml \
  --run smoke-test-openai-agentspan,smoke-test-anthropic-agentspan,smoke-test-claude-sonnet-4-6-agentspan --judge
```

### Full OpenAI example suite (10 examples)

```bash
# Native vs agentspan
uv run python3 -m validation.scripts.run_examples --config validation/runs.toml \
  --run openai-native,openai-agentspan --judge

# Multi-model comparison
uv run python3 -m validation.scripts.run_examples --config validation/runs.toml \
  --run openai-agentspan,anthropic-agentspan,claude-sonnet-4-6-agentspan,gpt-5-4-agentspan --judge
```

### create_react_agent (agentspan vs native)

```bash
# 2 OpenAI examples — agentspan vs native, judged
uv run python3 -m validation.scripts.run_examples --config validation/runs.toml \
  --run react-agent-agentspan,react-agent-native --judge

# All 3 examples including the Anthropic one
uv run python3 -m validation.scripts.run_examples --config validation/runs.toml \
  --run react-agent-all-agentspan,react-agent-all-native --judge
```

### LangGraph / LangChain

```bash
# Quick smoke test (8 examples incl. react-agent) — agentspan + native, judged
uv run python3 -m validation.scripts.run_examples --config validation/runs.toml \
  --run lc-smoke-test-agentspan,lc-smoke-test-native --judge

# Full LangGraph (43 examples)
uv run python3 -m validation.scripts.run_examples --config validation/runs.toml \
  --run langgraph-agentspan,langgraph-native --judge

# Full LangChain (25 examples)
uv run python3 -m validation.scripts.run_examples --config validation/runs.toml \
  --run langchain-agentspan,langchain-native --judge
```

### ADK (Google Gemini)

```bash
# Hello world debug
uv run python3 -m validation.scripts.run_examples --config validation/runs.toml \
  --run adk-hello-native,adk-hello-agentspan --judge

# Full ADK suite (32 examples)
uv run python3 -m validation.scripts.run_examples --config validation/runs.toml \
  --run adk-native,adk-agentspan --judge
```

### Preview without running

```bash
uv run python3 -m validation.scripts.run_examples --config validation/runs.toml \
  --run smoke-test-openai-agentspan --dry-run
```

### Judge existing results

```bash
uv run python3 -m validation.scripts.judge_results --run-dir validation/output/run_20250101_120000_abc123/
```

---

## All Run Names

| Run | Group | Model | Mode |
|-----|-------|-------|------|
| `openai-native` | OPENAI_EXAMPLES (10) | gpt-4o | Native |
| `openai-agentspan` | OPENAI_EXAMPLES (10) | gpt-4o | Agentspan |
| `anthropic-agentspan` | OPENAI_EXAMPLES (10) | claude-sonnet-4-20250514 | Agentspan |
| `claude-sonnet-4-6-agentspan` | OPENAI_EXAMPLES (10) | claude-sonnet-4-6 | Agentspan |
| `gpt-5-4-agentspan` | OPENAI_EXAMPLES (10) | gpt-5.4 | Agentspan |
| `smoke-test-openai-agentspan` | SMOKE_TEST (7) | gpt-4o | Agentspan |
| `smoke-test-anthropic-agentspan` | SMOKE_TEST (7) | claude-sonnet-4-20250514 | Agentspan |
| `smoke-test-claude-sonnet-4-6-agentspan` | SMOKE_TEST (7) | claude-sonnet-4-6 | Agentspan |
| `adk-hello-native` | ADK_HELLO (1) | gemini-2.5-flash | Native |
| `adk-hello-agentspan` | ADK_HELLO (1) | gemini-2.5-flash | Agentspan |
| `adk-native` | ADK_EXAMPLES (32) | gemini-2.5-flash | Native |
| `adk-agentspan` | ADK_EXAMPLES (32) | gemini-2.5-flash | Agentspan |
| `langgraph-agentspan` | LANGGRAPH_EXAMPLES (43) | gpt-4o-mini | Agentspan |
| `langgraph-native` | LANGGRAPH_EXAMPLES (43) | gpt-4o-mini | Native |
| `langchain-agentspan` | LANGCHAIN_EXAMPLES (25) | gpt-4o-mini | Agentspan |
| `langchain-native` | LANGCHAIN_EXAMPLES (25) | gpt-4o-mini | Native |
| `lc-smoke-test-agentspan` | LC_SMOKE_TEST (8) | gpt-4o-mini | Agentspan |
| `lc-smoke-test-native` | LC_SMOKE_TEST (8) | gpt-4o-mini | Native |
| `lc-claude-sonnet-4-6-agentspan` | LC_SMOKE_TEST (8) | claude-sonnet-4-6 | Agentspan |
| `lc-claude-sonnet-4-6-native` | LC_SMOKE_TEST (8) | claude-sonnet-4-6 | Native |
| `react-agent-agentspan` | REACT_AGENT_EXAMPLES (2) | gpt-4o-mini | Agentspan |
| `react-agent-native` | REACT_AGENT_EXAMPLES (2) | gpt-4o-mini | Native |
| `react-agent-all-agentspan` | REACT_AGENT_ALL (3) | gpt-4o-mini | Agentspan |
| `react-agent-all-native` | REACT_AGENT_ALL (3) | gpt-4o-mini | Native |

**Agentspan** = runs through Conductor orchestration. **Native** = runs directly via SDK, bypasses Conductor. Pair them with `--judge` to compare.

---

## Example Groups

| Group | Count | Contents |
|-------|-------|----------|
| `SMOKE_TEST` | 7 | Basic + structured output + handoffs (OpenAI + ADK) |
| `OPENAI_EXAMPLES` | 10 | Full OpenAI Agents SDK suite |
| `ADK_HELLO` | 1 | Single hello-world for ADK debugging |
| `ADK_EXAMPLES` | 32 | Full Google ADK suite |
| `LC_SMOKE_TEST` | 8 | 5 LangGraph + 3 LangChain basics (incl. react-agent examples) |
| `LANGGRAPH_EXAMPLES` | 43 | Full LangGraph suite (incl. create_react_agent examples) |
| `LANGCHAIN_EXAMPLES` | 25 | Full LangChain suite |
| `REACT_AGENT_EXAMPLES` | 2 | create_react_agent: basic + system prompt (OpenAI) |
| `REACT_AGENT_ALL` | 3 | create_react_agent: basic + system prompt + multi-model (Anthropic) |
| `PASSING_EXAMPLES` | 37 | Stable ADK-style examples |
| `SLOW_EXAMPLES` | 4 | >2 min each (08, 13, 23, 31) |
| `HITL_EXAMPLES` | 4 | Require stdin input (02, 09, 09b, 09c) |
| `KNOWN_FAILURES` | 6 | Server/config issues — skip these |

---

## Output

Each run creates `validation/output/run_{timestamp}_{id}/`:

```
run_20250101_120000_abc123/
├── openai/
│   ├── results.csv
│   └── outputs/
├── anthropic/
│   └── ...
└── judge/
    ├── report.html   ← open this — interactive heatmap + side-by-side diffs
    ├── report.md
    └── results.csv
```

Open `judge/report.html` in a browser for the full interactive dashboard.

---

## TOML Config Reference

`validation/runs.toml` (gitignored). Copy from `validation/runs.toml.example`.

```toml
[defaults]
timeout = 300       # per-example timeout (seconds)
parallel = true
max_workers = 8
server_url = "http://localhost:8080/api"

[judge]
baseline_run = "openai"   # run used as comparison baseline
model = "gpt-4o-mini"

[runs.my-run]
group = "SMOKE_TEST"
model = "openai/gpt-4o"
# native = true           # bypass Conductor, run via SDK directly
```

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | — | OpenAI/LangGraph/LangChain examples + judge |
| `ANTHROPIC_API_KEY` | — | Anthropic model examples |
| `GOOGLE_API_KEY` | — | ADK/Gemini examples |
| `AGENTSPAN_SERVER_URL` | `http://localhost:8080/api` | Conductor server |
| `AGENTSPAN_AUTH_KEY` | — | Auth (if required) |
| `AGENTSPAN_AUTH_SECRET` | — | Auth secret (if required) |
| `JUDGE_LLM_MODEL` | `gpt-4o-mini` | Override judge model |
| `JUDGE_MAX_OUTPUT_CHARS` | `3000` | Truncate outputs before judging |
| `JUDGE_MAX_TOKENS` | `300` | Max tokens per judge response |
| `JUDGE_MAX_CALLS` | `0` (unlimited) | Budget cap on judge API calls |
| `JUDGE_RATE_LIMIT` | `0.5` | Seconds between judge calls |

---

## CLI Reference

```
run_examples.py  --config PATH
                 [--run NAMES]          comma-separated run names
                 [--judge]              run cross-run judge after execution
                 [--dry-run]            preview without executing
                 [--output-dir DIR]     default: validation/output/
                 [--resume [RUN_DIR]]   skip already-completed examples
                 [--retry-failed DIR]   re-run only failed examples
                 [--list-groups]        list available groups and exit

judge_results.py --run-dir PATH         multi-run parent directory
                 [--judge-model MODEL]  override judge model
```
