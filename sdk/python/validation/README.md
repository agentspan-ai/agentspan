# E2E Validation: Multi-Provider Example Runner

Runs every SDK example against all configured models (OpenAI, Anthropic, ADK), scores outputs via an LLM judge.

## Prerequisites

- Python 3.11+
- Conductor server running (`AGENTSPAN_SERVER_URL`, default `http://localhost:8080/api`)
- Server configured with OpenAI, Anthropic, and Google provider keys
- For judging: `OPENAI_API_KEY` in env or `validation/.env.judge`

## Install

```bash
uv sync --extra validation
```

## Quick Start

```bash
# 1. Run all examples (× 3 models)
make validate

# 2. Judge the results
make validate-judge

# 3. Or do both in sequence
make validate-all
```

## Run Specific Examples

```bash
# All
python3 -m validation.scripts.run_examples

# Named group from validation/.env
python3 -m validation.scripts.run_examples --group=SMOKE_TEST
python3 -m validation.scripts.run_examples --group=PASSING_EXAMPLES
python3 -m validation.scripts.run_examples --group=HITL_EXAMPLES
python3 -m validation.scripts.run_examples --group=OPENAI_EXAMPLES
python3 -m validation.scripts.run_examples --group=ADK_EXAMPLES
```

## Example Groups

Defined in `validation/.env`. Use `--group=NAME` to filter:

| Group | Examples | Notes |
|-------|----------|-------|
| **SMOKE_TEST** | 8 examples | Quick sanity check across all frameworks |
| **PASSING_EXAMPLES** | 40 examples | Fast, reliable |
| **SLOW_EXAMPLES** | 08, 13, 23, 31 | >2 min each |
| **HITL_EXAMPLES** | 02, 09, 09b, 09c | Stdin piped via HITL_STDIN |
| **KNOWN_FAILURES** | 14, 21, 22, 33_ext, 34, 39c | Server/config issues |
| **OPENAI_EXAMPLES** | 10 examples | Requires `openai-agents` package |
| **ADK_EXAMPLES** | 32 examples | Requires `google-adk` package |

## Models

| Provider | Model ID |
|----------|----------|
| OpenAI | `openai/gpt-4o` |
| Anthropic | `anthropic/claude-sonnet-4-20250514` |
| ADK | `google_gemini/gemini-2.0-flash` |
| Judge | `gpt-4o-mini` |

## View Results

Each run creates `validation/output/run_{timestamp}_{id}/` containing:
- `results.csv` — execution + judge data
- `report.md` — human-readable summary
- `meta.json` — timing metadata
- `outputs/` — raw stdout/stderr per example per model

## CLI Reference

### run_examples.py

```
python3 -m validation.scripts.run_examples [prefixes...] [options]

Positional:
  prefixes              Example prefix filters (e.g., 01 03)

Options:
  --timeout SECONDS     Per-example timeout (default: 300, env: EXAMPLE_TIMEOUT)
  --retries N           Retry on failure (default: 0)
  --output-dir DIR      Output directory (default: validation/output/)
  --group NAME          Run only examples in named group from .env
```

### judge_results.py

```
python3 -m validation.scripts.judge_results [options]

Options:
  --csv PATH            Path to validation CSV (default: latest in output dir)
  --output-dir DIR      Output directory (default: validation/output/)
```

## Makefile Targets

| Target | Command | Description |
|--------|---------|-------------|
| `validate` | `python3 -m validation.scripts.run_examples` | Run all examples |
| `validate-judge` | `python3 -m validation.scripts.judge_results` | Judge latest results |
| `validate-all` | `validate` then `validate-judge` | Full pipeline |

## Environment

| Variable | Used by | Source | Purpose |
|----------|---------|--------|---------|
| `AGENTSPAN_SERVER_URL` | run_examples.py | `.env` or env | Server health check |
| `AGENT_LLM_MODEL` | examples (via subprocess) | Set by script | Model override |
| `OPENAI_API_KEY` | judge_results.py | .env.judge or env | Judge API calls |
| `EXAMPLE_TIMEOUT` | run_examples.py | env (optional) | Default timeout |

## Module Structure

```
validation/
├── config.py            # constants, model IDs, CSV schemas, Settings
├── models.py            # Example, RunResult models
├── parsing.py           # stdout parsing, prompt extraction, raw output loading
├── discovery.py         # example discovery, dependency checking
├── runner.py            # execution, health check, match computation
├── judge.py             # LLM judge calls, confidence computation
├── reporting.py         # report generation, CSV lookup
├── .env                 # example groups, HITL stdin (tracked)
├── .env.judge           # judge API keys (gitignored)
├── scripts/
│   ├── run_examples.py  # CLI: Phase 1 (execution)
│   └── judge_results.py # CLI: Phase 2 (judging)
├── README.md            # this file
└── DESIGN.md            # architecture and internals
```

## Wishlist

- Improve concurrency
  -- Run examples in parallel thread
  -- Spawn multiple agentspan server
- Use `openai` as baseline model for other models for result quality
- Validates end to end state of workflow creation by LLM Model is correct
