"""Output writing: raw outputs, CSV rows, symlinks."""

from __future__ import annotations

import csv
from pathlib import Path

from .models import RunResult


def write_single_output(outputs_dir: Path, example_name: str, result: RunResult) -> None:
    """Write raw output file for single-model result."""
    safe_name = example_name.replace("/", "_")
    out_file = outputs_dir / f"{safe_name}.txt"
    with open(out_file, "w") as f:
        f.write(f"=== STDOUT ===\n{result.stdout}\n\n=== STDERR ===\n{result.stderr}\n")


def build_single_row(example_name: str, result: RunResult) -> dict:
    """Build flat CSV row for single-model result."""
    row = {"example": example_name}
    row.update(result.to_csv_dict(""))
    return row


def write_csv_row(csv_path: Path, columns: list[str], row: dict):
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writerow(row)


def update_latest_symlink(output_dir: Path, run_dir: Path):
    latest = output_dir / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(run_dir.resolve())
    except OSError:
        pass
