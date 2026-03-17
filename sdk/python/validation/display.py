"""Display helpers: status lines, summary table, flaky detection, list groups."""

from __future__ import annotations

from .groups import GROUPS
from .models import ExampleResult
from .persistence import load_last_run


def print_status_line(i: int, total: int, name: str, results: dict, match: str):
    parts = []
    for provider, r in results.items():
        s = "✓" if r.status == "COMPLETED" else f"✗({r.status})"
        parts.append(f"{provider}:{s}")
    duration = max(r.duration_s for r in results.values()) if results else 0
    print(f"  [{i}/{total}] {name:<45s} {' '.join(parts)} [{duration:.0f}s] {match}")


def print_summary_table(all_results: list[ExampleResult], active_models: dict[str, str]):
    """Print per-provider summary table."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Summary")
        table.add_column("Provider")
        table.add_column("Total", justify="right")
        table.add_column("Completed", justify="right", style="green")
        table.add_column("Failed", justify="right", style="red")
        table.add_column("Error", justify="right", style="red")
        table.add_column("Timeout", justify="right", style="yellow")

        for provider in active_models:
            total = completed = failed = error = timeout = 0
            for er in all_results:
                r = er.results.get(provider)
                if not r:
                    continue
                total += 1
                if r.status == "COMPLETED":
                    completed += 1
                elif r.status == "FAILED":
                    failed += 1
                elif r.status == "ERROR":
                    error += 1
                elif r.status == "TIMEOUT":
                    timeout += 1
            table.add_row(
                provider, str(total), str(completed), str(failed), str(error), str(timeout)
            )

        # Overall row
        durations = []
        for er in all_results:
            if er.results:
                durations.append(max(r.duration_s for r in er.results.values()))
        fastest = f"{min(durations):.1f}s" if durations else "-"
        slowest = f"{max(durations):.1f}s" if durations else "-"

        console.print(table)
        console.print(f"  Fastest example: {fastest} | Slowest: {slowest}")

        # Flaky detection
        last_run = load_last_run()
        lr_examples = last_run.get("examples", {})
        flaky = []
        for er in all_results:
            entry = lr_examples.get(er.example.name, {})
            history = entry.get("history", [])
            if len(history) >= 3 and len(set(history)) > 1:
                flaky.append(er.example.name)
        if flaky:
            console.print(f"\n  [yellow]Flaky examples ({len(flaky)}):[/yellow]")
            for name in flaky:
                h = lr_examples[name]["history"]
                console.print(f"    {name}: {' '.join(h)}")

    except ImportError:
        # Fallback without rich
        print("\n  Provider Summary:")
        for provider in active_models:
            completed = sum(
                1
                for er in all_results
                if er.results.get(provider, None) and er.results[provider].status == "COMPLETED"
            )
            total = sum(1 for er in all_results if provider in er.results)
            print(f"    {provider}: {completed}/{total} completed")


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
