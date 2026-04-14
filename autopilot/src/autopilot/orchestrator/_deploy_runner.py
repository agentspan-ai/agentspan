"""Subprocess entry-point for deploying an agent.

Receives configuration via environment variables:
    DEPLOY_AGENT_DIR — absolute path to the agent directory
    DEPLOY_TIMEOUT   — execution timeout in seconds (default 120)

Steps:
    1. Install worker dependencies (requirements.txt)
    2. Validate workers compile
    3. Load agent via loader + run with AgentRuntime

Outputs a single JSON line prefixed with ``AGENT_RESULT:`` on stdout.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

# Ensure the autopilot package is importable.
# The caller sets PYTHONPATH or sys.path via DEPLOY_SRC_PATH.
src_path = os.environ.get("DEPLOY_SRC_PATH")
if src_path:
    sys.path.insert(0, src_path)

os.environ.setdefault("AGENTSPAN_LOG_LEVEL", "WARNING")


def _emit(execution_id: str = "", status: str = "ERROR", output: str = "") -> None:
    """Print the AGENT_RESULT JSON line and exit."""
    print("AGENT_RESULT:" + json.dumps({
        "execution_id": execution_id,
        "status": status,
        "output": output,
    }))


def main() -> None:
    agent_dir = Path(os.environ["DEPLOY_AGENT_DIR"])
    deploy_timeout = int(os.environ.get("DEPLOY_TIMEOUT", "120"))

    try:
        # Step 1: Install worker dependencies
        req_file = agent_dir / "workers" / "requirements.txt"
        if req_file.exists():
            deps = [l.strip() for l in req_file.read_text().splitlines() if l.strip()]
            if deps:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--quiet"] + deps,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode != 0:
                    _emit(output=f"Failed to install dependencies: {result.stderr[-500:]}")
                    sys.exit(1)

        # Step 2: Validate workers can be imported
        workers_dir = agent_dir / "workers"
        if workers_dir.exists():
            for py_file in workers_dir.glob("*.py"):
                try:
                    compile(py_file.read_text(), str(py_file), "exec")
                except SyntaxError as e:
                    _emit(output=f"Worker {py_file.name} has syntax error: {e}")
                    sys.exit(1)

        # Step 3: Load and run the agent
        from agentspan.agents import AgentRuntime
        from autopilot.loader import load_agent

        agent = load_agent(agent_dir)
        with AgentRuntime() as runtime:
            handle = runtime.start(agent, "Execute the agent task now. Produce output immediately.")
            result = handle.join(timeout=deploy_timeout)
            _emit(
                execution_id=handle.execution_id,
                status=result.status if result else "UNKNOWN",
                output=str(result.output)[:2000] if result and result.output else "",
            )

    except Exception as e:
        _emit(output=f"Agent failed: {str(e)[-500:]}\n{traceback.format_exc()[-500:]}")


if __name__ == "__main__":
    main()
