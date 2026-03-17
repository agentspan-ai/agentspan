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
from .report_html import generate_cross_html_report
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


def _score_style(score) -> str:
    """Return Rich style for a score value."""
    try:
        s = int(score)
    except (TypeError, ValueError):
        return "dim"
    if s >= 4:
        return "green"
    if s == 3:
        return "yellow"
    return "red"


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
    prev_judge_path = judge_dir / "last_run.json"
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
        "baseline_run": baseline_name,
        "runs": run_names,
    }
    (judge_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    # Write results
    if judge_rows:
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

        score, reason = judge_individual(settings, prompt, output)
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
                    settings, prompt, baseline_output, candidate_output
                )
                row[f"{run_name}_vs_{baseline_name}"] = bscore
                row[f"{run_name}_vs_{baseline_name}_reason"] = breason
                state.call_count += 1

    prev_judge.setdefault("examples", {})[example_name] = {
        "output_hashes": current_hashes,
        "judge_scores": current_scores,
    }

    return row


def _judge_with_rich(
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
):
    """Judge with Rich live progress + score table."""
    from rich.console import Group
    from rich.live import Live
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn
    from rich.table import Table
    from rich.text import Text

    total = len(all_example_names)

    progress = Progress(
        TextColumn("[bold blue]Judging"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("[dim]{task.fields[current]}"),
    )
    task_id = progress.add_task("Judge", total=total, current="")

    def _build_display():
        # Score table (shows last 15 rows + averages)
        score_table = Table(title="Judge Scores", expand=True, show_edge=True)
        score_table.add_column("Example", style="bold", min_width=25)
        for rn in run_names:
            score_table.add_column(rn, justify="center", min_width=8)
        if baseline_name:
            for rn in run_names:
                if rn != baseline_name:
                    score_table.add_column(
                        f"vs {baseline_name[:12]}", justify="center", min_width=8
                    )

        # Show last N rows
        display_rows = judge_rows[-15:] if len(judge_rows) > 15 else judge_rows
        if len(judge_rows) > 15:
            score_table.add_row(Text(f"... {len(judge_rows) - 15} more above", style="dim"))

        for row in display_rows:
            cells = [row["example"]]
            for rn in run_names:
                s = row.get(f"{rn}_score", "")
                if s:
                    cells.append(Text(f"{s}/5", style=_score_style(s)))
                else:
                    cells.append(Text("-", style="dim"))
            if baseline_name:
                for rn in run_names:
                    if rn != baseline_name:
                        bs = row.get(f"{rn}_vs_{baseline_name}", "")
                        if bs:
                            cells.append(Text(f"{bs}/5", style=_score_style(bs)))
                        else:
                            cells.append(Text("-", style="dim"))
            score_table.add_row(*cells)

        # Average row
        if judge_rows:
            avg_cells: list = [Text("Average", style="bold")]
            for rn in run_names:
                scores = [int(r[f"{rn}_score"]) for r in judge_rows if r.get(f"{rn}_score")]
                avg = sum(scores) / len(scores) if scores else 0
                style = "green" if avg >= 4 else ("yellow" if avg >= 3 else "red")
                avg_cells.append(Text(f"{avg:.1f}", style=f"bold {style}"))
            if baseline_name:
                for rn in run_names:
                    if rn != baseline_name:
                        scores = [
                            int(r[f"{rn}_vs_{baseline_name}"])
                            for r in judge_rows
                            if r.get(f"{rn}_vs_{baseline_name}")
                        ]
                        avg = sum(scores) / len(scores) if scores else 0
                        style = "green" if avg >= 4 else ("yellow" if avg >= 3 else "red")
                        avg_cells.append(Text(f"{avg:.1f}", style=f"bold {style}"))
            score_table.add_section()
            score_table.add_row(*avg_cells)

        return Group(progress, score_table)

    with Live(
        _build_display(),
        console=console,
        refresh_per_second=4,
        transient=False,
    ) as live:
        for i, example_name in enumerate(all_example_names):
            progress.update(task_id, current=example_name)
            row = _judge_example(
                example_name,
                run_names,
                run_examples,
                run_dirs,
                baseline_name,
                judge_config,
                settings,
                state,
                prev_judge,
            )
            judge_rows.append(row)
            progress.update(task_id, advance=1)
            live.update(_build_display())


def _judge_plain(
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
):
    """Judge with plain print output."""
    print(f"\n  Cross-run judge: {len(run_names)} runs | model: {settings.judge_model}")
    if baseline_name:
        print(f"  Baseline: {baseline_name}")

    for example_name in all_example_names:
        print(f"  [{example_name}]", end="", flush=True)
        row = _judge_example(
            example_name,
            run_names,
            run_examples,
            run_dirs,
            baseline_name,
            judge_config,
            settings,
            state,
            prev_judge,
        )
        judge_rows.append(row)

        parts = []
        for rn in run_names:
            s = row.get(f"{rn}_score", "")
            if s:
                parts.append(f"{rn}={s}/5")
            else:
                parts.append(f"{rn}=SKIP")
        print(f" {' '.join(parts)}")


def _print_rich_summary(console, judge_rows, run_names, baseline_name, state, elapsed, judge_dir):
    """Print final Rich summary table."""
    from rich.table import Table
    from rich.text import Text

    # Summary stats table
    summary = Table(title="Judge Summary", show_edge=True)
    summary.add_column("Run", style="bold")
    summary.add_column("Scored", justify="right")
    summary.add_column("Avg Score", justify="right")
    if baseline_name:
        summary.add_column(f"Avg vs {baseline_name}", justify="right")

    for rn in run_names:
        scores = [int(r[f"{rn}_score"]) for r in judge_rows if r.get(f"{rn}_score")]
        avg = sum(scores) / len(scores) if scores else 0
        style = "green" if avg >= 4 else ("yellow" if avg >= 3 else "red")

        row_data = [rn, str(len(scores)), Text(f"{avg:.2f}", style=style)]

        if baseline_name:
            if rn == baseline_name:
                row_data.append(Text("-", style="dim"))
            else:
                bscores = [
                    int(r[f"{rn}_vs_{baseline_name}"])
                    for r in judge_rows
                    if r.get(f"{rn}_vs_{baseline_name}")
                ]
                bavg = sum(bscores) / len(bscores) if bscores else 0
                bstyle = "green" if bavg >= 4 else ("yellow" if bavg >= 3 else "red")
                row_data.append(Text(f"{bavg:.2f}", style=bstyle))

        summary.add_row(*row_data)

    console.print()
    console.print(summary)
    console.print(
        f"  [dim]{state.call_count} calls"
        + (f" ({state.cache_hits} cached)" if state.cache_hits else "")
        + f" in {elapsed:.1f}s[/dim]"
    )
    console.print(f"  [dim]Results: {judge_dir}[/dim]")


def _write_outputs(
    judge_dir, judge_rows, run_names, baseline_name, run_examples, run_dirs, meta, elapsed
):
    """Write CSV, markdown, and HTML reports."""
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

    report_path = judge_dir / "report.md"
    _write_judge_report(report_path, judge_rows, run_names, baseline_name, elapsed)

    # Load raw outputs for HTML
    raw_outputs: dict[str, dict[str, str]] = {}
    for row in judge_rows:
        example = row["example"]
        raw_outputs[example] = {}
        for rn in run_names:
            ex_data = run_examples.get(rn, {}).get(example)
            if ex_data and ex_data.get("status") == "COMPLETED":
                raw_outputs[example][rn] = _load_single_output(run_dirs[rn] / "outputs", example)

    # Load per-run metadata
    run_meta_data: dict[str, dict] = {}
    for rn, rd in run_dirs.items():
        run_meta_path = rd / "meta.json"
        if run_meta_path.exists():
            try:
                run_meta_data[rn] = json.loads(run_meta_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

    html_path = judge_dir / "report.html"
    generate_cross_html_report(
        judge_rows,
        html_path,
        run_names=run_names,
        baseline=baseline_name,
        raw_outputs=raw_outputs,
        meta=meta,
        run_meta=run_meta_data,
    )


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
