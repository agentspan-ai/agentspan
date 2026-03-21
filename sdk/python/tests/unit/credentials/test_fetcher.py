# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for WorkerCredentialFetcher."""

import os
from unittest.mock import MagicMock, patch

import pytest

from agentspan.agents.runtime.credentials.fetcher import WorkerCredentialFetcher
from agentspan.agents.runtime.credentials.types import (
    CredentialAuthError,
    CredentialNotFoundError,
    CredentialRateLimitError,
    CredentialServiceError,
)


def _make_fetcher(strict_mode: bool = False, server_url: str = "http://localhost:8080/api"):
    return WorkerCredentialFetcher(server_url=server_url, strict_mode=strict_mode)


def _mock_response(status_code: int, json_body=None, text: str = ""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=resp,
        )
    return resp


class TestFetchWithToken:
    """Fetch credentials via /api/credentials/resolve."""

    def test_successful_fetch_returns_dict(self):
        fetcher = _make_fetcher()
        mock_resp = _mock_response(200, {"GITHUB_TOKEN": "ghp_xxx"})
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            result = fetcher.fetch("exec-token-abc", ["GITHUB_TOKEN"])

        assert result["GITHUB_TOKEN"] == "ghp_xxx"
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert "credentials/resolve" in call_kwargs[0][0]

    def test_post_payload_contains_token_and_names(self):
        fetcher = _make_fetcher()
        mock_resp = _mock_response(200, {"GITHUB_TOKEN": "ghp_xxx", "GH_TOKEN": "ghp_yyy"})
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            fetcher.fetch("exec-token-abc", ["GITHUB_TOKEN", "GH_TOKEN"])

        payload = mock_client.post.call_args[1]["json"]
        assert payload["token"] == "exec-token-abc"
        assert set(payload["names"]) == {"GITHUB_TOKEN", "GH_TOKEN"}

    def test_401_raises_credential_auth_error_immediately(self):
        """401 must raise CredentialAuthError — no env fallback."""
        fetcher = _make_fetcher(strict_mode=False)
        mock_resp = _mock_response(401, text="Unauthorized")
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            with pytest.raises(CredentialAuthError):
                fetcher.fetch("expired-token", ["GITHUB_TOKEN"])

    def test_401_does_not_fall_through_to_env_even_with_env_set(self):
        fetcher = _make_fetcher(strict_mode=False)
        mock_resp = _mock_response(401, text="Unauthorized")
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            with patch.dict(os.environ, {"GITHUB_TOKEN": "env_value"}):
                with pytest.raises(CredentialAuthError):
                    fetcher.fetch("expired-token", ["GITHUB_TOKEN"])

    def test_429_raises_rate_limit_error_immediately(self):
        fetcher = _make_fetcher(strict_mode=False)
        mock_resp = _mock_response(429, text="Too Many Requests")
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            with pytest.raises(CredentialRateLimitError):
                fetcher.fetch("valid-token", ["GITHUB_TOKEN"])

    def test_5xx_raises_service_error_in_strict_mode(self):
        fetcher = _make_fetcher(strict_mode=True)
        mock_resp = _mock_response(503, text="Service Unavailable")
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            with pytest.raises(CredentialServiceError) as exc_info:
                fetcher.fetch("valid-token", ["GITHUB_TOKEN"])
        assert exc_info.value.status_code == 503

    def test_5xx_falls_through_to_env_in_non_strict_mode(self):
        """5xx in non-strict mode: env fallback with warning."""
        fetcher = _make_fetcher(strict_mode=False)
        mock_resp = _mock_response(503, text="Service Unavailable")
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            with patch.dict(os.environ, {"GITHUB_TOKEN": "env_value"}):
                result = fetcher.fetch("valid-token", ["GITHUB_TOKEN"])
        assert result["GITHUB_TOKEN"] == "env_value"

    def test_missing_names_in_response_env_fallback_non_strict(self):
        """Names not in 200 response → env fallback when non-strict."""
        fetcher = _make_fetcher(strict_mode=False)
        # Server only returned GITHUB_TOKEN, not OPENAI_API_KEY
        mock_resp = _mock_response(200, {"GITHUB_TOKEN": "ghp_xxx"})
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env"}):
                result = fetcher.fetch("valid-token", ["GITHUB_TOKEN", "OPENAI_API_KEY"])
        assert result["GITHUB_TOKEN"] == "ghp_xxx"
        assert result["OPENAI_API_KEY"] == "sk-env"

    def test_missing_names_in_response_raises_in_strict_mode(self):
        fetcher = _make_fetcher(strict_mode=True)
        mock_resp = _mock_response(200, {"GITHUB_TOKEN": "ghp_xxx"})
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            with pytest.raises(CredentialNotFoundError) as exc_info:
                fetcher.fetch("valid-token", ["GITHUB_TOKEN", "OPENAI_API_KEY"])
        assert "OPENAI_API_KEY" in exc_info.value.missing_names


class TestFetchWithoutToken:
    """Local dev path: no execution token, fall straight to os.environ."""

    def test_empty_token_returns_env_vars(self):
        fetcher = _make_fetcher()
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_local"}):
            result = fetcher.fetch("", ["GITHUB_TOKEN"])
        assert result["GITHUB_TOKEN"] == "ghp_local"

    def test_none_token_returns_env_vars(self):
        fetcher = _make_fetcher()
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_local"}):
            result = fetcher.fetch(None, ["GITHUB_TOKEN"])
        assert result["GITHUB_TOKEN"] == "ghp_local"

    def test_empty_token_missing_env_returns_empty_in_non_strict(self):
        fetcher = _make_fetcher(strict_mode=False)
        with patch.dict(os.environ, {}, clear=True):
            result = fetcher.fetch("", ["GITHUB_TOKEN"])
        assert result == {}

    def test_empty_token_missing_env_raises_in_strict_mode(self):
        fetcher = _make_fetcher(strict_mode=True)
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(CredentialNotFoundError):
                fetcher.fetch("", ["GITHUB_TOKEN"])

    def test_no_http_call_when_token_absent(self):
        fetcher = _make_fetcher()
        with patch("httpx.Client") as mock_client_cls:
            with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_local"}):
                fetcher.fetch("", ["GITHUB_TOKEN"])
        mock_client_cls.assert_not_called()
