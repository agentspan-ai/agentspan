# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for WorkerCredentialFetcher — no mocks, no server required.

Server-dependent tests live in tests/e2e/test_credential_e2e.py.
"""

import os
from unittest.mock import patch

import pytest

from agentspan.agents.runtime.credentials.fetcher import WorkerCredentialFetcher
from agentspan.agents.runtime.credentials.types import (
    CredentialNotFoundError,
    CredentialServiceError,
)


def _make_fetcher():
    return WorkerCredentialFetcher(server_url="http://localhost:6767/api")


class TestFetchWithoutToken:
    """No execution token — must fail with CredentialNotFoundError."""

    def test_empty_token_raises(self):
        fetcher = _make_fetcher()
        with pytest.raises(CredentialNotFoundError):
            fetcher.fetch("", ["GITHUB_TOKEN"])

    def test_none_token_raises(self):
        fetcher = _make_fetcher()
        with pytest.raises(CredentialNotFoundError):
            fetcher.fetch(None, ["GITHUB_TOKEN"])

    def test_none_token_error_lists_names(self):
        fetcher = _make_fetcher()
        with pytest.raises(CredentialNotFoundError, match="GITHUB_TOKEN"):
            fetcher.fetch(None, ["GITHUB_TOKEN"])

    def test_empty_names_returns_empty(self):
        fetcher = _make_fetcher()
        result = fetcher.fetch(None, [])
        assert result == {}

    def test_multiple_names_in_error(self):
        fetcher = _make_fetcher()
        with pytest.raises(CredentialNotFoundError):
            fetcher.fetch(None, ["KEY_A", "KEY_B"])


class TestFetchUnreachableServer:
    """Network errors when server is not running — always raises, no fallback."""

    def test_unreachable_server_raises_service_error(self):
        fetcher = WorkerCredentialFetcher(server_url="http://127.0.0.1:19999/api")
        with pytest.raises(CredentialServiceError):
            fetcher.fetch("some-token", ["MY_KEY"])

    def test_unreachable_server_no_env_fallback(self):
        """Even with env var set, unreachable server raises — no silent fallback."""
        fetcher = WorkerCredentialFetcher(server_url="http://127.0.0.1:19999/api")
        with patch.dict(os.environ, {"MY_KEY": "from_env"}):
            with pytest.raises(CredentialServiceError):
                fetcher.fetch("some-token", ["MY_KEY"])
