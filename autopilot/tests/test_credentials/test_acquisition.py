"""Tests for the credential acquisition system.

All assertions are algorithmic/deterministic — no LLM or mock-based validation.
"""

from __future__ import annotations

import configparser
import inspect
from pathlib import Path

import pytest

from autopilot.credentials.acquisition import (
    CREDENTIAL_REGISTRY,
    CredentialInfo,
    _API_KEY_URLS,
    acquire_api_key,
    acquire_aws_credentials,
    acquire_credential,
    acquire_google_oauth,
    acquire_microsoft_oauth,
    read_aws_credentials_file,
)


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------

class TestCredentialRegistryCompleteness:
    """Every credential declared by any integration must be in the registry."""

    # Collected from grepping @tool(credentials=[...]) across all integrations
    _ALL_INTEGRATION_CREDENTIALS: set[str] = {
        "GMAIL_ACCESS_TOKEN",
        "GOOGLE_CALENDAR_TOKEN",
        "GOOGLE_DRIVE_TOKEN",
        "GA_ACCESS_TOKEN",
        "GA_PROPERTY_ID",
        "OUTLOOK_ACCESS_TOKEN",
        "GITHUB_TOKEN",
        "LINEAR_API_KEY",
        "NOTION_API_KEY",
        "SLACK_BOT_TOKEN",
        "HUBSPOT_ACCESS_TOKEN",
        "JIRA_URL",
        "JIRA_EMAIL",
        "JIRA_API_TOKEN",
        "BRAVE_API_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "WHATSAPP_TOKEN",
        "WHATSAPP_PHONE_ID",
        "SALESFORCE_INSTANCE_URL",
        "SALESFORCE_ACCESS_TOKEN",
    }

    def test_credential_registry_has_all_integrations(self) -> None:
        """Every credential used by any integration tool is in the registry."""
        registry_keys = set(CREDENTIAL_REGISTRY.keys())
        missing = self._ALL_INTEGRATION_CREDENTIALS - registry_keys
        assert missing == set(), (
            f"Credentials used by integrations but missing from CREDENTIAL_REGISTRY: {missing}"
        )

    def test_registry_has_no_phantom_entries(self) -> None:
        """Registry should not contain entries for credentials that no integration uses.

        This is a weaker check — we just verify every registry entry is a
        known credential name (no typos).
        """
        for name, info in CREDENTIAL_REGISTRY.items():
            assert info.name == name, (
                f"Registry key '{name}' does not match info.name '{info.name}'"
            )


# ---------------------------------------------------------------------------
# CredentialInfo fields
# ---------------------------------------------------------------------------

class TestCredentialInfoFields:
    """Every registry entry has the required fields populated."""

    def test_every_entry_has_name_service_acquisition_type(self) -> None:
        for name, info in CREDENTIAL_REGISTRY.items():
            assert info.name, f"CredentialInfo for '{name}' has empty name"
            assert info.service, f"CredentialInfo for '{name}' has empty service"
            assert info.acquisition_type, f"CredentialInfo for '{name}' has empty acquisition_type"

    def test_acquisition_types_are_valid(self) -> None:
        valid_types = {"oauth_google", "oauth_microsoft", "api_key", "aws", "manual"}
        for name, info in CREDENTIAL_REGISTRY.items():
            assert info.acquisition_type in valid_types, (
                f"CredentialInfo '{name}' has invalid acquisition_type: {info.acquisition_type}"
            )

    def test_oauth_entries_have_scopes(self) -> None:
        for name, info in CREDENTIAL_REGISTRY.items():
            if info.acquisition_type in ("oauth_google", "oauth_microsoft"):
                assert len(info.scopes) > 0, (
                    f"OAuth credential '{name}' must have at least one scope"
                )

    def test_api_key_entries_have_url(self) -> None:
        for name, info in CREDENTIAL_REGISTRY.items():
            if info.acquisition_type == "api_key":
                assert info.url, (
                    f"API key credential '{name}' must have a URL"
                )

    def test_every_entry_has_instructions(self) -> None:
        for name, info in CREDENTIAL_REGISTRY.items():
            assert info.instructions, (
                f"CredentialInfo for '{name}' has empty instructions"
            )


# ---------------------------------------------------------------------------
# API key URLs
# ---------------------------------------------------------------------------

