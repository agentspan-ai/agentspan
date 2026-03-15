"""HTML report generation using Jinja2 templates."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, PackageLoader


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
