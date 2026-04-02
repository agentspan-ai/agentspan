# Python SDK Credential Changes Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-user credential fetching, subprocess isolation, and credential-aware @tool/Agent decorators to the Agentspan Python SDK.

**Architecture:** A new `credentials/` subpackage under `runtime/` holds all credential logic: exception types, a `WorkerCredentialFetcher` that calls `POST /api/credentials/resolve` with fallback to `os.environ`, a `SubprocessIsolator` that runs tool functions in a fresh subprocess with injected credentials, and a `get_credential()` accessor backed by a `contextvars.ContextVar` for non-isolated tools. The `@tool` decorator gains `isolated` and `credentials` params; `Agent` gains a `credentials` param with auto-mapping from `cli_allowed_commands` via `CLI_CREDENTIAL_MAP`. Dispatch in `_dispatch.py` extracts `__agentspan_ctx__` from the Conductor task, calls the fetcher, then routes to the isolator or context-setter based on `isolated`.

**Tech Stack:** Python 3.9+, pytest, multiprocessing (spawn), httpx, cloudpickle

---

## File Structure

New files:
- `sdk/python/src/agentspan/agents/runtime/credentials/__init__.py` — package exports
- `sdk/python/src/agentspan/agents/runtime/credentials/types.py` — `CredentialFile` dataclass + 4 exception types
- `sdk/python/src/agentspan/agents/runtime/credentials/fetcher.py` — `WorkerCredentialFetcher`
- `sdk/python/src/agentspan/agents/runtime/credentials/isolator.py` — `SubprocessIsolator`
- `sdk/python/src/agentspan/agents/runtime/credentials/accessor.py` — `get_credential()` + context var
- `sdk/python/src/agentspan/agents/runtime/credentials/cli_map.py` — `CLI_CREDENTIAL_MAP` registry
- `sdk/python/tests/unit/credentials/__init__.py`
- `sdk/python/tests/unit/credentials/test_types.py`
- `sdk/python/tests/unit/credentials/test_fetcher.py`
- `sdk/python/tests/unit/credentials/test_isolator.py`
- `sdk/python/tests/unit/credentials/test_cli_map.py`

Modified files:
- `sdk/python/src/agentspan/agents/tool.py` — add `isolated: bool = True`, `credentials: list = []` to `@tool` and `ToolDef`
- `sdk/python/src/agentspan/agents/agent.py` — add `credentials` param to `Agent.__init__` and `AgentDef`, validate `terraform` in `cli_allowed_commands`
- `sdk/python/src/agentspan/agents/runtime/config.py` — add `credential_strict_mode: bool = False`, promote `api_key` to a real field
- `sdk/python/src/agentspan/agents/runtime/_dispatch.py` — extract `__agentspan_ctx__`, call fetcher before tool execution, route through isolator or context accessor
- `sdk/python/src/agentspan/agents/__init__.py` — export `get_credential`, `CredentialFile`, new exception types

---

## Chunk 1: Types, Exceptions, and CLI Map

### Task 1: Credential Types and Exception Hierarchy

**Files:**
- Create: `sdk/python/src/agentspan/agents/runtime/credentials/__init__.py`
- Create: `sdk/python/src/agentspan/agents/runtime/credentials/types.py`
- Create: `sdk/python/tests/unit/credentials/__init__.py`
- Create: `sdk/python/tests/unit/credentials/test_types.py`

- [ ] **Step 1: Create the test file**

```python
# sdk/python/tests/unit/credentials/test_types.py
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd sdk/python && uv run pytest tests/unit/credentials/test_types.py -v
```

Expected: `ModuleNotFoundError` — `credentials` package does not exist yet.

- [ ] **Step 3: Create the empty `__init__` files and types module**

Create `sdk/python/src/agentspan/agents/runtime/credentials/__init__.py`:
```python
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credential management subpackage for the Agentspan Python SDK."""

from agentspan.agents.runtime.credentials.accessor import get_credential
from agentspan.agents.runtime.credentials.cli_map import CLI_CREDENTIAL_MAP
from agentspan.agents.runtime.credentials.fetcher import WorkerCredentialFetcher
from agentspan.agents.runtime.credentials.isolator import SubprocessIsolator
from agentspan.agents.runtime.credentials.types import (
    CredentialAuthError,
    CredentialFile,
    CredentialNotFoundError,
    CredentialRateLimitError,
    CredentialServiceError,
)

__all__ = [
    "CredentialFile",
    "CredentialNotFoundError",
    "CredentialAuthError",
    "CredentialRateLimitError",
    "CredentialServiceError",
    "WorkerCredentialFetcher",
    "SubprocessIsolator",
    "get_credential",
    "CLI_CREDENTIAL_MAP",
]
```

Create `sdk/python/tests/unit/credentials/__init__.py`:
```python
```
(empty file)

Create `sdk/python/src/agentspan/agents/runtime/credentials/types.py`:
```python
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credential types: CredentialFile value object and exception hierarchy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from agentspan.agents.exceptions import AgentspanError


@dataclass(frozen=True)
class CredentialFile:
    """A credential that should be written to a file in the subprocess HOME.

    Attributes:
        env_var: Environment variable name that will point to the file path.
            Example: ``"KUBECONFIG"``
        relative_path: Path relative to the subprocess temp HOME directory.
            Example: ``".kube/config"``
        content: File content (set by fetcher after resolving the credential value).
            ``None`` means "not yet resolved".
    """

    env_var: str
    relative_path: str
    content: Optional[str] = None


class CredentialNotFoundError(AgentspanError):
    """One or more required credentials could not be resolved.

    Raised when a credential is absent from both the credential service
    and ``os.environ`` (or when ``strict_mode=True`` and it is absent
    from the service regardless of env fallback).
    """

    def __init__(self, missing_names: List[str]) -> None:
        self.missing_names = list(missing_names)
        names_str = ", ".join(missing_names)
        super().__init__(f"Required credentials not found: {names_str}")


class CredentialAuthError(AgentspanError):
    """Execution token is invalid, expired, or revoked.

    Raised on HTTP 401 from ``/api/credentials/resolve``.
    Do NOT retry and do NOT fall through to env var fallback.
    """

    def __init__(self, detail: str = "") -> None:
        msg = "Credential authentication failed (token expired or revoked)"
        if detail:
            msg = f"{msg}: {detail}"
        super().__init__(msg)


class CredentialRateLimitError(AgentspanError):
    """Rate limit exceeded on ``/api/credentials/resolve`` (HTTP 429).

    Do NOT fall through to env var fallback.
    """

    def __init__(self) -> None:
        super().__init__(
            "Credential resolution rate limit exceeded (429). "
            "Reduce resolve call frequency or increase the server rate limit."
        )


class CredentialServiceError(AgentspanError):
    """Credential service returned a 5xx error.

    In strict_mode, always fatal. In non-strict, caller may choose to
    fall through to env var with a warning.

    Attributes:
        status_code: The HTTP status code (e.g. 503).
    """

    def __init__(self, status_code: int, detail: str = "") -> None:
        self.status_code = status_code
        msg = f"Credential service error (HTTP {status_code})"
        if detail:
            msg = f"{msg}: {detail}"
        super().__init__(msg)
```

- [ ] **Step 4: Run tests — but `__init__.py` imports modules that don't exist yet, which will cause ImportError. Stub out the missing modules first.**

Create `sdk/python/src/agentspan/agents/runtime/credentials/fetcher.py` (stub):
```python
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.
"""WorkerCredentialFetcher — stub, implemented in Task 2."""


class WorkerCredentialFetcher:
    pass
```

Create `sdk/python/src/agentspan/agents/runtime/credentials/isolator.py` (stub):
```python
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.
"""SubprocessIsolator — stub, implemented in Task 3."""


class SubprocessIsolator:
    pass
```

Create `sdk/python/src/agentspan/agents/runtime/credentials/accessor.py` (stub):
```python
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.
"""get_credential() accessor — stub, implemented in Task 4."""


def get_credential(name: str) -> str:
    raise NotImplementedError
```

Create `sdk/python/src/agentspan/agents/runtime/credentials/cli_map.py` (stub):
```python
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.
"""CLI_CREDENTIAL_MAP — stub, implemented in Task 5."""

CLI_CREDENTIAL_MAP = {}
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd sdk/python && uv run pytest tests/unit/credentials/test_types.py -v
```

Expected: All 13 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/credentials/ sdk/python/tests/unit/credentials/
git commit -m "feat(credentials): add CredentialFile type and exception hierarchy"
```

---

### Task 2: CLI_CREDENTIAL_MAP Registry

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/credentials/cli_map.py`
- Create: `sdk/python/tests/unit/credentials/test_cli_map.py`

- [ ] **Step 1: Write the failing test**

```python
# sdk/python/tests/unit/credentials/test_cli_map.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for CLI_CREDENTIAL_MAP registry."""

import pytest

from agentspan.agents.runtime.credentials.cli_map import CLI_CREDENTIAL_MAP
from agentspan.agents.runtime.credentials.types import CredentialFile


class TestCliCredentialMap:
    """CLI_CREDENTIAL_MAP registry contents."""

    def test_gh_maps_to_github_tokens(self):
        assert "GITHUB_TOKEN" in CLI_CREDENTIAL_MAP["gh"]
        assert "GH_TOKEN" in CLI_CREDENTIAL_MAP["gh"]

    def test_git_maps_to_github_tokens(self):
        assert "GITHUB_TOKEN" in CLI_CREDENTIAL_MAP["git"]
        assert "GH_TOKEN" in CLI_CREDENTIAL_MAP["git"]

    def test_aws_maps_to_aws_keys(self):
        creds = CLI_CREDENTIAL_MAP["aws"]
        assert "AWS_ACCESS_KEY_ID" in creds
        assert "AWS_SECRET_ACCESS_KEY" in creds
        assert "AWS_SESSION_TOKEN" in creds

    def test_kubectl_maps_to_kubeconfig_file(self):
        creds = CLI_CREDENTIAL_MAP["kubectl"]
        assert any(
            isinstance(c, CredentialFile) and c.env_var == "KUBECONFIG"
            for c in creds
        )

    def test_helm_maps_to_kubeconfig_file(self):
        creds = CLI_CREDENTIAL_MAP["helm"]
        assert any(
            isinstance(c, CredentialFile) and c.env_var == "KUBECONFIG"
            for c in creds
        )

    def test_gcloud_maps_to_project_and_credentials_file(self):
        creds = CLI_CREDENTIAL_MAP["gcloud"]
        names = [c if isinstance(c, str) else c.env_var for c in creds]
        assert "GOOGLE_CLOUD_PROJECT" in names
        assert "GOOGLE_APPLICATION_CREDENTIALS" in names

    def test_az_maps_to_azure_vars(self):
        creds = CLI_CREDENTIAL_MAP["az"]
        assert "AZURE_CLIENT_ID" in creds
        assert "AZURE_CLIENT_SECRET" in creds
        assert "AZURE_TENANT_ID" in creds
        assert "AZURE_SUBSCRIPTION_ID" in creds

    def test_docker_maps_to_docker_creds(self):
        creds = CLI_CREDENTIAL_MAP["docker"]
        assert "DOCKER_USERNAME" in creds
        assert "DOCKER_PASSWORD" in creds

    def test_npm_maps_to_npm_token(self):
        assert "NPM_TOKEN" in CLI_CREDENTIAL_MAP["npm"]

    def test_cargo_maps_to_cargo_token(self):
        assert "CARGO_REGISTRY_TOKEN" in CLI_CREDENTIAL_MAP["cargo"]

    def test_terraform_maps_to_none(self):
        """terraform must explicitly map to None to trigger ConfigurationError at definition time."""
        assert "terraform" in CLI_CREDENTIAL_MAP
        assert CLI_CREDENTIAL_MAP["terraform"] is None

    def test_all_expected_keys_present(self):
        expected = {"gh", "git", "aws", "kubectl", "helm", "gcloud", "az", "docker",
                    "npm", "cargo", "terraform"}
        assert expected.issubset(set(CLI_CREDENTIAL_MAP.keys()))

    def test_kubeconfig_file_has_correct_relative_path(self):
        creds = CLI_CREDENTIAL_MAP["kubectl"]
        kubeconfig = next(
            c for c in creds if isinstance(c, CredentialFile) and c.env_var == "KUBECONFIG"
        )
        assert kubeconfig.relative_path == ".kube/config"

    def test_gcloud_credentials_file_has_correct_relative_path(self):
        creds = CLI_CREDENTIAL_MAP["gcloud"]
        gcloud_creds = next(
            c for c in creds
            if isinstance(c, CredentialFile)
            and c.env_var == "GOOGLE_APPLICATION_CREDENTIALS"
        )
        assert gcloud_creds.relative_path == ".config/gcloud/application_default_credentials.json"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd sdk/python && uv run pytest tests/unit/credentials/test_cli_map.py -v
```

