#!/usr/bin/env python3
"""Run SDK examples via TOML multi-run config.

Usage:
    python3 -m validation.scripts.run_examples --config runs.toml
    python3 -m validation.scripts.run_examples --config runs.toml --run openai-native
    python3 -m validation.scripts.run_examples --config runs.toml --dry-run
    python3 -m validation.scripts.run_examples --config runs.toml --judge
    python3 -m validation.scripts.run_examples --list-groups
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from validation.config import SCRIPT_DIR
from validation.discovery import discover_examples
from validation.display import list_groups


def main():
    parser = argparse.ArgumentParser(description="Run SDK examples via TOML config")
    parser.add_argument("--config", type=str, required=True, help="Path to TOML multi-run config")
    parser.add_argument(
        "--run", type=str, default=None, help="Comma-separated run names to execute"
    )
    parser.add_argument("--judge", action="store_true", help="Run cross-run judge after execution")
    parser.add_argument(
        "--output-dir", type=str, default=str(SCRIPT_DIR / "output"), help="Output directory"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument("--list-groups", action="store_true", help="List available groups and exit")
    parser.add_argument(
        "--resume", nargs="?", const="", default=None, help="Resume, skipping completed examples"
    )
    parser.add_argument(
        "--retry-failed", nargs="?", const="", default=None, help="Re-run only failed examples"
    )

    args = parser.parse_args()

    if args.list_groups:
        list_groups()
        return

    from validation.orchestrator import run_all
    from validation.toml_config import load_toml_config, resolve_runs

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    config = load_toml_config(config_path)
    selected = args.run.split(",") if args.run else None
    runs = resolve_runs(config, selected)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print("=" * 50)
        print(" DRY RUN — no examples will be executed")
        print("=" * 50)
        print(f"\n  Config: {config_path}")
        print(f"  Runs ({len(runs)}):")
        for r in runs:
            mode = "native" if r.native else "server"
            group_label = f" group={r.group}" if r.group else ""
            examples = discover_examples([], r.group)
            print(f"    {r.name}: {r.model} ({mode}){group_label} [{len(examples)} examples]")
            if r.secondary_model:
                print(f"      secondary: {r.secondary_model}")
            print(f"      timeout={r.timeout}s workers={r.max_workers} retries={r.retries}")

        if config.judge.baseline_run:
            print(f"\n  Judge baseline: {config.judge.baseline_run}")
            print(f"  Judge model: {config.judge.model}")
        print(f"\n  Output: {output_dir}")
        return

    # Banner
    print("=" * 50)
    print(f" Multi-Run Validation: {len(runs)} runs")
    for r in runs:
        mode = "native" if r.native else "server"
        group_label = f" ({r.group})" if r.group else ""
        print(f"   {r.name}: {r.model} [{mode}]{group_label}")
    print(f" Output: {output_dir}")
    print("=" * 50)
    print()

    run_all(
        config=config,
        runs=runs,
        output_dir=output_dir,
        resume=args.resume is not None,
        retry_failed=args.retry_failed is not None,
        judge_after=args.judge,
    )


if __name__ == "__main__":
    main()
