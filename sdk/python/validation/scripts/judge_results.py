#!/usr/bin/env python3
"""LLM-as-judge evaluation. Reads CSV + raw outputs from run_examples.py.

Scores each completed provider individually (1-5), then compares non-baseline
providers against the baseline (default: openai). Generates CSV, markdown report,
and interactive HTML report with dashboard, filters, and cost breakdown.

Features: output hash caching, regression detection, rate limiting, call budget.

Usage:
    python3 -m validation.scripts.judge_results                          # latest CSV
    python3 -m validation.scripts.judge_results --csv path/to/results.csv
    python3 -m validation.scripts.judge_results --skip-judged            # skip already-scored rows
    python3 -m validation.scripts.judge_results --judge-model gpt-4o    # override judge model
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

from validation.analysis import compute_costs, detect_regressions
from validation.config import MODELS, SCRIPT_DIR, Settings, build_csv_columns
from validation.judge import JudgeState, judge_row
from validation.output import write_judge_outputs
from validation.persistence import load_last_run, save_last_run
from validation.reporting import _format_duration, find_latest_csv


def main():
    settings = Settings.from_env()

    parser = argparse.ArgumentParser(description="Judge validation results with LLM")
    parser.add_argument("--csv", type=str, help="Path to validation CSV (default: latest)")
    parser.add_argument(
        "--output-dir", type=str, default=str(SCRIPT_DIR / "output"), help="Output directory"
    )
    parser.add_argument(
        "--judge-model", type=str, default=None, help="Override judge model (default: from config)"
    )
    parser.add_argument(
        "--skip-judged",
        action="store_true",
        help="Skip providers that already have judge scores",
    )
    parser.add_argument(
        "--run-dir",
        type=str,
        default=None,
        help="Multi-run parent directory for cross-run judging",
    )
    args = parser.parse_args()

    if args.judge_model:
        settings.judge_model = args.judge_model

    # Cross-run judging mode
    if args.run_dir:
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
        return

    start_time = time.monotonic()

    if not settings.openai_api_key:
        print(
            "ERROR: OPENAI_API_KEY not set. Export it or add to .env",
            file=sys.stderr,
        )
        sys.exit(1)

    output_dir = Path(args.output_dir)

    # Find CSV
    if args.csv:
        csv_path = Path(args.csv)
    else:
        csv_path = find_latest_csv(output_dir)
        if not csv_path:
            print("ERROR: No validation CSV found. Run run_examples.py first.", file=sys.stderr)
            sys.exit(1)

    run_dir = csv_path.parent
    outputs_dir = run_dir / "outputs"

    print(f"Reading: {csv_path}")
    print(f"Judge model: {settings.judge_model}")
    if args.skip_judged:
        print("Skipping already-judged providers")

    # Read existing CSV
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No rows in CSV.")
        sys.exit(0)

    print(f"Found {len(rows)} examples")

    # Load previous last_run for regression detection + hash cache
    prev_last_run = load_last_run()
    last_run = dict(prev_last_run)
    last_run["run_dir"] = str(run_dir)

    # Baseline validation
    baseline = settings.baseline_model
    if baseline not in MODELS:
        print(f"WARNING: baseline_model '{baseline}' not in MODELS, disabling baseline comparison")
        baseline = None

    if baseline:
        print(f"Baseline model: {baseline}")
    print()

    # Judge each row
    state = JudgeState()
    for i, row in enumerate(rows):
        print(f"  [{i + 1}/{len(rows)}] {row['example']:<45s}", end="", flush=True)
        parts = judge_row(
            row,
            settings,
            outputs_dir,
            MODELS,
            prev_last_run,
            last_run,
            state,
            baseline=baseline,
            skip_judged=args.skip_judged,
        )
        print(f" {' '.join(parts)}")

    # Regression detection
    provider_list = list(MODELS.keys())
    regressions = detect_regressions(rows, prev_last_run, provider_list)
    if regressions:
        print()
        print(f"WARNING: {len(regressions)} regression(s) detected:")
        for r in regressions:
            print(r)

    # Build meta
    judge_elapsed = time.monotonic() - start_time
    meta_path = run_dir / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    validation_duration = meta.get("validation_duration_s")

    costs = compute_costs(rows, provider_list)
    meta.update(
        {
            "judge_duration_s": round(judge_elapsed, 1),
            "judge_model": settings.judge_model,
            "judge_calls": state.call_count,
            "cache_hits": state.cache_hits,
            "costs": costs,
        }
    )
    if baseline:
        meta["baseline_model"] = baseline
    if regressions:
        meta["regressions"] = regressions
    meta_path.write_text(json.dumps(meta, indent=2))

    save_last_run(last_run)

    # Extract history from last_run for sparklines
    history: dict[str, list[str]] = {}
    for name, entry in last_run.get("examples", {}).items():
        h = entry.get("history", [])
        if h:
            history[name] = h

    # Write CSV + reports
    judge_columns = build_csv_columns(MODELS, judge=True, baseline_model=baseline)
    write_judge_outputs(
        rows,
        csv_path,
        run_dir,
        judge_columns,
        provider_list,
        baseline,
        meta,
        validation_duration,
        history=history,
    )

    # Summary
    print()
    print("=" * 50)
    print(f" Run directory: {run_dir}")
    print(
        f" Judge calls: {state.call_count}"
        + (f" (cache hits: {state.cache_hits})" if state.cache_hits else "")
    )

    total_cost = sum(c["estimated_cost"] for c in costs.values())
    if total_cost > 0:
        print(f" Estimated cost: ${total_cost:.4f}")
        for p, c in costs.items():
            if c["tokens_total"] > 0:
                print(f"   {p}: {int(c['tokens_total'])} tokens, ${c['estimated_cost']:.4f}")

    if validation_duration:
        print(f" Validation: {_format_duration(validation_duration)}")
    print(f" Judge: {_format_duration(judge_elapsed)}")
    if validation_duration:
        print(f" Total: {_format_duration(validation_duration + judge_elapsed)}")
    print("=" * 50)


if __name__ == "__main__":
    main()