Expected: FAIL — `CLI_CREDENTIAL_MAP` is currently an empty dict.

- [ ] **Step 3: Implement `cli_map.py`**

```python
# sdk/python/src/agentspan/agents/runtime/credentials/cli_map.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""CLI_CREDENTIAL_MAP — built-in registry mapping CLI tools to credential names.

``None`` entries (e.g. ``"terraform"``) indicate tools with no auto-mapping.
The ``Agent`` constructor raises ``ConfigurationError`` at definition time when
a ``None``-mapped tool is used without an explicit ``credentials=[...]`` list.

Enterprise module can extend this registry without modifying OSS code.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Union

from agentspan.agents.runtime.credentials.types import CredentialFile

# Each value is either:
#   - A list of str/CredentialFile  — auto-mapped credentials for this CLI tool
#   - None                          — no auto-mapping; raises ConfigurationError at Agent() time
CLI_CREDENTIAL_MAP: Dict[str, Optional[List[Union[str, CredentialFile]]]] = {
    "gh": ["GITHUB_TOKEN", "GH_TOKEN"],
    "git": ["GITHUB_TOKEN", "GH_TOKEN"],
    "aws": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"],
    "kubectl": [CredentialFile("KUBECONFIG", ".kube/config")],
    "helm": [CredentialFile("KUBECONFIG", ".kube/config")],
    "gcloud": [
        "GOOGLE_CLOUD_PROJECT",
        CredentialFile(
            "GOOGLE_APPLICATION_CREDENTIALS",
            ".config/gcloud/application_default_credentials.json",
        ),
    ],
    "az": [
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
        "AZURE_TENANT_ID",
        "AZURE_SUBSCRIPTION_ID",
    ],
    "docker": ["DOCKER_USERNAME", "DOCKER_PASSWORD"],
    "npm": ["NPM_TOKEN"],
    "cargo": ["CARGO_REGISTRY_TOKEN"],
    "terraform": None,  # No auto-mapping — raises ConfigurationError if no explicit credentials
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd sdk/python && uv run pytest tests/unit/credentials/test_cli_map.py -v
```

Expected: All 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/credentials/cli_map.py \
        sdk/python/tests/unit/credentials/test_cli_map.py
git commit -m "feat(credentials): add CLI_CREDENTIAL_MAP registry with 11 built-in mappings"
```

---

## Chunk 2: WorkerCredentialFetcher

### Task 3: WorkerCredentialFetcher

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/credentials/fetcher.py`
- Create: `sdk/python/tests/unit/credentials/test_fetcher.py`

The fetcher makes a synchronous HTTP POST to `/api/credentials/resolve`. It uses `httpx.Client` (sync, not async) because it is called from within a Conductor worker thread — not an async context. `httpx` is already a production dependency.

- [ ] **Step 1: Write the failing tests**

```python
# sdk/python/tests/unit/credentials/test_fetcher.py
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


def _make_fetcher(strict_mode: bool = False, server_url: str = "http://localhost:6767/api"):
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd sdk/python && uv run pytest tests/unit/credentials/test_fetcher.py -v
```

Expected: FAIL — stub `WorkerCredentialFetcher` has no `fetch` method.

- [ ] **Step 3: Implement `fetcher.py`**

```python
# sdk/python/src/agentspan/agents/runtime/credentials/fetcher.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""WorkerCredentialFetcher — resolves credentials for a Conductor task.

Resolution order:
  1. If execution token present: POST /api/credentials/resolve
  2. On 401: raise CredentialAuthError (no fallback)
  3. On 429: raise CredentialRateLimitError (no fallback)
  4. On 5xx + strict_mode: raise CredentialServiceError
  5. On 5xx + non-strict: env var fallback with warning
  6. Names missing from 200 response + non-strict: env var fallback
  7. Names missing from 200 response + strict: raise CredentialNotFoundError
  8. If token absent (local dev): env var fallback directly
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

import httpx

from agentspan.agents.runtime.credentials.types import (
    CredentialAuthError,
    CredentialNotFoundError,
    CredentialRateLimitError,
    CredentialServiceError,
)

logger = logging.getLogger("agentspan.agents.credentials.fetcher")


class WorkerCredentialFetcher:
    """Fetches credentials for a worker task execution.

    Args:
        server_url: Base URL of the agentspan server API (e.g. ``"http://localhost:6767/api"``).
        strict_mode: When ``True``, disables env var fallback entirely.
        api_key: Optional Bearer token or API key for the Authorization header.
    """

    def __init__(
        self,
        server_url: str = "http://localhost:6767/api",
        strict_mode: bool = False,
        api_key: Optional[str] = None,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._strict_mode = strict_mode
        self._api_key = api_key

    # ── Public API ──────────────────────────────────────────────────────

    def fetch(
        self,
        execution_token: Optional[str],
        names: List[str],
    ) -> Dict[str, str]:
        """Resolve credential values for *names* in this execution context.

        Args:
            execution_token: The ``__agentspan_ctx__`` token from Conductor task
                variables. ``None`` or empty string means local dev (no server).
            names: Logical credential names to resolve (e.g. ``["GITHUB_TOKEN"]``).

        Returns:
            Dict mapping credential name → plaintext value for names that were
            resolved. Names absent from the result were not found anywhere.

        Raises:
            CredentialAuthError: Token expired/revoked (401). Never retried.
            CredentialRateLimitError: Rate limit hit (429). Never retried.
            CredentialServiceError: Server 5xx in strict_mode.
            CredentialNotFoundError: Name(s) missing everywhere in strict_mode.
        """
        if not names:
            return {}

        if not execution_token:
            # Local dev / no server — go straight to env
            return self._env_fallback(names, require_all=self._strict_mode)

        return self._fetch_from_server(execution_token, names)

    # ── Private helpers ─────────────────────────────────────────────────

    def _fetch_from_server(
        self,
        execution_token: str,
        names: List[str],
    ) -> Dict[str, str]:
        url = f"{self._server_url}/credentials/resolve"
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
                response = client.post(
                    url,
                    json={"token": execution_token, "names": names},
                    headers=headers,
                )
        except httpx.RequestError as exc:
            # Network-level error — treat like 5xx
            logger.warning("Credential service unreachable: %s", exc)
            if self._strict_mode:
                raise CredentialServiceError(0, str(exc)) from exc
            logger.warning(
                "Falling back to env vars for %s (credential service unreachable)", names
            )
            return self._env_fallback(names, require_all=False)

        status = response.status_code

        if status == 401:
            raise CredentialAuthError(response.text)

        if status == 429:
            raise CredentialRateLimitError()

        if status >= 500:
            if self._strict_mode:
                raise CredentialServiceError(status, response.text)
            logger.warning(
                "Credential service returned %d; falling back to env vars for %s",
                status,
                names,
            )
            return self._env_fallback(names, require_all=False)

        # 200 OK
        resolved: Dict[str, str] = response.json()
        missing = [n for n in names if n not in resolved]
        if missing:
            if self._strict_mode:
                raise CredentialNotFoundError(missing)
            env_resolved = self._env_fallback(missing, require_all=False)
            resolved.update(env_resolved)
            still_missing = [n for n in missing if n not in env_resolved]
            if still_missing:
                logger.debug("Credentials not found anywhere: %s", still_missing)

        return resolved

    def _env_fallback(
        self,
        names: List[str],
        require_all: bool = False,
    ) -> Dict[str, str]:
        """Read *names* from ``os.environ``.

        Args:
            names: Names to look up.
            require_all: When ``True``, raise ``CredentialNotFoundError`` if
                any name is absent from the environment.
        """
        result = {n: os.environ[n] for n in names if n in os.environ}
        if require_all:
            missing = [n for n in names if n not in result]
            if missing:
                raise CredentialNotFoundError(missing)
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd sdk/python && uv run pytest tests/unit/credentials/test_fetcher.py -v
```

Expected: All 15 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/credentials/fetcher.py \
        sdk/python/tests/unit/credentials/test_fetcher.py
git commit -m "feat(credentials): add WorkerCredentialFetcher with HTTP error contract"
```

---

## Chunk 3: SubprocessIsolator and Credential Accessor

### Task 4: SubprocessIsolator

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/credentials/isolator.py`
- Create: `sdk/python/tests/unit/credentials/test_isolator.py`

The isolator runs a tool function in a fresh subprocess using `multiprocessing` with `start_method='spawn'`. Function serialization uses `cloudpickle`. The subprocess has a temp HOME directory and injected environment variables.

**Dependency note:** `cloudpickle` must be added to `pyproject.toml` before this task. Add it to the `dependencies` list: `"cloudpickle>=2.0"`.

- [ ] **Step 1: Add `cloudpickle` dependency**

Edit `sdk/python/pyproject.toml`, add `"cloudpickle>=2.0"` to the `dependencies` list:

```toml
dependencies = [
    "conductor-python>=1.3.6",
    "httpx>=0.24",
    "cloudpickle>=2.0",
]
```

Then sync:
```bash
cd sdk/python && uv sync
```

- [ ] **Step 2: Write the failing tests**

