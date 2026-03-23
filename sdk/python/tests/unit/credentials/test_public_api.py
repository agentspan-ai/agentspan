# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Verify that credential types are exported from the top-level agentspan.agents package."""

import pytest


class TestPublicApiExports:
    """Public API surface for credential management."""

    def test_get_credential_importable_from_top_level(self):
        from agentspan.agents import get_credential
        assert callable(get_credential)

    def test_credential_file_importable_from_top_level(self):
        from agentspan.agents import CredentialFile
        cf = CredentialFile("KUBECONFIG", ".kube/config")
        assert cf.env_var == "KUBECONFIG"

    def test_credential_not_found_error_importable(self):
        from agentspan.agents import CredentialNotFoundError
        exc = CredentialNotFoundError(["MISSING"])
        assert "MISSING" in str(exc)

    def test_credential_auth_error_importable(self):
        from agentspan.agents import CredentialAuthError
        exc = CredentialAuthError("expired")
        assert isinstance(exc, Exception)

    def test_credential_rate_limit_error_importable(self):
        from agentspan.agents import CredentialRateLimitError
        exc = CredentialRateLimitError()
        assert isinstance(exc, Exception)

    def test_credential_service_error_importable(self):
        from agentspan.agents import CredentialServiceError
        exc = CredentialServiceError(503)
        assert isinstance(exc, Exception)

    def test_tool_accepts_credentials_param_end_to_end(self):
        """@tool with credentials= is accepted and ToolDef.credentials is set."""
        from agentspan.agents import tool, CredentialFile

        @tool(credentials=["GITHUB_TOKEN", CredentialFile("KUBECONFIG", ".kube/config")])
        def my_tool(branch: str) -> str:
            """Deploy."""
            return "ok"

        td = my_tool._tool_def
        assert "GITHUB_TOKEN" in td.credentials
        assert any(
            hasattr(c, "env_var") and c.env_var == "KUBECONFIG"
            for c in td.credentials
        )

    def test_agent_accepts_credentials_param(self):
        from agentspan.agents import Agent
        a = Agent(
            name="test_agent_export",
            model="openai/gpt-4o",
            credentials=["GITHUB_TOKEN"],
        )
        assert "GITHUB_TOKEN" in a.credentials

    def test_all_credential_names_in_all_exports(self):
        """Every credential name must appear in __all__."""
        import agentspan.agents as module
        for name in ["get_credential", "CredentialFile", "CredentialNotFoundError",
                     "CredentialAuthError", "CredentialRateLimitError", "CredentialServiceError"]:
            assert name in module.__all__, f"{name!r} missing from __all__"
