"""Multi-run orchestrator: concurrent named runs from TOML config."""

from __future__ import annotations

import csv
import json
import signal
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from .config import SINGLE_RUN_CSV_COLUMNS, Settings
from .discovery import discover_examples
from .display import MultiRunProgress, compute_run_summary, print_multi_run_summary
from .execution import check_server_health, run_examples
from .persistence import (
    completed_examples_single,
    failed_examples_single,
    save_last_run,
    sort_slowest_first,
)
from .reporting import (
    _format_duration,
    build_single_row,
    update_latest_symlink,
    write_csv_row,
    write_single_output,
)
from .toml_config import MultiRunConfig, RunConfig


def run_all(
    config: MultiRunConfig,
    runs: list[RunConfig],
    output_dir: Path,
    resume: bool,
    retry_failed: bool,
    judge_after: bool,
) -> Path:
    """Orchestrate multiple concurrent runs. Returns parent run dir."""
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    run_id = uuid.uuid4().hex[:4]
    parent_dir = output_dir / f"run_{timestamp}_{run_id}"
    parent_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "timestamp": now.isoformat(),
        "runs": {r.name: {"model": r.model, "native": r.native, "group": r.group} for r in runs},
    }

    # Shared abort event
    abort_event = threading.Event()
    original_handler = signal.getsignal(signal.SIGINT)

    def _handle_sigint(sig, frame):
        abort_event.set()

    signal.signal(signal.SIGINT, _handle_sigint)

    # Assign ports for server (non-native) runs
    port_assignments: dict[str, int] = {}
    next_port = 8080
    for r in runs:
        if not r.native:
            port_assignments[r.name] = next_port
            next_port += 1

    # Try rich live progress, fall back to plain print
    try:
        progress = MultiRunProgress(runs, max_example_rows=config.display.max_example_rows)
        use_rich = True
    except ImportError:
        progress = None
        use_rich = False

    run_summaries: list[dict] = []
    summaries_lock = threading.Lock()
    start_time = time.monotonic()

    try:
        if use_rich:
            progress.start()

        if len(runs) == 1:
            summary = _run_single(
                runs[0],
                parent_dir,
                abort_event,
                port_assignments.get(runs[0].name),
                resume,
                retry_failed,
                progress,
            )
            if summary:
                run_summaries.append(summary)
        else:
            with ThreadPoolExecutor(max_workers=len(runs)) as pool:
                futures = {
                    pool.submit(
                        _run_single,
                        r,
                        parent_dir,
                        abort_event,
                        port_assignments.get(r.name),
                        resume,
                        retry_failed,
                        progress,
                    ): r
                    for r in runs
                }
                for future in as_completed(futures):
                    summary = future.result()
                    if summary:
                        with summaries_lock:
                            run_summaries.append(summary)
    finally:
        signal.signal(signal.SIGINT, original_handler)
        if use_rich:
            progress.stop()

    elapsed = time.monotonic() - start_time
    meta["total_duration_s"] = round(elapsed, 1)
    meta["run_summaries"] = run_summaries

    meta_path = parent_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))

    update_latest_symlink(output_dir, parent_dir)

    # Final summary
    print()
    if run_summaries:
        print_multi_run_summary(run_summaries)

    print()
    print("=" * 50)
    print(f" Run directory: {parent_dir}")
    print(f" Total time: {_format_duration(elapsed)}")
    print("=" * 50)

    # Judge
    if judge_after and not abort_event.is_set():
        from .judge import judge_across_runs

        settings = Settings.from_env()
        judge_across_runs(parent_dir, config.judge, settings)

    return parent_dir


