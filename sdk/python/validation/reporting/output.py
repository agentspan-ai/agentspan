"""Output writing: raw outputs, symlinks."""

from __future__ import annotations

from pathlib import Path

from ..models import RunResult


def write_single_output(outputs_dir: Path, example_name: str, result: RunResult) -> None:
    """Write raw output file for single-model result."""
    safe_name = example_name.replace("/", "_")
    out_file = outputs_dir / f"{safe_name}.txt"
    with open(out_file, "w") as f:
        f.write(f"=== STDOUT ===\n{result.stdout}\n\n=== STDERR ===\n{result.stderr}\n")


def update_latest_symlink(output_dir: Path, run_dir: Path):
    latest = output_dir / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(run_dir.resolve())
    except OSError:
        pass
