"""Run autonomous Claude Code CLI agents and produce HTML comparison reports.

Each run in the TOML config points to a prompt .md file. The script spawns
`claude --print --output-format json` for each run, captures token usage and
output, and writes run_results.json in the same format the existing
judge/HTML report system reads.

Usage:
    cd sdk/python
    python -m validation.scripts.run_claude_code --config validation/cc_compare.toml
    python -m validation.scripts.run_claude_code --config validation/cc_compare.toml --judge
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-reuse-declared]

SCRIPT_DIR = Path(__file__).resolve().parent
SDK_DIR = SCRIPT_DIR.parent.parent  # sdk/python/
OUTPUT_DIR = SDK_DIR / "output"


# ── TOML config ──────────────────────────────────────────────────────────────

def _load_config(config_path: Path) -> dict:
    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    defaults = raw.get("defaults", {})
    judge = raw.get("judge", {})
    runs_raw = raw.get("runs", {})

    runs = {}
    for name, run in runs_raw.items():
        merged = {**defaults, **run, "name": name}
        runs[name] = merged

    return {"runs": runs, "judge": judge}


# ── Claude CLI invocation ─────────────────────────────────────────────────────

def _run_claude(prompt: str, timeout: int) -> dict:
    """Invoke `claude --print --output-format json` and return parsed output."""
    try:
        proc = subprocess.run(
            ["claude", "--print", "--output-format", "json", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {"error": "claude CLI not found — is it installed and on PATH?"}
    except subprocess.TimeoutExpired:
        return {"error": f"timeout after {timeout}s"}

    raw = proc.stdout.strip()
    if not raw:
        return {"error": f"no output (exit {proc.returncode})", "stderr": proc.stderr[:500]}

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "JSON decode failed", "raw": raw[:500]}


# ── Token mapping ─────────────────────────────────────────────────────────────

def _extract_example(run_name: str, prompt_file: str, prompt: str, claude_output: dict) -> dict:
    """Map claude CLI JSON output → run_results.json example entry."""
    is_error = claude_output.get("is_error", True) or "error" in claude_output

    usage = claude_output.get("usage", {})
    tokens_prompt = (
        (usage.get("input_tokens") or 0)
        + (usage.get("cache_creation_input_tokens") or 0)
        + (usage.get("cache_read_input_tokens") or 0)
    )
    tokens_completion = usage.get("output_tokens") or 0
    tokens_total = tokens_prompt + tokens_completion

    output_text = claude_output.get("result", claude_output.get("error", ""))
    duration_s = round((claude_output.get("duration_ms") or 0) / 1000, 1)

    return {
        "exit_code": 1 if is_error else 0,
        "status": "ERROR" if is_error else "COMPLETED",
        "duration_s": duration_s,
        "execution_id": claude_output.get("session_id") or str(uuid.uuid4()),
        "tool_calls": claude_output.get("num_turns") or 0,
        "tokens_total": tokens_total,
        "tokens_prompt": tokens_prompt,
        "tokens_completion": tokens_completion,
        "output_text": output_text,
        "output_length": len(output_text),
        "has_error": is_error,
        "error_summary": claude_output.get("error", "") if is_error else "",
        "history": [],
        "_prompt": prompt,
    }


# ── Output helpers ────────────────────────────────────────────────────────────

def _write_run(parent_dir: Path, run_name: str, example_name: str, example: dict) -> None:
    run_dir = parent_dir / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    run_meta = {
        "run_name": run_name,
        "model": "claude-code",
        "native": True,
        "group": None,
        "duration_s": example["duration_s"],
        "examples_total": 1,
        "examples_completed": 1 if example["status"] == "COMPLETED" else 0,
    }

    run_results = {**run_meta, "examples": {example_name: example}}
    (run_dir / "run_results.json").write_text(json.dumps(run_results, indent=2))
    (run_dir / "meta.json").write_text(json.dumps(run_meta, indent=2))


def _write_parent_meta(parent_dir: Path, run_summaries: list[dict]) -> None:
    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "runs": {s["run"]: {"model": "claude-code", "native": True, "group": None} for s in run_summaries},
        "total_duration_s": round(sum(s["duration_s"] for s in run_summaries), 1),
        "run_summaries": run_summaries,
    }
    (parent_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    # Copy config into parent dir so judge_results.py can find it
    # (judge_results.py looks for config.toml to load JudgeConfig)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Run Claude Code agents and compare token usage")
    parser.add_argument("--config", required=True, help="Path to TOML config (relative to sdk/python/)")
    parser.add_argument("--judge", action="store_true", help="Run LLM judge after execution")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Output root directory")
    args = parser.parse_args()

    config_path = Path(args.config) if Path(args.config).is_absolute() else SDK_DIR / args.config
    if not config_path.exists():
        print(f"ERROR: config not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    config = _load_config(config_path)
    runs = config["runs"]
    judge_cfg = config.get("judge", {})

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    parent_dir = Path(args.output_dir) / f"cc_{timestamp}"
    parent_dir.mkdir(parents=True, exist_ok=True)

    # Copy config so judge_results.py can pick it up
    import shutil
    shutil.copy(config_path, parent_dir / "config.toml")

    print(f"\nOutput: {parent_dir}\n")

    # Use the example name derived from the config filename (sans extension)
    example_name = config_path.stem

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _run_one(run_name: str, run_cfg: dict) -> dict | None:
        prompt_file = run_cfg.get("prompt_file")
        if not prompt_file:
            print(f"  [{run_name}] SKIP — no prompt_file", file=sys.stderr)
            return None

        prompt_path = Path(prompt_file) if Path(prompt_file).is_absolute() else SDK_DIR / prompt_file
        if not prompt_path.exists():
            print(f"  [{run_name}] ERROR — prompt file not found: {prompt_path}", file=sys.stderr)
            return None

        prompt = prompt_path.read_text()
        timeout = int(run_cfg.get("timeout", 300))

        print(f"  [{run_name}] Running claude... (timeout={timeout}s)")
        t0 = time.monotonic()
        claude_output = _run_claude(prompt, timeout)
        elapsed = round(time.monotonic() - t0, 1)

        example = _extract_example(run_name, prompt_file, prompt, claude_output)
        status = example["status"]
        tokens = example["tokens_total"]
        print(f"  [{run_name}] {status} in {elapsed}s — {tokens:,} tokens total")

        _write_run(parent_dir, run_name, example_name, example)

        return {
            "run": run_name,
            "model": "claude-code",
            "total": 1,
            "completed": 1 if status == "COMPLETED" else 0,
            "failed": 0,
            "error": 1 if status == "ERROR" else 0,
            "timeout": 0,
            "duration_s": elapsed,
        }

    run_summaries = []
    with ThreadPoolExecutor(max_workers=len(runs)) as pool:
        futures = {pool.submit(_run_one, name, cfg): name for name, cfg in runs.items()}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                run_summaries.append(result)

    _write_parent_meta(parent_dir, run_summaries)

    print(f"\n  Results written to {parent_dir}")

    if args.judge:
        print("\n  Running judge...")
        from validation.config import Settings
        from validation.judge import judge_across_runs
        from validation.toml_config import JudgeConfig

        jc = JudgeConfig(
            baseline_run=judge_cfg.get("baseline_run"),
            model=judge_cfg.get("model", "gpt-4o-mini"),
            max_output_chars=int(judge_cfg.get("max_output_chars", 4000)),
            max_tokens=int(judge_cfg.get("max_tokens", 400)),
            rate_limit=float(judge_cfg.get("rate_limit", 0.5)),
        )
        settings = Settings.from_env()
        if not settings.openai_api_key:
            print("ERROR: OPENAI_API_KEY not set — skipping judge.", file=sys.stderr)
        else:
            judge_across_runs(parent_dir, jc, settings)


if __name__ == "__main__":
    main()
