"""Rich display for cross-run judging."""

from __future__ import annotations

_MAX_COL_NAME = 14
_MAX_EXAMPLE_WIDTH = 30


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


def _trunc(name: str, max_width: int = _MAX_COL_NAME) -> str:
    return name if len(name) <= max_width else name[: max_width - 2] + ".."


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
    """Judge with Rich live progress + split score tables."""
    from rich.console import Group
    from rich.live import Live
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn
    from rich.table import Table
    from rich.text import Text

    from .cross import _judge_example

    total = len(all_example_names)

    progress = Progress(
        TextColumn("[bold blue]Judging"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("[dim]{task.fields[current]}"),
    )
    task_id = progress.add_task("Judge", total=total, current="")

    def _build_display():
        display_rows = judge_rows[-15:] if len(judge_rows) > 15 else judge_rows

        # Shared example column width: longest visible name, capped
        ex_width = min(
            max((len(r["example"]) for r in display_rows), default=10),
            _MAX_EXAMPLE_WIDTH,
        )

        # Table 1: absolute scores
        score_table = Table(title="Run Scores", expand=False, show_edge=True)
        score_table.add_column("Example", style="bold", min_width=ex_width, max_width=ex_width, no_wrap=True)
        for rn in run_names:
            score_table.add_column(_trunc(rn), justify="center", min_width=8)

        if len(judge_rows) > 15:
            score_table.add_row(Text(f"... {len(judge_rows) - 15} more above", style="dim"))

        for row in display_rows:
            cells = [row["example"]]
            for rn in run_names:
                s = row.get(f"{rn}_score", "")
                cells.append(Text(f"{s}/5", style=_score_style(s)) if s else Text("-", style="dim"))
            score_table.add_row(*cells)

        if judge_rows:
            avg_cells: list = [Text("Average", style="bold")]
            for rn in run_names:
                scores = [int(r[f"{rn}_score"]) for r in judge_rows if r.get(f"{rn}_score")]
                avg = sum(scores) / len(scores) if scores else 0
                style = "green" if avg >= 4 else ("yellow" if avg >= 3 else "red")
                avg_cells.append(Text(f"{avg:.1f}", style=f"bold {style}"))
            score_table.add_section()
            score_table.add_row(*avg_cells)

        renderables = [progress, score_table]

        # Table 2: vs-baseline (only when baseline set)
        if baseline_name:
            non_baseline = [rn for rn in run_names if rn != baseline_name]
            if non_baseline:
                vs_table = Table(title=f"vs {_trunc(baseline_name)}", expand=False, show_edge=True)
                vs_table.add_column("Example", style="bold", min_width=ex_width, max_width=ex_width, no_wrap=True)
                for rn in non_baseline:
                    vs_table.add_column(_trunc(rn), justify="center", min_width=8)

                if len(judge_rows) > 15:
                    vs_table.add_row(Text(f"... {len(judge_rows) - 15} more above", style="dim"))

                for row in display_rows:
                    cells = [row["example"]]
                    for rn in non_baseline:
                        bs = row.get(f"{rn}_vs_{baseline_name}", "")
                        cells.append(
                            Text(f"{bs}/5", style=_score_style(bs)) if bs else Text("-", style="dim")
                        )
                    vs_table.add_row(*cells)

                if judge_rows:
                    avg_cells2: list = [Text("Average", style="bold")]
                    for rn in non_baseline:
                        scores = [
                            int(r[f"{rn}_vs_{baseline_name}"])
                            for r in judge_rows
                            if r.get(f"{rn}_vs_{baseline_name}")
                        ]
                        avg = sum(scores) / len(scores) if scores else 0
                        style = "green" if avg >= 4 else ("yellow" if avg >= 3 else "red")
                        avg_cells2.append(Text(f"{avg:.1f}", style=f"bold {style}"))
                    vs_table.add_section()
                    vs_table.add_row(*avg_cells2)

                renderables.append(vs_table)

        return Group(*renderables)

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
    from .cross import _judge_example

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
    """Print final Rich summary — two tables (absolute + vs-baseline) + token usage."""
    from rich.table import Table
    from rich.text import Text

    # Table 1: absolute avg scores
    summary = Table(title="Judge Summary", show_edge=True)
    summary.add_column("Run", style="bold")
    summary.add_column("Scored", justify="right")
    summary.add_column("Avg Score", justify="right")

    for rn in run_names:
        scores = [int(r[f"{rn}_score"]) for r in judge_rows if r.get(f"{rn}_score")]
        avg = sum(scores) / len(scores) if scores else 0
        style = "green" if avg >= 4 else ("yellow" if avg >= 3 else "red")
        summary.add_row(rn, str(len(scores)), Text(f"{avg:.2f}", style=style))

    console.print()
    console.print(summary)

    # Table 2: avg vs-baseline (only when baseline set)
    if baseline_name:
        non_baseline = [rn for rn in run_names if rn != baseline_name]
        if non_baseline:
            vs_summary = Table(title=f"vs {baseline_name}", show_edge=True)
            vs_summary.add_column("Run", style="bold")
            vs_summary.add_column("Scored", justify="right")
            vs_summary.add_column(f"Avg vs {_trunc(baseline_name)}", justify="right")

            for rn in non_baseline:
                bscores = [
                    int(r[f"{rn}_vs_{baseline_name}"])
                    for r in judge_rows
                    if r.get(f"{rn}_vs_{baseline_name}")
                ]
                bavg = sum(bscores) / len(bscores) if bscores else 0
                bstyle = "green" if bavg >= 4 else ("yellow" if bavg >= 3 else "red")
                vs_summary.add_row(rn, str(len(bscores)), Text(f"{bavg:.2f}", style=bstyle))

            console.print(vs_summary)

    token_str = ""
    if state.input_tokens or state.output_tokens:
        token_str = f" | {state.input_tokens:,} in / {state.output_tokens:,} out tokens"

    console.print(
        f"  [dim]{state.call_count} calls"
        + (f" ({state.cache_hits} cached)" if state.cache_hits else "")
        + f" in {elapsed:.1f}s{token_str}[/dim]"
    )
    console.print(f"  [dim]Results: {judge_dir}[/dim]")