def _run_single(
    run_cfg: RunConfig,
    parent_dir: Path,
    abort_event: threading.Event,
    port: int | None,
    resume: bool,
    retry_failed: bool,
    progress: MultiRunProgress | None,
) -> dict | None:
    """Execute a single run in its own sub-directory. Returns summary dict."""
    run_dir = parent_dir / run_cfg.name
    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    csv_path = run_dir / "results.csv"

    model_id = run_cfg.model
    model_name = model_id.split("/")[0] if "/" in model_id else model_id

    # Discover examples
    examples = discover_examples([], run_cfg.group)
    if not examples:
        msg = f"[{run_cfg.name}] No examples found" + (
            f" for group {run_cfg.group}" if run_cfg.group else ""
        )
        if progress:
            progress.log(f"  {msg}")
        else:
            print(f"  {msg}")
        return None

    # Load last run for sorting
    last_run_path = run_dir / "report.json"
    if last_run_path.exists():
        try:
            last_run = json.loads(last_run_path.read_text())
        except (json.JSONDecodeError, OSError):
            last_run = {}
    else:
        last_run = {}

    last_run_lock = threading.Lock()
    examples = sort_slowest_first(examples, last_run)

    # Resume
    if resume:
        done = completed_examples_single(run_dir)
        if done:
            examples = [ex for ex in examples if ex.name not in done]
            if not examples:
                return None

    # Retry-failed
    if retry_failed and last_run:
        fails = failed_examples_single(last_run)
        examples = [ex for ex in examples if ex.name in fails]
        if not examples:
            return None

    # Set total in progress display
    total = len(examples)
    if progress:
        progress.set_total(run_cfg.name, total, [ex.name for ex in examples])

    # Server health check
    server_url = None
    pool = None
    if not run_cfg.native:
        if port:
            server_url = f"http://localhost:{port}/api"
        else:
            server_url = run_cfg.server_url

        if not check_server_health(server_url):
            try:
                from .execution import ServerPool

                pool = ServerPool(base_port=port or 8080)
                pool.start({model_name: model_id}, log_dir=run_dir / "logs")
                urls = pool.get_server_urls()
                server_url = urls.get(model_name, server_url)
            except Exception as e:
                msg = f"[{run_cfg.name}] Server start failed: {e}"
                if progress:
                    progress.log(f"  {msg}")
                else:
                    print(f"  {msg}")
                if pool:
                    pool.shutdown()
                return None

    # CSV header
    columns = SINGLE_RUN_CSV_COLUMNS
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()

    last_run["run_dir"] = str(run_dir)
    start_time = time.monotonic()

    # Progress callbacks
    def on_start(example):
        if progress:
            progress.mark_running(run_cfg.name, example.name)

    def on_complete(sr):
        write_single_output(outputs_dir, sr.example.name, sr.result)
        write_csv_row(csv_path, columns, build_single_row(sr.example.name, sr.result))

        from .persistence import update_last_run_single

        update_last_run_single(last_run, sr.example.name, sr, last_run_lock)

        if progress:
            progress.update(run_cfg.name, sr.example.name, sr.result.status, sr.result.duration_s)
        else:
            status = "✓" if sr.result.status == "COMPLETED" else f"✗({sr.result.status})"
            print(
                f"    [{run_cfg.name}] {sr.example.name:<40s} {status} [{sr.result.duration_s:.1f}s]"
            )

    try:
        results = run_examples(
            examples=examples,
            model_name=model_name,
            model_id=model_id,
            timeout=run_cfg.timeout,
            retries=run_cfg.retries,
            max_workers=run_cfg.max_workers if run_cfg.parallel else 1,
            native=run_cfg.native,
            server_url=server_url,
            secondary_model=run_cfg.secondary_model,
            abort_event=abort_event,
            on_complete=on_complete,
            on_start=on_start,
        )
    finally:
        if pool:
            pool.shutdown()

    elapsed = time.monotonic() - start_time

    if progress:
        progress.mark_finished(run_cfg.name)

    # Save run metadata
    run_meta = {
        "run_name": run_cfg.name,
        "model": model_id,
        "native": run_cfg.native,
        "group": run_cfg.group,
        "duration_s": round(elapsed, 1),
        "examples_total": total,
        "examples_completed": sum(1 for sr in results if sr.result.status == "COMPLETED"),
    }
    run_meta_path = run_dir / "meta.json"
    run_meta_path.write_text(json.dumps(run_meta, indent=2))

    save_last_run(last_run, last_run_lock)

    summary = compute_run_summary(results, run_cfg.name, model_id)
    return summary
