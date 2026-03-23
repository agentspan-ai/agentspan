# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for get_credential() accessor."""

import pytest

from agentspan.agents.runtime.credentials.accessor import (
    _credential_context,
    get_credential,
    set_credential_context,
    clear_credential_context,
)
from agentspan.agents.runtime.credentials.types import CredentialNotFoundError


class TestGetCredential:
    """get_credential() reads from contextvars context."""

    def setup_method(self):
        """Ensure clean state before each test."""
        clear_credential_context()

    def teardown_method(self):
        """Restore clean state after each test."""
        clear_credential_context()

    def test_returns_value_when_set(self):
        set_credential_context({"GITHUB_TOKEN": "ghp_test"})
        assert get_credential("GITHUB_TOKEN") == "ghp_test"

    def test_raises_when_not_in_context(self):
        set_credential_context({})
        with pytest.raises(CredentialNotFoundError) as exc_info:
            get_credential("MISSING_CRED")
        assert "MISSING_CRED" in exc_info.value.missing_names

    def test_raises_when_context_not_set_at_all(self):
        """Context was never set — raises CredentialNotFoundError."""
        with pytest.raises(CredentialNotFoundError):
            get_credential("SOME_CRED")

    def test_multiple_credentials_accessible(self):
        set_credential_context({
            "GITHUB_TOKEN": "ghp_test",
            "OPENAI_API_KEY": "sk-test",
        })
        assert get_credential("GITHUB_TOKEN") == "ghp_test"
        assert get_credential("OPENAI_API_KEY") == "sk-test"

    def test_context_is_isolated_per_thread(self):
        """contextvars.ContextVar is thread-local — different threads have independent contexts."""
        import threading

        results = {}

        def thread_fn(name: str, token: str):
            set_credential_context({"TOKEN": token})
            results[name] = get_credential("TOKEN")

        t1 = threading.Thread(target=thread_fn, args=("t1", "token_for_t1"))
        t2 = threading.Thread(target=thread_fn, args=("t2", "token_for_t2"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results["t1"] == "token_for_t1"
        assert results["t2"] == "token_for_t2"

    def test_clear_removes_context(self):
        set_credential_context({"GITHUB_TOKEN": "ghp_test"})
        clear_credential_context()
        with pytest.raises(CredentialNotFoundError):
            get_credential("GITHUB_TOKEN")
