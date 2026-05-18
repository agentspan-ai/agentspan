#!/usr/bin/env python3
"""Cross-SDK wire format comparison: Python vs TypeScript AgentConfig JSON.

Compares serialized AgentConfig output between the Python and TypeScript SDKs.
Optionally uses an LLM judge to evaluate whether structural differences are
semantically meaningful.

Usage:
    cd sdk/python
    uv run python -m validation.scripts.compare_wire_format
    uv run python -m validation.scripts.compare_wire_format --judge
    uv run python -m validation.scripts.compare_wire_format --regen
    uv run python -m validation.scripts.compare_wire_format --json output/wire_format.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Paths ─────────────────────────────────────────────────────────────

SDK_ROOT = Path(__file__).resolve().parents[3]  # sdk/
PY_SDK = SDK_ROOT / "python"
TS_SDK = SDK_ROOT / "typescript"
PY_CONFIGS = PY_SDK / "examples" / "_configs"
TS_CONFIGS = TS_SDK / "examples" / "_configs"
PY_DUMP_SCRIPT = PY_SDK / "examples" / "dump_agent_configs.py"
TS_DUMP_SCRIPT = TS_SDK / "examples" / "dump-agent-configs.ts"


# ── Data models ───────────────────────────────────────────────────────


@dataclass
class FieldDiff:
    path: str
    kind: str  # "added", "removed", "changed", "type_changed"
    python_val: Any = None
    ts_val: Any = None


@dataclass
class KnownDiff(FieldDiff):
    explanation: str = ""


@dataclass
class ExampleResult:
    name: str
    status: str = "SKIP"  # MATCH, KNOWN_DIFFS, MISMATCH, SKIP
    real_diffs: List[FieldDiff] = field(default_factory=list)
    known_diffs: List[KnownDiff] = field(default_factory=list)
    judge_verdict: Optional[str] = None
    judge_score: Optional[int] = None
    judge_reason: Optional[str] = None


# ── Deep diff ─────────────────────────────────────────────────────────


def deep_diff(py: Any, ts: Any, path: str, diffs: List[FieldDiff]) -> None:
    """Recursively compare two JSON values and collect diffs."""
    if py is None and ts is None:
        return
    if py is None and ts is not None:
        diffs.append(FieldDiff(path, "added", ts_val=ts))
        return
    if py is not None and ts is None:
        diffs.append(FieldDiff(path, "removed", python_val=py))
        return
    if type(py) != type(ts):
        diffs.append(FieldDiff(path, "type_changed", python_val=py, ts_val=ts))
        return

    if isinstance(py, dict):
        all_keys = sorted(set(list(py.keys()) + list(ts.keys())))
        for key in all_keys:
            child = f"{path}.{key}" if path else key
            if key in py and key not in ts:
                diffs.append(FieldDiff(child, "removed", python_val=py[key]))
            elif key not in py and key in ts:
                diffs.append(FieldDiff(child, "added", ts_val=ts[key]))
            else:
                deep_diff(py[key], ts[key], child, diffs)
    elif isinstance(py, list):
        max_len = max(len(py), len(ts))
        for i in range(max_len):
            child = f"{path}[{i}]"
            if i >= len(py):
                diffs.append(FieldDiff(child, "added", ts_val=ts[i]))
            elif i >= len(ts):
                diffs.append(FieldDiff(child, "removed", python_val=py[i]))
            else:
                deep_diff(py[i], ts[i], child, diffs)
    elif py != ts:
        diffs.append(FieldDiff(path, "changed", python_val=py, ts_val=ts))


# ── Known-diff classifier ────────────────────────────────────────────

# These are known SDK-level differences that are expected and documented.
# As they get fixed, entries should be removed from this list.


def _field_match(path: str, field_name: str) -> bool:
    """Check if path ends with .fieldName or IS fieldName (root level)."""
    return path == field_name or path.endswith(f".{field_name}")


def classify_known_diff(d: FieldDiff) -> Optional[str]:
    """Return explanation string if this is a known SDK difference, else None."""
    p = d.path

    # ── Fixed in ts-sdk-updates branch (removed rules 1-3, 5-8) ──
    # Rules for external/maxTurns/timeoutSeconds always-emit,
    # agentTool naming/description/inputSchema, and pipe() model
    # propagation were removed after fixing the TS SDK to match Python.

    # 1. outputSchema auto-generation
    if _field_match(p, "outputSchema") and d.kind == "removed" and d.python_val is not None:
        return "Python auto-generates outputSchema from return type; TS omits"

    # 2. Guardrail maxRetries default
    if _field_match(p, "maxRetries") and d.kind == "removed" and d.python_val == 3:
        return "Guardrail maxRetries default(3): Python emits, TS omits"

    # 3. outputType.className: Pydantic name vs "Output"
    if _field_match(p, "outputType.className") and d.kind == "changed":
        if d.ts_val == "Output":
            return "outputType className: Python uses class name; TS defaults to 'Output'"

    # 4. Pydantic schema metadata (title fields)
    if "outputType.schema" in p or "inputSchema" in p:
        if p.endswith(".title") and d.kind == "removed":
            return "Pydantic adds title to schema; TS does not"

    return None


# ── Comparison engine ─────────────────────────────────────────────────


def compare_example(name: str, py_path: Path, ts_path: Path) -> ExampleResult:
    """Compare a single example's Python and TypeScript AgentConfig JSON."""
    result = ExampleResult(name=name)

    if not py_path.exists() or not ts_path.exists():
        missing = []
        if not py_path.exists():
            missing.append("Python")
        if not ts_path.exists():
            missing.append("TypeScript")
        result.status = "SKIP"
        result.real_diffs = [
            FieldDiff("", "removed", python_val=f"Missing from: {', '.join(missing)}")
        ]
        return result

    py_data = json.loads(py_path.read_text())
    ts_data = json.loads(ts_path.read_text())

    raw_diffs: List[FieldDiff] = []
    deep_diff(py_data, ts_data, "", raw_diffs)

    for d in raw_diffs:
        explanation = classify_known_diff(d)
        if explanation:
            result.known_diffs.append(
                KnownDiff(
                    path=d.path,
                    kind=d.kind,
                    python_val=d.python_val,
                    ts_val=d.ts_val,
                    explanation=explanation,
                )
            )
        else:
            result.real_diffs.append(d)

    if not raw_diffs:
        result.status = "MATCH"
    elif not result.real_diffs:
        result.status = "KNOWN_DIFFS"
    else:
        result.status = "MISMATCH"

    return result