```python
# sdk/python/tests/unit/credentials/test_isolator.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for SubprocessIsolator."""

import os
import stat
import tempfile
from pathlib import Path

import pytest

from agentspan.agents.runtime.credentials.isolator import SubprocessIsolator
from agentspan.agents.runtime.credentials.types import CredentialFile


class TestSubprocessIsolatorBasic:
    """SubprocessIsolator runs functions in isolated subprocesses."""

    def test_runs_function_and_returns_result(self):
        isolator = SubprocessIsolator()

        def simple_fn(x: int, y: int) -> int:
            return x + y

        result = isolator.run(simple_fn, args=(), kwargs={"x": 3, "y": 4}, credentials={})
        assert result == 7

    def test_runs_function_with_positional_args(self):
        isolator = SubprocessIsolator()

        def multiply(a: int, b: int) -> int:
            return a * b

        result = isolator.run(multiply, args=(6, 7), kwargs={}, credentials={})
        assert result == 42

    def test_subprocess_has_isolated_home(self):
        """Subprocess HOME must differ from parent HOME."""
        isolator = SubprocessIsolator()
        parent_home = os.environ.get("HOME", "")

        def get_home() -> str:
            import os
            return os.environ["HOME"]

        subprocess_home = isolator.run(get_home, args=(), kwargs={}, credentials={})
        assert subprocess_home != parent_home
        assert "agentspan-" in subprocess_home

    def test_subprocess_home_deleted_after_run(self):
        """Temp HOME directory must be deleted synchronously after the subprocess exits."""
        isolator = SubprocessIsolator()
        captured = {}

        def capture_home() -> str:
            import os
            return os.environ["HOME"]

        tmp_home = isolator.run(capture_home, args=(), kwargs={}, credentials={})
        assert not os.path.exists(tmp_home), f"Temp HOME still exists: {tmp_home}"

    def test_exception_in_subprocess_propagates(self):
        isolator = SubprocessIsolator()

        def failing_fn() -> str:
            raise ValueError("boom from subprocess")

        with pytest.raises(Exception, match="boom from subprocess"):
            isolator.run(failing_fn, args=(), kwargs={}, credentials={})


class TestSubprocessIsolatorCredentials:
    """Credential injection into subprocess environment."""

    def test_string_credential_injected_as_env_var(self):
        isolator = SubprocessIsolator()

        def read_env(name: str) -> str:
            import os
            return os.environ.get(name, "NOT_FOUND")

        result = isolator.run(
            read_env,
            args=(),
            kwargs={"name": "GITHUB_TOKEN"},
            credentials={"GITHUB_TOKEN": "ghp_injected"},
        )
        assert result == "ghp_injected"

    def test_string_credential_not_in_parent_env(self):
        """Credential must NOT be set in the parent process environment."""
        isolator = SubprocessIsolator()

        def noop() -> str:
            return "ok"

        before = os.environ.get("GITHUB_TOKEN")
        isolator.run(noop, args=(), kwargs={}, credentials={"GITHUB_TOKEN": "ghp_injected"})
        after = os.environ.get("GITHUB_TOKEN")
        # Parent env should be unchanged
        assert before == after

    def test_file_credential_written_to_tmp_home(self):
        """CredentialFile content is written to {tmp_home}/{relative_path}."""
        isolator = SubprocessIsolator()
        kubeconfig_content = "apiVersion: v1\nclusters: []\n"
        cred_file = CredentialFile("KUBECONFIG", ".kube/config", content=kubeconfig_content)

        def read_kubeconfig() -> str:
            import os
            path = os.environ.get("KUBECONFIG", "")
            if not path:
                return "NO_KUBECONFIG_VAR"
            try:
                with open(path) as f:
                    return f.read()
            except FileNotFoundError:
                return "FILE_NOT_FOUND"

        result = isolator.run(
            read_kubeconfig,
            args=(),
            kwargs={},
            credentials={"KUBECONFIG": cred_file},
        )
        assert result == kubeconfig_content

    def test_file_credential_has_0600_permissions(self):
        """Credential files must be written with mode 0o600."""
        isolator = SubprocessIsolator()
        cred_file = CredentialFile("KUBECONFIG", ".kube/config", content="apiVersion: v1\n")

        def check_permissions() -> int:
            import os
            import stat
            path = os.environ.get("KUBECONFIG", "")
            if not path:
                return -1
            return stat.S_IMODE(os.stat(path).st_mode)

        file_mode = isolator.run(
            check_permissions,
            args=(),
            kwargs={},
            credentials={"KUBECONFIG": cred_file},
        )
        assert file_mode == 0o600, f"Expected 0600, got {oct(file_mode)}"

    def test_file_credential_env_var_points_to_correct_path(self):
        """KUBECONFIG env var must point to {tmp_home}/.kube/config."""
        isolator = SubprocessIsolator()
        cred_file = CredentialFile("KUBECONFIG", ".kube/config", content="")

        def get_kubeconfig_path() -> str:
            import os
            home = os.environ["HOME"]
            kubeconfig = os.environ.get("KUBECONFIG", "")
            return kubeconfig.startswith(home) and ".kube/config" in kubeconfig

        result = isolator.run(
            get_kubeconfig_path,
            args=(),
            kwargs={},
            credentials={"KUBECONFIG": cred_file},
        )
        assert result is True

    def test_multiple_credentials_all_injected(self):
        isolator = SubprocessIsolator()

        def read_env(names: list) -> dict:
            import os
            return {n: os.environ.get(n, "MISSING") for n in names}

        result = isolator.run(
            read_env,
            args=(),
            kwargs={"names": ["GITHUB_TOKEN", "AWS_ACCESS_KEY_ID"]},
            credentials={
                "GITHUB_TOKEN": "ghp_xxx",
                "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
            },
        )
        assert result["GITHUB_TOKEN"] == "ghp_xxx"
        assert result["AWS_ACCESS_KEY_ID"] == "AKIAIOSFODNN7EXAMPLE"

    def test_credential_files_deleted_after_run(self):
        """Credential files on disk must be gone after the subprocess exits."""
        isolator = SubprocessIsolator()
        cred_file = CredentialFile("KUBECONFIG", ".kube/config", content="apiVersion: v1\n")
        captured_path = {}

        def capture_kubeconfig_path() -> str:
            import os
            return os.environ.get("KUBECONFIG", "")

        kubeconfig_path = isolator.run(
            capture_kubeconfig_path,
            args=(),
            kwargs={},
            credentials={"KUBECONFIG": cred_file},
        )
        assert not os.path.exists(kubeconfig_path), (
            f"Credential file still exists after subprocess exit: {kubeconfig_path}"
        )
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd sdk/python && uv run pytest tests/unit/credentials/test_isolator.py -v
```

Expected: FAIL — stub `SubprocessIsolator` has no `run` method.

- [ ] **Step 4: Implement `isolator.py`**

```python
# sdk/python/src/agentspan/agents/runtime/credentials/isolator.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""SubprocessIsolator — runs tool functions in credential-isolated subprocesses.

Security model:
  - Each tool execution gets a fresh temporary HOME directory.
  - String credentials are injected as environment variables.
  - File credentials are written to {tmp_home}/{relative_path} with 0o600 permissions.
  - The env var for file credentials points to the absolute path of the written file.
  - The subprocess exits; the temp HOME (and all credential files) are deleted
    synchronously by the parent via TemporaryDirectory context manager.
  - Parent process environment is never modified.

Implementation: uses ``multiprocessing`` with ``start_method='spawn'`` for clean
isolation (no inherited file descriptors or open resources). ``cloudpickle`` is
used to serialize the function and arguments across the process boundary.
"""

from __future__ import annotations

import multiprocessing
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, Union

from agentspan.agents.runtime.credentials.types import CredentialFile


def _subprocess_entry(
    pickled_fn_and_args: bytes,
    result_queue: "multiprocessing.Queue[Any]",
) -> None:
    """Entry point that runs inside the spawned subprocess.

    Receives a cloudpickle-serialized ``(fn, args, kwargs)`` tuple,
    calls ``fn(*args, **kwargs)``, and puts the result (or exception)
    in *result_queue*.
    """
    import cloudpickle  # noqa: PLC0415

    try:
        fn, args, kwargs = cloudpickle.loads(pickled_fn_and_args)
        result = fn(*args, **kwargs)
        result_queue.put(("ok", result))
    except BaseException as exc:  # noqa: BLE001
        result_queue.put(("error", exc))


class SubprocessIsolator:
    """Runs a callable in a subprocess with an isolated HOME and injected credentials.

    Args:
        timeout: Maximum seconds to wait for the subprocess to complete.
            ``None`` means wait forever. Defaults to ``None`` (inherits task timeout).
    """

    def __init__(self, timeout: Optional[int] = None) -> None:
        self._timeout = timeout

    def run(
        self,
        fn: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        credentials: Dict[str, Union[str, CredentialFile]],
    ) -> Any:
        """Execute *fn* in a subprocess with an isolated credential environment.

        Args:
            fn: The callable to execute.
            args: Positional arguments for *fn*.
            kwargs: Keyword arguments for *fn*.
            credentials: Dict mapping credential name → string value or
                ``CredentialFile``. Injected into the subprocess environment only.

        Returns:
            The return value of ``fn(*args, **kwargs)``.

        Raises:
            Any exception raised by *fn* is re-raised in the caller's process.
            ``TimeoutError`` if the subprocess exceeds *timeout* seconds.
        """
        with tempfile.TemporaryDirectory(prefix="agentspan-") as tmp_home:
            env = self._build_env(tmp_home, credentials)
            return self._run_in_subprocess(fn, args, kwargs, env, tmp_home)

    # ── Private helpers ──────────────────────────────────────────────────

    def _build_env(
        self,
        tmp_home: str,
        credentials: Dict[str, Union[str, CredentialFile]],
    ) -> Dict[str, str]:
        """Build the subprocess environment with HOME overridden and credentials injected."""
        env = os.environ.copy()
        env["HOME"] = tmp_home

        for _name, value in credentials.items():
            if isinstance(value, str):
                # String type: inject directly as env var using the key name
                env[_name] = value
            elif isinstance(value, CredentialFile):
                # File type: write to {tmp_home}/{relative_path}, set env var to path
                abs_path = os.path.join(tmp_home, value.relative_path)
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                content = value.content or ""
                Path(abs_path).write_text(content)
                os.chmod(abs_path, 0o600)
                env[value.env_var] = abs_path

        return env

    def _run_in_subprocess(
        self,
        fn: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        env: Dict[str, str],
        tmp_home: str,
    ) -> Any:
        """Serialize fn+args with cloudpickle, spawn a subprocess, return result."""
        import cloudpickle  # noqa: PLC0415

        pickled = cloudpickle.dumps((fn, args, kwargs))

        ctx = multiprocessing.get_context("spawn")
        result_queue: multiprocessing.Queue = ctx.Queue()

        proc = ctx.Process(
            target=_subprocess_entry,
            args=(pickled, result_queue),
        )
        # Propagate the credential env to the spawned process
        # We do this by temporarily modifying the env for the spawn call.
        # multiprocessing spawn passes os.environ to the child; we override
        # the child's environment by writing a small bootstrap that sets env vars.
        #
        # Simpler approach: write env to a temp file the subprocess reads, OR
        # use the os.environment approach below (safe because the TemporaryDirectory
        # context ensures cleanup before we exit _run_in_subprocess).
        #
        # We save/restore os.environ in the parent so other threads are not affected.
        saved_env = os.environ.copy()
        try:
            os.environ.clear()
            os.environ.update(env)
            proc.start()
        finally:
            os.environ.clear()
            os.environ.update(saved_env)

        proc.join(timeout=self._timeout)

        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
            raise TimeoutError(
                f"Subprocess timed out after {self._timeout}s"
            )

        if not result_queue.empty():
            status, value = result_queue.get_nowait()
            if status == "ok":
                return value
            raise value  # Re-raise the exception from the subprocess

        raise RuntimeError(
            f"Subprocess exited with code {proc.exitcode} and produced no result"
        )
```

**Note on env injection approach:** The `os.environ.clear()/update()` approach is thread-unsafe if other threads are running concurrent tasks. A safer production approach (documented here for the implementer) is to use a `_subprocess_bootstrap` that reads env vars from a cloudpickle-serialized dict passed as an argument, rather than relying on `os.environ` inheritance from the spawn. The tests are single-threaded so this will pass; a follow-up task (Task 11) addresses thread safety.

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd sdk/python && uv run pytest tests/unit/credentials/test_isolator.py -v
```

Expected: All 11 tests PASS. Note: spawn-based tests take a few seconds due to subprocess startup overhead.

- [ ] **Step 6: Commit**

```bash
git add sdk/python/pyproject.toml \
        sdk/python/src/agentspan/agents/runtime/credentials/isolator.py \
        sdk/python/tests/unit/credentials/test_isolator.py
