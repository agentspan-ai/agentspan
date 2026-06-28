# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""get_secret() accessor — read resolved credentials without going through env vars.

The worker framework calls ``set_credential_context(secrets_dict)`` before
executing a tool, making credentials available via ``get_secret(name)`` inside
that tool's call frame.

Uses ``contextvars.ContextVar`` so each thread (Conductor worker thread) /
async task has its own independent credential context. No cross-task
credential leakage, and no contention with the process-wide env-injection lock.

Prefer this accessor over ``os.environ`` when the tool's framework SDK accepts
an explicit ``api_key`` parameter — it avoids touching the shared
``os.environ`` entirely (see ``docs/design/secret-injection-contract.md``)::

    @tool(credentials=["OPENAI_API_KEY"])
    def call_openai(prompt: str) -> str:
        key = get_secret("OPENAI_API_KEY")
        client = openai.OpenAI(api_key=key)
        ...

The framework sets the context before calling the function and clears it after.
"""

from __future__ import annotations

import contextvars
from typing import Dict, Optional

from conductor.ai.agents.runtime.credentials.types import CredentialNotFoundError

# Thread-local (via contextvars) credential map set by the worker framework.
# Value is None when no context has been established.
_credential_context: contextvars.ContextVar[Optional[Dict[str, str]]] = contextvars.ContextVar(
    "_credential_context", default=None
)


def set_credential_context(credentials: Dict[str, str]) -> None:
    """Set the credential context for the current execution context (thread/task).

    Called by the worker framework (``_dispatch.py``) before executing a tool
    that declares ``credentials=[...]``.

    Args:
        credentials: Dict mapping credential name → plaintext value.
    """
    _credential_context.set(credentials)


def clear_credential_context() -> None:
    """Clear the credential context for the current execution context.

    Called by the worker framework after the tool execution completes.
    """
    _credential_context.set(None)


def get_secret(name: str) -> str:
    """Read a credential value from the current execution context.

    Only usable inside ``@tool(credentials=[...])`` functions. The worker framework
    populates the context before your tool runs.

    Args:
        name: The logical credential name (e.g. ``"OPENAI_API_KEY"``).

    Returns:
        The plaintext credential value.

    Raises:
        CredentialNotFoundError: If the credential is not in the current context,
            or if called outside of a credential-aware tool execution.

    Example::

        @tool(credentials=["OPENAI_API_KEY"])
        def call_openai(prompt: str) -> str:
            key = get_secret("OPENAI_API_KEY")
            client = openai.OpenAI(api_key=key)
            ...
    """
    ctx = _credential_context.get()
    if ctx is None:
        raise CredentialNotFoundError([name])
    if name not in ctx:
        raise CredentialNotFoundError([name])
    return ctx[name]
