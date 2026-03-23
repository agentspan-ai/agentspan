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
    return WorkerCredentialFetcher(server_url="http://localhost:8080/api")


class TestFetchWithoutToken:
    """Local dev path: no execution token, read from os.environ."""

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

    def test_missing_env_returns_partial(self):
        """Missing env vars are silently omitted (local dev convenience)."""
        fetcher = _make_fetcher()
        result = fetcher.fetch("", ["_NONEXISTENT_KEY_12345"])
        assert result == {}

    def test_empty_names_returns_empty(self):
        fetcher = _make_fetcher()
        result = fetcher.fetch(None, [])
        assert result == {}

    def test_multiple_env_vars_returned(self):
        fetcher = _make_fetcher()
        with patch.dict(os.environ, {"KEY_A": "val_a", "KEY_B": "val_b"}):
            result = fetcher.fetch(None, ["KEY_A", "KEY_B"])
        assert result == {"KEY_A": "val_a", "KEY_B": "val_b"}

    def test_partial_env_returns_found_only(self):
        fetcher = _make_fetcher()
        with patch.dict(os.environ, {"KEY_A": "val_a"}):
            result = fetcher.fetch(None, ["KEY_A", "KEY_MISSING"])
        assert result == {"KEY_A": "val_a"}


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