git commit -m "feat(credentials): add SubprocessIsolator with temp HOME and 0600 file permissions"
```

---

### Task 5: Thread-Safe SubprocessIsolator Environment Injection

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/credentials/isolator.py`
- Modify: `sdk/python/tests/unit/credentials/test_isolator.py`

The Task 4 implementation modifies `os.environ` globally for subprocess spawn. This is unsafe when multiple Conductor worker threads run concurrently. Fix by passing the env dict as a serialized argument to the subprocess entry point.

- [ ] **Step 1: Add thread-safety test**

Append to `sdk/python/tests/unit/credentials/test_isolator.py`:

```python
class TestSubprocessIsolatorThreadSafety:
    """Env injection must not corrupt the parent process environment."""

    def test_parent_env_unchanged_after_run(self):
        """os.environ in parent must be identical before and after run()."""
        isolator = SubprocessIsolator()
        env_before = dict(os.environ)

        def simple() -> str:
            return "done"

        isolator.run(
            simple,
            args=(),
            kwargs={},
            credentials={"GITHUB_TOKEN": "ghp_test", "AWS_SECRET": "secret"},
        )

        env_after = dict(os.environ)
        assert env_before == env_after, (
            "Parent os.environ was modified by SubprocessIsolator.run()"
        )

    def test_injected_credentials_not_visible_in_parent(self):
        """Credentials injected into subprocess must NOT appear in parent env."""
        isolator = SubprocessIsolator()
        secret_key = "AGENTSPAN_TEST_SECRET_XYZ_12345"
        assert secret_key not in os.environ, "Test pollution: key already in env"

        def simple() -> str:
            return "done"

        isolator.run(
            simple,
            args=(),
            kwargs={},
            credentials={secret_key: "super-secret-value"},
        )

        assert secret_key not in os.environ
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd sdk/python && uv run pytest tests/unit/credentials/test_isolator.py::TestSubprocessIsolatorThreadSafety -v
```

Expected: FAIL — current implementation modifies parent env temporarily, which may cause the test to detect the contamination timing window.

- [ ] **Step 3: Rewrite `isolator.py` with safe env passing**

Replace `_subprocess_entry` and `_run_in_subprocess` with an approach that passes the env dict inside the cloudpickle payload, sets it inside the child before calling the function, and never touches the parent's `os.environ`:

```python
# sdk/python/src/agentspan/agents/runtime/credentials/isolator.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""SubprocessIsolator — runs tool functions in credential-isolated subprocesses.

Security model:
  - Each tool execution gets a fresh temporary HOME directory.
  - String credentials are injected as environment variables (subprocess only).
  - File credentials are written to {tmp_home}/{relative_path} with 0o600 perms.
  - The env var for file credentials points to the absolute path.
  - Temp HOME and all credential files are deleted synchronously after the
    subprocess exits (TemporaryDirectory context manager).
  - Parent process environment is NEVER modified — env dict is serialized
    inside the cloudpickle payload and applied inside the child process.

Implementation uses multiprocessing spawn + cloudpickle for clean isolation.
"""

from __future__ import annotations

import multiprocessing
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, Union

from agentspan.agents.runtime.credentials.types import CredentialFile


def _subprocess_entry(pickled_payload: bytes, result_queue: Any) -> None:
    """Subprocess entry point.

    The payload is a cloudpickle-serialized ``(env, fn, args, kwargs)`` tuple.
    We apply *env* to the subprocess's ``os.environ`` first, then call the function.
    """
    import cloudpickle  # noqa: PLC0415

    try:
        env, fn, args, kwargs = cloudpickle.loads(pickled_payload)
        # Apply the isolated environment inside the child process only.
        os.environ.clear()
        os.environ.update(env)
        result = fn(*args, **kwargs)
        result_queue.put(("ok", result))
    except BaseException as exc:  # noqa: BLE001
        result_queue.put(("error", exc))


class SubprocessIsolator:
    """Runs a callable in a subprocess with an isolated HOME and injected credentials.

    The parent process environment is never modified. All credential material
    lives only in the spawned child process and the temp directory, which is
    deleted synchronously after the child exits.

    Args:
        timeout: Maximum seconds to wait for the subprocess. ``None`` = no limit.
    """

    def __init__(self, timeout: Optional[int] = None) -> None:
        self._timeout = timeout

    def run(
        self,
        fn: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        credentials: Dict[str, Union[str, CredentialFile]],
    ) -> Any:
        """Execute *fn* in a subprocess with an isolated credential environment.

        Args:
            fn: The callable to execute.
            args: Positional arguments for *fn*.
            kwargs: Keyword arguments for *fn*.
            credentials: Credential name → string value or ``CredentialFile``.

        Returns:
            Return value of ``fn(*args, **kwargs)``.

        Raises:
            Any exception raised by *fn* (re-raised in caller's process).
            ``TimeoutError`` if the subprocess exceeds *timeout* seconds.
        """
        with tempfile.TemporaryDirectory(prefix="agentspan-") as tmp_home:
            env = self._build_env(tmp_home, credentials)
            return self._run_in_subprocess(fn, args, kwargs, env)

    # ── Private helpers ──────────────────────────────────────────────────

    def _build_env(
        self,
        tmp_home: str,
        credentials: Dict[str, Union[str, CredentialFile]],
    ) -> Dict[str, str]:
        """Build subprocess environment: parent env + HOME override + credentials."""
        env = os.environ.copy()
        env["HOME"] = tmp_home

        for _name, value in credentials.items():
            if isinstance(value, str):
                env[_name] = value
            elif isinstance(value, CredentialFile):
                abs_path = os.path.join(tmp_home, value.relative_path)
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                content = value.content or ""
                Path(abs_path).write_text(content)
                os.chmod(abs_path, 0o600)
                env[value.env_var] = abs_path

        return env

    def _run_in_subprocess(
        self,
        fn: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        env: Dict[str, str],
    ) -> Any:
        """Serialize (env, fn, args, kwargs) with cloudpickle and spawn a process."""
        import cloudpickle  # noqa: PLC0415

        # Env dict is part of the payload — parent os.environ is never touched.
        pickled = cloudpickle.dumps((env, fn, args, kwargs))

        ctx = multiprocessing.get_context("spawn")
        result_queue: multiprocessing.Queue = ctx.Queue()
        proc = ctx.Process(target=_subprocess_entry, args=(pickled, result_queue))
        proc.start()
        proc.join(timeout=self._timeout)

        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
            raise TimeoutError(f"Subprocess timed out after {self._timeout}s")

        if not result_queue.empty():
            status, value = result_queue.get_nowait()
            if status == "ok":
                return value
            raise value

        raise RuntimeError(
            f"Subprocess exited with code {proc.exitcode} and produced no result"
        )
```

- [ ] **Step 4: Run all isolator tests**

```bash
cd sdk/python && uv run pytest tests/unit/credentials/test_isolator.py -v
```

Expected: All tests PASS (including new thread-safety tests).

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/credentials/isolator.py \
        sdk/python/tests/unit/credentials/test_isolator.py
git commit -m "fix(credentials): pass env dict in cloudpickle payload to avoid parent env mutation"
```

---

### Task 6: `get_credential()` Accessor

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/credentials/accessor.py`
- Create: `sdk/python/tests/unit/credentials/test_accessor.py`

`get_credential(name)` reads from a `contextvars.ContextVar` that the worker framework sets before executing a non-isolated tool. This is only used for `isolated=False` tools.

- [ ] **Step 1: Write the failing tests**

```python
# sdk/python/tests/unit/credentials/test_accessor.py
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd sdk/python && uv run pytest tests/unit/credentials/test_accessor.py -v
```

Expected: FAIL — stub accessor has no `set_credential_context` or `clear_credential_context`.

- [ ] **Step 3: Implement `accessor.py`**

```python
# sdk/python/src/agentspan/agents/runtime/credentials/accessor.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""get_credential() accessor for isolated=False tools.

The worker framework calls ``set_credential_context(credentials_dict)`` before
executing a non-isolated tool, making credentials available via
``get_credential(name)`` inside that tool's call frame.

Uses ``contextvars.ContextVar`` so each thread (Conductor worker thread) has its
own independent credential context. No cross-task credential leakage.

Usage in non-isolated tools::

    @tool(isolated=False, credentials=["OPENAI_API_KEY"])
    def call_openai(prompt: str) -> str:
        key = get_credential("OPENAI_API_KEY")
        ...

The framework sets the context before calling the function and clears it after.
"""

from __future__ import annotations

import contextvars
from typing import Dict, Optional

from agentspan.agents.runtime.credentials.types import CredentialNotFoundError

# Thread-local (via contextvars) credential map set by the worker framework.
# Value is None when no context has been established.
_credential_context: contextvars.ContextVar[Optional[Dict[str, str]]] = (
    contextvars.ContextVar("_credential_context", default=None)
)


def set_credential_context(credentials: Dict[str, str]) -> None:
    """Set the credential context for the current execution context (thread/task).

    Called by the worker framework (``_dispatch.py``) before executing a
    ``isolated=False`` tool.

    Args:
        credentials: Dict mapping credential name → plaintext value.
    """
    _credential_context.set(credentials)


def clear_credential_context() -> None:
    """Clear the credential context for the current execution context.

    Called by the worker framework after the tool execution completes.
    """
    _credential_context.set(None)


def get_credential(name: str) -> str:
    """Read a credential value from the current execution context.

    Only usable inside ``@tool(isolated=False, credentials=[...])`` functions.
    The worker framework populates the context before your tool runs.

    Args:
        name: The logical credential name (e.g. ``"OPENAI_API_KEY"``).

    Returns:
        The plaintext credential value.

    Raises:
        CredentialNotFoundError: If the credential is not in the current context,
            or if called outside of a credential-aware tool execution.

    Example::

        @tool(isolated=False, credentials=["OPENAI_API_KEY"])
        def call_openai(prompt: str) -> str:
            key = get_credential("OPENAI_API_KEY")
            client = openai.OpenAI(api_key=key)
            ...
    """
    ctx = _credential_context.get()
    if ctx is None:
        raise CredentialNotFoundError([name])
    if name not in ctx:
        raise CredentialNotFoundError([name])
    return ctx[name]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd sdk/python && uv run pytest tests/unit/credentials/test_accessor.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/credentials/accessor.py \
        sdk/python/tests/unit/credentials/test_accessor.py
git commit -m "feat(credentials): add get_credential() accessor backed by contextvars"
```

---

## Chunk 4: @tool and ToolDef Changes

### Task 7: Add `isolated` and `credentials` to `@tool` and `ToolDef`

**Files:**
- Modify: `sdk/python/src/agentspan/agents/tool.py`
- Modify: `sdk/python/tests/unit/test_tool.py`

`ToolDef` gets two new fields: `isolated: bool = True` and `credentials: list = []`. The `@tool` decorator gains matching parameters. These are purely declarative at this stage — they are read by `_dispatch.py` in Task 9.

- [ ] **Step 1: Write the failing tests**

Append a new class to `sdk/python/tests/unit/test_tool.py`:

