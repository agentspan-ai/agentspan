# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Hooks — extension points for permission, validation, and audit."""

from .runner import (
    Hook,
    HookOutcome,
    HookRunner,
    PostToolHookFn,
    PreToolHookFn,
    SessionStartHookFn,
    StopHookFn,
)

__all__ = [
    "Hook",
    "HookOutcome",
    "HookRunner",
    "PostToolHookFn",
    "PreToolHookFn",
    "SessionStartHookFn",
    "StopHookFn",
]
