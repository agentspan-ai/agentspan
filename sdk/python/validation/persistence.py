"""Last-run persistence: last_run.json load/save, sorting, resume/retry."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import threading
from pathlib import Path

from .config import SCRIPT_DIR
from .models import ExampleResult

OUTPUT_DIR = SCRIPT_DIR / "output"
LAST_RUN_SYMLINK = OUTPUT_DIR / ".last_run.json"


def load_last_run() -> dict:
    """Load last_run.json via the symlink (or direct path)."""
    if LAST_RUN_SYMLINK.exists():
        try:
            return json.loads(LAST_RUN_SYMLINK.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_last_run(data: dict, lock: threading.Lock | None = None) -> None:
    """Write last_run.json into run_dir, symlink output/.last_run.json to it."""
    run_dir = data.get("run_dir")
    if run_dir:
        target = Path(run_dir) / "last_run.json"
        target.parent.mkdir(parents=True, exist_ok=True)
    else:
        # Fallback: write directly to output dir
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        target = OUTPUT_DIR / ".last_run.json"

    tmp = target.with_suffix(".json.tmp")
    content = json.dumps(data, indent=2)

    def _write():
        tmp.write_text(content)
        os.replace(tmp, target)
        # Update symlink
        if run_dir and target != LAST_RUN_SYMLINK:
            try:
                if LAST_RUN_SYMLINK.is_symlink() or LAST_RUN_SYMLINK.exists():
                    LAST_RUN_SYMLINK.unlink()
                LAST_RUN_SYMLINK.symlink_to(target.resolve())
            except OSError:
                pass

    if lock:
        with lock:
            _write()
    else:
        _write()


def compute_output_hash(output: str) -> str:
    """SHA-256 hash of output text for change detection."""
    return hashlib.sha256(output.encode()).hexdigest()[:16]


def update_last_run_example(
    last_run: dict, example_name: str, result: ExampleResult, lock: threading.Lock
) -> None:
    """Thread-safe update of a single example in last_run.json."""
    with lock:
        examples = last_run.setdefault("examples", {})
        entry = examples.get(example_name, {})

        durations = {k: r.duration_s for k, r in result.results.items()}
        statuses = {k: r.status for k, r in result.results.items()}
        max_dur = max(durations.values()) if durations else 0

        entry["max_duration_s"] = max_dur
        entry["match"] = result.match
        entry["durations"] = durations
        entry["statuses"] = statuses

        # Append to history, keep last 10
        history = entry.get("history", [])
        history.append(result.match)
        entry["history"] = history[-10:]

        examples[example_name] = entry

    save_last_run(last_run, lock)


def update_last_run_judge(
    last_run: dict,
    example_name: str,
    judge_scores: dict[str, int],
    output_hashes: dict[str, str],
) -> None:
    """Store judge scores and output hashes for regression/cache detection."""
    examples = last_run.setdefault("examples", {})
    entry = examples.setdefault(example_name, {})
    entry["judge_scores"] = judge_scores
    entry["output_hashes"] = output_hashes


def sort_slowest_first(examples, last_run: dict):
    """Sort examples by max_duration_s descending from last run data."""
    lr_examples = last_run.get("examples", {})
    if not lr_examples:
        return examples

    def sort_key(ex):
        entry = lr_examples.get(ex.name, {})
        return -(entry.get("max_duration_s", 0))

    return sorted(examples, key=sort_key)


def resolve_run_dir(arg_value: str | None, output_dir: str) -> Path | None:
    """Resolve run dir from arg or last_run.json."""
    if arg_value:
        p = Path(arg_value)
        if p.exists():
            return p
    last_run = load_last_run()
    rd = last_run.get("run_dir")
    if rd:
        p = Path(rd)
        if p.exists():
            return p
    return None


def completed_examples(run_dir: Path, models: dict[str, str]) -> set[str]:
    """Return example names where all model output files exist."""
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
                all_present = all((outputs_dir / f"{safe_name}_{m}.txt").exists() for m in models)
                if all_present:
                    completed.add(name)
    return completed


def failed_examples(last_run: dict) -> set[str]:
    """Return example names with any ERROR/TIMEOUT/FAILED status."""
    failed = set()
    for name, entry in last_run.get("examples", {}).items():
        statuses = entry.get("statuses", {})
        if any(s in ("ERROR", "TIMEOUT", "FAILED") for s in statuses.values()):
            failed.add(name)
    return failed
