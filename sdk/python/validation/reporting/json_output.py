"""Write run_results.json per run."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..models import RunResult, SingleResult

_EXCLUDE = {"stdout", "stderr"}


def _result_to_dict(result: RunResult) -> dict:
    d = asdict(result)
    for k in _EXCLUDE:
        d.pop(k, None)
    return d


def write_run_results_json(
    run_dir: Path,
    run_meta: dict,
    results: list[SingleResult],
    last_run: dict,
) -> None:
    """Write run_results.json with full example data + history."""
    examples = {}
    for sr in results:
        name = sr.example.name
        ex = _result_to_dict(sr.result)
        ex["history"] = last_run.get("examples", {}).get(name, {}).get("history", [])
        examples[name] = ex

    data = {**run_meta, "examples": examples}
    (run_dir / "run_results.json").write_text(json.dumps(data, indent=2))
