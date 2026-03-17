# E2E Validation: Multi-Run Example Runner

Runs SDK examples against configured models via TOML config. One run = one model, concurrent execution, cross-run LLM judge.

## Prerequisites

- Python 3.11+
- Conductor server running (for server-mode runs)
- For judging: `OPENAI_API_KEY` in env or `.env`

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
python3 -m validation.scripts.run_examples --config validation/runs.toml --run openai-native

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

[judge]          # cross-run judge settings
baseline_run = "openai-server"
model = "gpt-4o-mini"

[runs.openai-server]
model = "openai/gpt-4o"
group = "SMOKE_TEST"

[runs.openai-native]
model = "openai/gpt-4o"
native = true
group = "SMOKE_TEST"
```

## Example Groups

Defined in `validation/groups.py`. Set `group = "NAME"` in TOML run config:

| Group | Examples | Notes |
|-------|----------|-------|
| **SMOKE_TEST** | 8 examples | Quick sanity check |
| **PASSING_EXAMPLES** | 40 examples | Fast, reliable |
| **SLOW_EXAMPLES** | 08, 13, 23, 31 | >2 min each |
| **HITL_EXAMPLES** | 02, 09, 09b, 09c | Stdin piped via HITL_STDIN |
| **KNOWN_FAILURES** | 14, 21, 22, 33_ext, 34, 39c | Server/config issues |
| **OPENAI_EXAMPLES** | 10 examples | Requires `openai-agents` package |
| **ADK_EXAMPLES** | 32 examples | Requires `google-adk` package |

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
| `OPENAI_API_KEY` | judge | — | Judge API calls |
| `JUDGE_LLM_MODEL` | judge | `gpt-4o-mini` | Judge model |
| `JUDGE_MAX_OUTPUT_CHARS` | judge | 3000 | Truncate before judging |
| `MAX_JUDGE_CALLS` | judge | 0 (unlimited) | Budget cap |
| `JUDGE_RATE_LIMIT` | judge | 0.5 | Seconds between calls |

## Module Structure

```
validation/
├── _env.py              # find_dotenv() helper
├── config.py            # constants, CSV schema, Settings
├── toml_config.py       # TOML multi-run config parser
├── orchestrator.py      # multi-run orchestrator
├── cross_judge.py       # cross-run judge + baseline comparison
├── groups.py            # example groups, HITL stdin mappings
├── models.py            # Example, RunResult, SingleResult
├── parsing.py           # stdout parsing, prompt extraction
├── discovery.py         # example discovery, dependency checking
├── runner.py            # single example execution, health check
├── execution.py         # concurrent example execution
├── judge.py             # LLM judge calls (individual + comparison)
├── reporting.py         # report helpers
├── report_html.py       # cross-run HTML report (Jinja2)
├── persistence.py       # last-run persistence, hash caching
├── output.py            # file writing (CSV, outputs, symlinks)
├── display.py           # terminal display helpers
├── server_pool.py       # dedicated servers for parallel execution
├── runs.toml.example    # annotated TOML config template
├── templates/
│   └── cross_report.html.j2  # cross-run HTML report template
├── native/
│   ├── shim.py          # monkey-patch for native execution
│   └── openai_runner.py # OpenAI native runner
├── scripts/
│   ├── run_examples.py  # CLI: execution
│   └── judge_results.py # CLI: cross-run judging
├── README.md            # this file
└── DESIGN.md            # architecture and internals
```

## Wishlist

- Validates end to end state of workflow creation by LLM Model is correct

### Judge Quality TODOs

- Multi-judge consensus (2-3 calls, median score)
- Judge model comparison (gpt-4o vs gpt-4o-mini consistency)
- Custom rubrics per example
- Retry on transient API failures (429/500 + backoff)
- Parallel judging (ThreadPoolExecutor + semaphore rate limiter)
