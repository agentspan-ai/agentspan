"""Judge report writing: CSV, markdown, HTML."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ..reporting import generate_cross_html_report
from .cross import _load_single_output


def _write_outputs(
    judge_dir, judge_rows, run_names, baseline_name, run_examples, run_dirs, meta, elapsed
):
    """Write CSV, markdown, and HTML reports."""
    columns = ["example"]
    for run_name in run_names:
        columns.extend([f"{run_name}_score", f"{run_name}_reason"])
    if baseline_name:
        for run_name in run_names:
            if run_name != baseline_name:
                columns.extend(
                    [
                        f"{run_name}_vs_{baseline_name}",
                        f"{run_name}_vs_{baseline_name}_reason",
                    ]
                )

    csv_path = judge_dir / "results.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(judge_rows)

    report_path = judge_dir / "report.md"
    _write_judge_report(report_path, judge_rows, run_names, baseline_name, elapsed)

    # Load raw outputs for HTML
    raw_outputs: dict[str, dict[str, str]] = {}
    for row in judge_rows:
        example = row["example"]
        raw_outputs[example] = {}
        for rn in run_names:
            ex_data = run_examples.get(rn, {}).get(example)
            if ex_data and ex_data.get("status") == "COMPLETED":
                raw_outputs[example][rn] = _load_single_output(run_dirs[rn] / "outputs", example)

    # Load per-run metadata
    run_meta_data: dict[str, dict] = {}
    for rn, rd in run_dirs.items():
        run_meta_path = rd / "meta.json"
        if run_meta_path.exists():
            try:
                run_meta_data[rn] = json.loads(run_meta_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

    html_path = judge_dir / "report.html"
    generate_cross_html_report(
        judge_rows,
        html_path,
        run_names=run_names,
        baseline=baseline_name,
        raw_outputs=raw_outputs,
        meta=meta,
        run_meta=run_meta_data,
    )


def _write_judge_report(
    path: Path,
    rows: list[dict],
    run_names: list[str],
    baseline_name: str | None,
    elapsed: float,
) -> None:
    """Write markdown judge report."""
    with open(path, "w") as f:
        f.write("# Cross-Run Judge Report\n\n")
        f.write(f"Runs: {', '.join(run_names)}\n")
        if baseline_name:
            f.write(f"Baseline: {baseline_name}\n")
        f.write(f"Duration: {elapsed:.1f}s\n\n")

        f.write("## Scores\n\n")
        header = "| Example | " + " | ".join(run_names) + " |\n"
        sep = "|---------|" + "|".join("-" * 10 for _ in run_names) + "|\n"
        f.write(header)
        f.write(sep)

        for row in rows:
            scores = []
            for rn in run_names:
                s = row.get(f"{rn}_score", "")
                if s:
                    scores.append(f"{s}/5")
                else:
                    scores.append("-")
            f.write(f"| {row['example']} | " + " | ".join(scores) + " |\n")

        if baseline_name:
            f.write(f"\n## Baseline Comparison (vs {baseline_name})\n\n")
            non_baseline = [rn for rn in run_names if rn != baseline_name]
            header = "| Example | " + " | ".join(non_baseline) + " |\n"
            sep = "|---------|" + "|".join("-" * 10 for _ in non_baseline) + "|\n"
            f.write(header)
            f.write(sep)

            for row in rows:
                scores = []
                for rn in non_baseline:
                    s = row.get(f"{rn}_vs_{baseline_name}", "")
                    if s:
                        scores.append(f"{s}/5")
                    else:
                        scores.append("-")
                f.write(f"| {row['example']} | " + " | ".join(scores) + " |\n")
