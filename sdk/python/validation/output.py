"""Output writing: raw outputs, CSV rows, JSON, symlinks."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from .models import ExampleResult
from .parsing import load_raw_output
from .report_html import generate_html_report
from .reporting import generate_report


def write_outputs(outputs_dir: Path, example_name: str, results: dict):
    safe_name = example_name.replace("/", "_")
    for model_name, r in results.items():
        out_file = outputs_dir / f"{safe_name}_{model_name}.txt"
        with open(out_file, "w") as f:
            f.write(f"=== STDOUT ===\n{r.stdout}\n\n=== STDERR ===\n{r.stderr}\n")


def write_csv_row(csv_path: Path, columns: list[str], row: dict):
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writerow(row)


def build_row(example_name: str, results: dict, match: str, confidence: str, notes: str) -> dict:
    row = {"example": example_name}
    for provider, r in results.items():
        row.update(r.to_csv_dict(provider))
    row.update({"match": match, "confidence": confidence, "notes": notes})
    return row


def write_json_results(json_path: Path, all_results: list[ExampleResult]):
    json_data = []
    for er in all_results:
        entry = {
            "example": er.example.name,
            "match": er.match,
            "confidence": er.confidence,
            "notes": er.notes,
            "models": {},
        }
        for provider, r in er.results.items():
            d = asdict(r)
            d.pop("stdout", None)
            d.pop("stderr", None)
            entry["models"][provider] = d
        json_data.append(entry)
    json_path.write_text(json.dumps(json_data, indent=2))


def write_judge_outputs(
    rows: list[dict],
    csv_path: Path,
    run_dir: Path,
    columns: list[str],
    providers: list[str],
    baseline: str | None,
    meta: dict,
    validation_duration: float | None,
    history: dict[str, list[str]] | None = None,
) -> None:
    """Write judge CSV, markdown report, and HTML report."""
    # CSV
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    # Markdown report
    report_path = run_dir / "report.md"
    generate_report(
        rows,
        report_path,
        validation_duration,
        meta.get("judge_duration_s"),
        providers=providers,
    )

    # Load raw outputs for HTML
    outputs_dir = run_dir / "outputs"
    raw_outputs: dict[str, dict[str, str]] = {}
    for row in rows:
        example = row["example"]
        raw_outputs[example] = {}
        for p in providers:
            if row.get(f"{p}_status") == "COMPLETED":
                raw_outputs[example][p] = load_raw_output(outputs_dir, example, p)

    # HTML report
    html_path = run_dir / "report.html"
    generate_html_report(
        rows,
        html_path,
        providers=providers,
        baseline_model=baseline,
        raw_outputs=raw_outputs,
        meta=meta,
        history=history,
    )


def update_latest_symlink(output_dir: Path, run_dir: Path):
    latest = output_dir / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(run_dir.resolve())
    except OSError:
        pass
