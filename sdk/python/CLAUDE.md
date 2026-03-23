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

- Install deps: `uv sync --extra validation`
- Config: `Settings.from_env()` reads env vars — see `validation/config.py`
- Groups defined in `validation/groups.py` — use `--group=NAME` to filter in TOML config.

### TOML Config (required)

All validation runs require a TOML config file. One run = one model, executed concurrently.

- Config: `validation/runs.toml` (gitignored), example: `validation/runs.toml.example`
- Run all: `uv run python3 -m validation.scripts.run_examples --config runs.toml`
- Run subset: `--run openai,anthropic`
- Dry-run: `--config runs.toml --dry-run`
- With judge: `--config runs.toml --judge`
- Cross-run judge only: `uv run python3 -m validation.scripts.judge_results --run-dir <parent_dir>`
- Output: `output/run_*/` parent with sub-dirs per run + `judge/` for cross-run results + `report.html`

### Judge Config

Configured in `[judge]` section of TOML config, or via env vars:

| Variable | Default | Purpose |
|----------|---------|---------|
| `JUDGE_LLM_MODEL` | gpt-4o-mini | LLM model for judging |
| `JUDGE_MAX_OUTPUT_CHARS` | 3000 | Truncate outputs before judging |
| `JUDGE_MAX_TOKENS` | 300 | Max tokens for judge response |
| `JUDGE_MAX_CALLS` | 0 (unlimited) | Budget cap on judge API calls |
| `JUDGE_RATE_LIMIT` | 0.5 | Seconds between judge calls |

### Output

- `judge/report.html` — cross-run interactive dashboard with score heatmap, side-by-side outputs, filters, dark mode

## Reference

- SDK API docs: `../../docs/python-sdk/api-reference.md`
- Design docs: `../../docs/`
