"""Run a single OCG-aware Claude Code agent on a prompt.

Quick local eval: feed it a prompt file, get the response on stdout. No TOML,
no judge, no iteration loops, no JSON output files.

Usage:
    cd sdk/python
    python -m validation.scripts.run_ocg_agent path/to/prompt.md
    echo "where does X live?" | python -m validation.scripts.run_ocg_agent -
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from validation.scripts.run_claude_code import (
    REPO_ROOT,
    _expand_env_vars,
    _run_claude,
)

ALLOWED_TOOLS = ["Bash(curl:*)", "Read", "Glob", "Grep"]

# Local OCG dev server. The script auto-prepends this primer so the user's
# prompt can be just a question. If the local server doesn't require auth,
# `OCG_API_KEY` can be set to any non-empty value to satisfy env-var expansion.
OCG_URL = "http://localhost:6100/api/v1/agent/query"
OCG_PRIMER = (
    f"For codebase questions, use OCG (Open Context Graph) at `{OCG_URL}`. "
    "Auth: `X-Api-Key: $OCG_API_KEY`.\n\n"
    "Body fields:\n"
    "- `query` (required): natural-language string\n"
    "- `max_results`: default 10; raise up to **100** for broader coverage "
    "or to count recurring events\n"
    "- `traversal_level`: default 1\n"
    "- `start_time` / `end_time`: ISO 8601 UTC, e.g. `2026-06-04T15:00:00Z` "
    "— filters results to this window\n"
    "- `include_citations`: `true` to get source citations\n\n"
    "Query budget: 3 OCG calls maximum. Stop after the first if it returns "
    "plausible results. Never invent endpoints.\n\n"
    "---\n\n"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a single OCG-aware Claude Code agent on a prompt."
    )
    parser.add_argument(
        "prompt_file",
        help='Path to prompt file. Use "-" to read from stdin.',
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Subprocess timeout in seconds (default: 300)",
    )
    args = parser.parse_args()

    if args.prompt_file == "-":
        prompt = sys.stdin.read()
    else:
        path = Path(args.prompt_file)
        if not path.is_absolute():
            # Resolve relative to the user's cwd (where they invoked the script),
            # not to sdk/python, so `python -m ... prompts/foo.md` works.
            path = Path.cwd() / path
        if not path.exists():
            print(f"ERROR: prompt file not found: {path}", file=sys.stderr)
            sys.exit(1)
        prompt = path.read_text()

    prompt = OCG_PRIMER + prompt
    try:
        resolved = _expand_env_vars(prompt)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(
        f"Running claude (timeout={args.timeout}s, cwd={REPO_ROOT})...",
        file=sys.stderr,
    )
    t0 = time.monotonic()
    out = _run_claude(resolved, args.timeout, ALLOWED_TOOLS)
    elapsed = round(time.monotonic() - t0, 1)

    if "error" in out:
        print(f"ERROR after {elapsed}s: {out['error']}", file=sys.stderr)
        if "stderr" in out:
            print(out["stderr"], file=sys.stderr)
        sys.exit(1)

    result = out.get("result", "")
    usage = out.get("usage", {})
    tokens_in = (
        (usage.get("input_tokens") or 0)
        + (usage.get("cache_creation_input_tokens") or 0)
        + (usage.get("cache_read_input_tokens") or 0)
    )
    tokens_out = usage.get("output_tokens") or 0

    print(result)
    print(
        f"\n--- {elapsed}s | {out.get('num_turns', 0)} turns | "
        f"{tokens_in:,} in / {tokens_out:,} out tokens ---",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
