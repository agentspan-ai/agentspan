# Claude Code Instructions

## Python

- Use `uv` for all package management — never `pip`. Use `uv run` to execute scripts, `uv add` to add deps.
- Use `pydantic` for all models and config classes — no plain dataclasses or hand-rolled validation.
- Format with `ruff format`, lint with `ruff check`.

## Validation Module

- Install deps: `uv sync --extra validation`
- Run examples: `uv run python3 -m validation.scripts.run_examples`
- Run judge: `uv run python3 -m validation.scripts.judge_results`
- Groups defined in `validation/groups.py` — use `--group=NAME` to filter.
- Quick smoke test: `--group=SMOKE_TEST`

### Judge Config

| Variable | Default | Purpose |
|----------|---------|---------|
| `JUDGE_LLM_MODEL` | gpt-4o-mini | LLM model for judging |
| `JUDGE_MAX_OUTPUT_CHARS` | 3000 | Truncate outputs before judging |
| `MAX_JUDGE_CALLS` | 0 (unlimited) | Budget cap on judge API calls |
| `JUDGE_RATE_LIMIT` | 0.5 | Seconds between judge calls |
| `BASELINE_MODEL` | openai | Baseline provider for comparison |

### Judge CLI Flags

- `--judge-model MODEL` — override judge model
- `--skip-judged` — skip providers with existing scores

### Output

- `report.html` — interactive dashboard with filters, sorting, score distribution, cost breakdown, baseline comparison, regression markers

## Reference

- SDK API docs: `AGENTS.md`
- Design docs: `docs/`
