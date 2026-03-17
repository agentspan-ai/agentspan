"""Cross-run judge: compare outputs across named runs."""

from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path

from .config import Settings
from .judge import JudgeState, judge_comparison, judge_individual
from .parsing import AGENT_OUTPUT_RE, extract_prompt
from .persistence import compute_output_hash
from .toml_config import JudgeConfig


def _load_single_output(outputs_dir: Path, example_name: str) -> str:
    """Load raw output from single-model output file (no provider suffix)."""
    safe_name = example_name.replace("/", "_")
    path = outputs_dir / f"{safe_name}.txt"
    if not path.exists():
        return ""
    text = path.read_text()
    m = re.search(r"=== STDOUT ===\n(.*?)(?:\n\n=== STDERR ===|\Z)", text, re.DOTALL)
    stdout = m.group(1).strip() if m else text
    output_match = AGENT_OUTPUT_RE.search(stdout)
    return output_match.group(1).strip() if output_match else stdout[:2000]


def judge_across_runs(
    parent_dir: Path,
    judge_config: JudgeConfig,
    settings: Settings,
) -> None:
    """Judge outputs across runs in a multi-run parent directory."""
    # Override settings with judge config
    settings.judge_model = judge_config.model
    settings.judge_max_output_chars = judge_config.max_output_chars
    settings.judge_rate_limit = judge_config.rate_limit
    settings.max_judge_calls = judge_config.max_calls

    # Discover runs
    run_dirs: dict[str, Path] = {}
    for d in sorted(parent_dir.iterdir()):
        if d.is_dir() and (d / "results.csv").exists():
            run_dirs[d.name] = d

    if len(run_dirs) < 1:
        print("  No runs found to judge.")
        return

    run_names = list(run_dirs.keys())
    print(f"\n  Cross-run judge: {len(run_names)} runs")
    print(f"  Judge model: {settings.judge_model}")

    baseline_name = judge_config.baseline_run
    if baseline_name and baseline_name not in run_dirs:
        print(f"  WARNING: baseline_run '{baseline_name}' not found, skipping baseline comparison")
        baseline_name = None

    if baseline_name:
        print(f"  Baseline: {baseline_name}")

    # Load examples per run
    run_examples: dict[str, dict[str, dict]] = {}  # run -> example -> csv row
    for name, rd in run_dirs.items():
        csv_path = rd / "results.csv"
        with open(csv_path) as f:
            rows = list(csv.DictReader(f))
        run_examples[name] = {row["example"]: row for row in rows}

    # Find all example names across runs
    all_example_names: set[str] = set()
    for examples in run_examples.values():
        all_example_names.update(examples.keys())

    state = JudgeState()
    judge_dir = parent_dir / "judge"
    judge_dir.mkdir(exist_ok=True)

    # Load previous judge data for caching
    prev_judge_path = judge_dir / "last_run.json"
    prev_judge: dict = {}
    if prev_judge_path.exists():
        try:
            prev_judge = json.loads(prev_judge_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    start_time = time.monotonic()
    judge_rows: list[dict] = []

    for example_name in sorted(all_example_names):
        print(f"  [{example_name}]", end="", flush=True)
        prompt = extract_prompt(example_name)
        row: dict = {"example": example_name}
        parts: list[str] = []

        prev_entry = prev_judge.get("examples", {}).get(example_name, {})
        prev_hashes = prev_entry.get("output_hashes", {})
        prev_scores = prev_entry.get("judge_scores", {})
        current_hashes: dict[str, str] = {}
        current_scores: dict[str, int] = {}

        # Individual scoring per run
        for run_name in run_names:
            ex_data = run_examples.get(run_name, {}).get(example_name)
            if not ex_data or ex_data.get("status") != "COMPLETED":
                row[f"{run_name}_score"] = ""
                row[f"{run_name}_reason"] = ""
                parts.append(f"{run_name}=SKIP")
                continue

            outputs_dir = run_dirs[run_name] / "outputs"
            output = _load_single_output(outputs_dir, example_name)
            output_hash = compute_output_hash(output)
            current_hashes[run_name] = output_hash

            # Cache check
            if prev_hashes.get(run_name) == output_hash and prev_scores.get(run_name):
                cached_score = int(prev_scores[run_name])
                row[f"{run_name}_score"] = cached_score
                row[f"{run_name}_reason"] = "cached"
                current_scores[run_name] = cached_score
                parts.append(f"{run_name}={cached_score}/5$")
                state.cache_hits += 1
                continue

            if judge_config.max_calls > 0 and state.call_count >= judge_config.max_calls:
                parts.append(f"{run_name}=BUDGET")
                continue

            if state.call_count > 0 and judge_config.rate_limit > 0:
                time.sleep(judge_config.rate_limit)

            score, reason = judge_individual(settings, prompt, output)
            row[f"{run_name}_score"] = score
            row[f"{run_name}_reason"] = reason
            current_scores[run_name] = score
            parts.append(f"{run_name}={score}/5")
            state.call_count += 1

        # Baseline comparison
        if baseline_name and baseline_name in run_examples:
            baseline_data = run_examples[baseline_name].get(example_name)
            if baseline_data and baseline_data.get("status") == "COMPLETED":
                baseline_output = _load_single_output(
                    run_dirs[baseline_name] / "outputs", example_name
                )
                for run_name in run_names:
                    if run_name == baseline_name:
                        continue
                    candidate_data = run_examples.get(run_name, {}).get(example_name)
                    if not candidate_data or candidate_data.get("status") != "COMPLETED":
                        continue

                    if judge_config.max_calls > 0 and state.call_count >= judge_config.max_calls:
                        break

                    if state.call_count > 0 and judge_config.rate_limit > 0:
                        time.sleep(judge_config.rate_limit)

                    candidate_output = _load_single_output(
                        run_dirs[run_name] / "outputs", example_name
                    )
                    bscore, breason = judge_comparison(
                        settings, prompt, baseline_output, candidate_output
                    )
                    row[f"{run_name}_vs_{baseline_name}"] = bscore
                    row[f"{run_name}_vs_{baseline_name}_reason"] = breason
                    parts.append(f"{run_name}_vs_{baseline_name}={bscore}/5")
                    state.call_count += 1

        # Store hashes/scores for caching
        prev_judge.setdefault("examples", {})[example_name] = {
            "output_hashes": current_hashes,
            "judge_scores": current_scores,
        }

        print(f" {' '.join(parts)}")
        judge_rows.append(row)

    elapsed = time.monotonic() - start_time

    # Write results
    if judge_rows:
        # Build columns dynamically from rows
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

        # Write report
        report_path = judge_dir / "report.md"
        _write_judge_report(report_path, judge_rows, run_names, baseline_name, elapsed)

    # Save cache
    prev_judge_path.write_text(json.dumps(prev_judge, indent=2))

    # Meta
    meta = {
        "judge_duration_s": round(elapsed, 1),
        "judge_model": settings.judge_model,
        "judge_calls": state.call_count,
        "cache_hits": state.cache_hits,
        "baseline_run": baseline_name,
        "runs": run_names,
    }
    (judge_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    print()
    print(
        f"  Judge: {state.call_count} calls"
        + (f" ({state.cache_hits} cached)" if state.cache_hits else "")
        + f" in {elapsed:.1f}s"
    )
    print(f"  Results: {judge_dir / 'results.csv'}")


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

        # Summary table
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

        # Baseline comparison
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
