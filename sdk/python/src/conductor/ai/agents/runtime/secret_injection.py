"""Secret injection for framework passthrough — concurrency-safe.

See ``docs/design/secret-injection-contract.md`` for the full contract this
module implements. The TL;DR:

* **Tier 1 (preferred):** the user's agent factory accepts a ``secrets`` kwarg
  and passes resolved values directly to model constructors
  (``ChatOpenAI(api_key=...)`` etc.). No shared global state, fully concurrent.

* **Tier 2 (fallback):** for frameworks that only read ``os.environ`` (Google
  ADK ``genai.configure``, Claude Agent SDK CLI mode), this module's
  :func:`inject_via_env` wraps the full framework invocation under a single
  process-wide lock. Correct but strictly serial within a worker process —
  scale by adding worker processes.

The previous implementation acquired its lock only around the env-mutation
step and released it before invoking the framework. That left the
mutate-invoke-restore sequence interleaved across threads, so concurrent
framework workers clobbered each other's keys. This module replaces that.
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from typing import Callable, Dict, Iterator, Mapping, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ── Tier 2: env injection with lock around full invoke ────────────────────────

# A SINGLE process-wide lock guards os.environ writes. All tier-2 framework
# workers in this process contend for this one lock. Tier-1 (explicit-key)
# paths must NOT acquire it — that would defeat the concurrency win of tier 1.
_env_injection_lock = threading.RLock()


@contextmanager
def _env_overrides(values: Mapping[str, str]) -> Iterator[None]:
    """Apply env overrides and restore prior values on exit.

    Restores the original value if there was one; pops the key if there wasn't.
    Safe under exception in the framework call — the finally branch always runs.
    """
    if not values:
        yield
        return

    previous: Dict[str, Optional[str]] = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            os.environ[k] = v
        yield
    finally:
        for k, prev in previous.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev


def inject_via_env(secrets: Mapping[str, str], invoke: Callable[[], T]) -> T:
    """Run ``invoke()`` with ``secrets`` injected into ``os.environ``.

    Acquires a process-wide lock spanning the whole invocation: mutation,
    framework call, and restoration are atomic with respect to any other
    tier-2 call in this process. Strictly serial.

    Used by framework integrations whose underlying SDK only reads env vars.

    Args:
        secrets: name → plaintext mapping; written into ``os.environ`` for the
            duration of the call. Non-string values are silently skipped.
        invoke: zero-argument callable that runs the framework. Return value is
            propagated to the caller.

    Returns:
        Whatever ``invoke()`` returns.

    Raises:
        Whatever ``invoke()`` raises — exceptions do not corrupt env state
        because the restore happens in a ``finally`` block inside the lock.
    """
    clean: Dict[str, str] = {k: v for k, v in secrets.items() if isinstance(v, str)}
    if not clean:
        return invoke()

    with _env_injection_lock, _env_overrides(clean):
        return invoke()


# ── Tier 1: explicit-key passthrough — no env mutation, no lock ───────────────


class ExplicitSecrets(Mapping[str, str]):
    """Read-only view of resolved secrets passed to a tier-1 agent factory.

    Mapping interface so users can write ``secrets["OPENAI_API_KEY"]`` directly
    or ``**secrets`` to spread into a constructor.

    Intentionally minimal — this exists so framework integrations have a clear
    type to pass into user factory functions without exposing the underlying
    dict (which the integration may continue to mutate as more secrets are
    fetched lazily).
    """

    def __init__(self, values: Mapping[str, str]):
        # Defensive copy — caller can't mutate after construction
        self._values = dict(values)

    def __getitem__(self, key: str) -> str:
        return self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        # Don't leak values in repr — show only names
        return f"ExplicitSecrets({sorted(self._values.keys())!r})"


def factory_accepts_secrets(factory: Callable) -> bool:
    """Return True if ``factory`` accepts a ``secrets`` keyword argument.

    Used by framework integrations to choose between tier 1 (call factory with
    ``secrets=...``) and tier 2 (legacy: invoke pre-built agent under env-lock).
    """
    import inspect

    try:
        sig = inspect.signature(factory)
    except (TypeError, ValueError):
        return False
    params = sig.parameters
    if "secrets" in params:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
