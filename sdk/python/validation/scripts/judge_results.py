#!/usr/bin/env python3
"""Evaluate validation outputs with LLM-as-judge. Reads CSV + raw outputs from run_examples.py.

Usage:
    python3 -m validation.scripts.judge_results                          # latest CSV
    python3 -m validation.scripts.judge_results --csv path/to/results.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

from validation.config import JUDGE_CSV_COLUMNS, MODELS, SCRIPT_DIR, Settings
from validation.judge import compute_confidence, judge_individual
from validation.parsing import extract_prompt, load_raw_output
from validation.reporting import _format_duration, find_latest_csv, generate_report


def main():
    settings = Settings()

    parser = argparse.ArgumentParser(description="Judge validation results with LLM")
    parser.add_argument("--csv", type=str, help="Path to validation CSV (default: latest)")
    parser.add_argument(
        "--output-dir", type=str, default=str(SCRIPT_DIR / "output"), help="Output directory"
    )
    args = parser.parse_args()

    start_time = time.monotonic()

    if not settings.openai_api_key:
        print(
            "ERROR: OPENAI_API_KEY not set. Export it or add to validation/.env.judge",
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

    # Derive run directory from CSV location
    run_dir = csv_path.parent
    outputs_dir = run_dir / "outputs"

    print(f"Reading: {csv_path}")

    # Read existing CSV
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("No rows in CSV.")
        sys.exit(0)

    print(f"Found {len(rows)} examples")
    print()

    # Judge each row
    for i, row in enumerate(rows):
        example = row["example"]
        print(f"  [{i + 1}/{len(rows)}] {example:<45s}", end="", flush=True)

        # Check if any provider completed
        statuses = {p: row.get(f"{p}_status", "") for p in MODELS}
        completed = {p for p, s in statuses.items() if s == "COMPLETED"}

        if not completed:
            row["confidence"] = compute_confidence(row)
            status_str = " ".join(f"{p}={s}" for p, s in statuses.items())
            print(f" SKIP ({status_str})")
            continue

        prompt = extract_prompt(example)

        # Individual scores for completed providers
        score_parts = []
        for provider in MODELS:
            if provider not in completed:
                score_parts.append(f"{provider}=SKIP")
                continue
            output = load_raw_output(outputs_dir, example, provider)
            score, reason = judge_individual(settings, prompt, output)
            row[f"{provider}_judge_score"] = score
            row[f"{provider}_judge_reason"] = reason
            score_parts.append(f"{provider}={score}/5")

        # Update confidence
        row["confidence"] = compute_confidence(row)

        print(f" {' '.join(score_parts)} [{row['confidence']}]")

    # Write updated CSV + report into same run directory
    judge_elapsed = time.monotonic() - start_time

    # Read validation timing from meta.json
    meta_path = run_dir / "meta.json"
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
    validation_duration = meta.get("validation_duration_s")

    # Save judge timing
    meta["judge_duration_s"] = round(judge_elapsed, 1)
    meta_path.write_text(json.dumps(meta, indent=2))

    report_path = run_dir / "report.md"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=JUDGE_CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    # Generate report with timing
    generate_report(rows, report_path, validation_duration, judge_elapsed)

    print()
    print("=" * 50)
    print(f" Run directory: {run_dir}")
    if validation_duration:
        print(f" Validation: {_format_duration(validation_duration)}")
    print(f" Judge: {_format_duration(judge_elapsed)}")
    if validation_duration:
        print(f" Total: {_format_duration(validation_duration + judge_elapsed)}")
    print("=" * 50)


if __name__ == "__main__":
    main()
