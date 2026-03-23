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
