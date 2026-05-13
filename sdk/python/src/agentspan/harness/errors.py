# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Typed errors for the harness.

Most error conditions in the harness become tool-result errors visible to
the model — never raw Python exceptions. These exception types exist for
internal control-flow only (engine-level abort signals, configuration
errors before the loop starts).
"""


class HarnessError(Exception):
    """Base class for all harness-internal exceptions."""


class HarnessConfigError(HarnessError):
    """Misconfiguration discovered at HarnessRuntime construction time —
    bad tool definition, conflicting permission rules, missing provider,
    invalid sandbox config. Should fail loudly before any turn runs.
    """


class ToolValidationError(HarnessError):
    """Schema or semantic validation failed for tool input. The orchestrator
    catches this and returns a synthetic tool_result with ``is_error=True``;
    the model can recover. Tools should NOT raise this directly — return
    a ``ToolResult.error(...)`` instead so the validator stays auditable.
    """

    def __init__(self, message: str, *, tool_name: str, suggestions: str = ""):
        super().__init__(message)
        self.tool_name = tool_name
        self.suggestions = suggestions


class PermissionDeniedError(HarnessError):
    """Permission engine returned deny and the orchestrator is materializing
    the resulting tool-result error. Carries the permission ``reason`` so
    audit logs can explain why.
    """

    def __init__(self, message: str, *, tool_name: str, reason: str):
        super().__init__(message)
        self.tool_name = tool_name
        self.reason = reason


class SandboxViolationError(HarnessError):
    """Sandbox check rejected an attempted operation. Distinct from
    permission denial because sandbox violations represent enforcement
    boundaries the user cannot override at runtime — they require config
    changes.
    """

    def __init__(self, message: str, *, kind: str):
        super().__init__(message)
        self.kind = kind


class ProviderError(HarnessError):
    """Underlying model provider returned an error. The engine attempts
    recovery (compaction, retry, fallback model) before surfacing this.
    """

    def __init__(self, message: str, *, provider: str, status: int = 0):
        super().__init__(message)
        self.provider = provider
        self.status = status


class HookBlockedError(HarnessError):
    """A hook returned a blocking decision (e.g. ``pre_tool_use`` denied
    the call). Carries the hook name so the orchestrator can surface a
    clear tool-result error.
    """

    def __init__(self, message: str, *, hook_name: str):
        super().__init__(message)
        self.hook_name = hook_name