```python
class TestToolCredentialParams:
    """@tool decorator: isolated and credentials params."""

    def test_isolated_defaults_to_true(self):
        @tool
        def my_tool(x: str) -> str:
            """A tool."""
            return x

        assert my_tool._tool_def.isolated is True

    def test_isolated_false(self):
        @tool(isolated=False)
        def my_tool(x: str) -> str:
            """A tool."""
            return x

        assert my_tool._tool_def.isolated is False

    def test_credentials_defaults_to_empty_list(self):
        @tool
        def my_tool(x: str) -> str:
            """A tool."""
            return x

        assert my_tool._tool_def.credentials == []

    def test_credentials_string_list(self):
        @tool(credentials=["GITHUB_TOKEN", "GH_TOKEN"])
        def my_tool(x: str) -> str:
            """A tool."""
            return x

        assert "GITHUB_TOKEN" in my_tool._tool_def.credentials
        assert "GH_TOKEN" in my_tool._tool_def.credentials

    def test_credentials_with_credential_file(self):
        from agentspan.agents.runtime.credentials.types import CredentialFile

        cf = CredentialFile("KUBECONFIG", ".kube/config")

        @tool(credentials=["GITHUB_TOKEN", cf])
        def my_tool(x: str) -> str:
            """A tool."""
            return x

        creds = my_tool._tool_def.credentials
        assert "GITHUB_TOKEN" in creds
        assert cf in creds

    def test_isolated_false_with_credentials(self):
        @tool(isolated=False, credentials=["OPENAI_API_KEY"])
        def my_tool(x: str) -> str:
            """A tool."""
            return x

        assert my_tool._tool_def.isolated is False
        assert "OPENAI_API_KEY" in my_tool._tool_def.credentials

    def test_existing_params_still_work_alongside_new_params(self):
        @tool(name="custom_name", approval_required=True, isolated=False, credentials=["KEY"])
        def my_tool(x: str) -> str:
            """A tool."""
            return x

        td = my_tool._tool_def
        assert td.name == "custom_name"
        assert td.approval_required is True
        assert td.isolated is False
        assert "KEY" in td.credentials
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd sdk/python && uv run pytest tests/unit/test_tool.py::TestToolCredentialParams -v
```

Expected: FAIL — `ToolDef` has no `isolated` or `credentials` fields, `@tool` doesn't accept them.

- [ ] **Step 3: Modify `tool.py`**

In `ToolDef` dataclass (after line 79, before the closing of the class), add two new fields. The full updated `ToolDef` class body:

```python
@dataclass
class ToolDef:
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    func: Optional[Callable[..., Any]] = field(default=None, repr=False)
    approval_required: bool = False
    timeout_seconds: Optional[int] = None
    tool_type: str = "worker"
    config: Dict[str, Any] = field(default_factory=dict)
    guardrails: List[Any] = field(default_factory=list)
    isolated: bool = True
    credentials: List[Any] = field(default_factory=list)
```

Update the two `@overload` signatures and the actual `tool()` function signature to add the new parameters. The updated `tool()` function:

```python
@overload
def tool(func: F) -> F: ...


@overload
def tool(
    *,
    name: Optional[str] = None,
    external: bool = False,
    approval_required: bool = False,
    timeout_seconds: Optional[int] = None,
    guardrails: Optional[List[Any]] = None,
    isolated: bool = True,
    credentials: Optional[List[Any]] = None,
) -> Callable[[F], F]: ...


def tool(
    func: Optional[F] = None,
    *,
    name: Optional[str] = None,
    external: bool = False,
    approval_required: bool = False,
    timeout_seconds: Optional[int] = None,
    guardrails: Optional[List[Any]] = None,
    isolated: bool = True,
    credentials: Optional[List[Any]] = None,
) -> Any:
    """Register a Python function as a Conductor agent tool.

    ... (existing docstring, add below) ...

    Credential params:
        isolated: When ``True`` (default), the tool runs in a subprocess with
            a fresh HOME directory and credentials injected as env vars.
            Set to ``False`` for tools that call ``get_credential()`` directly
            (avoids subprocess overhead for pure Python tools).
        credentials: List of credential names (str) or
            :class:`~agentspan.agents.runtime.credentials.CredentialFile` instances
            that this tool requires. Fetched from the credential service (or
            env var fallback) before execution.
    """

    def _wrap(fn: F) -> F:
        tool_name = name or fn.__name__
        description = inspect.getdoc(fn) or ""

        from agentspan.agents._internal.schema_utils import schema_from_function

        schemas = schema_from_function(fn)

        tool_def = ToolDef(
            name=tool_name,
            description=description,
            input_schema=schemas.get("input", {}),
            output_schema=schemas.get("output", {}),
            func=None if external else fn,
            approval_required=approval_required,
            timeout_seconds=timeout_seconds,
            tool_type="worker",
            guardrails=list(guardrails) if guardrails else [],
            isolated=isolated,
            credentials=list(credentials) if credentials else [],
        )

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        wrapper._tool_def = tool_def  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    if func is not None:
        return _wrap(func)
    return _wrap
```

- [ ] **Step 4: Run all tool tests**

```bash
cd sdk/python && uv run pytest tests/unit/test_tool.py -v
```

Expected: All tests PASS including the new `TestToolCredentialParams` class.

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/tool.py sdk/python/tests/unit/test_tool.py
git commit -m "feat(credentials): add isolated and credentials params to @tool decorator and ToolDef"
```

---

## Chunk 5: AgentConfig and Agent Changes

### Task 8: AgentConfig — `credential_strict_mode` and first-class `api_key`

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/config.py`
- Modify: `sdk/python/tests/unit/test_config_env.py`

`AgentConfig` already has `api_key` as a property alias for `auth_key`. The spec calls for a first-class `api_key: str | None = None` field preferred over `auth_key`. We add it as a new field alongside `auth_key` for backward compat, and add `credential_strict_mode: bool = False`.

- [ ] **Step 1: Write the failing tests**

Append to `sdk/python/tests/unit/test_config_env.py`:

```python
class TestAgentConfigCredentialFields:
    """credential_strict_mode and api_key fields."""

    def test_credential_strict_mode_defaults_false(self):
        from agentspan.agents.runtime.config import AgentConfig
        config = AgentConfig()
        assert config.credential_strict_mode is False

    def test_credential_strict_mode_can_be_set(self):
        from agentspan.agents.runtime.config import AgentConfig
        config = AgentConfig(credential_strict_mode=True)
        assert config.credential_strict_mode is True

    def test_credential_strict_mode_from_env_true(self):
        import os
        from unittest import mock
        from agentspan.agents.runtime.config import AgentConfig
        with mock.patch.dict(os.environ, {"AGENTSPAN_CREDENTIAL_STRICT_MODE": "true"}):
            config = AgentConfig.from_env()
        assert config.credential_strict_mode is True

    def test_credential_strict_mode_from_env_false(self):
        import os
        from unittest import mock
        from agentspan.agents.runtime.config import AgentConfig
        with mock.patch.dict(os.environ, {"AGENTSPAN_CREDENTIAL_STRICT_MODE": "false"}):
            config = AgentConfig.from_env()
        assert config.credential_strict_mode is False

    def test_api_key_field_defaults_none(self):
        from agentspan.agents.runtime.config import AgentConfig
        config = AgentConfig()
        # api_key field (new) takes precedence; auth_key kept for backward compat
        assert config.api_key is None

    def test_api_key_field_can_be_set(self):
        from agentspan.agents.runtime.config import AgentConfig
        config = AgentConfig(api_key="asp_my_key")
        assert config.api_key == "asp_my_key"

    def test_api_key_from_env(self):
        import os
        from unittest import mock
        from agentspan.agents.runtime.config import AgentConfig
        with mock.patch.dict(os.environ, {"AGENTSPAN_API_KEY": "asp_env_key"}):
            config = AgentConfig.from_env()
        assert config.api_key == "asp_env_key"

    def test_auth_key_backward_compat_still_works(self):
        """auth_key must still be accepted for backward compat."""
        from agentspan.agents.runtime.config import AgentConfig
        config = AgentConfig(auth_key="old_key")
        assert config.auth_key == "old_key"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd sdk/python && uv run pytest tests/unit/test_config_env.py::TestAgentConfigCredentialFields -v
```

Expected: FAIL — `credential_strict_mode` and `api_key` field don't exist yet.

- [ ] **Step 3: Modify `config.py`**

Add `api_key` as a true field (not property) and `credential_strict_mode`. Note: `AgentConfig` already has a `api_key` property — remove it (replace with a field). Keep `auth_key` and `auth_secret` for backward compat.

The updated `AgentConfig` dataclass:

```python
@dataclass
class AgentConfig:
    """Configuration for the agents runtime.

    Attributes:
        server_url: Agentspan server API URL.
        api_key: Bearer token or static API key for the Authorization header.
            Preferred over auth_key/auth_secret for new deployments.
        auth_key: Auth key (kept for backward compatibility).
        auth_secret: Auth secret (kept for backward compatibility).
        worker_poll_interval_ms: Worker polling interval in milliseconds.
        worker_thread_count: Number of threads per worker.
        auto_start_workers: Whether to auto-start worker processes.
        daemon_workers: Whether worker processes are daemon (killed on exit).
        auto_start_server: Whether to auto-start the local server process.
        auto_register_integrations: Auto-create LLM integrations on startup.
        credential_strict_mode: When ``True``, disables env var fallback for
            credential resolution. Required credentials must come from the
            credential service.
        log_level: Logging level for the agentspan logger.
    """

    server_url: str = "http://localhost:6767/api"
    api_key: Optional[str] = None
    auth_key: Optional[str] = None
    auth_secret: Optional[str] = None
    llm_retry_count: int = 3
    worker_poll_interval_ms: int = 100
    worker_thread_count: int = 1
    auto_start_workers: bool = True
    auto_start_server: bool = True
    daemon_workers: bool = True
    auto_register_integrations: bool = False
    streaming_enabled: bool = True
    credential_strict_mode: bool = False
    log_level: str = "INFO"

    def __post_init__(self):
        """Normalise server_url: auto-append /api if missing."""
        if self.server_url:
            stripped = self.server_url.rstrip("/")
            if not stripped.endswith("/api"):
                logger.info(
                    "server_url %r does not end with '/api' — appending automatically.",
                    self.server_url,
                )
                self.server_url = stripped + "/api"
            else:
                self.server_url = stripped

    @classmethod
    def from_env(cls) -> "AgentConfig":
        """Create an ``AgentConfig`` by reading ``AGENTSPAN_*`` env vars."""
        log_level = _env("AGENTSPAN_LOG_LEVEL", "INFO")
        if isinstance(log_level, str) and log_level.strip() == "":
            log_level = "INFO"
        return cls(
            server_url=_env("AGENTSPAN_SERVER_URL", "http://localhost:6767/api"),
            api_key=_env("AGENTSPAN_API_KEY"),
            auth_key=_env("AGENTSPAN_AUTH_KEY"),
            auth_secret=_env("AGENTSPAN_AUTH_SECRET"),
            llm_retry_count=_env_int("AGENTSPAN_LLM_RETRY_COUNT", 3),
            worker_poll_interval_ms=_env_int("AGENTSPAN_WORKER_POLL_INTERVAL", 100),
            worker_thread_count=_env_int("AGENTSPAN_WORKER_THREADS", 1),
            auto_start_workers=_env_bool("AGENTSPAN_AUTO_START_WORKERS", True),
            auto_start_server=_env_bool("AGENTSPAN_AUTO_START_SERVER", True),
            daemon_workers=_env_bool("AGENTSPAN_DAEMON_WORKERS", True),
            auto_register_integrations=_env_bool("AGENTSPAN_INTEGRATIONS_AUTO_REGISTER", False),
            streaming_enabled=_env_bool("AGENTSPAN_STREAMING_ENABLED", True),
            credential_strict_mode=_env_bool("AGENTSPAN_CREDENTIAL_STRICT_MODE", False),
            log_level=log_level,
        )

    @property
    def api_secret(self) -> Optional[str]:
        """Alias for :attr:`auth_secret` (industry-standard naming)."""
        return self.auth_secret

    def to_conductor_configuration(self) -> "Configuration":
        """Convert to a ``conductor-python`` :class:`Configuration` object."""
        from conductor.client.configuration.configuration import Configuration

        config = Configuration(server_api_url=self.server_url)
        # Prefer api_key; fall back to auth_key for backward compat
        effective_key = self.api_key or self.auth_key
        if effective_key:
            from conductor.client.configuration.settings.authentication_settings import (
                AuthenticationSettings,
            )
            config.authentication_settings = AuthenticationSettings(
                key_id=effective_key,
                key_secret=self.auth_secret or "",
            )
        return config
```

