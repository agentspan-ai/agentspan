#!/usr/bin/env python3
"""Cross-run LLM judge. Reads outputs from multi-run parent directory,
scores each run individually (1-5), compares against baseline.

Usage:
    python3 -m validation.scripts.judge_results --run-dir path/to/run_*/
    python3 -m validation.scripts.judge_results --run-dir path/to/run_*/ --judge-model gpt-4o
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from validation.config import Settings


def main():
    settings = Settings.from_env()

    parser = argparse.ArgumentParser(description="Cross-run judge for validation results")
    parser.add_argument(
        "--run-dir",
        type=str,
        required=True,
        help="Multi-run parent directory containing per-run sub-dirs",
    )
    parser.add_argument(
        "--judge-model", type=str, default=None, help="Override judge model (default: from config)"
    )
    args = parser.parse_args()

    if args.judge_model:
        settings.judge_model = args.judge_model

    if not settings.openai_api_key:
        print("ERROR: OPENAI_API_KEY not set. Export it or add to .env", file=sys.stderr)
        sys.exit(1)

    from validation.cross_judge import judge_across_runs
    from validation.toml_config import JudgeConfig

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(f"ERROR: Run directory not found: {run_dir}", file=sys.stderr)
        sys.exit(1)

    # Load config.toml from run dir if exists, else use defaults
    config_path = run_dir / "config.toml"
    if config_path.exists():
        from validation.toml_config import load_toml_config

        config = load_toml_config(config_path)
        judge_config = config.judge
    else:
        judge_config = JudgeConfig(model=settings.judge_model)

    if args.judge_model:
        judge_config.model = args.judge_model

    judge_across_runs(run_dir, judge_config, settings)


if __name__ == "__main__":
    main()
