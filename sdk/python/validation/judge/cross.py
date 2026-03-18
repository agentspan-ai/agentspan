"""Cross-run judge: compare outputs across named runs."""

from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path

from ..config import Settings
from ..parsing import AGENT_OUTPUT_RE, extract_prompt
from ..persistence import compute_output_hash
from ..toml_config import JudgeConfig
from .llm import JudgeState, judge_comparison, judge_individual


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
    settings.judge_max_tokens = judge_config.max_tokens
    settings.judge_rate_limit = judge_config.rate_limit
    settings.judge_max_calls = judge_config.max_calls

    # Discover runs
    run_dirs: dict[str, Path] = {}
    for d in sorted(parent_dir.iterdir()):
        if d.is_dir() and (d / "results.csv").exists():
            run_dirs[d.name] = d

    if len(run_dirs) < 1:
        print("  No runs found to judge.")
        return

    run_names = list(run_dirs.keys())

    baseline_name = judge_config.baseline_run
    if baseline_name and baseline_name not in run_dirs:
        baseline_name = None

    # Load examples per run
    run_examples: dict[str, dict[str, dict]] = {}
    for name, rd in run_dirs.items():
        csv_path = rd / "results.csv"
        with open(csv_path) as f:
            rows = list(csv.DictReader(f))
        run_examples[name] = {row["example"]: row for row in rows}

    all_example_names = sorted({name for examples in run_examples.values() for name in examples})

    state = JudgeState()
    judge_dir = parent_dir / "judge"
    judge_dir.mkdir(exist_ok=True)

    # Load previous judge data for caching
    prev_judge_path = judge_dir / "report.json"
    prev_judge: dict = {}
    if prev_judge_path.exists():
        try:
            prev_judge = json.loads(prev_judge_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Try Rich live display
    try:
        from rich.console import Console

        use_rich = True
        console = Console()
    except ImportError:
        use_rich = False

    start_time = time.monotonic()
    judge_rows: list[dict] = []

    from .display import _judge_plain, _judge_with_rich, _print_rich_summary

    if use_rich:
        _judge_with_rich(
            console,
            all_example_names,
            run_names,
            run_examples,
            run_dirs,
            baseline_name,
            judge_config,
            settings,
            state,
            prev_judge,
            judge_rows,
        )
    else:
        _judge_plain(
            all_example_names,
            run_names,
            run_examples,
            run_dirs,
            baseline_name,
            judge_config,
            settings,
            state,
            prev_judge,
            judge_rows,
        )

    elapsed = time.monotonic() - start_time

    # Save cache
    prev_judge_path.write_text(json.dumps(prev_judge, indent=2))

    # Build meta
    meta = {
        "judge_duration_s": round(elapsed, 1),
        "judge_model": settings.judge_model,
        "judge_calls": state.call_count,
        "cache_hits": state.cache_hits,
        "input_tokens": state.input_tokens,
        "output_tokens": state.output_tokens,
        "baseline_run": baseline_name,
        "runs": run_names,
    }
    (judge_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    # Write results
    if judge_rows:
        from .reports import _write_outputs

        _write_outputs(
            judge_dir, judge_rows, run_names, baseline_name, run_examples, run_dirs, meta, elapsed
        )

    # Final summary
    if use_rich:
        _print_rich_summary(
            console, judge_rows, run_names, baseline_name, state, elapsed, judge_dir
        )
    else:
        print()
        print(
            f"  Judge: {state.call_count} calls"
            + (f" ({state.cache_hits} cached)" if state.cache_hits else "")
            + f" in {elapsed:.1f}s"
        )
        if state.input_tokens or state.output_tokens:
            print(f"  Tokens: {state.input_tokens:,} in / {state.output_tokens:,} out")
        print(f"  Results: {judge_dir / 'results.csv'}")


def _judge_example(
    example_name: str,
    run_names: list[str],
    run_examples: dict,
    run_dirs: dict,
    baseline_name: str | None,
    judge_config: JudgeConfig,
    settings: Settings,
    state: JudgeState,
    prev_judge: dict,
) -> dict:
    """Judge one example across all runs. Returns row dict."""
    prompt = extract_prompt(example_name)
    row: dict = {"example": example_name}

    prev_entry = prev_judge.get("examples", {}).get(example_name, {})
    prev_hashes = prev_entry.get("output_hashes", {})
    prev_scores = prev_entry.get("judge_scores", {})
    current_hashes: dict[str, str] = {}
    current_scores: dict[str, int] = {}

    for run_name in run_names:
        ex_data = run_examples.get(run_name, {}).get(example_name)
        if not ex_data or ex_data.get("status") != "COMPLETED":
            row[f"{run_name}_score"] = ""
            row[f"{run_name}_reason"] = ""
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
            state.cache_hits += 1
            continue

        if judge_config.max_calls > 0 and state.call_count >= judge_config.max_calls:
            continue

        if state.call_count > 0 and judge_config.rate_limit > 0:
            time.sleep(judge_config.rate_limit)

        score, reason = judge_individual(settings, prompt, output, state=state)
        row[f"{run_name}_score"] = score
        row[f"{run_name}_reason"] = reason
        current_scores[run_name] = score
        state.call_count += 1

    # Baseline comparison
    if baseline_name and baseline_name in run_examples:
        baseline_data = run_examples[baseline_name].get(example_name)
        if baseline_data and baseline_data.get("status") == "COMPLETED":
            baseline_output = _load_single_output(run_dirs[baseline_name] / "outputs", example_name)
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

                candidate_output = _load_single_output(run_dirs[run_name] / "outputs", example_name)
                bscore, breason = judge_comparison(
                    settings, prompt, baseline_output, candidate_output, state=state
                )
                row[f"{run_name}_vs_{baseline_name}"] = bscore
                row[f"{run_name}_vs_{baseline_name}_reason"] = breason
                state.call_count += 1

    prev_judge.setdefault("examples", {})[example_name] = {
        "output_hashes": current_hashes,
        "judge_scores": current_scores,
    }

    return row
