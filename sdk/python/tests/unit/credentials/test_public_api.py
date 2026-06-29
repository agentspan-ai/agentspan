# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Verify that credential types are exported from the top-level conductor.ai.agents package."""


class TestPublicApiExports:
    """Public API surface for credential management."""

    def test_get_credential_importable_from_top_level(self):
        from conductor.ai.agents import get_secret

        assert callable(get_secret)

    def test_credential_not_found_error_importable(self):
        from conductor.ai.agents import CredentialNotFoundError

        exc = CredentialNotFoundError(["MISSING"])
        assert "MISSING" in str(exc)

    def test_credential_auth_error_importable(self):
        from conductor.ai.agents import CredentialAuthError

        exc = CredentialAuthError("expired")
        assert isinstance(exc, Exception)

    def test_credential_rate_limit_error_importable(self):
        from conductor.ai.agents import CredentialRateLimitError

        exc = CredentialRateLimitError()
        assert isinstance(exc, Exception)

    def test_credential_service_error_importable(self):
        from conductor.ai.agents import CredentialServiceError

        exc = CredentialServiceError(503)
        assert isinstance(exc, Exception)

    def test_tool_accepts_credentials_param_end_to_end(self):
        """@tool with credentials= is accepted and ToolDef.credentials is set."""
        from conductor.ai.agents import tool

        @tool(credentials=["GITHUB_TOKEN"])
        def my_tool(branch: str) -> str:
            """Deploy."""
            return "ok"

        td = my_tool._tool_def
        assert "GITHUB_TOKEN" in td.credentials

    def test_agent_accepts_credentials_param(self):
        from conductor.ai.agents import Agent

        a = Agent(
            name="test_agent_export",
            model="openai/gpt-4o",
            credentials=["GITHUB_TOKEN"],
        )
        assert "GITHUB_TOKEN" in a.credentials

    def test_all_credential_names_in_all_exports(self):
        """Every credential name must appear in __all__."""
        import conductor.ai.agents as module

        for name in [
            "get_secret",
            "CredentialNotFoundError",
            "CredentialAuthError",
            "CredentialRateLimitError",
            "CredentialServiceError",
        ]:
            assert name in module.__all__, f"{name!r} missing from __all__"
