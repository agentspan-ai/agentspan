# E2E Validation: Multi-Provider Example Runner

Runs every SDK example against all configured models (OpenAI, Anthropic, ADK), scores outputs via an LLM judge.

## Prerequisites

- Python 3.11+
- Conductor server running (`AGENTSPAN_SERVER_URL`, default `http://localhost:8080/api`)
- Server configured with OpenAI, Anthropic, and Google provider keys
- For judging: `OPENAI_API_KEY` in env or `.env`

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

# Named group from validation/groups.py
python3 -m validation.scripts.run_examples --group=SMOKE_TEST
python3 -m validation.scripts.run_examples --group=PASSING_EXAMPLES
python3 -m validation.scripts.run_examples --group=HITL_EXAMPLES
python3 -m validation.scripts.run_examples --group=OPENAI_EXAMPLES
python3 -m validation.scripts.run_examples --group=ADK_EXAMPLES
```

## Judge Examples

```bash
# Judge latest run
python3 -m validation.scripts.judge_results

# Skip already-scored providers (faster re-runs)
python3 -m validation.scripts.judge_results --skip-judged

# Use a different judge model
python3 -m validation.scripts.judge_results --judge-model gpt-4o

# Judge a specific CSV
python3 -m validation.scripts.judge_results --csv validation/output/run_*/results.csv
```

Output includes `report.html` — open in browser for interactive dashboard with filters, sorting, score distribution, baseline comparison, and cost breakdown.

## Example Groups

Defined in `validation/groups.py`. Use `--group=NAME` to filter:

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
- `results.csv` — execution + judge data (including baseline comparison scores)
- `report.md` — human-readable summary
- `report.html` — interactive dashboard (filters, sorting, score distribution, cost breakdown, baseline comparison, regression markers)
- `meta.json` — timing, costs, regressions, judge config
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
  --group NAME          Run only examples in named group from groups.py
```

### judge_results.py

```
python3 -m validation.scripts.judge_results [options]

Options:
  --csv PATH            Path to validation CSV (default: latest in output dir)
  --output-dir DIR      Output directory (default: validation/output/)
  --judge-model MODEL   Override judge model (default: from config/env)
  --skip-judged         Skip providers that already have judge scores
```

## Makefile Targets

| Target | Command | Description |
|--------|---------|-------------|
| `validate` | `python3 -m validation.scripts.run_examples` | Run all examples |
| `validate-judge` | `python3 -m validation.scripts.judge_results` | Judge latest results |
| `validate-all` | `validate` then `validate-judge` | Full pipeline |

## Environment

| Variable | Used by | Source | Default | Purpose |
|----------|---------|--------|---------|---------|
| `AGENTSPAN_SERVER_URL` | run_examples.py | `.env` or env | `http://localhost:8080/api` | Server health check |
| `AGENTSPAN_LLM_MODEL` | examples (via subprocess) | Set by script | — | Model override |
| `OPENAI_API_KEY` | judge_results.py | .env or env | — | Judge API calls |
| `EXAMPLE_TIMEOUT` | run_examples.py | env (optional) | 300 | Default timeout |
| `JUDGE_LLM_MODEL` | judge_results.py | .env or env | `gpt-4o-mini` | Judge LLM model |
| `JUDGE_MAX_OUTPUT_CHARS` | judge_results.py | .env or env | 3000 | Truncate outputs before judging |
| `MAX_JUDGE_CALLS` | judge_results.py | .env or env | 0 (unlimited) | Budget cap on judge calls |
| `JUDGE_RATE_LIMIT` | judge_results.py | .env or env | 0.5 | Seconds between judge calls |
| `BASELINE_MODEL` | judge_results.py | .env or env | `openai` | Baseline provider for comparison |

## Module Structure

```
validation/
├── _env.py              # find_dotenv() helper
├── config.py            # constants, model IDs, CSV schemas, pricing, Settings
├── groups.py            # example groups, HITL stdin mappings
├── models.py            # Example, RunResult models
├── parsing.py           # stdout parsing, prompt extraction, raw output loading
├── discovery.py         # example discovery, dependency checking
├── runner.py            # execution, health check, match computation
├── judge.py             # LLM judge calls, baseline comparison, confidence
├── reporting.py         # markdown report generation, CSV lookup
├── report_html.py       # interactive HTML report (Jinja2)
├── analysis.py          # cost estimation, regression detection
├── persistence.py       # last-run persistence, output hash caching
├── templates/
│   └── report.html.j2   # HTML report template
├── scripts/
│   ├── run_examples.py  # CLI: Phase 1 (execution)
│   └── judge_results.py # CLI: Phase 2 (judging)
├── README.md            # this file
└── DESIGN.md            # architecture and internals
```

## Wishlist

- ~~Improve concurrency~~ (done: parallel mode with dedicated servers)
- ~~Use `openai` as baseline model for other models~~ (done: baseline comparison)
- Validates end to end state of workflow creation by LLM Model is correct

### Judge Quality TODOs

- Multi-judge consensus (2-3 calls, median score)
- Judge model comparison (gpt-4o vs gpt-4o-mini consistency)
- Custom rubrics per example
- Retry on transient API failures (429/500 + backoff)
- Parallel judging (ThreadPoolExecutor + semaphore rate limiter)
