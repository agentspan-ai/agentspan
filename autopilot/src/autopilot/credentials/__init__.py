"""Credential acquisition — OAuth flows, API key browser open, AWS credential reading.

This package provides seamless credential acquisition for all Agentspan
integration types.  Instead of telling users to "run a CLI command", it opens
browsers, runs OAuth callbacks on a local server, and stores tokens
automatically via ``agentspan credentials set``.
"""

from autopilot.credentials.acquisition import (
    CREDENTIAL_REGISTRY,
    CredentialInfo,
    acquire_api_key,
    acquire_aws_credentials,
    acquire_credential,
    acquire_google_oauth,
    acquire_microsoft_oauth,
)

__all__ = [
    "CREDENTIAL_REGISTRY",
    "CredentialInfo",
    "acquire_api_key",
    "acquire_aws_credentials",
    "acquire_credential",
    "acquire_google_oauth",
    "acquire_microsoft_oauth",
]
