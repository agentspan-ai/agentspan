#!/usr/bin/env python3
"""Run SDK examples with all configured models, capture outputs.

Requires: uv sync --extra validation

Usage:
    python3 -m validation.scripts.run_examples              # all examples
    python3 -m validation.scripts.run_examples --group=SMOKE_TEST
    python3 -m validation.scripts.run_examples --group=PASSING_EXAMPLES
    python3 -m validation.scripts.run_examples --group=ADK_EXAMPLES
    python3 -m validation.scripts.run_examples --timeout 120

Groups are defined in validation/.env
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from validation.config import EXECUTION_CSV_COLUMNS, MODELS, SCRIPT_DIR
from validation.discovery import discover_examples
from validation.reporting import _format_duration
from validation.runner import check_server_health, compute_match, run_example_all


def main():
    parser = argparse.ArgumentParser(description="Run SDK examples with all configured models")
    parser.add_argument("prefixes", nargs="*", help="Example prefix filters (e.g. 01 03)")
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.environ.get("EXAMPLE_TIMEOUT", "300")),
        help="Per-example timeout in seconds (default: 300)",
    )
    parser.add_argument("--retries", type=int, default=0, help="Retries on failure (default: 0)")
    parser.add_argument(
        "--output-dir", type=str, default=str(SCRIPT_DIR / "output"), help="Output directory"
    )
    parser.add_argument(
        "--group",
        type=str,
        default=None,
        help="Run only examples in named group from .env.judge (e.g. HITL_EXAMPLES, KNOWN_FAILURES)",
    )
    args = parser.parse_args()

    start_time = time.monotonic()

    # Health check
    if not check_server_health():
        print("ERROR: Server not reachable. Start it first.", file=sys.stderr)
        sys.exit(1)

    # Discover examples
    examples = discover_examples(args.prefixes, args.group)
    if not examples:
        print("No examples to run.")
        sys.exit(0)

    # Output setup — each run gets its own directory
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    run_id = uuid.uuid4().hex[:4]
    run_dir = Path(args.output_dir) / f"run_{timestamp}_{run_id}"
    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    csv_path = run_dir / "results.csv"

    group_label = f" (group: {args.group})" if args.group else ""
    print("=" * 50)
    print(f" Validation: {len(examples)} examples × {len(MODELS)} models{group_label}")
    print(f" Models: {', '.join(MODELS.values())}")
    print(f" Timeout: {args.timeout}s | Retries: {args.retries}")
    print(f" Output: {run_dir}")
    print("=" * 50)
    print()

    # CSV setup
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXECUTION_CSV_COLUMNS)
        writer.writeheader()

    # Run each example
    total = len(examples)
    for i, example in enumerate(examples, 1):
        name = example.name
        safe_name = name.replace("/", "_")
        print(f"  [{i}/{total}] {name:<45s}", end="", flush=True)

        results = run_example_all(example, args.timeout, args.retries)

        match, confidence, notes = compute_match(results)

        # Save raw outputs
        for model_name, r in results.items():
            out_file = outputs_dir / f"{safe_name}_{model_name}.txt"
            with open(out_file, "w") as f:
                f.write(f"=== STDOUT ===\n{r.stdout}\n\n=== STDERR ===\n{r.stderr}\n")

        # Write CSV row
        row = {"example": name}
        for provider, r in results.items():
            row.update(r.to_csv_dict(provider))
        row.update({"match": match, "confidence": confidence, "notes": notes})

        with open(csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=EXECUTION_CSV_COLUMNS)
            writer.writerow(row)

        # Status line
        parts = []
        for provider, r in results.items():
            s = "✓" if r.status == "COMPLETED" else f"✗({r.status})"
            parts.append(f"{provider}:{s}")
        duration = max(r.duration_s for r in results.values())
        print(f" {' '.join(parts)} [{duration:.0f}s] {match}")

    # Save timing metadata for judge
    elapsed = time.monotonic() - start_time
    meta_path = run_dir / "meta.json"
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
    meta["validation_duration_s"] = round(elapsed, 1)
    meta_path.write_text(json.dumps(meta, indent=2))

    # Summary
    print()
    print("=" * 50)
    print(f" Run directory: {run_dir}")
    print(f" Total time: {_format_duration(elapsed)}")
    print("=" * 50)


if __name__ == "__main__":
    main()
