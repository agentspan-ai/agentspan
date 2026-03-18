"""Run persistence: report.json load/save, sorting, resume/retry."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import threading
from pathlib import Path

from .config import SCRIPT_DIR
from .models import SingleResult

OUTPUT_DIR = SCRIPT_DIR / "output"


def load_last_run() -> dict:
    """Load report.json from the latest run via output/latest symlink."""
    latest = OUTPUT_DIR / "latest" / "report.json"
    if latest.exists():
        try:
            return json.loads(latest.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_last_run(data: dict, lock: threading.Lock | None = None) -> None:
    """Write report.json into run_dir atomically."""
    run_dir = data.get("run_dir")
    if run_dir:
        target = Path(run_dir) / "report.json"
        target.parent.mkdir(parents=True, exist_ok=True)
    else:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        target = OUTPUT_DIR / "report.json"

    tmp = target.with_suffix(".json.tmp")
    content = json.dumps(data, indent=2)

    def _write():
        tmp.write_text(content)
        os.replace(tmp, target)

    if lock:
        with lock:
            _write()
    else:
        _write()


def compute_output_hash(output: str) -> str:
    """SHA-256 hash of output text for change detection."""
    return hashlib.sha256(output.encode()).hexdigest()[:16]


def update_last_run_single(
    last_run: dict, example_name: str, result: SingleResult, lock: threading.Lock
) -> None:
    """Thread-safe update for single-model run."""
    with lock:
        examples = last_run.setdefault("examples", {})
        entry = examples.get(example_name, {})
        entry["max_duration_s"] = result.result.duration_s
        entry["status"] = result.result.status
        entry["duration_s"] = result.result.duration_s

        history = entry.get("history", [])
        history.append(result.result.status)
        entry["history"] = history[-10:]

        examples[example_name] = entry

    save_last_run(last_run, lock)


def completed_examples_single(run_dir: Path) -> set[str]:
    """Return completed example names (no provider suffix)."""
    outputs_dir = run_dir / "outputs"
    if not outputs_dir.exists():
        return set()
    completed = set()
    csv_path = run_dir / "results.csv"
    if csv_path.exists():
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("example", "")
                safe_name = name.replace("/", "_")
                if (outputs_dir / f"{safe_name}.txt").exists():
                    completed.add(name)
    return completed


def failed_examples_single(last_run: dict) -> set[str]:
    """Return failed examples for single-model run."""
    failed = set()
    for name, entry in last_run.get("examples", {}).items():
        status = entry.get("status", "")
        if status in ("ERROR", "TIMEOUT", "FAILED"):
            failed.add(name)
    return failed


def sort_slowest_first(examples, last_run: dict):
    """Sort examples by max_duration_s descending from last run data."""
    lr_examples = last_run.get("examples", {})
    if not lr_examples:
        return examples

    def sort_key(ex):
        entry = lr_examples.get(ex.name, {})
        return -(entry.get("max_duration_s", 0))

    return sorted(examples, key=sort_key)
