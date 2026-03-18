#!/usr/bin/env python3
"""Cross-run LLM judge. Reads outputs from multi-run parent directory,
scores each run individually (1-5), compares against baseline.

Usage:
    python3 -m validation.scripts.judge_results                              # latest run
    python3 -m validation.scripts.judge_results --run-dir path/to/run_*/
    python3 -m validation.scripts.judge_results --judge-model gpt-4o
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from validation.config import SCRIPT_DIR, Settings


def _resolve_latest(output_dir: Path) -> Path | None:
    """Resolve the latest run directory via symlink or glob."""
    latest = output_dir / "latest"
    if latest.is_symlink() or latest.exists():
        resolved = latest.resolve()
        if resolved.is_dir():
            return resolved
    # Fallback: newest run_* dir
    dirs = sorted(output_dir.glob("run_*"), key=lambda d: d.name)
    return dirs[-1] if dirs else None


def main():
    settings = Settings.from_env()

    parser = argparse.ArgumentParser(description="Cross-run judge for validation results")
    parser.add_argument(
        "--run-dir",
        type=str,
        default=None,
        help="Multi-run parent directory (default: latest run)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(SCRIPT_DIR / "output"),
        help="Output directory to find latest run (default: validation/output)",
    )
    parser.add_argument(
        "--judge-model", type=str, default=None, help="Override judge model (default: from config)"
    )
    args = parser.parse_args()

    if args.judge_model:
        settings.judge_model = args.judge_model

    if not settings.openai_api_key:
        print("ERROR: OPENAI_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    from validation.judge import judge_across_runs
    from validation.toml_config import JudgeConfig

    if args.run_dir:
        run_dir = Path(args.run_dir)
    else:
        run_dir = _resolve_latest(Path(args.output_dir))
        if not run_dir:
            print("ERROR: No runs found. Run examples first or pass --run-dir.", file=sys.stderr)
            sys.exit(1)
        print(f"  Using latest run: {run_dir}")

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