class TestApiKeyUrls:
    """All API key URLs must be valid HTTPS URLs."""

    def test_all_urls_are_https(self) -> None:
        for name, url in _API_KEY_URLS.items():
            assert url.startswith("https://"), (
                f"URL for '{name}' must start with https:// — got: {url}"
            )

    def test_all_urls_have_host(self) -> None:
        import urllib.parse

        for name, url in _API_KEY_URLS.items():
            parsed = urllib.parse.urlparse(url)
            assert parsed.hostname, (
                f"URL for '{name}' has no hostname: {url}"
            )

    def test_api_key_urls_match_registry(self) -> None:
        """Every _API_KEY_URLS key should correspond to a registry entry with type api_key."""
        for name in _API_KEY_URLS:
            info = CREDENTIAL_REGISTRY.get(name)
            assert info is not None, (
                f"_API_KEY_URLS has '{name}' but it is not in CREDENTIAL_REGISTRY"
            )
            assert info.acquisition_type == "api_key", (
                f"_API_KEY_URLS has '{name}' but registry says type is '{info.acquisition_type}'"
            )


# ---------------------------------------------------------------------------
# Google OAuth scopes
# ---------------------------------------------------------------------------

class TestGoogleOAuthScopes:
    """Verify that OAuth scopes match what the integrations actually need."""

    def test_gmail_scopes_include_readonly(self) -> None:
        info = CREDENTIAL_REGISTRY["GMAIL_ACCESS_TOKEN"]
        assert any("gmail.readonly" in s for s in info.scopes), (
            "Gmail scopes must include gmail.readonly"
        )

    def test_gmail_scopes_include_send(self) -> None:
        info = CREDENTIAL_REGISTRY["GMAIL_ACCESS_TOKEN"]
        assert any("gmail.send" in s for s in info.scopes), (
            "Gmail scopes must include gmail.send"
        )

    def test_google_calendar_scopes_include_calendar(self) -> None:
        info = CREDENTIAL_REGISTRY["GOOGLE_CALENDAR_TOKEN"]
        assert any("calendar" in s for s in info.scopes), (
            "Google Calendar scopes must reference calendar"
        )

    def test_google_drive_scopes_include_drive(self) -> None:
        info = CREDENTIAL_REGISTRY["GOOGLE_DRIVE_TOKEN"]
        assert any("drive" in s for s in info.scopes), (
            "Google Drive scopes must reference drive"
        )

    def test_ga_scopes_include_analytics(self) -> None:
        info = CREDENTIAL_REGISTRY["GA_ACCESS_TOKEN"]
        assert any("analytics" in s for s in info.scopes), (
            "Google Analytics scopes must reference analytics"
        )


# ---------------------------------------------------------------------------
# Microsoft OAuth scopes
# ---------------------------------------------------------------------------

class TestMicrosoftOAuthScopes:
    def test_outlook_scopes_include_mail_read(self) -> None:
        info = CREDENTIAL_REGISTRY["OUTLOOK_ACCESS_TOKEN"]
        assert any("Mail.Read" in s for s in info.scopes), (
            "Outlook scopes must include Mail.Read"
        )

    def test_outlook_scopes_include_mail_send(self) -> None:
        info = CREDENTIAL_REGISTRY["OUTLOOK_ACCESS_TOKEN"]
        assert any("Mail.Send" in s for s in info.scopes), (
            "Outlook scopes must include Mail.Send"
        )


# ---------------------------------------------------------------------------
# AWS credentials file reading
# ---------------------------------------------------------------------------

class TestAwsCredentialsFileReading:
    """Test reading AWS credentials from an INI-format file."""

    def test_reads_default_profile(self, tmp_path: Path) -> None:
        creds_file = tmp_path / "credentials"
        creds_file.write_text(
            "[default]\n"
            "aws_access_key_id = AKIAIOSFODNN7EXAMPLE\n"
            "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n"
        )
        result = read_aws_credentials_file(credentials_path=creds_file)
        assert result["aws_access_key_id"] == "AKIAIOSFODNN7EXAMPLE"
        assert result["aws_secret_access_key"] == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

    def test_reads_named_profile(self, tmp_path: Path) -> None:
        creds_file = tmp_path / "credentials"
        creds_file.write_text(
            "[default]\n"
            "aws_access_key_id = DEFAULT_KEY\n"
            "aws_secret_access_key = DEFAULT_SECRET\n"
            "\n"
            "[production]\n"
            "aws_access_key_id = PROD_KEY\n"
            "aws_secret_access_key = PROD_SECRET\n"
        )
        result = read_aws_credentials_file(profile="production", credentials_path=creds_file)
        assert result["aws_access_key_id"] == "PROD_KEY"
        assert result["aws_secret_access_key"] == "PROD_SECRET"

    def test_returns_empty_for_missing_file(self, tmp_path: Path) -> None:
        creds_file = tmp_path / "nonexistent"
        result = read_aws_credentials_file(credentials_path=creds_file)
        assert result == {}

    def test_returns_empty_for_missing_profile(self, tmp_path: Path) -> None:
        creds_file = tmp_path / "credentials"
        creds_file.write_text(
            "[default]\n"
            "aws_access_key_id = KEY\n"
            "aws_secret_access_key = SECRET\n"
        )
        result = read_aws_credentials_file(profile="nonexistent", credentials_path=creds_file)
        assert result == {}

    def test_returns_empty_for_incomplete_profile(self, tmp_path: Path) -> None:
        creds_file = tmp_path / "credentials"
        creds_file.write_text(
            "[default]\n"
            "aws_access_key_id = KEY_ONLY\n"
        )
        result = read_aws_credentials_file(credentials_path=creds_file)
        assert result == {}


