# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Standalone guardrails — use as plain callables or as Conductor workers.

The ``@guardrail`` decorator produces a plain callable.  You can:

1. **Call directly** — validate any text in-process, no server needed.
2. **Run as Conductor workers** — register guardrails as worker tasks
   that any agent (in any language/service) can reference via
   ``Guardrail(name="no_pii")``.

Same functions, two execution modes.

Requirements:
    Part 1 (standalone): none — no server, no LLM, no workers.
    Part 2 (as workers): Conductor server
        - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

import re
import sys

from agentspan.agents import GuardrailResult, guardrail


# ── Define guardrails ────────────────────────────────────────────────

@guardrail
def no_pii(content: str) -> GuardrailResult:
    """Reject content that contains credit card numbers or SSNs."""
    cc_pattern = r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"
    ssn_pattern = r"\b\d{3}-\d{2}-\d{4}\b"

    if re.search(cc_pattern, content) or re.search(ssn_pattern, content):
        return GuardrailResult(
            passed=False,
            message="Contains PII (credit card or SSN).",
        )
    return GuardrailResult(passed=True)


@guardrail
def no_profanity(content: str) -> GuardrailResult:
    """Reject content with profanity."""
    banned = {"damn", "hell", "crap"}
    words = set(content.lower().split())
    found = words & banned
    if found:
        return GuardrailResult(
            passed=False,
            message=f"Profanity detected: {', '.join(sorted(found))}",
        )
    return GuardrailResult(passed=True)


@guardrail
def word_limit(content: str) -> GuardrailResult:
    """Reject content over 100 words."""
    count = len(content.split())
    if count > 100:
        return GuardrailResult(
            passed=False,
            message=f"Too long ({count} words). Limit is 100.",
        )
    return GuardrailResult(passed=True)


# =====================================================================
# Part 1: Standalone — call guardrails directly, no server needed
# =====================================================================

def validate(text: str, guardrails: list) -> bool:
    """Run a list of guardrails against text.  Returns True if all pass."""
    all_passed = True
    for g in guardrails:
        result = g(text)
        if result.passed:
            print(f"  [PASS] {g.__name__}")
        else:
            print(f"  [FAIL] {g.__name__}: {result.message}")
            all_passed = False
    return all_passed


def run_standalone():
    print("=" * 60)
    print("Part 1: Standalone guardrails (no server)")
    print("=" * 60)

    checks = [no_pii, no_profanity, word_limit]

    print("\nTest 1 — clean text:")
    text1 = "Hello, your order #1234 has shipped and will arrive Friday."
    passed = validate(text1, checks)
    print(f"  Result: {'PASSED' if passed else 'BLOCKED'}\n")

    print("Test 2 — contains credit card number:")
    text2 = "Your card on file is 4532-0150-1234-5678. Order confirmed."
    passed = validate(text2, checks)
    print(f"  Result: {'PASSED' if passed else 'BLOCKED'}\n")

    print("Test 3 — contains profanity:")
    text3 = "What the hell happened to my order?"
    passed = validate(text3, checks)
    print(f"  Result: {'PASSED' if passed else 'BLOCKED'}\n")

    print("Test 4 — exceeds word limit:")
    text4 = "word " * 150
    passed = validate(text4, checks)
    print(f"  Result: {'PASSED' if passed else 'BLOCKED'}\n")


# =====================================================================
# Part 2: As Conductor workers — no agent, just guardrail workers
# =====================================================================
#
# Each @guardrail function is registered as a @worker_task that polls
# the Conductor server for tasks.  Any agent — in any language or
# service — can reference these guardrails by name:
#
#     Guardrail(name="no_pii", on_fail=OnFail.RETRY)
#
# The worker contract:
#   Input:  {"content": "<text to validate>"}
#   Output: {"passed": bool, "message": str}

def register_guardrail_worker(guardrail_fn):
    """Wrap a @guardrail function as a Conductor @worker_task.

    The task definition name is the guardrail's function name (or the
    custom name passed to ``@guardrail(name=...)``).
    """
    from conductor.client.worker.worker_task import worker_task

    gd = guardrail_fn._guardrail_def
    task_name = gd.name

    def _worker(content: str = "") -> dict:
        result = guardrail_fn(content)
        return {
            "passed": result.passed,
            "message": result.message,
            "fixed_output": getattr(result, "fixed_output", None),
            "should_continue": not result.passed,  # retry if failed
        }

    _worker.__name__ = f"{task_name}_worker"
    _worker.__annotations__ = {"content": str, "return": dict}

    worker_task(
        task_definition_name=task_name,
        register_task_def=True,
        overwrite_task_def=True,
    )(_worker)

    return task_name


def run_as_workers():
    from conductor.client.automator.task_handler import TaskHandler
    from conductor.client.configuration.configuration import Configuration

    print("=" * 60)
    print("Part 2: Guardrail workers (polling Conductor server)")
    print("=" * 60)

    # Register each guardrail as a Conductor worker task
    for fn in [no_pii, no_profanity, word_limit]:
        name = register_guardrail_worker(fn)
        print(f"  Registered worker: {name}")

    # Start polling — TaskHandler discovers all @worker_task functions
    from agentspan.agents.runtime.config import AgentConfig
    config = Configuration(server_api_url=AgentConfig().server_url)
    handler = TaskHandler(
        workers=[],
        configuration=config,
        scan_for_annotated_workers=True,
    )
    handler.start_processes()

    print("\nWorkers running. Any agent can reference these guardrails by name:")
    print('  Guardrail(name="no_pii", on_fail=OnFail.RETRY)')
    print('  Guardrail(name="no_profanity", on_fail=OnFail.RETRY)')
    print('  Guardrail(name="word_limit", on_fail=OnFail.RETRY)')
    print("\nPress Ctrl+C to stop.\n")

    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        handler.stop_processes()
        print("\nWorkers stopped.")


# =====================================================================

if __name__ == "__main__":
    # Part 1 always runs (no server needed)
    run_standalone()

    # Part 2 only runs with --workers flag (requires Conductor server)
    if "--workers" in sys.argv:
        run_as_workers()
    else:
        print("-" * 60)
        print("To run guardrails as Conductor workers (no agent needed):")
        print("  python examples/35_standalone_guardrails.py --workers")
