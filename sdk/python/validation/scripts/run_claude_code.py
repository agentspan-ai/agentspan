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
import os
import re
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


# ── Prompt env-var expansion ──────────────────────────────────────────────────

# Matches $NAME or ${NAME} where NAME is UPPER_SNAKE_CASE. Restricting to
# uppercase avoids accidentally rewriting things like "$1" or "$foo" that
# appear in prose.
_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}|\$([A-Z_][A-Z0-9_]*)")


def _expand_env_vars(text: str) -> str:
    """Substitute $UPPER_NAME / ${UPPER_NAME} with values from os.environ.

    Claude Code's sandbox blocks env-var expansion in shell commands it spawns,
    so any prompt that tells the agent to use `$OCG_API_KEY` would fail at
    runtime. Resolving the value into the prompt before invocation sidesteps
    that. Raises ValueError listing every missing variable rather than silently
    leaving the literal `$NAME` in place.
    """
    missing: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        value = os.environ.get(name)
        if value is None:
            missing.append(name)
            return match.group(0)
        return value

    resolved = _ENV_VAR_PATTERN.sub(_sub, text)
    if missing:
        unique = sorted(set(missing))
        raise ValueError(
            f"prompt references unset environment variable(s): {', '.join(unique)}"
        )
    return resolved


# ── Claude CLI invocation ─────────────────────────────────────────────────────

def _run_claude(prompt: str, timeout: int, allowed_tools: list[str]) -> dict:
    """Invoke `claude --print --output-format json` and return parsed output.

    `--bare` and `--no-session-persistence` keep each run memory-isolated:
    no CLAUDE.md auto-discovery, no ~/.claude/projects/.../memory loading,
    and no session state written that a sibling iteration could resume.

    `allowed_tools` is a list like ["Bash(curl:*)", "Read", "Grep"] — joined
    with spaces for the CLI, which accepts space- or comma-separated tools.
    """
    try:
        proc = subprocess.run(
            [
                "claude",
                "--print",
                "--bare",
                "--no-session-persistence",
                "--output-format", "json",
                "--allowed-tools", " ".join(allowed_tools),
                "-p", prompt,
            ],
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


# ── Iteration helpers ─────────────────────────────────────────────────────────

def _iteration_example_name(stem: str, n: int) -> str:
    """Build the per-iteration example name. 1-indexed so the first run reads
    as `_iter_1`, matching the convention judge/report consumers will see.
    """
    return f"{stem}_iter_{n}"


def _per_iteration_summary(examples: list[dict]) -> dict:
    """Aggregate iteration-level stats for inclusion in run meta.json.

    Returns a dict with:
      - iterations: total examples seen
      - completed:  count where status == "COMPLETED"
      - tokens_total: sum of tokens_total across iterations
      - duration_s:  sum of per-iteration durations
      - per_iteration: 1-indexed list of {iter, status, tokens_total, duration_s}
    """
    per_iter = [
        {
            "iter": i + 1,
            "status": ex.get("status", "ERROR"),
            "tokens_total": ex.get("tokens_total", 0),
            "duration_s": ex.get("duration_s", 0.0),
        }
        for i, ex in enumerate(examples)
    ]
    return {
        "iterations": len(examples),
        "completed": sum(1 for ex in examples if ex.get("status") == "COMPLETED"),
        "tokens_total": sum(ex.get("tokens_total", 0) for ex in examples),
        "duration_s": round(sum(ex.get("duration_s", 0.0) for ex in examples), 1),
        "per_iteration": per_iter,
    }


# ── Output helpers ────────────────────────────────────────────────────────────

def _write_run(
    parent_dir: Path,
    run_name: str,
    examples: dict[str, dict],
    iteration_summary: dict,
) -> None:
    """Write run_results.json + meta.json for one agent's N iterations.

    `examples` maps iteration example name -> example dict. `iteration_summary`
    is the output of `_per_iteration_summary` for the same examples in order.
    """
    run_dir = parent_dir / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    run_meta = {
        "run_name": run_name,
        "model": "claude-code",
        "native": True,
        "group": None,
        "duration_s": iteration_summary["duration_s"],
        "examples_total": iteration_summary["iterations"],
        "examples_completed": iteration_summary["completed"],
        "tokens_total": iteration_summary["tokens_total"],
        "per_iteration": iteration_summary["per_iteration"],
    }

    run_results = {**run_meta, "examples": examples}
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
        try:
            resolved_prompt = _expand_env_vars(prompt)
        except ValueError as e:
            print(f"  [{run_name}] ERROR — {e}", file=sys.stderr)
            return None
        timeout = int(run_cfg.get("timeout", 300))
        iterations = int(run_cfg.get("iterations", 1))
        allowed_tools = run_cfg.get("allowed_tools") or ["Bash(curl:*)"]

        # Sequential iterations within an agent; outer pool runs agents in
        # parallel. Caps subprocess concurrency at len(runs) regardless of N.
        examples: dict[str, dict] = {}
        ordered_examples: list[dict] = []
        for n in range(1, iterations + 1):
            iter_name = _iteration_example_name(example_name, n)
            print(f"  [{run_name}] iter {n}/{iterations} — running claude... (timeout={timeout}s)")
            t0 = time.monotonic()
            claude_output = _run_claude(resolved_prompt, timeout, allowed_tools)
            elapsed = round(time.monotonic() - t0, 1)

            # Pass the unresolved prompt to _extract_example so secrets don't
            # land on disk in run_results.json / judge inputs.
            example = _extract_example(run_name, prompt_file, prompt, claude_output)
            status = example["status"]
            tokens = example["tokens_total"]
            print(
                f"  [{run_name}] iter {n}/{iterations} — {status} in {elapsed}s "
                f"— {tokens:,} tokens"
            )
            examples[iter_name] = example
            ordered_examples.append(example)

        summary = _per_iteration_summary(ordered_examples)
        _write_run(parent_dir, run_name, examples, summary)

        return {
            "run": run_name,
            "model": "claude-code",
            "total": summary["iterations"],
            "completed": summary["completed"],
            "failed": 0,
            "error": summary["iterations"] - summary["completed"],
            "timeout": 0,
            "duration_s": summary["duration_s"],
            "tokens_total": summary["tokens_total"],
            "per_iteration": summary["per_iteration"],
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
