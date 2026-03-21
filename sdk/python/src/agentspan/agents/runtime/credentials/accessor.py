# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""get_credential() accessor for isolated=False tools.

The worker framework calls ``set_credential_context(credentials_dict)`` before
executing a non-isolated tool, making credentials available via
``get_credential(name)`` inside that tool's call frame.

Uses ``contextvars.ContextVar`` so each thread (Conductor worker thread) has its
own independent credential context. No cross-task credential leakage.

Usage in non-isolated tools::

    @tool(isolated=False, credentials=["OPENAI_API_KEY"])
    def call_openai(prompt: str) -> str:
        key = get_credential("OPENAI_API_KEY")
        ...

The framework sets the context before calling the function and clears it after.
"""

from __future__ import annotations

import contextvars
from typing import Dict, Optional

from agentspan.agents.runtime.credentials.types import CredentialNotFoundError

# Thread-local (via contextvars) credential map set by the worker framework.
# Value is None when no context has been established.
_credential_context: contextvars.ContextVar[Optional[Dict[str, str]]] = contextvars.ContextVar(
    "_credential_context", default=None
)


def set_credential_context(credentials: Dict[str, str]) -> None:
    """Set the credential context for the current execution context (thread/task).

    Called by the worker framework (``_dispatch.py``) before executing a
    ``isolated=False`` tool.

    Args:
        credentials: Dict mapping credential name → plaintext value.
    """
    _credential_context.set(credentials)


def clear_credential_context() -> None:
    """Clear the credential context for the current execution context.

    Called by the worker framework after the tool execution completes.
    """
    _credential_context.set(None)


def get_credential(name: str) -> str:
    """Read a credential value from the current execution context.

    Only usable inside ``@tool(isolated=False, credentials=[...])`` functions.
    The worker framework populates the context before your tool runs.

    Args:
        name: The logical credential name (e.g. ``"OPENAI_API_KEY"``).

    Returns:
        The plaintext credential value.

    Raises:
        CredentialNotFoundError: If the credential is not in the current context,
            or if called outside of a credential-aware tool execution.

    Example::

        @tool(isolated=False, credentials=["OPENAI_API_KEY"])
        def call_openai(prompt: str) -> str:
            key = get_credential("OPENAI_API_KEY")
            client = openai.OpenAI(api_key=key)
            ...
    """
    ctx = _credential_context.get()
    if ctx is None:
        raise CredentialNotFoundError([name])
    if name not in ctx:
        raise CredentialNotFoundError([name])
    return ctx[name]
