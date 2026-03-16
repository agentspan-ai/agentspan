# Claude Code Instructions

## Python

- Use `uv` for all package management — never `pip`. Use `uv run` to execute scripts, `uv add` to add deps.
- Use `dataclasses` for models and config. Use `os.environ.get()` for env var loading.
- Pydantic is NOT a dependency — only use when required by external frameworks (e.g., OpenAI structured output).
- Config classes use `from_env()` classmethod pattern (see `AgentConfig`).
- Format with `ruff format`, lint with `ruff check`.

## Plans

- Always break plans into multiple stages.
- Validation/verification is a separate stage that comes BEFORE documentation.
- Documentation updates are a separate final stage.

## Validation Module

- Install deps: `uv sync --extra validation` (includes `python-dotenv` for `.env` loading)
- If `python-dotenv` is installed, validation scripts auto-load `.env` files. Otherwise, export env vars directly.
- Config: `Settings.from_env()` pattern — see `validation/config.py`
- Env template: `validation/.env.example`
- Run examples: `uv run python3 -m validation.scripts.run_examples`
- Run judge: `uv run python3 -m validation.scripts.judge_results`
- Groups defined in `validation/groups.py` — use `--group=NAME` to filter.
- Quick smoke test: `--group=SMOKE_TEST`
- Native mode (no server): `--native` — runs via framework SDK directly, bypasses Conductor
  - `uv run python3 -m validation.scripts.run_examples --group=SMOKE_TEST --native --only openai`
  - Shim: `uv run python3 -m validation.native.shim <example_script.py>`

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