Note: The old `api_key` property is replaced by a real field. The old `api_secret` property stays since it aliases `auth_secret` which is still a field. The existing test `test_config_env.py` has a test for `api_key` as a property — update that test to use the new field behavior if it exists.

- [ ] **Step 4: Check existing tests still pass**

```bash
cd sdk/python && uv run pytest tests/unit/test_config_env.py -v
```

Expected: All tests PASS. If any existing test broke because it tested `api_key` as a property of `auth_key`, update that test: the new field is independent.

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/config.py \
        sdk/python/tests/unit/test_config_env.py
git commit -m "feat(credentials): add credential_strict_mode and first-class api_key to AgentConfig"
```

---

### Task 9: Agent — `credentials` param + terraform ConfigurationError

**Files:**
- Modify: `sdk/python/src/agentspan/agents/agent.py`
- Modify: `sdk/python/tests/unit/test_agent.py`

`Agent` gains a `credentials` param (explicit list). When `cli_allowed_commands` includes `"terraform"` and no explicit `credentials` are provided, raise `ConfigurationError` at `Agent()` definition time. Auto-map other `cli_allowed_commands` entries via `CLI_CREDENTIAL_MAP` to populate `self.credentials` if none explicitly provided.

- [ ] **Step 1: Write the failing tests**

Append a new class to `sdk/python/tests/unit/test_agent.py` (check what already exists; add to the file):

```python
class TestAgentCredentials:
    """Agent credentials param and CLI auto-mapping."""

    def test_credentials_defaults_to_empty_list(self):
        from agentspan.agents.agent import Agent
        a = Agent(name="test_agent", model="openai/gpt-4o")
        assert a.credentials == []

    def test_explicit_credentials_stored(self):
        from agentspan.agents.agent import Agent
        a = Agent(
            name="test_agent",
            model="openai/gpt-4o",
            credentials=["GITHUB_TOKEN", "OPENAI_API_KEY"],
        )
        assert "GITHUB_TOKEN" in a.credentials
        assert "OPENAI_API_KEY" in a.credentials

    def test_cli_allowed_commands_automapped_gh(self):
        """gh → GITHUB_TOKEN, GH_TOKEN auto-mapped when no explicit credentials."""
        from agentspan.agents.agent import Agent
        a = Agent(
            name="test_agent",
            model="openai/gpt-4o",
            cli_commands=True,
            cli_allowed_commands=["gh", "git"],
        )
        assert "GITHUB_TOKEN" in a.credentials
        assert "GH_TOKEN" in a.credentials

    def test_cli_allowed_commands_automapped_aws(self):
        from agentspan.agents.agent import Agent
        a = Agent(
            name="test_agent",
            model="openai/gpt-4o",
            cli_commands=True,
            cli_allowed_commands=["aws"],
        )
        assert "AWS_ACCESS_KEY_ID" in a.credentials
        assert "AWS_SECRET_ACCESS_KEY" in a.credentials

    def test_cli_allowed_commands_no_dup_in_credentials(self):
        """gh and git both map to GITHUB_TOKEN — deduplication required."""
        from agentspan.agents.agent import Agent
        a = Agent(
            name="test_agent",
            model="openai/gpt-4o",
            cli_commands=True,
            cli_allowed_commands=["gh", "git"],
        )
        # GITHUB_TOKEN should appear only once
        assert a.credentials.count("GITHUB_TOKEN") == 1

    def test_terraform_without_credentials_raises_configuration_error(self):
        """terraform in cli_allowed_commands without explicit credentials is an error."""
        from agentspan.agents.agent import Agent
        with pytest.raises(ConfigurationError, match="terraform"):
            Agent(
                name="test_agent",
                model="openai/gpt-4o",
                cli_commands=True,
                cli_allowed_commands=["terraform"],
            )

    def test_terraform_with_explicit_credentials_does_not_raise(self):
        """terraform is fine when explicit credentials are declared."""
        from agentspan.agents.agent import Agent
        # Should not raise
        a = Agent(
            name="test_agent",
            model="openai/gpt-4o",
            cli_commands=True,
            cli_allowed_commands=["terraform", "aws"],
            credentials=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "TF_VAR_db_password"],
        )
        assert "TF_VAR_db_password" in a.credentials

    def test_commands_not_in_map_are_ignored_gracefully(self):
        """CLI commands like mktemp, rm not in map produce no credentials (no error)."""
        from agentspan.agents.agent import Agent
        a = Agent(
            name="test_agent",
            model="openai/gpt-4o",
            cli_commands=True,
            cli_allowed_commands=["mktemp", "rm"],
        )
        # Neither command has credentials — empty list is fine
        assert a.credentials == []

    def test_explicit_credentials_override_automapping(self):
        """When explicit credentials provided, auto-mapping is not applied."""
        from agentspan.agents.agent import Agent
        a = Agent(
            name="test_agent",
            model="openai/gpt-4o",
            cli_commands=True,
            cli_allowed_commands=["gh"],
            credentials=["MY_CUSTOM_TOKEN"],
        )
        # Only explicit credentials, no auto-mapped ones added on top
        assert a.credentials == ["MY_CUSTOM_TOKEN"]
        assert "GITHUB_TOKEN" not in a.credentials
```

Add the needed import at the top of `test_agent.py`:
```python
import pytest
from agentspan.agents.agent import ConfigurationError  # (new exception we will add)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd sdk/python && uv run pytest tests/unit/test_agent.py::TestAgentCredentials -v
```

Expected: FAIL — `Agent` has no `credentials` param and no `ConfigurationError`.

- [ ] **Step 3: Add `ConfigurationError` to `agent.py` and modify `Agent`**

At the top of `agent.py`, add:

```python
class ConfigurationError(ValueError):
    """Raised at agent definition time for invalid configuration.

    Example: using ``terraform`` in ``cli_allowed_commands`` without providing
    an explicit ``credentials=[...]`` list.
    """
```

Add `credentials` to `AgentDef`:

```python
@dataclass
class AgentDef:
    # ... existing fields ...
    credentials: List[Any] = field(default_factory=list)
```

Add `credentials` to `@agent` decorator signature:

```python
def agent(
    func: Optional[Callable[..., Any]] = None,
    *,
    # ... existing params ...
    credentials: Optional[List[Any]] = None,
) -> Any:
```

And in `_wrap` inside `agent()`, add `credentials=list(credentials) if credentials else []` to the `AgentDef(...)` constructor.

Also update `_resolve_agent` to pass `credentials=ad.credentials or []` to `Agent(...)`.

Update `Agent.__init__`:

1. Add `credentials: Optional[List[Any]] = None` parameter (after `cli_config`).
2. Add credential auto-mapping logic in `__init__`. The full logic block to add (after the existing cli_config setup, before the final lines):

```python
# ── Credential setup ─────────────────────────────────────────────
# When explicit credentials provided, use them as-is.
# When not provided, auto-map from cli_allowed_commands via CLI_CREDENTIAL_MAP.
from agentspan.agents.runtime.credentials.cli_map import CLI_CREDENTIAL_MAP

if credentials is not None:
    self.credentials: List[Any] = list(credentials)
elif self.cli_config and self.cli_config.allowed_commands:
    # Check for terraform (None entry) before auto-mapping
    null_mapped = [
        cmd for cmd in self.cli_config.allowed_commands
        if CLI_CREDENTIAL_MAP.get(cmd) is None and cmd in CLI_CREDENTIAL_MAP
    ]
    if null_mapped:
        raise ConfigurationError(
            f"CLI command(s) {null_mapped!r} have no credential auto-mapping. "
            f"You must provide an explicit credentials=[...] list. "
            f"Example: Agent(cli_allowed_commands=['terraform', ...], "
            f"credentials=['AWS_ACCESS_KEY_ID', 'TF_VAR_...'])"
        )
    # Collect and deduplicate
    seen: set = set()
    auto_creds: List[Any] = []
    for cmd in self.cli_config.allowed_commands:
        mapped = CLI_CREDENTIAL_MAP.get(cmd)
        if mapped:
            for cred in mapped:
                key = cred.env_var if hasattr(cred, "env_var") else cred
                if key not in seen:
                    seen.add(key)
                    auto_creds.append(cred)
    self.credentials = auto_creds
else:
    self.credentials = []
```

- [ ] **Step 4: Run all agent tests**

```bash
cd sdk/python && uv run pytest tests/unit/test_agent.py -v
```

Expected: All tests PASS. The new `TestAgentCredentials` class all pass.

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/agent.py sdk/python/tests/unit/test_agent.py
git commit -m "feat(credentials): add credentials param to Agent with CLI auto-mapping and terraform guard"
```

---

## Chunk 6: Dispatch Integration

### Task 10: `_dispatch.py` — extract token, call fetcher, route through isolator/accessor

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/_dispatch.py`
- Modify: `sdk/python/tests/unit/test_dispatch.py`

This is the integration point. `make_tool_worker` must:
1. Extract `__agentspan_ctx__` from the Conductor task's input or workflow variables.
2. Read the `ToolDef` for the tool (if available) to get `isolated` and `credentials`.
3. Call `WorkerCredentialFetcher.fetch()` with the token and credential names.
4. For `isolated=True` tools: run via `SubprocessIsolator`.
5. For `isolated=False` tools: set credential context, run normally, clear context.

- [ ] **Step 1: Write the failing tests**

Append a new class to `sdk/python/tests/unit/test_dispatch.py`:

```python
class TestCredentialExtraction:
    """_dispatch.py extracts __agentspan_ctx__ from task input/variables."""

    def test_extract_token_from_input_data(self):
        from agentspan.agents.runtime._dispatch import _extract_execution_token

        class FakeTask:
            input_data = {"__agentspan_ctx__": "token-from-input", "x": "hello"}
            workflow_input = {}

        token = _extract_execution_token(FakeTask())
        assert token == "token-from-input"

    def test_extract_token_returns_none_when_absent(self):
        from agentspan.agents.runtime._dispatch import _extract_execution_token

        class FakeTask:
            input_data = {"x": "hello"}
            workflow_input = {}

        token = _extract_execution_token(FakeTask())
        assert token is None