# ── Regenerate configs ────────────────────────────────────────────────


def regen_configs() -> Tuple[bool, bool]:
    """Re-run both dump scripts. Returns (py_ok, ts_ok)."""
    env = {
        **os.environ,
        "AGENTSPAN_LLM_MODEL": "openai/gpt-4o-mini",
        "AGENTSPAN_SECONDARY_LLM_MODEL": "openai/gpt-4o",
    }

    print("Regenerating Python configs...")
    py_ok = (
        subprocess.run(
            ["uv", "run", "python", str(PY_DUMP_SCRIPT)],
            cwd=str(PY_SDK),
            env=env,
            capture_output=True,
        ).returncode
        == 0
    )

    print("Regenerating TypeScript configs...")
    ts_ok = (
        subprocess.run(
            ["npx", "tsx", str(TS_DUMP_SCRIPT)],
            cwd=str(TS_SDK),
            env=env,
            capture_output=True,
        ).returncode
        == 0
    )

    return py_ok, ts_ok


# ── LLM Judge ─────────────────────────────────────────────────────────

WIRE_FORMAT_JUDGE_SYSTEM = """\
You are a judge evaluating whether two JSON agent configurations (one from a \
Python SDK, one from a TypeScript SDK) are functionally equivalent.

Both JSONs describe the same agent for the same server. Minor cosmetic \
differences (key order, whitespace) don't matter. Focus on:
1. Will the server compile the SAME workflow from both configs?
2. Are there semantic differences that could cause different runtime behavior?
3. Are tool definitions (name, inputSchema, description) compatible?

Respond with ONLY JSON:
{"verdict": "PASS"|"FAIL"|"WARN", "score": 1-5, "reason": "brief explanation"}

SCORING:
1 = Configs produce fundamentally different workflows
2 = Significant semantic differences that affect behavior
3 = Minor differences that likely don't affect behavior
4 = Cosmetically different but semantically equivalent
5 = Identical or trivially equivalent"""


