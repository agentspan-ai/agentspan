"""Report generation and CSV helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import MODELS


def find_latest_csv(output_dir: Path) -> Path | None:
    csvs = sorted(output_dir.glob("run_*/results.csv"))
    if csvs:
        return csvs[-1]
    csvs = sorted(output_dir.glob("validation_results_*.csv"))
    return csvs[-1] if csvs else None


def _format_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def _model_display(row: dict, prefix: str) -> str:
    score = row.get(f"{prefix}_judge_score", "")
    status = "✓" if row.get(f"{prefix}_status") == "COMPLETED" else row.get(f"{prefix}_status", "?")
    return f"{status} ({score}/5)" if score else status


def generate_report(
    rows: list[dict],
    report_path: Path,
    validation_duration_s: float | None = None,
    judge_duration_s: float | None = None,
) -> None:
    total = len(rows)
    passed = sum(1 for r in rows if r["match"] == "PASS")
    failed = sum(1 for r in rows if r["match"] == "FAIL")
    partial = sum(1 for r in rows if r["match"] == "PARTIAL")
    skipped = sum(1 for r in rows if r["match"] == "SKIP")

    high = sum(1 for r in rows if r.get("confidence") == "HIGH")
    medium = sum(1 for r in rows if r.get("confidence") == "MEDIUM")
    low = sum(1 for r in rows if r.get("confidence") == "LOW")

    with open(report_path, "w") as f:
        f.write("# Validation Report\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        if validation_duration_s is not None or judge_duration_s is not None:
            f.write("## Timing\n\n")
            if validation_duration_s is not None:
                f.write(f"- **Validation**: {_format_duration(validation_duration_s)}\n")
            if judge_duration_s is not None:
                f.write(f"- **Judge**: {_format_duration(judge_duration_s)}\n")
            total = (validation_duration_s or 0) + (judge_duration_s or 0)
            if validation_duration_s and judge_duration_s:
                f.write(f"- **Total**: {_format_duration(total)}\n")
            f.write("\n")

        f.write("## Summary\n\n")
        f.write("| Metric | Count |\n")
        f.write("|--------|-------|\n")
        f.write(f"| Total | {total} |\n")
        f.write(f"| Pass | {passed} |\n")
        f.write(f"| Fail | {failed} |\n")
        f.write(f"| Partial | {partial} |\n")
        f.write(f"| Skip | {skipped} |\n")
        f.write("\n")
        f.write("| Confidence | Count |\n")
        f.write("|------------|-------|\n")
        f.write(f"| HIGH | {high} |\n")
        f.write(f"| MEDIUM | {medium} |\n")
        f.write(f"| LOW | {low} |\n")
        f.write("\n")

        # Results table
        providers = list(MODELS.keys())
        f.write("## Results\n\n")
        header = (
            "| Example | "
            + " | ".join(p.title() for p in providers)
            + " | Duration | Match | Confidence |\n"
        )
        sep = (
            "|---------|"
            + "|".join("-" * 10 for _ in providers)
            + "|----------|-------|------------|\n"
        )
        f.write(header)
        f.write(sep)
        for r in rows:
            displays = [_model_display(r, p) for p in providers]
            durations = [float(r.get(f"{p}_duration_s", 0) or 0) for p in providers]
            dur_display = _format_duration(max(durations))
            cols = " | ".join(displays)
            f.write(
                f"| {r['example']} | {cols} | {dur_display} | {r['match']} | {r.get('confidence', '')} |\n"
            )
        f.write("\n")

        # Per-example details
        f.write("## Details\n\n")
        for r in rows:
            f.write(f"### {r['example']}\n\n")
            f.write(f"- **Match**: {r['match']} | **Confidence**: {r.get('confidence', 'N/A')}\n")
            for prefix in providers:
                label = prefix.title()
                f.write(
                    f"- **{label}**: status={r.get(f'{prefix}_status')} duration={r.get(f'{prefix}_duration_s')}s tools={r.get(f'{prefix}_tool_calls')} tokens={r.get(f'{prefix}_tokens_total')}\n"
                )

            for prefix in providers:
                if r.get(f"{prefix}_judge_score"):
                    label = prefix.title()
                    f.write(
                        f"- **{label} judge**: {r[f'{prefix}_judge_score']}/5 — {r.get(f'{prefix}_judge_reason', '')}\n"
                    )

            has_errors = any(r.get(f"{p}_has_error") == "True" for p in providers)
            if has_errors:
                f.write("\n**Errors**:\n")
                for prefix in providers:
                    if r.get(f"{prefix}_error_summary"):
                        f.write(f"- {prefix.title()}: {r[f'{prefix}_error_summary']}\n")

            if r.get("notes"):
                f.write(f"- **Notes**: {r['notes']}\n")

            f.write("\n")