class TestMakeToolWorkerWithCredentials:
    """make_tool_worker integrates with credential fetching."""

    def _make_task(self, input_data=None, ctx_token=None):
        from conductor.client.http.models.task import Task
        t = Task()
        t.input_data = input_data or {}
        if ctx_token:
            t.input_data["__agentspan_ctx__"] = ctx_token
        t.workflow_instance_id = "test-wf-001"
        t.task_id = "test-task-001"
        return t

    def test_non_isolated_tool_sets_credential_context(self):
        """isolated=False tool receives credentials via context var."""
        from unittest.mock import patch, MagicMock
        from agentspan.agents.runtime._dispatch import make_tool_worker
        from agentspan.agents.runtime.credentials.accessor import get_credential
        from agentspan.agents.tool import ToolDef, tool

        captured_token = {}

        @tool(isolated=False, credentials=["GITHUB_TOKEN"])
        def my_tool(x: str) -> str:
            """Get credential in tool."""
            captured_token["val"] = get_credential("GITHUB_TOKEN")
            return "ok"

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = {"GITHUB_TOKEN": "ghp_from_service"}

        with patch(
            "agentspan.agents.runtime._dispatch._get_credential_fetcher",
            return_value=mock_fetcher,
        ):
            wrapper = make_tool_worker(my_tool, "my_tool")
            task = self._make_task(input_data={"x": "hello"}, ctx_token="exec-token-abc")
            result = wrapper(task)

        assert result.status == "COMPLETED"
        assert captured_token["val"] == "ghp_from_service"
        mock_fetcher.fetch.assert_called_once_with("exec-token-abc", ["GITHUB_TOKEN"])

    def test_no_credentials_no_fetcher_call(self):
        """Tool with no credentials — fetcher is not called."""
        from unittest.mock import patch, MagicMock
        from agentspan.agents.runtime._dispatch import make_tool_worker
        from agentspan.agents.tool import tool

        @tool
        def simple_tool(x: str) -> str:
            """No credentials needed."""
            return f"hello {x}"

        mock_fetcher = MagicMock()

        with patch(
            "agentspan.agents.runtime._dispatch._get_credential_fetcher",
            return_value=mock_fetcher,
        ):
            wrapper = make_tool_worker(simple_tool, "simple_tool")
            task = self._make_task(input_data={"x": "world"})
            result = wrapper(task)

        assert result.status == "COMPLETED"
        mock_fetcher.fetch.assert_not_called()

    def test_credential_auth_error_fails_task(self):
        """CredentialAuthError → task marked FAILED."""
        from unittest.mock import patch, MagicMock
        from agentspan.agents.runtime._dispatch import make_tool_worker
        from agentspan.agents.runtime.credentials.types import CredentialAuthError
        from agentspan.agents.tool import tool

        @tool(isolated=False, credentials=["GITHUB_TOKEN"])
        def my_tool(x: str) -> str:
            """Tool."""
            return "ok"

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.side_effect = CredentialAuthError("token expired")

        with patch(
            "agentspan.agents.runtime._dispatch._get_credential_fetcher",
            return_value=mock_fetcher,
        ):
            wrapper = make_tool_worker(my_tool, "my_tool")
            task = self._make_task(input_data={"x": "hello"}, ctx_token="expired-token")
            result = wrapper(task)

        assert result.status == "FAILED"
        assert "expired" in result.reason_for_incompletion.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd sdk/python && uv run pytest tests/unit/test_dispatch.py::TestCredentialExtraction tests/unit/test_dispatch.py::TestMakeToolWorkerWithCredentials -v
```

Expected: FAIL — `_extract_execution_token` and `_get_credential_fetcher` don't exist yet.

- [ ] **Step 3: Modify `_dispatch.py`**

Note: `_dispatch.py` explicitly avoids `from __future__ import annotations` — keep that constraint.

Add at the top of `_dispatch.py`, after existing imports:

```python
import logging
import json
import inspect

logger = logging.getLogger("agentspan.agents.dispatch")
```

(Already present — no change needed for logger/json/inspect.)

Add these new module-level helpers and one module-level singleton reference:

```python
# Lazily created credential fetcher — initialized from AgentConfig on first use
_credential_fetcher = None


def _get_credential_fetcher():
    """Return the module-level WorkerCredentialFetcher, creating it on first call.

    The fetcher is initialized from AgentConfig.from_env() so it picks up
    AGENTSPAN_SERVER_URL, AGENTSPAN_API_KEY, AGENTSPAN_CREDENTIAL_STRICT_MODE.
    """
    global _credential_fetcher
    if _credential_fetcher is None:
        from agentspan.agents.runtime.config import AgentConfig
        from agentspan.agents.runtime.credentials.fetcher import WorkerCredentialFetcher
        config = AgentConfig.from_env()
        _credential_fetcher = WorkerCredentialFetcher(
            server_url=config.server_url,
            strict_mode=config.credential_strict_mode,
            api_key=config.api_key or config.auth_key,
        )
    return _credential_fetcher


def _extract_execution_token(task) -> str | None:
    """Extract __agentspan_ctx__ execution token from a Conductor task.

    Checks task.input_data first (most common), then task.workflow_input.
    Returns None if not present.
    """
    # input_data is the primary source (set by Conductor enrichment scripts)
    token = (task.input_data or {}).get("__agentspan_ctx__")
    if token:
        return token
    # Fallback: check workflow_input (set at workflow start)
    token = (getattr(task, "workflow_input", None) or {}).get("__agentspan_ctx__")
    return token or None


def _get_credential_names_from_tool(tool_func) -> list:
    """Extract credential names from a @tool-decorated function's ToolDef.

    Returns empty list if the function has no _tool_def attribute.
    """
    tool_def = getattr(tool_func, "_tool_def", None)
    if tool_def is None:
        return []
    return list(getattr(tool_def, "credentials", []))


def _is_isolated(tool_func) -> bool:
    """Return the isolated flag from a @tool-decorated function's ToolDef.

    Defaults to True (safe default) if no ToolDef is present.
    """
    tool_def = getattr(tool_func, "_tool_def", None)
    if tool_def is None:
        return True
    return getattr(tool_def, "isolated", True)
```

Modify `make_tool_worker` to integrate credential fetching. The `tool_worker` inner function needs to be updated. Here is the updated body of `tool_worker` inside `make_tool_worker` (replace the existing `tool_worker` function):

```python
def tool_worker(task: Task) -> TaskResult:
    """Worker wrapper that receives a Task object from Conductor."""
    task_result = TaskResult(
        task_id=task.task_id,
        workflow_instance_id=task.workflow_instance_id,
        worker_id="agent-sdk",
    )
    try:
        # Extract server-side agent state
        agent_state = task.input_data.pop("_agent_state", None) or {}

        # ── Credential fetching ───────────────────────────────────────
        credential_names = _get_credential_names_from_tool(tool_func)
        resolved_credentials = {}
        if credential_names:
            token = _extract_execution_token(task)
            fetcher = _get_credential_fetcher()
            resolved_credentials = fetcher.fetch(token, credential_names)

        # Map task input to function kwargs (existing logic unchanged)
        sig = inspect.signature(tool_func)
        fn_kwargs = {}
        for param_name in sig.parameters:
            if param_name == "context":
                continue
            if param_name in task.input_data:
                raw_value = task.input_data[param_name]
                ann = tool_func.__annotations__.get(param_name, inspect.Parameter.empty)
                fn_kwargs[param_name] = _coerce_value(raw_value, ann)
            elif sig.parameters[param_name].default is not inspect.Parameter.empty:
                fn_kwargs[param_name] = sig.parameters[param_name].default
            else:
                fn_kwargs[param_name] = None

        # ── Execution routing: isolated vs non-isolated ───────────────
        if credential_names and _is_isolated(tool_func):
            # Isolated path: run in subprocess with credentials injected
            # Build CredentialFile instances with content filled in
            from agentspan.agents.runtime.credentials.isolator import SubprocessIsolator
            from agentspan.agents.runtime.credentials.types import CredentialFile

            # Build credentials dict for isolator:
            # - For str creds: key = name, value = resolved plaintext string
            # - For CredentialFile creds: key = cf.env_var, value = CredentialFile with content
            tool_def_credentials = _get_credential_names_from_tool(tool_func)
            isolator_creds = {}
            for cred_spec in tool_def_credentials:
                if isinstance(cred_spec, str):
                    if cred_spec in resolved_credentials:
                        isolator_creds[cred_spec] = resolved_credentials[cred_spec]
                elif isinstance(cred_spec, CredentialFile):
                    content = resolved_credentials.get(cred_spec.env_var, "")
                    isolator_creds[cred_spec.env_var] = CredentialFile(
                        env_var=cred_spec.env_var,
                        relative_path=cred_spec.relative_path,
                        content=content,
                    )

            isolator = SubprocessIsolator()
            result = _execute_via_isolator(
                isolator, tool_func, fn_kwargs, agent_state, isolator_creds,
                tool_name, guardrails
            )
        else:
            # Non-isolated path (or no credentials): set context var, run directly
            from agentspan.agents.runtime.credentials.accessor import (
                clear_credential_context,
                set_credential_context,
            )
            if resolved_credentials:
                set_credential_context(resolved_credentials)
            try:
                result = _execute(fn_kwargs, wf_id=task.workflow_instance_id or "",
                                  agent_state=agent_state)
            finally:
                if resolved_credentials:
                    clear_credential_context()

        if isinstance(result, dict):
            task_result.output_data = result
        else:
            task_result.output_data = {"result": result}
        task_result.status = TaskResultStatus.COMPLETED
        return task_result
    except Exception as e:
        _tool_error_counts[tool_name] = _tool_error_counts.get(tool_name, 0) + 1
        logger.error(
            "Tool '%s' failed (count=%d): %s", tool_name, _tool_error_counts[tool_name], e
        )
        task_result.status = TaskResultStatus.FAILED
        task_result.reason_for_incompletion = str(e)
        return task_result
```

Add a helper for the isolated execution path (to keep `make_tool_worker` readable):

```python
def _execute_via_isolator(isolator, tool_func, fn_kwargs, agent_state, credentials,
                           tool_name, guardrails):
    """Run tool_func via SubprocessIsolator.

    Note: ToolContext injection and guardrails are applied in the subprocess.
    The subprocess receives the same kwargs and agent_state.
    """
    # Build a simple wrapper that calls _execute in the subprocess
    def _subprocess_wrapper(**kwargs):
        return _execute(kwargs, wf_id="", agent_state=agent_state)

    return isolator.run(
        _subprocess_wrapper,
        args=(),
        kwargs=fn_kwargs,
        credentials=credentials,
    )
```

Wait — there's a complexity: `_execute` calls `tool_func` which is defined in the parent process. Because we're using cloudpickle with spawn, the function will be serialized. However, `tool_func` has the original function reference which cloudpickle can serialize. The guardrails are also closures. This approach is correct for cloudpickle.

However, `ToolContext` injection via `_execute` calls `_needs_context(tool_func)` which needs the function in the subprocess. Since cloudpickle serializes the entire function, this should work.

- [ ] **Step 4: Run the dispatch tests**

```bash
cd sdk/python && uv run pytest tests/unit/test_dispatch.py -v
```

Expected: All tests PASS including new credential tests.

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/_dispatch.py \
        sdk/python/tests/unit/test_dispatch.py
git commit -m "feat(credentials): integrate credential fetching and isolation into _dispatch.py"
```

---

## Chunk 7: Public API Exports and Final Wiring

### Task 11: Export `get_credential`, `CredentialFile`, and exceptions from `agentspan.agents`

**Files:**
- Modify: `sdk/python/src/agentspan/agents/__init__.py`
- Create: `sdk/python/tests/unit/credentials/test_public_api.py`

