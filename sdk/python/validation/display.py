"""Display helpers: live progress, run summaries, list groups."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from .groups import GROUPS

if TYPE_CHECKING:
    from .toml_config import RunConfig


class MultiRunProgress:
    """Thread-safe live progress display for concurrent runs using Rich."""

    def __init__(self, runs: list[RunConfig]):
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
        self._last_example: dict[str, str] = {r.name: "" for r in runs}
        self._last_status: dict[str, str] = {r.name: "waiting" for r in runs}
        self._finished: dict[str, bool] = {r.name: False for r in runs}
        self._durations: dict[str, float] = {r.name: 0.0 for r in runs}

        # Log lines (recent per run)
        self._log_lines: list[str] = []
        self._max_log_lines = 12

        self._live = Live(
            self._build_table(),
            console=self._console,
            refresh_per_second=4,
            transient=False,
        )

    def _build_table(self):
        from rich.table import Table
        from rich.text import Text

        table = Table(
            title="Validation Runs",
            show_edge=True,
            pad_edge=True,
            expand=True,
        )
        table.add_column("Run", style="bold", min_width=18)
        table.add_column("Model", style="dim", min_width=20)
        table.add_column("Progress", min_width=16)
        table.add_column("Pass", justify="right", style="green", min_width=5)
        table.add_column("Fail", justify="right", style="red", min_width=5)
        table.add_column("Latest", min_width=30)

        for name in self._run_names:
            total = self._totals.get(name, 0)
            done = self._completed.get(name, 0)
            passed = self._passed.get(name, 0)
            failed = self._failed.get(name, 0)
            cfg = self._run_configs[name]
            mode = "native" if cfg.native else "server"
            model_str = f"{cfg.model} ({mode})"

            if self._finished.get(name):
                bar = Text(f"done {done}/{total}", style="bold green")
            elif total > 0:
                pct = done / total
                filled = int(pct * 20)
                bar_str = "█" * filled + "░" * (20 - filled)
                bar = Text(f"{bar_str} {done}/{total}")
            else:
                bar = Text("waiting...", style="dim")

            latest = self._last_example.get(name, "")
            status = self._last_status.get(name, "")
            if status == "COMPLETED":
                latest_text = Text(f"✓ {latest}", style="green")
            elif status in ("FAILED", "ERROR", "TIMEOUT"):
                latest_text = Text(f"✗ {latest} ({status})", style="red")
            elif status == "waiting":
                latest_text = Text("", style="dim")
            else:
                latest_text = Text(latest, style="dim")

            table.add_row(name, model_str, bar, str(passed), str(failed), latest_text)

        return table

    def start(self):
        self._live.start()

    def stop(self):
        self._live.stop()

    def set_total(self, run_name: str, total: int):
        with self._lock:
            self._totals[run_name] = total
            self._live.update(self._build_table())

    def update(self, run_name: str, example_name: str, status: str, duration: float):
        with self._lock:
            self._completed[run_name] = self._completed.get(run_name, 0) + 1
            if status == "COMPLETED":
                self._passed[run_name] = self._passed.get(run_name, 0) + 1
            else:
                self._failed[run_name] = self._failed.get(run_name, 0) + 1
            self._last_example[run_name] = example_name
            self._last_status[run_name] = status
            self._durations[run_name] = self._durations.get(run_name, 0.0) + duration

            # Add to log
            icon = "✓" if status == "COMPLETED" else f"✗({status})"
            line = f"  [{run_name}] {example_name:<40s} {icon} [{duration:.1f}s]"
            self._log_lines.append(line)
            if len(self._log_lines) > self._max_log_lines:
                self._log_lines = self._log_lines[-self._max_log_lines :]

            self._live.update(self._build_table())

    def mark_finished(self, run_name: str):
        with self._lock:
            self._finished[run_name] = True
            self._last_status[run_name] = "done"
            self._live.update(self._build_table())

    def log(self, message: str):
        """Print a message below the live display."""
        self._live.console.print(message)

    def get_summaries(self) -> list[dict]:
        """Return summary dicts for all runs."""
        summaries = []
        for name in self._run_names:
            summaries.append(
                {
                    "run": name,
                    "model": self._run_configs[name].model,
                    "total": self._totals.get(name, 0),
                    "completed": self._passed.get(name, 0),
                    "failed": self._failed.get(name, 0),
                    "error": 0,
                    "timeout": 0,
                    "duration_s": round(self._durations.get(name, 0), 1),
                }
            )
        return summaries


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
