# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credential management subpackage for the Agentspan Python SDK."""

from agentspan.agents.runtime.credentials.accessor import get_secret
from agentspan.agents.runtime.credentials.fetcher import WorkerCredentialFetcher
from agentspan.agents.runtime.credentials.types import (
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
    "WorkerCredentialFetcher",
    "get_secret",
]
