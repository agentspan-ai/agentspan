#!/usr/bin/env python3
"""Run SDK examples — TOML multi-run mode or legacy single-command mode.

TOML mode (new):
    python3 -m validation.scripts.run_examples --config runs.toml
    python3 -m validation.scripts.run_examples --config runs.toml --run openai-native
    python3 -m validation.scripts.run_examples --config runs.toml --dry-run
    python3 -m validation.scripts.run_examples --config runs.toml --judge

Legacy mode (no --config):
    python3 -m validation.scripts.run_examples              # all examples (sequential)
    python3 -m validation.scripts.run_examples -j           # parallel mode
    python3 -m validation.scripts.run_examples --group=SMOKE_TEST
    python3 -m validation.scripts.run_examples --only openai --group=SMOKE_TEST
    python3 -m validation.scripts.run_examples --resume
    python3 -m validation.scripts.run_examples --list-groups
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from validation.config import MODELS, SCRIPT_DIR, Settings, build_csv_columns
from validation.discovery import discover_examples
from validation.display import list_groups, print_summary_table
from validation.execution import run_parallel, run_sequential
from validation.output import update_latest_symlink, write_json_results
from validation.persistence import (
    completed_examples,
    failed_examples,
    load_last_run,
    resolve_run_dir,
    save_last_run,
    sort_slowest_first,
)
from validation.reporting import _format_duration
from validation.runner import check_server_health


def main():
    parser = argparse.ArgumentParser(description="Run SDK examples with all configured models")
    parser.add_argument("prefixes", nargs="*", help="Example prefix filters (e.g. 01 03)")

    # TOML mode args
    parser.add_argument("--config", type=str, default=None, help="Path to TOML multi-run config")
    parser.add_argument(
        "--run", type=str, default=None, help="Comma-separated run names to execute (TOML mode)"
    )
    parser.add_argument(
        "--judge", action="store_true", help="Run cross-run judge after execution (TOML mode)"
    )

    # Shared args
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

    # Legacy mode args
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.environ.get("EXAMPLE_TIMEOUT", "300")),
        help="Per-example timeout in seconds (default: 300)",
    )
    parser.add_argument("--retries", type=int, default=0, help="Retries on failure (default: 0)")
    parser.add_argument(
        "--group", type=str, default=None, help="Run only examples in named group from groups.py"
    )
    parser.add_argument(
        "-j",
        "--parallel",
        action="store_true",
        help="Run examples in parallel with dedicated servers per provider",
    )
    parser.add_argument("--base-port", type=int, default=8080, help="Base port for server pool")
    parser.add_argument(
        "--max-workers", type=int, default=8, help="Max concurrent examples (default: 8)"
    )
    parser.add_argument(
        "--only", type=str, default=None, help="Run only this provider (e.g. openai)"
    )
    parser.add_argument(
        "--native", action="store_true", help="Run via framework SDK directly (no Conductor server)"
    )
    parser.add_argument(
        "--format", type=str, choices=["csv", "json"], default="csv", help="Output format"
    )

    args = parser.parse_args()

    if args.list_groups:
        list_groups()
        return

    # Route to TOML mode or legacy mode
    if args.config:
        _run_toml_mode(args)
    else:
        _run_legacy_mode(args)


def _run_toml_mode(args):
    """TOML multi-run mode."""
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


def _run_legacy_mode(args):
    """Legacy single-command mode (no TOML config)."""
    settings = Settings.from_env()
    start_time = time.monotonic()

    # Determine active models
    if args.only:
        if args.only not in MODELS:
            print(
                f"ERROR: Unknown model '{args.only}'. Available: {', '.join(MODELS)}",
                file=sys.stderr,
            )
            sys.exit(1)
        active_models = {args.only: MODELS[args.only]}
    else:
        active_models = settings.get_active_models()

    if not active_models:
        print("ERROR: No models available. Set API keys in .env or environment.", file=sys.stderr)
        sys.exit(1)

    csv_columns = build_csv_columns(active_models)

    # Discover examples
    examples = discover_examples(args.prefixes, args.group)
    if not examples:
        print("No examples to run.")
        sys.exit(0)

    # Load last run for sorting + resume/retry
    last_run = load_last_run()
    last_run_lock = threading.Lock()
    examples = sort_slowest_first(examples, last_run)

    # Resume
    run_dir = None
    if args.resume is not None:
        run_dir = resolve_run_dir(args.resume or None, args.output_dir)
        if run_dir:
            done = completed_examples(run_dir, active_models)
            before = len(examples)
            examples = [ex for ex in examples if ex.name not in done]
            print(f"  Resuming: {before - len(examples)} already done, {len(examples)} remaining")
            if not examples:
                print("  All examples already completed.")
                return
        else:
            print("  No previous run found, starting fresh.")

    # Retry-failed
    if args.retry_failed is not None:
        run_dir = resolve_run_dir(args.retry_failed or None, args.output_dir)
        if run_dir:
            fails = failed_examples(last_run)
            examples = [ex for ex in examples if ex.name in fails]
            print(f"  Retrying {len(examples)} failed examples")
            if not examples:
                print("  No failed examples to retry.")
                return
        else:
            print("  No previous run found, starting fresh.")

    # Setup run dir
    if not run_dir:
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        run_id = uuid.uuid4().hex[:4]
        run_dir = Path(args.output_dir) / f"run_{timestamp}_{run_id}"

    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    csv_path = run_dir / "results.csv"
    last_run["run_dir"] = str(run_dir)

    # Server pool for parallel mode
    pool = None
    server_urls = None

    if args.parallel:
        from validation.server_pool import ServerPool

        pool = ServerPool(base_port=args.base_port)

    # Dry-run
    if args.dry_run:
        print("=" * 50)
        print(" DRY RUN — no examples will be executed")
        print("=" * 50)
        print(
            f"\n  Mode: {'native' if args.native else ('parallel' if args.parallel else 'sequential')}"
        )
        print(f"  Models ({len(active_models)}):")
        if args.parallel:
            port = args.base_port
            for name, model_id in active_models.items():
                print(f"    {name}: {model_id} → port {port}")
                port += 1
        else:
            for name, model_id in active_models.items():
                print(f"    {name}: {model_id}")
        print(f"\n  Examples ({len(examples)}):")
        for ex in examples:
            lr = last_run.get("examples", {}).get(ex.name, {})
            dur = lr.get("max_duration_s")
            dur_str = f" [{dur:.1f}s]" if dur else ""
            print(f"    {ex.name}{dur_str}")
        print(f"\n  Output: {run_dir}")
        print(f"  Timeout: {args.timeout}s | Workers: {args.max_workers}")
        return

    # Banner
    mode = "native" if args.native else ("parallel" if args.parallel else "sequential")
    group_label = f" (group: {args.group})" if args.group else ""
    print("=" * 50)
    print(f" Validation: {len(examples)} examples × {len(active_models)} models{group_label}")
    print(f" Models: {', '.join(active_models.values())}")
    print(f" Mode: {mode}" + (f" (workers={args.max_workers})" if args.parallel else ""))
    print(f" Timeout: {args.timeout}s | Retries: {args.retries}")
    print(f" Output: {run_dir}")
    print("=" * 50)
    print()

    if args.parallel:
        log_dir = run_dir / "logs"
        try:
            pool.start(active_models, log_dir=log_dir)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        server_urls = pool.get_server_urls()
        for name, url in server_urls.items():
            srv = pool.servers[name]
            reused = "reused" if not srv.we_started else "started"
            print(f"  {name}: {url} ({reused})")
        print()
    elif not args.native:
        if not check_server_health():
            print("ERROR: Server not reachable. Start it first.", file=sys.stderr)
            sys.exit(1)

    # CSV header
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=csv_columns)
            writer.writeheader()

    # Run
    try:
        if args.parallel:
            all_results = run_parallel(
                examples,
                active_models,
                csv_columns,
                csv_path,
                outputs_dir,
                args.timeout,
                args.retries,
                args.max_workers,
                server_urls,
                last_run,
                last_run_lock,
                native=args.native,
            )
        else:
            all_results = run_sequential(
                examples,
                active_models,
                csv_columns,
                csv_path,
                outputs_dir,
                args.timeout,
                args.retries,
                last_run,
                last_run_lock,
                native=args.native,
            )
    finally:
        if pool:
            pool.shutdown()

    # JSON output
    if args.format == "json":
        write_json_results(run_dir / "results.json", all_results)

    # Save timing metadata
    elapsed = time.monotonic() - start_time
    meta_path = run_dir / "meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    meta["validation_duration_s"] = round(elapsed, 1)
    meta_path.write_text(json.dumps(meta, indent=2))

    update_latest_symlink(Path(args.output_dir), run_dir)
    save_last_run(last_run, last_run_lock)

    # Summary
    print()
    print_summary_table(all_results, active_models)
    print()
    print("=" * 50)
    print(f" Run directory: {run_dir}")
    print(f" Total time: {_format_duration(elapsed)}")
    print("=" * 50)


if __name__ == "__main__":
    main()
