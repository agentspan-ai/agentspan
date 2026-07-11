# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credential management subpackage for the Agentspan Python SDK."""

from conductor.ai.agents.runtime.credentials._task_compat import ensure_runtime_metadata_field
from conductor.ai.agents.runtime.credentials.accessor import get_secret
from conductor.ai.agents.runtime.credentials.types import (
    CredentialAuthError,
    CredentialNotFoundError,
    CredentialRateLimitError,
    CredentialServiceError,
)

__all__ = [
    "CredentialNotFoundError",
    "CredentialAuthError",
    "CredentialRateLimitError",
    "CredentialServiceError",
    "ensure_runtime_metadata_field",
    "get_secret",
]