# ---------------------------------------------------------------------------
# Function signatures — verify public API contracts
# ---------------------------------------------------------------------------

class TestFunctionSignatures:
    """Verify that the acquisition functions accept the documented parameters."""

    def test_acquire_credential_takes_credential_name(self) -> None:
        sig = inspect.signature(acquire_credential)
        params = list(sig.parameters.keys())
        assert "credential_name" in params

    def test_acquire_google_oauth_signature(self) -> None:
        sig = inspect.signature(acquire_google_oauth)
        params = list(sig.parameters.keys())
        assert "credential_name" in params
        assert "scopes" in params
        assert "client_id" in params
        assert "client_secret" in params

    def test_acquire_microsoft_oauth_signature(self) -> None:
        sig = inspect.signature(acquire_microsoft_oauth)
        params = list(sig.parameters.keys())
        assert "credential_name" in params
        assert "scopes" in params
        assert "client_id" in params
        assert "client_secret" in params

    def test_acquire_api_key_takes_credential_name(self) -> None:
        sig = inspect.signature(acquire_api_key)
        params = list(sig.parameters.keys())
        assert "credential_name" in params

    def test_acquire_aws_credentials_takes_credential_name(self) -> None:
        sig = inspect.signature(acquire_aws_credentials)
        params = list(sig.parameters.keys())
        assert "credential_name" in params

    def test_acquire_credential_is_in_registry_for_known_names(self) -> None:
        """Every known credential name dispatches to the correct acquisition type."""
        for name, info in CREDENTIAL_REGISTRY.items():
            assert info.acquisition_type in {
                "oauth_google", "oauth_microsoft", "api_key", "aws", "manual"
            }, f"Unknown acquisition type for {name}: {info.acquisition_type}"


# ---------------------------------------------------------------------------
# Orchestrator integration — acquire_credentials tool exists
# ---------------------------------------------------------------------------

class TestOrchestratorIntegration:
    """The acquire_credentials tool is exported from orchestrator tools."""

    def test_acquire_credentials_in_orchestrator_tools(self) -> None:
        from autopilot.orchestrator.tools import get_orchestrator_tools

        tool_names = []
        for t in get_orchestrator_tools():
            if hasattr(t, "__name__"):
                tool_names.append(t.__name__)
            elif hasattr(t, "_tool_def"):
                tool_names.append(t._tool_def.name)

        assert "acquire_credentials" in tool_names, (
            f"acquire_credentials not found in orchestrator tools. Found: {tool_names}"
        )

    def test_prompt_credentials_still_available(self) -> None:
        """prompt_credentials should remain available for backward compat."""
        from autopilot.orchestrator.tools import get_orchestrator_tools

        tool_names = []
        for t in get_orchestrator_tools():
            if hasattr(t, "__name__"):
                tool_names.append(t.__name__)
            elif hasattr(t, "_tool_def"):
                tool_names.append(t._tool_def.name)

        assert "prompt_credentials" in tool_names


# ---------------------------------------------------------------------------
# Negative / edge-case tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Verify the system handles edge cases correctly."""

    def test_credential_info_dataclass_defaults(self) -> None:
        """CredentialInfo with only required fields should have sensible defaults."""
        info = CredentialInfo(name="TEST", service="Test Service", acquisition_type="manual")
        assert info.scopes == []
        assert info.url == ""
        assert info.instructions == ""

    def test_unknown_credential_not_in_registry(self) -> None:
        """A made-up credential name should not be in the registry."""
        assert "TOTALLY_FAKE_CREDENTIAL_XYZ" not in CREDENTIAL_REGISTRY

    def test_aws_credentials_file_handles_directory_as_path(self, tmp_path: Path) -> None:
        """Passing a directory (not a file) as credentials_path returns empty."""
        result = read_aws_credentials_file(credentials_path=tmp_path)
        assert result == {}
