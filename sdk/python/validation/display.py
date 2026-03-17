"""Display helpers: live progress, run summaries, list groups."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from .groups import GROUPS

if TYPE_CHECKING:
    from .toml_config import RunConfig


class MultiRunProgress:
    """Thread-safe live progress display for concurrent runs using Rich.

    Shows two tables:
    1. Run summary — per-run progress bars, pass/fail counts
    2. Example matrix — per-example status across all runs with duration
    """

    def __init__(self, runs: list[RunConfig], max_example_rows: int = 40):
        from rich.console import Console
        from rich.live import Live

        self._console = Console()
        self._lock = threading.Lock()
        self._run_names = [r.name for r in runs]
        self._run_configs = {r.name: r for r in runs}

        # Per-run state
        self._totals: dict[str, int] = {}
        self._completed: dict[str, int] = {r.name: 0 for r in runs}
        self._passed: dict[str, int] = {r.name: 0 for r in runs}
        self._failed: dict[str, int] = {r.name: 0 for r in runs}
        self._finished: dict[str, bool] = {r.name: False for r in runs}
        self._durations: dict[str, float] = {r.name: 0.0 for r in runs}

        # Per-example × run state: {example_name: {run_name: (status, duration)}}
        self._example_results: dict[str, dict[str, tuple[str, float]]] = {}
        # Track which examples are currently running: {run_name: {example_name: start_time}}
        self._running: dict[str, dict[str, float]] = {r.name: {} for r in runs}
        # All known examples in order
        self._all_examples: list[str] = []
        self._example_set: set[str] = set()

        # Track start times
        self._start_time = time.monotonic()

        self._max_example_rows = max_example_rows

        self._live = Live(
            self._build_display(),
            console=self._console,
            refresh_per_second=4,
            transient=False,
        )

    def _build_display(self):
        from rich.console import Group
        from rich.table import Table
        from rich.text import Text

        # ── Run summary table ──
        run_table = Table(show_edge=True, pad_edge=True, expand=True, title="Runs")
        run_table.add_column("Run", style="bold", min_width=16)
        run_table.add_column("Model", style="dim", min_width=16, max_width=30)
        run_table.add_column("Progress", min_width=18)
        run_table.add_column("Pass", justify="right", style="green", min_width=5)
        run_table.add_column("Fail", justify="right", style="red", min_width=5)
        run_table.add_column("Time", justify="right", min_width=6)

        for name in self._run_names:
            total = self._totals.get(name, 0)
            done = self._completed.get(name, 0)
            passed = self._passed.get(name, 0)
            failed = self._failed.get(name, 0)
            dur = self._durations.get(name, 0)
            cfg = self._run_configs[name]
            mode = "native" if cfg.native else "server"
            model_str = f"{cfg.model} ({mode})"

            if self._finished.get(name):
                bar = Text(f"✓ {done}/{total}", style="bold green")
            elif total > 0:
                pct = done / total
                filled = int(pct * 20)
                bar_str = "█" * filled + "░" * (20 - filled)
                bar = Text(f"{bar_str} {done}/{total}")
            else:
                bar = Text("waiting...", style="dim")

            dur_str = f"{dur:.0f}s" if dur > 0 else ""
            run_table.add_row(name, model_str, bar, str(passed), str(failed), dur_str)

        # ── Example matrix table ──
        ex_table = Table(show_edge=True, pad_edge=True, expand=True, title="Examples")
        ex_table.add_column("Example", style="bold", min_width=25)
        for rn in self._run_names:
            ex_table.add_column(rn, justify="center", min_width=12)

        # Show recent examples (last N that have any activity)
        active_examples = [ex for ex in self._all_examples if ex in self._example_results]
        if len(active_examples) > self._max_example_rows:
            skipped = len(active_examples) - self._max_example_rows
            display_examples = active_examples[-self._max_example_rows :]
            ex_table.add_row(
                Text(f"... {skipped} more above", style="dim"),
                *[Text("", style="dim") for _ in self._run_names],
            )
        else:
            display_examples = active_examples

        for ex_name in display_examples:
            cells: list[Text] = [Text(ex_name)]
            run_data = self._example_results.get(ex_name, {})
            for rn in self._run_names:
                if rn in run_data:
                    status, dur = run_data[rn]
                    if status == "COMPLETED":
                        cells.append(Text(f"✓ {dur:.1f}s", style="green"))
                    elif status == "TIMEOUT":
                        cells.append(Text(f"✗ {dur:.0f}s", style="yellow"))
                    else:
                        cells.append(Text(f"✗ {status[:5]}", style="red"))
                elif ex_name in self._running.get(rn, {}):
                    elapsed = time.monotonic() - self._running[rn][ex_name]
                    cells.append(Text(f"⟳ {elapsed:.0f}s", style="cyan"))
                else:
                    cells.append(Text("·", style="dim"))
            ex_table.add_row(*cells)

        return Group(run_table, ex_table)

    def start(self):
        self._live.start()

    def stop(self):
        self._live.stop()

    def set_total(self, run_name: str, total: int, example_names: list[str] | None = None):
        with self._lock:
            self._totals[run_name] = total
            if example_names:
                for ex in example_names:
                    if ex not in self._example_set:
                        self._example_set.add(ex)
                        self._all_examples.append(ex)
            self._live.update(self._build_display())

    def mark_running(self, run_name: str, example_name: str):
        """Mark an example as currently running in a run."""
        with self._lock:
            if example_name not in self._example_set:
                self._example_set.add(example_name)
                self._all_examples.append(example_name)
            self._running.setdefault(run_name, {})[example_name] = time.monotonic()
            self._live.update(self._build_display())

    def update(self, run_name: str, example_name: str, status: str, duration: float):
        with self._lock:
            self._completed[run_name] = self._completed.get(run_name, 0) + 1
            if status == "COMPLETED":
                self._passed[run_name] = self._passed.get(run_name, 0) + 1
            else:
                self._failed[run_name] = self._failed.get(run_name, 0) + 1
            self._durations[run_name] = self._durations.get(run_name, 0.0) + duration

            # Update example matrix
            if example_name not in self._example_set:
                self._example_set.add(example_name)
                self._all_examples.append(example_name)
            self._example_results.setdefault(example_name, {})[run_name] = (status, duration)
            self._running.get(run_name, {}).pop(example_name, None)

            self._live.update(self._build_display())

    def mark_finished(self, run_name: str):
        with self._lock:
            self._finished[run_name] = True
            self._running[run_name] = {}
            self._live.update(self._build_display())

    def log(self, message: str):
        """Print a message below the live display."""
        self._live.console.print(message)


def compute_run_summary(results, run_name: str, model: str) -> dict:
    """Compute summary dict for a single run (no printing)."""
    total = len(results)
    completed = sum(1 for sr in results if sr.result.status == "COMPLETED")
    failed = sum(1 for sr in results if sr.result.status == "FAILED")
    error = sum(1 for sr in results if sr.result.status == "ERROR")
    timeout = sum(1 for sr in results if sr.result.status == "TIMEOUT")
    durations = [sr.result.duration_s for sr in results if sr.result.duration_s > 0]
    total_dur = sum(durations)

    return {
        "run": run_name,
        "model": model,
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
        table = Table(title="Results")
        table.add_column("Run", style="bold")
        table.add_column("Model", style="dim")
        table.add_column("Examples", justify="right")
        table.add_column("Pass", justify="right", style="green")
        table.add_column("Fail", justify="right", style="red")
        table.add_column("Error", justify="right", style="red")
        table.add_column("Timeout", justify="right", style="yellow")
        table.add_column("Duration", justify="right")

        for s in run_summaries:
            table.add_row(
                s["run"],
                s.get("model", ""),
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
