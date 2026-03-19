"""Cross-run judge: compare outputs across named runs."""

from __future__ import annotations

import json
import time
from pathlib import Path

from ..config import Settings
from ..parsing import extract_prompt
from ..persistence import compute_output_hash
from ..toml_config import JudgeConfig
from .llm import JudgeState, judge_comparison, judge_individual


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

    # Discover runs (require run_results.json)
    run_dirs: dict[str, Path] = {}
    for d in sorted(parent_dir.iterdir()):
        if d.is_dir() and (d / "run_results.json").exists():
            run_dirs[d.name] = d

    if len(run_dirs) < 1:
        print("  No runs found to judge.")
        return

    run_names = list(run_dirs.keys())

    baseline_name = judge_config.baseline_run
    if baseline_name and baseline_name not in run_dirs:
        baseline_name = None

    # Load examples per run from run_results.json
    run_examples: dict[str, dict[str, dict]] = {}
    for name, rd in run_dirs.items():
        data = json.loads((rd / "run_results.json").read_text())
        run_examples[name] = data.get("examples", {})

    all_example_names = sorted({name for examples in run_examples.values() for name in examples})

    state = JudgeState()
    judge_dir = parent_dir / "judge"
    judge_dir.mkdir(exist_ok=True)

    # Load previous judge data for caching (judge_results.json)
    prev_judge_path = judge_dir / "judge_results.json"
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

    # Build judge_results.json (output + cache)
    judge_results = {
        "baseline_run": baseline_name,
        "runs": run_names,
        "judge_model": settings.judge_model,
        "judge_duration_s": round(elapsed, 1),
        "judge_calls": state.call_count,
        "cache_hits": state.cache_hits,
        "input_tokens": state.input_tokens,
        "output_tokens": state.output_tokens,
        "examples": prev_judge.get("examples", {}),
    }
    prev_judge_path.write_text(json.dumps(judge_results, indent=2))

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

    # Write reports
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
        print(f"  Results: {judge_dir / 'judge_results.json'}")


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
    prev_runs = prev_entry.get("runs", {})
    current_hashes: dict[str, str] = {}
    current_scores: dict[str, int] = {}
    current_reasons: dict[str, str] = {}

    for run_name in run_names:
        ex_data = run_examples.get(run_name, {}).get(example_name)
        if not ex_data or ex_data.get("status") != "COMPLETED":
            row[f"{run_name}_score"] = ""
            row[f"{run_name}_reason"] = ""
            continue

        output = ex_data.get("output_text", "")
        output_hash = compute_output_hash(output)
        current_hashes[run_name] = output_hash

        # Cache check
        prev_run = prev_runs.get(run_name, {})
        if prev_run.get("output_hash") == output_hash and prev_run.get("score"):
            score = int(prev_run["score"])
            reason = prev_run.get("reason", "cached")
            row[f"{run_name}_score"] = score
            row[f"{run_name}_reason"] = reason
            current_scores[run_name] = score
            current_reasons[run_name] = reason
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
        current_reasons[run_name] = reason
        state.call_count += 1

    # Baseline comparison
    if baseline_name and baseline_name in run_examples:
        baseline_data = run_examples[baseline_name].get(example_name)
        if baseline_data and baseline_data.get("status") == "COMPLETED":
            baseline_output = run_examples[baseline_name][example_name].get("output_text", "")
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

                candidate_output = run_examples[run_name][example_name].get("output_text", "")
                bscore, breason = judge_comparison(
                    settings, prompt, baseline_output, candidate_output, state=state
                )
                row[f"{run_name}_vs_{baseline_name}"] = bscore
                row[f"{run_name}_vs_{baseline_name}_reason"] = breason
                state.call_count += 1

    # Update cache in new format
    example_entry = prev_judge.setdefault("examples", {}).setdefault(example_name, {})
    example_entry["prompt"] = prompt
    runs_entry = example_entry.setdefault("runs", {})
    for run_name in current_hashes:
        run_entry = runs_entry.setdefault(run_name, {})
        run_entry["output_hash"] = current_hashes[run_name]
        run_entry["score"] = current_scores.get(run_name, 0)
        run_entry["reason"] = current_reasons.get(run_name, "")
        if baseline_name and run_name != baseline_name:
            vs_key = f"{run_name}_vs_{baseline_name}"
            if vs_key in row:
                run_entry["vs_baseline_score"] = row[vs_key]
                run_entry["vs_baseline_reason"] = row.get(f"{vs_key}_reason", "")

    return row
