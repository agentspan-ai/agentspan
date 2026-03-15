"""Cost estimation and regression detection."""

from __future__ import annotations

from .config import MODEL_PRICING


def _safe_float(val: object) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def compute_costs(rows: list[dict], providers: list[str]) -> dict[str, dict[str, float]]:
    """Compute estimated costs per provider from token columns."""
    costs: dict[str, dict[str, float]] = {}
    for p in providers:
        pricing = MODEL_PRICING.get(p, {"prompt": 0, "completion": 0})
        prompt_tokens = sum(_safe_float(r.get(f"{p}_tokens_prompt")) for r in rows)
        completion_tokens = sum(_safe_float(r.get(f"{p}_tokens_completion")) for r in rows)
        total_tokens = sum(_safe_float(r.get(f"{p}_tokens_total")) for r in rows)
        cost = (prompt_tokens / 1000 * pricing["prompt"]) + (
            completion_tokens / 1000 * pricing["completion"]
        )
        costs[p] = {
            "tokens_prompt": prompt_tokens,
            "tokens_completion": completion_tokens,
            "tokens_total": total_tokens,
            "estimated_cost": round(cost, 4),
        }
    return costs


def detect_regressions(rows: list[dict], prev_last_run: dict, providers: list[str]) -> list[str]:
    """Compare current judge scores to previous, flag drops > 1 point."""
    warnings: list[str] = []
    prev_examples = prev_last_run.get("examples", {})
    for row in rows:
        example = row["example"]
        prev_entry = prev_examples.get(example, {})
        prev_scores = prev_entry.get("judge_scores", {})
        for p in providers:
            curr = row.get(f"{p}_judge_score")
            prev = prev_scores.get(p)
            if curr and prev:
                try:
                    drop = int(prev) - int(curr)
                except (TypeError, ValueError):
                    continue
                if drop > 1:
                    warnings.append(f"  REGRESSION: {example} {p} {prev}->{curr} (drop={drop})")
    return warnings
