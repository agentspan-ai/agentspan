"""Run persistence: report.json load/save, sorting, resume/retry."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

from .config import SCRIPT_DIR
from .models import SingleResult

OUTPUT_DIR = SCRIPT_DIR / "output"


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
    """Return completed example names from run_results.json."""
    json_path = run_dir / "run_results.json"
    if not json_path.exists():
        return set()
    try:
        data = json.loads(json_path.read_text())
    except (json.JSONDecodeError, OSError):
        return set()
    return {
        name for name, ex in data.get("examples", {}).items() if ex.get("status") == "COMPLETED"
    }


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
