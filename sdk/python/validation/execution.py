"""Execution modes: sequential and parallel example runners."""

from __future__ import annotations

import signal
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .display import print_status_line
from .models import ExampleResult
from .output import build_row, write_csv_row, write_outputs
from .persistence import update_last_run_example
from .runner import compute_match, run_example_all


def run_sequential(
    examples,
    active_models: dict[str, str],
    csv_columns: list[str],
    csv_path: Path,
    outputs_dir: Path,
    timeout: int,
    retries: int,
    last_run: dict,
    last_run_lock: threading.Lock,
    native: bool = False,
) -> list[ExampleResult]:
    all_results = []
    total = len(examples)

    for i, example in enumerate(examples, 1):
        name = example.name
        print(f"  [{i}/{total}] {name:<45s}", end="", flush=True)

        results = run_example_all(example, timeout, retries, models=active_models, native=native)
        match, confidence, notes = compute_match(results)

        er = ExampleResult(
            example=example, results=results, match=match, confidence=confidence, notes=notes
        )
        all_results.append(er)

        write_outputs(outputs_dir, name, results)
        write_csv_row(csv_path, csv_columns, build_row(name, results, match, confidence, notes))
        update_last_run_example(last_run, name, er, last_run_lock)

        # Status line
        parts = []
        for provider, r in results.items():
            s = "✓" if r.status == "COMPLETED" else f"✗({r.status})"
            parts.append(f"{provider}:{s}")
        duration = max(r.duration_s for r in results.values()) if results else 0
        print(f" {' '.join(parts)} [{duration:.0f}s] {match}")

    return all_results


def run_parallel(
    examples,
    active_models: dict[str, str],
    csv_columns: list[str],
    csv_path: Path,
    outputs_dir: Path,
    timeout: int,
    retries: int,
    max_workers: int,
    server_urls: dict[str, str] | None,
    last_run: dict,
    last_run_lock: threading.Lock,
    native: bool = False,
) -> list[ExampleResult]:
    abort_event = threading.Event()
    all_results: list[ExampleResult] = []
    results_lock = threading.Lock()
    completed_count = [0]

    original_handler = signal.getsignal(signal.SIGINT)

    def _handle_sigint(sig, frame):
        print("\n  Aborting... writing partial results.")
        abort_event.set()

    signal.signal(signal.SIGINT, _handle_sigint)

    total = len(examples)

    try:
        # Try rich progress
        use_rich = False
        try:
            from rich.console import Console
            from rich.progress import (
                BarColumn,
                MofNCompleteColumn,
                Progress,
                TextColumn,
                TimeRemainingColumn,
            )

            use_rich = True
        except ImportError:
            pass

        def _run_one(example):
            if abort_event.is_set():
                return None
            results = run_example_all(
                example, timeout, retries, models=active_models, server_urls=server_urls,
                native=native,
            )
            if abort_event.is_set():
                return None
            match, confidence, notes = compute_match(results)
            er = ExampleResult(
                example=example, results=results, match=match, confidence=confidence, notes=notes
            )

            write_outputs(outputs_dir, example.name, results)
            write_csv_row(
                csv_path, csv_columns, build_row(example.name, results, match, confidence, notes)
            )
            update_last_run_example(last_run, example.name, er, last_run_lock)

            with results_lock:
                all_results.append(er)
                completed_count[0] += 1

            return er

        if use_rich:
            console = Console()
            progress = Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeRemainingColumn(),
                console=console,
            )
            task_id = progress.add_task("Examples", total=total)

            with progress:
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    futures = {pool.submit(_run_one, ex): ex for ex in examples}
                    for future in as_completed(futures):
                        if abort_event.is_set():
                            break
                        er = future.result()
                        if er:
                            progress.update(task_id, advance=1)
                            parts = []
                            for prov, r in er.results.items():
                                s = "✓" if r.status == "COMPLETED" else "✗"
                                parts.append(f"{prov}:{s}")
                            dur = (
                                max(r.duration_s for r in er.results.values()) if er.results else 0
                            )
                            progress.console.print(
                                f"    {er.example.name:<45s} {' '.join(parts)} [{dur:.0f}s] {er.match}"
                            )
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(_run_one, ex): ex for ex in examples}
                for future in as_completed(futures):
                    if abort_event.is_set():
                        break
                    er = future.result()
                    if er:
                        print_status_line(
                            completed_count[0], total, er.example.name, er.results, er.match
                        )

    finally:
        signal.signal(signal.SIGINT, original_handler)

    # Sort results back to original order
    order = {ex.name: i for i, ex in enumerate(examples)}
    all_results.sort(key=lambda er: order.get(er.example.name, 0))

    return all_results