def judge_example(
    example_name: str,
    py_json: dict,
    ts_json: dict,
    diffs: List[FieldDiff],
) -> Tuple[str, int, str]:
    """Use LLM judge to evaluate whether diffs are meaningful."""
    try:
        from openai import OpenAI
    except ImportError:
        return "ERROR", 0, "openai package not installed"

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return "ERROR", 0, "OPENAI_API_KEY not set"

    judge_model = os.environ.get("JUDGE_LLM_MODEL", "openai/gpt-4o-mini")
    # Strip provider prefix for OpenAI client
    model_name = judge_model.split("/", 1)[-1] if "/" in judge_model else judge_model

    diff_summary = "\n".join(
        f"  {d.kind.upper()} {d.path}: py={_trunc(d.python_val)} ts={_trunc(d.ts_val)}"
        for d in diffs[:30]  # Cap to avoid token explosion
    )

    user_prompt = f"""\
EXAMPLE: {example_name}

PYTHON CONFIG:
{json.dumps(py_json, indent=2, default=str)[:3000]}

TYPESCRIPT CONFIG:
{json.dumps(ts_json, indent=2, default=str)[:3000]}

STRUCTURAL DIFFERENCES ({len(diffs)} total):
{diff_summary}"""

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": WIRE_FORMAT_JUDGE_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        max_tokens=300,
        response_format={"type": "json_object"},
    )
    text = resp.choices[0].message.content.strip()

    try:
        parsed = json.loads(text)
        verdict = parsed.get("verdict", "UNKNOWN")
        score = max(1, min(5, int(parsed.get("score", 0))))
        reason = parsed.get("reason", "")
        return verdict, score, reason
    except (json.JSONDecodeError, ValueError):
        return "ERROR", 0, text[:200]


def _trunc(val: Any, max_len: int = 50) -> str:
    s = json.dumps(val, default=str) if val is not None else "null"
    return s[:max_len] + "..." if len(s) > max_len else s


# ── Report ────────────────────────────────────────────────────────────


def print_report(results: List[ExampleResult], use_judge: bool) -> None:
    """Print comparison report to stdout."""
    print()
    print("=" * 90)
    print("  Wire Format Comparison: Python SDK vs TypeScript SDK")
    print("=" * 90)

    # Summary table
    print()
    print(f"  {'Example':<44} {'Status':<12} {'Real':<6} {'Known':<6} {'Judge':<8}")
    print("  " + "-" * 86)

    for r in results:
        judge_col = ""
        if r.judge_verdict:
            judge_col = f"{r.judge_verdict}({r.judge_score})"
        print(
            f"  {r.name:<44} [{r.status:<10}] {len(r.real_diffs):<6} "
            f"{len(r.known_diffs):<6} {judge_col:<8}"
        )

    print("  " + "-" * 86)

    # Counts
    match = sum(1 for r in results if r.status == "MATCH")
    known = sum(1 for r in results if r.status == "KNOWN_DIFFS")
    mismatch = sum(1 for r in results if r.status == "MISMATCH")
    skip = sum(1 for r in results if r.status == "SKIP")

    print(
        f"\n  Total: {len(results)}  |  MATCH: {match}  |  "
        f"KNOWN_DIFFS: {known}  |  MISMATCH: {mismatch}  |  SKIP: {skip}"
    )

    # Known diff categories
    known_categories: Dict[str, int] = {}
    for r in results:
        for kd in r.known_diffs:
            # Generalize the explanation
            key = kd.explanation.split(":")[0] if ":" in kd.explanation else kd.explanation
            known_categories[key] = known_categories.get(key, 0) + 1

    if known_categories:
        print("\n  KNOWN DIFFERENCE CATEGORIES:")
        for cat, count in sorted(known_categories.items(), key=lambda x: -x[1]):
            print(f"    ({count:>3}x) {cat}")

    # Real mismatches detail
    mismatches = [r for r in results if r.status == "MISMATCH"]
    if mismatches:
        print()
        print("=" * 90)
        print("  REAL MISMATCHES (require investigation)")
        print("=" * 90)

        for r in mismatches:
            print(f"\n  --- {r.name} ---")
            for d in r.real_diffs[:20]:
                py_str = f" py={_trunc(d.python_val)}" if d.python_val is not None else ""
                ts_str = f" ts={_trunc(d.ts_val)}" if d.ts_val is not None else ""
                print(f"    {d.kind.upper()} {d.path}{py_str}{ts_str}")
            if len(r.real_diffs) > 20:
                print(f"    ... and {len(r.real_diffs) - 20} more")
            if r.judge_reason:
                print(f"    JUDGE: [{r.judge_verdict}] {r.judge_reason}")

    # Judge summary
    if use_judge:
        judged = [r for r in results if r.judge_verdict]
        if judged:
            print()
            print("=" * 90)
            print("  LLM JUDGE SUMMARY")
            print("=" * 90)
            for r in judged:
                print(
                    f"  {r.name:<44} [{r.judge_verdict}] score={r.judge_score}  "
                    f"{r.judge_reason}"
                )

    print()
    print("=" * 90)


