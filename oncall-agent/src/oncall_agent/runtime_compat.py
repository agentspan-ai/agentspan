"""Runtime compatibility shims for local execution."""
from __future__ import annotations

import platform
from typing import Any


class TriageIncomplete(Exception):
    """The agent finished without the mandated *Cause*: answer (ran out of turns,
    narrated, or returned an empty result). Never post or remember it as a triage."""


def summary_text(result: Any) -> str:
    """Extract the agent's final text from an ``AgentRuntime.run`` result.

    The server returns the agent output as a dict
    ``{"result": <text>, "finishReason": ..., "context": ..., "rejectionReason": ...}``;
    older SDK builds exposed the text directly on ``result.output``. Accept both.

    The model narrates before the summary despite instructions ("I have all the
    data I need. Let me..."), so enforce the contract deterministically: if the
    text contains the mandated ``*Cause*:`` line, drop everything before it.
    """
    output = getattr(result, "output", None)
    text: str | None = None
    if isinstance(output, dict):
        candidate = output.get("result")
        if isinstance(candidate, str) and candidate.strip():
            text = candidate
    if text is None and isinstance(output, str) and output.strip():
        text = output
    if text is None:
        raise TriageIncomplete(f"agent returned no text: {str(output if output is not None else result)[:200]}")
    marker = text.find("*Cause*:")
    if marker < 0:
        raise TriageIncomplete(f"agent answer has no *Cause*: line: {text[:200]}")
    return text[marker:]


def use_thread_workers_if_needed() -> None:
    """Run conductor tool-workers as THREADS instead of forked processes on macOS.

    conductor-python forks a process per worker. On macOS a forked child segfaults
    the instant it does DNS/HTTPS (``getaddrinfo`` / Network.framework are not
    fork-safe), and the 'spawn' alternative can't pickle the worker's ``_thread.lock``.
    The conductor agent SDK already ships a thread-based worker shim for exactly this
    reason but only enables it on Windows — the same shim fixes macOS. Enable it here.

    No-op on Linux, where fork is safe — which is how this runs in production
    (the agent runs inside ah5r-prod, a Linux cluster).
    """
    if platform.system() not in ("Darwin", "Windows"):
        return
    try:
        from conductor.ai.agents.runtime.worker_manager import (
            _patch_conductor_use_threads_on_windows as _patch,
        )
    except Exception:
        return
    _patch()
