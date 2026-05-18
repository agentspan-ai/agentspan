# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credential management subpackage for the Agentspan Python SDK."""

from agentspan.agents.runtime.credentials.accessor import get_credential
from agentspan.agents.runtime.credentials.fetcher import WorkerCredentialFetcher
from agentspan.agents.runtime.credentials.isolator import SubprocessIsolator
from agentspan.agents.runtime.credentials.types import (
    CredentialAuthError,
    CredentialFile,
    CredentialNotFoundError,
    CredentialRateLimitError,
    CredentialServiceError,
)

__all__ = [
    "CredentialFile",
    "CredentialNotFoundError",
    "CredentialAuthError",
    "CredentialRateLimitError",
    "CredentialServiceError",
    "WorkerCredentialFetcher",
    "SubprocessIsolator",
    "get_credential",
]
