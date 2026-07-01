# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for credential exception hierarchy."""

from conductor.ai.agents.runtime.credentials.types import (
    CredentialAuthError,
    CredentialNotFoundError,
    CredentialRateLimitError,
    CredentialServiceError,
)
from conductor.ai.agents.exceptions import AgentspanError


class TestCredentialExceptions:
    """Exception hierarchy."""

    def test_credential_not_found_error_is_agentspan_error(self):
        exc = CredentialNotFoundError(["GITHUB_TOKEN"])
        assert isinstance(exc, AgentspanError)

    def test_credential_not_found_error_message_contains_names(self):
        exc = CredentialNotFoundError(["GITHUB_TOKEN", "OPENAI_API_KEY"])
        assert "GITHUB_TOKEN" in str(exc)
        assert "OPENAI_API_KEY" in str(exc)

    def test_credential_not_found_error_stores_names(self):
        exc = CredentialNotFoundError(["GITHUB_TOKEN"])
        assert exc.missing_names == ["GITHUB_TOKEN"]

    def test_credential_auth_error_is_agentspan_error(self):
        exc = CredentialAuthError("token expired")
        assert isinstance(exc, AgentspanError)

    def test_credential_auth_error_message(self):
        exc = CredentialAuthError("token expired")
        assert "token expired" in str(exc)

    def test_credential_rate_limit_error_is_agentspan_error(self):
        exc = CredentialRateLimitError()
        assert isinstance(exc, AgentspanError)

    def test_credential_service_error_is_agentspan_error(self):
        exc = CredentialServiceError(503, "unavailable")
        assert isinstance(exc, AgentspanError)

    def test_credential_service_error_stores_status_code(self):
        exc = CredentialServiceError(503, "unavailable")
        assert exc.status_code == 503
