# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for credential types and exceptions."""
import pytest

from agentspan.agents.runtime.credentials.types import (
    CredentialAuthError,
    CredentialFile,
    CredentialNotFoundError,
    CredentialRateLimitError,
    CredentialServiceError,
)
from agentspan.agents.exceptions import AgentspanError


class TestCredentialFile:
    """CredentialFile value object."""

    def test_basic_construction(self):
        cf = CredentialFile("KUBECONFIG", ".kube/config")
        assert cf.env_var == "KUBECONFIG"
        assert cf.relative_path == ".kube/config"

    def test_content_defaults_to_none(self):
        cf = CredentialFile("KUBECONFIG", ".kube/config")
        assert cf.content is None

    def test_content_can_be_set(self):
        cf = CredentialFile("KUBECONFIG", ".kube/config", content="apiVersion: v1")
        assert cf.content == "apiVersion: v1"

    def test_equality(self):
        a = CredentialFile("KUBECONFIG", ".kube/config")
        b = CredentialFile("KUBECONFIG", ".kube/config")
        assert a == b

    def test_inequality_different_env_var(self):
        a = CredentialFile("KUBECONFIG", ".kube/config")
        b = CredentialFile("OTHER", ".kube/config")
        assert a != b

    def test_repr_contains_env_var(self):
        cf = CredentialFile("KUBECONFIG", ".kube/config")
        assert "KUBECONFIG" in repr(cf)

    def test_is_hashable(self):
        """CredentialFile must be usable in sets/dict keys for deduplication."""
        cf1 = CredentialFile("KUBECONFIG", ".kube/config")
        cf2 = CredentialFile("KUBECONFIG", ".kube/config")
        s = {cf1, cf2}
        assert len(s) == 1


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
