"""Single-model example execution."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from .models import Example, SingleResult
from .runner import run_example


def run_examples(
    examples: list[Example],
    model_name: str,
    model_id: str,
    timeout: int,
    retries: int,
    max_workers: int,
    native: bool,
    server_url: str | None,
    secondary_model: str | None,
    abort_event: threading.Event,
    on_complete: Callable[[SingleResult], None] | None = None,
) -> list[SingleResult]:
    """Run examples against a single model. max_workers=1 for sequential."""
    all_results: list[SingleResult] = []
    results_lock = threading.Lock()

    def _run_one(example: Example) -> SingleResult | None:
        if abort_event.is_set():
            return None
        result = run_example(
            example,
            model_name,
            model_id,
            timeout,
            retries,
            server_url=server_url,
            native=native,
            secondary_model=secondary_model,
        )
        if abort_event.is_set():
            return None
        sr = SingleResult(example=example, result=result)
        with results_lock:
            all_results.append(sr)
        if on_complete:
            on_complete(sr)
        return sr

    if max_workers <= 1:
        for example in examples:
            sr = _run_one(example)
            if sr is None:
                break
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_run_one, ex): ex for ex in examples}
            for future in as_completed(futures):
                if abort_event.is_set():
                    break
                future.result()  # propagate exceptions

    # Sort back to original order
    order = {ex.name: i for i, ex in enumerate(examples)}
    all_results.sort(key=lambda sr: order.get(sr.example.name, 0))
    return all_results