- [ ] **Step 1: Write the failing test**

```python
# sdk/python/tests/unit/credentials/test_public_api.py
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd sdk/python && uv run pytest tests/unit/credentials/test_public_api.py -v
```

Expected: FAIL — nothing is exported yet from the top-level package.

- [ ] **Step 3: Update `__init__.py`**

Add the following imports to `sdk/python/src/agentspan/agents/__init__.py`:

After the `from agentspan.agents.exceptions import ...` line, add:

```python
# Credential management
from agentspan.agents.runtime.credentials.accessor import get_credential
from agentspan.agents.runtime.credentials.types import (
    CredentialAuthError,
    CredentialFile,
    CredentialNotFoundError,
    CredentialRateLimitError,
    CredentialServiceError,
)
```

Also add `ConfigurationError` from agent.py:

```python
from agentspan.agents.agent import (
    Agent, AgentDef, ConfigurationError, PromptTemplate, Strategy, agent, scatter_gather
)
```

Update `__all__` to include the new names:

```python
__all__ = [
    # ... existing entries ...
    # Credentials
    "get_credential",
    "CredentialFile",
    "CredentialNotFoundError",
    "CredentialAuthError",
    "CredentialRateLimitError",
    "CredentialServiceError",
    # Configuration errors
    "ConfigurationError",
]
```

- [ ] **Step 4: Run all public API tests**

```bash
cd sdk/python && uv run pytest tests/unit/credentials/test_public_api.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 5: Run full unit test suite to catch regressions**

```bash
cd sdk/python && uv run pytest tests/unit/ -v --tb=short 2>&1 | tail -40
```

Expected: All pre-existing tests still PASS. Zero regressions.

- [ ] **Step 6: Commit**

```bash
git add sdk/python/src/agentspan/agents/__init__.py \
        sdk/python/tests/unit/credentials/test_public_api.py
git commit -m "feat(credentials): export get_credential, CredentialFile, and exceptions from agentspan.agents"
```

---

### Task 12: Lint and Type Checks

**Files:**
- All modified Python files

- [ ] **Step 1: Run ruff format**

```bash
cd sdk/python && uv run ruff format src/agentspan/agents/runtime/credentials/ \
    src/agentspan/agents/tool.py \
    src/agentspan/agents/agent.py \
    src/agentspan/agents/runtime/config.py \
    src/agentspan/agents/runtime/_dispatch.py \
    src/agentspan/agents/__init__.py
```

Expected: Files reformatted with no errors.

- [ ] **Step 2: Run ruff lint**

```bash
cd sdk/python && uv run ruff check src/agentspan/agents/runtime/credentials/ \
    src/agentspan/agents/tool.py \
    src/agentspan/agents/agent.py \
    src/agentspan/agents/runtime/config.py \
    src/agentspan/agents/runtime/_dispatch.py \
    src/agentspan/agents/__init__.py
```

Expected: No errors. Fix any `E`, `F`, `W`, `I` lint violations before proceeding.

- [ ] **Step 3: Run mypy**

```bash
cd sdk/python && uv run mypy src/agentspan/agents
Continuing the plan from where it was cut:

---

```
Expected: No errors or only ``ignore_missing_imports``-covered stubs.
Common issues to fix:
- Add ``# type: ignore[attr-defined]`` if mypy cannot resolve ``ContextVar.set()`` return type.
- The ``str | None`` union syntax is Python 3.10+ — use ``Optional[str]`` in all new files (already done in the implementations above, since the codebase targets Python 3.9+).
```

- [ ] **Step 4: Run full test suite one final time**

```bash
cd sdk/python && uv run pytest tests/unit/ -v --tb=short
```

Expected: All tests PASS. Count: existing tests + all new credential tests.

- [ ] **Step 5: Commit lint fixes**

```bash
git add -u
git commit -m "style(credentials): apply ruff format and fix lint warnings"
```

---

### Task 13: Verify `isolated=True` path end-to-end with subprocess

**Files:**
- Create: `sdk/python/tests/unit/credentials/test_dispatch_isolated.py`

This is the final integration test verifying that an `isolated=True` tool actually receives its credentials inside the subprocess environment, not via `get_credential()`.

- [ ] **Step 1: Write the test**

```python
# sdk/python/tests/unit/credentials/test_dispatch_isolated.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Integration test: isolated=True tool receives credentials in subprocess env."""

import os
from unittest.mock import MagicMock, patch

import pytest

from agentspan.agents.runtime._dispatch import make_tool_worker
from agentspan.agents.tool import tool


def _make_task(input_data=None, ctx_token=None):
    from conductor.client.http.models.task import Task
    t = Task()
    t.input_data = input_data or {}
    if ctx_token:
        t.input_data["__agentspan_ctx__"] = ctx_token
    t.workflow_instance_id = "test-wf-isolated"
    t.task_id = "test-task-isolated"
    return t


class TestIsolatedToolDispatch:
    """isolated=True tool runs in subprocess with env var credentials."""

    def test_isolated_tool_reads_credential_from_env(self):
        """The subprocess has GITHUB_TOKEN in its environment."""

        @tool(isolated=True, credentials=["GITHUB_TOKEN"])
        def read_github_token() -> str:
            """Read GITHUB_TOKEN from subprocess env."""
            import os
            return os.environ.get("GITHUB_TOKEN", "NOT_FOUND")

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = {"GITHUB_TOKEN": "ghp_subprocess_token"}

        with patch(
            "agentspan.agents.runtime._dispatch._get_credential_fetcher",
            return_value=mock_fetcher,
        ):
            wrapper = make_tool_worker(read_github_token, "read_github_token")
            task = _make_task(ctx_token="exec-token-xyz")
            result = wrapper(task)

        assert result.status == "COMPLETED"
        assert result.output_data.get("result") == "ghp_subprocess_token"

    def test_isolated_tool_credential_not_in_parent_env(self):
        """The isolated credential must NOT appear in parent os.environ."""
        secret_key = "AGENTSPAN_TEST_ISOLATED_SECRET_99999"
        assert secret_key not in os.environ

        @tool(isolated=True, credentials=[secret_key])
        def noop_tool() -> str:
            """Does nothing."""
            return "done"

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = {secret_key: "super-secret"}

        with patch(
            "agentspan.agents.runtime._dispatch._get_credential_fetcher",
            return_value=mock_fetcher,
        ):
            wrapper = make_tool_worker(noop_tool, "noop_tool")
            task = _make_task(ctx_token="exec-token-xyz")
            wrapper(task)

        # Parent env must be clean
        assert secret_key not in os.environ
```

- [ ] **Step 2: Run test to verify it passes**

```bash
cd sdk/python && uv run pytest tests/unit/credentials/test_dispatch_isolated.py -v
```

Expected: Both tests PASS. (These spawn subprocesses — allow 10-15 seconds.)

- [ ] **Step 3: Commit**

```bash
git add sdk/python/tests/unit/credentials/test_dispatch_isolated.py
git commit -m "test(credentials): add end-to-end dispatch integration test for isolated=True tools"
```

---

## Summary: All Files

### New Files

| Path | Purpose |
|------|---------|
| `sdk/python/src/agentspan/agents/runtime/credentials/__init__.py` | Package exports |
| `sdk/python/src/agentspan/agents/runtime/credentials/types.py` | `CredentialFile` + 4 exception types |
| `sdk/python/src/agentspan/agents/runtime/credentials/fetcher.py` | `WorkerCredentialFetcher` |
| `sdk/python/src/agentspan/agents/runtime/credentials/isolator.py` | `SubprocessIsolator` |
| `sdk/python/src/agentspan/agents/runtime/credentials/accessor.py` | `get_credential()` + context var |
| `sdk/python/src/agentspan/agents/runtime/credentials/cli_map.py` | `CLI_CREDENTIAL_MAP` |
| `sdk/python/tests/unit/credentials/__init__.py` | Test package marker |
| `sdk/python/tests/unit/credentials/test_types.py` | Types + exceptions tests |
| `sdk/python/tests/unit/credentials/test_fetcher.py` | Fetcher tests |
| `sdk/python/tests/unit/credentials/test_isolator.py` | Isolator tests |
| `sdk/python/tests/unit/credentials/test_cli_map.py` | Registry tests |
| `sdk/python/tests/unit/credentials/test_accessor.py` | Accessor tests |
| `sdk/python/tests/unit/credentials/test_public_api.py` | Public API surface tests |
| `sdk/python/tests/unit/credentials/test_dispatch_isolated.py` | End-to-end isolated dispatch test |

### Modified Files

| Path | Changes |
|------|---------|
| `sdk/python/src/agentspan/agents/tool.py` | Add `isolated`, `credentials` to `ToolDef` and `@tool` |
| `sdk/python/src/agentspan/agents/agent.py` | Add `ConfigurationError`, `credentials` param, terraform guard, CLI auto-map |
| `sdk/python/src/agentspan/agents/runtime/config.py` | Add `credential_strict_mode`, promote `api_key` to field |
| `sdk/python/src/agentspan/agents/runtime/_dispatch.py` | Add token extraction, fetcher integration, isolator/accessor routing |
| `sdk/python/src/agentspan/agents/__init__.py` | Export credential types and `get_credential` |
| `sdk/python/pyproject.toml` | Add `cloudpickle>=2.0` dependency |

---

**To save this plan, write it to:**
`/Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/docs/superpowers/plans/2026-03-20-credential-management-python-sdk.md`

The plan header must start exactly with:

```markdown
# Python SDK Credential Changes Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-user credential fetching, subprocess isolation, and credential-aware @tool/Agent decorators to the Agentspan Python SDK.

**Architecture:** A new `credentials/` subpackage under `runtime/` holds all credential logic: exception types, a `WorkerCredentialFetcher` that calls `POST /api/credentials/resolve` with fallback to `os.environ`, a `SubprocessIsolator` that runs tool functions in a fresh subprocess with injected credentials, and a `get_credential()` accessor backed by a `contextvars.ContextVar` for non-isolated tools. The `@tool` decorator gains `isolated` and `credentials` params; `Agent` gains a `credentials` param with auto-mapping from `cli_allowed_commands` via `CLI_CREDENTIAL_MAP`. Dispatch in `_dispatch.py` extracts `__agentspan_ctx__` from the Conductor task, calls the fetcher, then routes to the isolator or context-setter based on `isolated`.

**Tech Stack:** Python 3.9+, pytest, multiprocessing, httpx, cloudpickle

---
```

### Critical Files for Implementation

- `/Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/sdk/python/src/agentspan/agents/runtime/_dispatch.py` — Core logic to modify: add token extraction, fetcher integration, and isolated/non-isolated routing before tool execution
- `/Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/sdk/python/src/agentspan/agents/tool.py` — Add `isolated` and `credentials` fields to `ToolDef` dataclass and `@tool` decorator signature
- `/Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/sdk/python/src/agentspan/agents/agent.py` — Add `credentials` param, `ConfigurationError`, and `CLI_CREDENTIAL_MAP` auto-mapping logic to `Agent.__init__`
- `/Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/sdk/python/src/agentspan/agents/runtime/credentials/isolator.py` — New: `SubprocessIsolator` with thread-safe env injection via cloudpickle payload
- `/Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/sdk/python/src/agentspan/agents/runtime/credentials/fetcher.py` — New: `WorkerCredentialFetcher` with the exact HTTP error contract (401 → auth error, 429 → rate limit, 5xx → service error or env fallback per strict mode)