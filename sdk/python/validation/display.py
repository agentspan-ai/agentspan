"""Display helpers: run summaries, list groups."""

from __future__ import annotations

from .groups import GROUPS


def print_single_run_summary(results, run_name: str) -> dict:
    """Print summary for a single-model run. Returns summary dict."""
    total = len(results)
    completed = sum(1 for sr in results if sr.result.status == "COMPLETED")
    failed = sum(1 for sr in results if sr.result.status == "FAILED")
    error = sum(1 for sr in results if sr.result.status == "ERROR")
    timeout = sum(1 for sr in results if sr.result.status == "TIMEOUT")
    durations = [sr.result.duration_s for sr in results if sr.result.duration_s > 0]
    total_dur = sum(durations)

    print(
        f"\n  [{run_name}] {completed}/{total} completed"
        f" | {failed} failed | {error} error | {timeout} timeout"
        f" | {total_dur:.0f}s total"
    )

    return {
        "run": run_name,
        "total": total,
        "completed": completed,
        "failed": failed,
        "error": error,
        "timeout": timeout,
        "duration_s": round(total_dur, 1),
    }


def print_multi_run_summary(run_summaries: list[dict]) -> None:
    """Print combined table for all runs."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Multi-Run Summary")
        table.add_column("Run")
        table.add_column("Examples", justify="right")
        table.add_column("Pass", justify="right", style="green")
        table.add_column("Fail", justify="right", style="red")
        table.add_column("Error", justify="right", style="red")
        table.add_column("Timeout", justify="right", style="yellow")
        table.add_column("Duration", justify="right")

        for s in run_summaries:
            table.add_row(
                s["run"],
                str(s["total"]),
                str(s["completed"]),
                str(s["failed"]),
                str(s["error"]),
                str(s["timeout"]),
                f"{s['duration_s']:.0f}s",
            )

        console.print(table)
    except ImportError:
        print("\n  Multi-Run Summary:")
        for s in run_summaries:
            print(
                f"    {s['run']}: {s['completed']}/{s['total']} pass"
                f" | {s['failed']} fail | {s['error']} error"
                f" | {s['timeout']} timeout | {s['duration_s']:.0f}s"
            )


def list_groups():
    print("Available groups:")
    for name, stems in GROUPS.items():
        if stems:
            print(f"  {name}: {len(stems)} examples")
