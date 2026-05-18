"""Multi-run orchestrator: concurrent named runs from TOML config."""

from __future__ import annotations

import json
import signal
import sys
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from .config import Settings
from .discovery import discover_examples
from .display import MultiRunProgress, compute_run_summary, print_multi_run_summary
from .execution import run_examples
from .execution.runner import build_resolved_env
from .persistence import (
    completed_examples_single,
    failed_examples_single,
    save_last_run,
    sort_slowest_first,
)
from .reporting import (
    _format_duration,
    update_latest_symlink,
    write_run_results_json,
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

    # Start one shared server for all non-native runs
    shared_server_url: str | None = None
    server_pool = None
    has_server_runs = any(not r.native for r in runs)
    if has_server_runs:
        from .execution import ServerPool

        first_server_run = next(r for r in runs if not r.native)
        port = _parse_port(first_server_run.server_url)
        server_pool = ServerPool(base_port=port)
        server_pool.start(
            {"server": first_server_run.server_url},
            log_dir=parent_dir / "logs",
            extra_env=config.env or None,
        )
        urls = server_pool.get_server_urls()
        shared_server_url = urls.get("server", first_server_run.server_url)

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

        with ThreadPoolExecutor(max_workers=len(runs)) as executor:
            futures = {
                executor.submit(
                    _run_single,
                    r,
                    parent_dir,
                    abort_event,
                    shared_server_url,
                    resume,
                    retry_failed,
                    progress,
                    config.env or None,
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
        if server_pool:
            server_pool.shutdown()

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

        settings = Settings.from_env().with_env_overrides(config.judge.env)
        if not settings.openai_api_key:
            print(
                "ERROR: OPENAI_API_KEY not set for judge. Set it in shell or in [judge.env] in runs.toml.",
                file=sys.stderr,
            )
            sys.exit(1)
        judge_across_runs(parent_dir, config.judge, settings)

    return parent_dir


def _run_single(
    run_cfg: RunConfig,
    parent_dir: Path,
    abort_event: threading.Event,
    shared_server_url: str | None,
    resume: bool,
    retry_failed: bool,
    progress: MultiRunProgress | None,
    global_env: dict | None = None,
) -> dict | None:
    """Execute a single run in its own sub-directory. Returns summary dict."""
    run_dir = parent_dir / run_cfg.name
    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

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

    server_url = shared_server_url if not run_cfg.native else None

    resolved = build_resolved_env(
        model_id, server_url, run_cfg.secondary_model, global_env, run_cfg.env
    )
    _write_preflight_log(run_dir, run_cfg, resolved)

    # agentspan doctor (non-native only)
    if server_url:
        cli_server_url = server_url.rstrip("/").removesuffix("/api")
        try:
            result = subprocess.run(
                ["agentspan", "--server", cli_server_url, "doctor"],
                capture_output=True,
                text=True,
                check=False,
                env=resolved,
            )
            doctor_out = (result.stdout or "") + (result.stderr or "")
        except FileNotFoundError:
            doctor_out = "agentspan not found in PATH\n"
        (run_dir / "doctor.log").write_text(doctor_out)

    last_run["run_dir"] = str(run_dir)
    start_time = time.monotonic()

    # Progress callbacks
    def on_start(example):
        if progress:
            progress.mark_running(run_cfg.name, example.name)

    def on_complete(sr):
        write_single_output(outputs_dir, sr.example.name, sr.result)

        from .persistence import update_last_run_single

        update_last_run_single(last_run, sr.example.name, sr, last_run_lock)

        if progress:
            progress.update(run_cfg.name, sr.example.name, sr.result.status, sr.result.duration_s)
        else:
            status = "✓" if sr.result.status == "COMPLETED" else f"✗({sr.result.status})"
            print(
                f"    [{run_cfg.name}] {sr.example.name:<40s} {status} [{sr.result.duration_s:.1f}s]"
            )

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
        extra_env={**(global_env or {}), **run_cfg.env} or None,
    )

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

    write_run_results_json(run_dir, run_meta, results, last_run)
    save_last_run(last_run, last_run_lock)

    summary = compute_run_summary(results, run_cfg.name, model_id)
    return summary


def _parse_port(server_url: str) -> int:
    """Extract port from URL like http://localhost:6767/api. Defaults to 6767."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(server_url)
        return parsed.port or 6767
    except Exception:
        return 6767


_API_KEY_VARS = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"}
_CONFIG_VARS = [
    "AGENTSPAN_SERVER_URL",
    "JUDGE_LLM_MODEL",
    "JUDGE_MAX_OUTPUT_CHARS",
    "JUDGE_MAX_TOKENS",
    "JUDGE_MAX_CALLS",
    "JUDGE_RATE_LIMIT",
]


def _write_preflight_log(run_dir: Path, run_cfg: "RunConfig", resolved: dict) -> None:
    lines = ["=== EFFECTIVE ENV ==="]
    for k in sorted(_API_KEY_VARS):
        val = resolved.get(k)
        lines.append(f"  {k}: {'***set***' if val else '(not set)'}")
    for k in _CONFIG_VARS:
        val = resolved.get(k)
        lines.append(f"  {k}: {val if val is not None else '(not set)'}")
    lines.append("")
    lines.append("=== AGENTSPAN_ VARS ===")
    agentspan_vars = sorted(k for k in resolved if k.startswith("AGENTSPAN_"))
    if agentspan_vars:
        for k in agentspan_vars:
            lines.append(f"  {k}: {resolved[k]}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("=== RUN CONFIG ===")
    lines.append(f"  name: {run_cfg.name}")
    lines.append(f"  model: {run_cfg.model}")
    lines.append(f"  native: {run_cfg.native}")
    lines.append(f"  group: {run_cfg.group}")
    run_env = run_cfg.env or {}
    if run_env:
        masked = {k: ("***set***" if k in _API_KEY_VARS else v) for k, v in run_env.items()}
        lines.append(f"  env: {masked}")
    else:
        lines.append("  env: (none)")

    (run_dir / "preflight.log").write_text("\n".join(lines) + "\n")