def save_json_report(results: List[ExampleResult], output_path: Path) -> None:
    """Save structured JSON report."""
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": {
            "total": len(results),
            "match": sum(1 for r in results if r.status == "MATCH"),
            "known_diffs": sum(1 for r in results if r.status == "KNOWN_DIFFS"),
            "mismatch": sum(1 for r in results if r.status == "MISMATCH"),
            "skip": sum(1 for r in results if r.status == "SKIP"),
        },
        "results": [
            {
                "name": r.name,
                "status": r.status,
                "real_diffs": [
                    {"path": d.path, "kind": d.kind, "python": d.python_val, "ts": d.ts_val}
                    for d in r.real_diffs
                ],
                "known_diffs": [
                    {"path": kd.path, "kind": kd.kind, "explanation": kd.explanation}
                    for kd in r.known_diffs
                ],
                "judge": (
                    {
                        "verdict": r.judge_verdict,
                        "score": r.judge_score,
                        "reason": r.judge_reason,
                    }
                    if r.judge_verdict
                    else None
                ),
            }
            for r in results
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\n  JSON report saved to {output_path}")


# ── Main ──────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare Python vs TypeScript SDK wire format (AgentConfig JSON)."
    )
    parser.add_argument(
        "--regen",
        action="store_true",
        help="Regenerate _configs by running both dump scripts before comparing.",
    )
    parser.add_argument(
        "--judge",
        action="store_true",
        help="Use LLM judge to evaluate mismatches (requires OPENAI_API_KEY).",
    )
    parser.add_argument(
        "--json",
        type=str,
        default=None,
        help="Save structured JSON report to this path.",
    )
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit with code 1 if any real mismatches found (for CI).",
    )
    args = parser.parse_args()

    # Regenerate if requested
    if args.regen:
        py_ok, ts_ok = regen_configs()
        if not py_ok:
            print("WARNING: Python dump failed", file=sys.stderr)
        if not ts_ok:
            print("WARNING: TypeScript dump failed", file=sys.stderr)

    # Check dirs exist
    if not PY_CONFIGS.exists():
        print(f"ERROR: Python configs not found: {PY_CONFIGS}", file=sys.stderr)
        print("Run: cd sdk/python && uv run python examples/dump_agent_configs.py")
        return 1
    if not TS_CONFIGS.exists():
        print(f"ERROR: TypeScript configs not found: {TS_CONFIGS}", file=sys.stderr)
        print("Run: cd sdk/typescript && npx tsx examples/dump-agent-configs.ts")
        return 1

    # Collect all example names from both dirs
    py_names = {p.stem for p in PY_CONFIGS.glob("*.json")}
    ts_names = {p.stem for p in TS_CONFIGS.glob("*.json")}
    all_names = sorted(py_names | ts_names)

    if not all_names:
        print("ERROR: No config files found.", file=sys.stderr)
        return 1

    print(f"Python configs: {PY_CONFIGS} ({len(py_names)} files)")
    print(f"TypeScript configs: {TS_CONFIGS} ({len(ts_names)} files)")
    print(f"Comparing {len(all_names)} examples...")

    # Compare each example
    results: List[ExampleResult] = []
    for name in all_names:
        r = compare_example(
            name,
            PY_CONFIGS / f"{name}.json",
            TS_CONFIGS / f"{name}.json",
        )
        results.append(r)

    # Judge mismatches if requested
    if args.judge:
        mismatches = [r for r in results if r.status == "MISMATCH"]
        if mismatches:
            print(f"\nJudging {len(mismatches)} mismatches with LLM...")
            for r in mismatches:
                py_data = json.loads((PY_CONFIGS / f"{r.name}.json").read_text())
                ts_data = json.loads((TS_CONFIGS / f"{r.name}.json").read_text())
                verdict, score, reason = judge_example(
                    r.name, py_data, ts_data, r.real_diffs
                )
                r.judge_verdict = verdict
                r.judge_score = score
                r.judge_reason = reason
                print(f"  {r.name}: [{verdict}] score={score} {reason[:60]}")

    # Output
    print_report(results, use_judge=args.judge)

    if args.json:
        save_json_report(results, Path(args.json))

    # Exit code
    has_mismatch = any(r.status == "MISMATCH" for r in results)
    if args.fail_on_mismatch and has_mismatch:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
