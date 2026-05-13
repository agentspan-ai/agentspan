"""E2E test infrastructure. No mocks. Real server, real CLI, real services."""

import os
import subprocess

import pytest
import requests

# ── Configuration from env (set by orchestrator) ────────────────────────

SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
BASE_URL = SERVER_URL.rstrip("/").replace("/api", "")
CLI_PATH = os.environ.get("AGENTSPAN_CLI_PATH", "agentspan")
MCP_TESTKIT_URL = os.environ.get("MCP_TESTKIT_URL", "http://localhost:3001")
MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini")


# ── Prevent runtime from auto-starting a second server ──────────────────

os.environ["AGENTSPAN_AUTO_START_SERVER"] = "false"


# ── Markers ─────────────────────────────────────────────────────────────


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring live server")
    config.addinivalue_line(
        "markers", "xdist_group(name): assign test to named xdist group for serial execution"
    )
    config.addinivalue_line(
        "markers", "timeout(seconds): per-test timeout (requires pytest-timeout)"
    )


# ── Session-scoped health check ─────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def verify_server():
    """Fail fast if server is not running."""
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        assert resp.json().get("healthy"), "Server reports unhealthy"
    except Exception as e:
        pytest.skip(f"Server not available at {BASE_URL}: {e}")


# ── Runtime fixture ─────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def runtime():
    """Module-scoped AgentRuntime — shared across tests in a module."""
    from agentspan.agents import AgentRuntime

    with AgentRuntime() as rt:
        yield rt


# ── Model fixture ───────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def model():
    return MODEL


@pytest.fixture(scope="session")
def mcp_url():
    return MCP_TESTKIT_URL


# ── CLI credential helper ──────────────────────────────────────────────


class CredentialsCLI:
    """Wraps the agentspan CLI for credential operations.

    The CLI expects AGENTSPAN_SERVER_URL without the /api suffix
    (e.g., http://localhost:6767). It appends /api internally.
    """

    def __init__(self, cli_path: str, server_url: str):
        self._cli = cli_path
        # CLI expects base URL without /api — strip it if present
        self._server_url = server_url.rstrip("/").removesuffix("/api")

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        cmd = [self._cli] + list(args)
        env = {**os.environ, "AGENTSPAN_SERVER_URL": self._server_url}
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=15, env=env
        )

    def set(self, name: str, value: str) -> None:
        result = self._run("credentials", "set", name, value)
        assert result.returncode == 0, (
            f"credentials set {name} failed: {result.stderr}"
        )

    def delete(self, name: str) -> None:
        result = self._run("credentials", "delete", name)
        # Ignore "not found" errors during cleanup
        if result.returncode != 0 and "not found" not in result.stderr.lower():
            raise AssertionError(
                f"credentials delete {name} failed: {result.stderr}"
            )

    def list(self) -> str:
        result = self._run("credentials", "list")
        assert result.returncode == 0, f"credentials list failed: {result.stderr}"
        return result.stdout


@pytest.fixture(scope="session")
def cli_credentials():
    return CredentialsCLI(CLI_PATH, SERVER_URL)


# ── Server API helpers ──────────────────────────────────────────────────


def get_workflow(execution_id: str) -> dict:
    """Fetch full workflow execution from server."""
    resp = requests.get(f"{BASE_URL}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_task_by_name(execution_id: str, task_ref_prefix: str) -> list:
    """Find tasks in a workflow whose referenceTaskName contains prefix."""
    wf = get_workflow(execution_id)
    return [
        t
        for t in wf.get("tasks", [])
        if task_ref_prefix in t.get("referenceTaskName", "")
    ]
