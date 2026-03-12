# Claude Code Instructions

## Python

- Use `uv` for all package management — never `pip`. Use `uv run` to execute scripts, `uv add` to add deps.
- Use `pydantic` for all models and config classes — no plain dataclasses or hand-rolled validation.
- Format with `ruff format`, lint with `ruff check`.

## Validation Module

- Install deps: `uv sync --extra validation`
- Run examples: `uv run python3 -m validation.scripts.run_examples`
- Run judge: `uv run python3 -m validation.scripts.judge_results`
- Groups defined in `validation/.env` — use `--group=NAME` to filter.
- Quick smoke test: `--group=SMOKE_TEST`

## Reference

- SDK API docs: `AGENTS.md`
- Design docs: `docs/`
