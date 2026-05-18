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
  --judge               Run LLM judge after execution
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
- Per-run sub-directories with `run_results.json` + `preflight.log` + `outputs/`
- `judge/report.html` — interactive dashboard with score heatmap, side-by-side outputs
- `judge/judge_results.json` — per-run scores + baseline comparison
- `judge/report.md` — markdown summary
- `meta.json` — timing and run metadata

## Environment

| Variable | Used by | Default | Purpose |
|----------|---------|---------|---------|
| `OPENAI_API_KEY` | judge | — | Judge API calls |
| `JUDGE_LLM_MODEL` | judge | `gpt-4o-mini` | Judge model |
| `JUDGE_MAX_OUTPUT_CHARS` | judge | 3000 | Truncate before judging |
| `JUDGE_MAX_TOKENS` | judge | 300 | Max tokens for judge response |
| `JUDGE_MAX_CALLS` | judge | 0 (unlimited) | Budget cap |
| `JUDGE_RATE_LIMIT` | judge | 0.5 | Seconds between calls |


## Wishlist

- Validates end to end state of agent creation by LLM Model is correct

### Judge Quality TODOs

- Multi-judge consensus (2-3 calls, median score)
- Judge model comparison (gpt-4o vs gpt-4o-mini consistency)
- Custom rubrics per example
- Retry on transient API failures (429/500 + backoff)
- Parallel judging (ThreadPoolExecutor + semaphore rate limiter)
