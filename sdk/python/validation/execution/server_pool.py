"""Server pool — starts and manages a single shared agentspan server."""

from __future__ import annotations

import atexit
import os
import signal
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .runner import check_server_health


@dataclass
class ServerInstance:
    port: int
    url: str  # http://localhost:{port}/api
    model_name: str  # "openai", "anthropic", "adk"
    process: subprocess.Popen | None = None  # None if pre-existing
    we_started: bool = False  # True if we launched this server


def _port_in_use(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def _is_agentspan_server(port: int) -> bool:
    """Check if the process on this port is an agentspan server."""
    return check_server_health(f"http://localhost:{port}/api")


def _find_pid_on_port(port: int) -> int | None:
    """Find the PID of the process listening on a TCP port."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            # May return multiple PIDs; take the first
            return int(result.stdout.strip().splitlines()[0])
    except Exception:
        pass
    return None


def _kill_pid(pid: int) -> None:
    """SIGTERM then SIGKILL a process by PID."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    # Wait up to 5s
    for _ in range(50):
        try:
            os.kill(pid, 0)  # check if alive
        except ProcessLookupError:
            return
        time.sleep(0.1)
    # Force kill
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _kill_server_on_port(port: int) -> bool:
    """Find and kill whatever is listening on this port. Returns True if killed."""
    pid = _find_pid_on_port(port)
    if pid:
        _kill_pid(pid)
        # Verify
        time.sleep(0.5)
        return not _port_in_use(port)
    return False


class ServerPool:
    def __init__(self, base_port: int = 8080):
        self._base_port = base_port
        self._servers: dict[str, ServerInstance] = {}
        self._started = False

    @property
    def servers(self) -> dict[str, ServerInstance]:
        return self._servers

    def start(
        self,
        models: dict[str, str],
        log_dir: Path | None = None,
        extra_env: dict | None = None,
    ) -> None:
        """Start one fresh server per model on a free port."""
        if self._started:
            return

        if log_dir:
            log_dir.mkdir(parents=True, exist_ok=True)

        port = self._base_port
        assignments: dict[str, int] = {}

        # Assign ports — reuse if an agentspan server is already running there
        for model_name in models:
            if _port_in_use(port) and _is_agentspan_server(port):
                assignments[model_name] = port
            else:
                while _port_in_use(port):
                    port += 1
                assignments[model_name] = port
            port += 1

        server_env = {**os.environ, **(extra_env or {})}

        # Start servers in parallel
        def _start_one(model_name: str, assigned_port: int) -> ServerInstance:
            url = f"http://localhost:{assigned_port}/api"

            # Reuse pre-existing agentspan server
            if _is_agentspan_server(assigned_port):
                return ServerInstance(
                    port=assigned_port,
                    url=url,
                    model_name=model_name,
                    process=None,
                    we_started=False,
                )

            # Start server
            cmd = ["agentspan", "server", "start", "-p", str(assigned_port)]

            log_file = None
            if log_dir:
                log_path = log_dir / f"server_{assigned_port}.log"
                log_file = open(log_path, "w")  # noqa: SIM115

            proc = subprocess.Popen(
                cmd,
                stdout=log_file or subprocess.DEVNULL,
                stderr=log_file or subprocess.DEVNULL,
                env=server_env,
            )

            # Wait for health
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if check_server_health(url):
                    return ServerInstance(
                        port=assigned_port,
                        url=url,
                        model_name=model_name,
                        process=proc,
                        we_started=True,
                    )
                # CLI may exit after daemonizing — that's OK, check health not proc
                time.sleep(1)

            raise RuntimeError(
                f"Server for {model_name} on port {assigned_port} failed to start within 60s"
            )

        with ThreadPoolExecutor(max_workers=len(assignments)) as pool:
            futures = {pool.submit(_start_one, name, p): name for name, p in assignments.items()}
            for future in futures:
                name = futures[future]
                self._servers[name] = future.result()

        self._started = True
        atexit.register(self.shutdown)

    def get_server_urls(self) -> dict[str, str]:
        """model_name → url"""
        return {name: s.url for name, s in self._servers.items()}

    def check_and_restart(self, model_name: str) -> bool:
        """Health check, one restart attempt. Returns True if healthy."""
        server = self._servers.get(model_name)
        if not server:
            return False

        if check_server_health(server.url):
            return True

        # One restart attempt — only for servers we started
        if not server.we_started:
            return False

        _kill_server_on_port(server.port)

        cmd = ["agentspan", "server", "start", "-p", str(server.port)]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if check_server_health(server.url):
                server.process = proc
                return True
            time.sleep(1)

        return False

    def shutdown(self) -> None:
        """Stop all servers we started."""
        for name, server in self._servers.items():
            if not server.we_started:
                continue  # pre-existing, don't touch

            # Try graceful stop via CLI
            for attempt in range(3):
                try:
                    subprocess.run(
                        [
                            "agentspan",
                            "server",
                            "stop",
                            "--server",
                            f"http://localhost:{server.port}",
                        ],
                        capture_output=True,
                        timeout=10,
                    )
                except Exception:
                    pass
                time.sleep(2)
                if not check_server_health(server.url):
                    break

            # Force kill by port — catches daemonized Java processes
            if check_server_health(server.url) or _port_in_use(server.port):
                _kill_server_on_port(server.port)

        self._servers.clear()
        self._started = False
