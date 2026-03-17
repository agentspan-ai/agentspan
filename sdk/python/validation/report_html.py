"""HTML report generation using Jinja2 templates."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, PackageLoader


def _cross_score_distribution(rows: list[dict], run_names: list[str]) -> tuple[dict, dict]:
    """Compute score distribution per run. Returns (dist, max_per_run)."""
    dist: dict[str, dict[int, int]] = {}
    for rn in run_names:
        counts: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for row in rows:
            s = row.get(f"{rn}_score")
            if s:
                try:
                    counts[int(s)] = counts.get(int(s), 0) + 1
                except (ValueError, TypeError):
                    pass
        dist[rn] = counts
    maxes = {rn: max(dist[rn].values()) or 1 for rn in run_names}
    return dist, maxes


def generate_cross_html_report(
    rows: list[dict],
    report_path: Path,
    run_names: list[str],
    baseline: str | None = None,
    raw_outputs: dict[str, dict[str, str]] | None = None,
    meta: dict | None = None,
    run_meta: dict[str, dict] | None = None,
) -> None:
    """Generate cross-run HTML report with side-by-side comparison."""
    env = Environment(
        loader=PackageLoader("validation", "templates"),
        autoescape=False,
    )
    template = env.get_template("cross_report.html.j2")

    total_examples = len(rows)
    score_dist, score_dist_max = _cross_score_distribution(rows, run_names)

    # Compute averages
    avg_scores: dict[str, float] = {}
    completed_counts: dict[str, int] = {}
    for rn in run_names:
        scores = [int(row[f"{rn}_score"]) for row in rows if row.get(f"{rn}_score")]
        avg_scores[rn] = sum(scores) / len(scores) if scores else 0
        completed_counts[rn] = len(scores)

    avg_baseline_scores: dict[str, float] = {}
    if baseline:
        for rn in run_names:
            if rn == baseline:
                continue
            scores = [
                int(row[f"{rn}_vs_{baseline}"]) for row in rows if row.get(f"{rn}_vs_{baseline}")
            ]
            avg_baseline_scores[rn] = sum(scores) / len(scores) if scores else 0

    html = template.render(
        rows=rows,
        runs=run_names,
        baseline=baseline,
        raw_outputs=raw_outputs or {},
        meta=meta or {},
        run_meta=run_meta or {},
        total_examples=total_examples,
        avg_scores=avg_scores,
        completed_counts=completed_counts,
        avg_baseline_scores=avg_baseline_scores,
        score_dist=score_dist,
        score_dist_max=score_dist_max,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    report_path.write_text(html)


def _score_distribution(rows: list[dict], providers: list[str]) -> tuple[dict, dict]:
    """Compute score distribution per provider. Returns (dist, max_per_provider)."""
    dist: dict[str, dict[int, int]] = {}
    for p in providers:
        counts: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for row in rows:
            s = row.get(f"{p}_judge_score")
            if s:
                try:
                    counts[int(s)] = counts.get(int(s), 0) + 1
                except (ValueError, TypeError):
                    pass
        dist[p] = counts
    maxes = {p: max(dist[p].values()) or 1 for p in providers}
    return dist, maxes


def generate_html_report(
    rows: list[dict],
    report_path: Path,
    providers: list[str],
    baseline_model: str | None = None,
    raw_outputs: dict[str, dict[str, str]] | None = None,
    meta: dict | None = None,
    history: dict[str, list[str]] | None = None,
) -> None:
    """Generate self-contained HTML report.

    Args:
        history: {example_name: ["PASS", "FAIL", ...]} from last_run.json
    """
    env = Environment(
        loader=PackageLoader("validation", "templates"),
        autoescape=False,
    )
    template = env.get_template("report.html.j2")

    total = len(rows)
    passed = sum(1 for r in rows if r.get("match") == "PASS")
    failed = sum(1 for r in rows if r.get("match") == "FAIL")
    partial = sum(1 for r in rows if r.get("match") == "PARTIAL")
    skipped = sum(1 for r in rows if r.get("match") == "SKIP")

    score_dist, score_dist_max = _score_distribution(rows, providers)

    html = template.render(
        rows=rows,
        providers=providers,
        baseline_model=baseline_model,
        raw_outputs=raw_outputs or {},
        meta=meta or {},
        history=history or {},
        total=total,
        passed=passed,
        failed=failed,
        partial=partial,
        skipped=skipped,
        score_dist=score_dist,
        score_dist_max=score_dist_max,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    report_path.write_text(html)
