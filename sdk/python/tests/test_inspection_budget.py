"""Cross-process inspection-budget tests for ``_issue_fixer_tools``.

The original gate at ``_record_inspection`` used a Python module-level dict
that lived in process memory. Agentspan's worker pool is multi-process (spawn
mode), so the counter never accumulated across worker processes and the
10-call budget never fired — observed empirically in workflow
``fb257ccd-e3e2-468e-9a4b-50b0b3284b15`` where 408 inspections went through
with 0 blocked. The gate is now backed by ``.contextbook/.progress/<eid>.json``
under ``fcntl.flock``. These tests verify the file-backed counter is enforced
across multiple processes hammering the same execution context.

No LLM. No server. Pure ``multiprocessing.Pool``.
"""

from __future__ import annotations

import os
import sys
from multiprocessing import get_context
from pathlib import Path
from typing import Optional

EXAMPLES_DIR = (Path(__file__).resolve().parent.parent / "examples").resolve()
if str(EXAMPLES_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLES_DIR))

# Pull the real agentspan ToolContext so the tests exercise the production
# code path — including agent_name='' which the SDK always emits because
# _current_context is never populated (see _dispatch.py:258).
SDK_SRC = (Path(__file__).resolve().parent.parent / "src").resolve()
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))
from agentspan.agents.tool import ToolContext  # noqa: E402


def _hammer_inspection(args: tuple[str, int]) -> list[Optional[str]]:
    """Worker entrypoint: call ``_record_inspection`` ``n`` times in this process.

    Workers do NOT call ``set_working_dir`` themselves — they receive the
    working dir via the ``AGENTSPAN_FIXER_WORKING_DIR`` env var that the
    parent process set before spawning. Each spawn-mode worker imports the
    module fresh, the import reads the env var, and ``_WORKING_DIR`` is
    populated. This mirrors production: only the SDK process calls
    ``set_working_dir``; workers inherit through env.
    """
    execution_id, n = args
    import _issue_fixer_tools as ift  # noqa: WPS433 — intentional per-worker import

    # Production reality: agent_name is "" because agentspan's dispatch
    # _current_context dict is never populated. The gate must still fire.
    ctx = ToolContext(execution_id=execution_id, agent_name="")
    return [ift._record_inspection("grep_search", ctx) for _ in range(n)]


def _hammer_inspection_after_edit(args: tuple[str, int]) -> list[Optional[str]]:
    """Same as above but flag a successful edit FIRST, then call N times.

    Once ``_mark_successful_edit`` is called, the gate must stay disabled
    forever for that execution_id — regardless of how many further inspections
    happen in any worker process.
    """
    execution_id, n = args
    import _issue_fixer_tools as ift  # noqa: WPS433

    ctx = ToolContext(execution_id=execution_id, agent_name="")
    ift._mark_successful_edit(ctx)
    return [ift._record_inspection("grep_search", ctx) for _ in range(n)]


def _read_budget() -> int:
    import _issue_fixer_tools as ift

    return ift._CODER_INSPECTION_BUDGET_BEFORE_EDIT


def _setup_env(tmp_path: Path) -> None:
    """Mirror production: parent sets AGENTSPAN_FIXER_WORKING_DIR so spawned
    workers inherit it. Each test gets its own tmp_path → its own progress
    file directory → no test cross-pollution.
    """
    os.environ["AGENTSPAN_FIXER_WORKING_DIR"] = str(tmp_path)


def test_budget_fires_with_empty_agent_name(tmp_path: Path) -> None:
    """The original ``_record_inspection`` short-circuited on
    ``_is_agent(context, "issue_fixer_coder")``. agentspan's dispatch never
    populates ``context.agent_name`` (it's always ``""``), so that check
    always returned False and the gate was effectively dead. The fixed gate
    must fire even when ``agent_name`` is empty.

    Setup: spawn-mode workers collectively call ``_record_inspection``
    ``budget + 22`` times with the SAME execution_id and ``agent_name=""``.
    Expect exactly ``budget`` ``None`` returns and 22 blocked. Sizing the
    call count off the live constant means the test continues to validate
    the gate regardless of how the budget is tuned.
    """
    _setup_env(tmp_path)
    eid = "wf-test-empty-agent-name"
    budget = _read_budget()
    extra_blocks = 22
    total = budget + extra_blocks
    n_workers = 4
    # Divide work roughly evenly; first worker gets the remainder.
    base = total // n_workers
    remainder = total - base * n_workers
    per_worker = [base + (1 if i < remainder else 0) for i in range(n_workers)]
    assert sum(per_worker) == total

    ctx_method = get_context("spawn")
    with ctx_method.Pool(processes=n_workers) as pool:
        results = pool.map(
            _hammer_inspection,
            [(eid, n) for n in per_worker],
        )

    flat = [r for sub in results for r in sub]
    assert len(flat) == total, f"expected {total} results, got {len(flat)}"

    ok = [r for r in flat if r is None]
    blocked = [r for r in flat if r is not None]

    assert len(ok) == budget, (
        f"expected exactly {budget} ok returns across all workers (gate must "
        f"fire even when agent_name is empty), got {len(ok)}. blocked count: {len(blocked)}"
    )
    assert len(blocked) == extra_blocks
    assert all("Blocked: coder inspection budget exceeded" in b for b in blocked)


def test_gate_disabled_after_first_successful_edit(tmp_path: Path) -> None:
    """A worker calls ``_mark_successful_edit``. All later inspections — even
    in OTHER worker processes — must pass through.
    """
    _setup_env(tmp_path)
    eid = "wf-test-edit-seen"

    ctx_method = get_context("spawn")
    with ctx_method.Pool(processes=3) as pool:
        # Each worker flips the edit-seen flag (idempotent), then inspects 30 times.
        results = pool.map(
            _hammer_inspection_after_edit,
            [(eid, 30)] * 3,
        )

    flat = [r for sub in results for r in sub]
    assert len(flat) == 90
    assert all(r is None for r in flat), (
        "once successful_edit_seen is set, the gate must be permanently disabled "
        "for that execution_id across all workers; saw blocked returns: "
        + repr([r for r in flat if r is not None][:3])
    )


def test_separate_executions_have_separate_budgets(tmp_path: Path) -> None:
    """Two distinct execution_ids share the host but their counters must be
    independent — each gets its own full budget. This guards against the
    progress file collapsing into one global counter (the failure mode that
    would otherwise interfere with successive issue-fixer runs on the same
    host).
    """
    _setup_env(tmp_path)

    ctx_method = get_context("spawn")
    with ctx_method.Pool(processes=2) as pool:
        # Two distinct execution_ids, each gets 8 inspection calls. Total 16
        # calls < 2 × budget(10), so NONE should be blocked.
        results = pool.map(
            _hammer_inspection,
            [("wf-exec-A", 8), ("wf-exec-B", 8)],
        )

    flat = [r for sub in results for r in sub]
    assert len(flat) == 16
    assert all(r is None for r in flat), (
        "two distinct execution_ids must have independent budgets; saw blocked: "
        + repr([r for r in flat if r is not None][:3])
    )
