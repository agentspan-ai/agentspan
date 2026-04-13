"""E2e test: deploy_agent tool -> real server -> running execution -> output.

Tests the FULL deploy path that would have caught the bug where deploy_agent
used the wrong URL (http://localhost:6767/agent/start instead of
http://localhost:6767/api/agent/start).

All tests hit the REAL server. No mocks. The deploy must actually happen.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from agentspan.agents import AgentRuntime, EventType
from agentspan.agents.result import AgentHandle

from autopilot.config import AutopilotConfig
from autopilot.loader import load_agent
from autopilot.orchestrator.server import get_execution
from autopilot.orchestrator.state import StateManager
from autopilot.orchestrator.tools import deploy_agent


def _make_agent_on_disk(
    base_dir: Path,
    agent_name: str = "e2e_deploy_test",
    instructions: str | None = None,
) -> Path:
    """Create a minimal agent directory with agent.yaml under base_dir/agents/."""
    agents_dir = base_dir / "agents"
    agent_dir = agents_dir / agent_name
    agent_dir.mkdir(parents=True)
    (agent_dir / "workers").mkdir()

    default_instructions = (
        "You are a web search agent. As soon as you start, immediately call "
        "web_search with the query 'Agentspan AI' and return a concise summary "
        "of the top results. Do NOT ask the user for a query -- just search "
        "immediately. Include specific facts and URLs from the search results."
    )

    (agent_dir / "agent.yaml").write_text(yaml.dump({
        "name": agent_name,
        "model": os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o"),
        "instructions": instructions or default_instructions,
        "tools": ["builtin:web_search"],
        "trigger": {"type": "daemon"},
        "error_handling": {
            "max_retries": 3,
            "backoff": "exponential",
            "on_failure": "pause_and_notify",
        },
    }))

    (agent_dir / "expanded_prompt.md").write_text(
        f"# {agent_name}\n\nSearches the web and summarizes findings.\n"
    )

    return agent_dir


def _make_config(base_dir: Path, server_url: str | None = None) -> AutopilotConfig:
    """Build a config pointing at tmp_path but using the real server URL."""
    real_config = AutopilotConfig.from_env()
    return AutopilotConfig(
        server_url=server_url or real_config.server_url,
        llm_model=real_config.llm_model,
        base_dir=base_dir,
    )


@pytest.mark.e2e
class TestDeployAgent:
    """Tests that exercise the deploy_agent @tool function against the real server."""

    def test_deploy_agent_creates_running_execution(self, tmp_path, monkeypatch):
        """deploy_agent -> server returns execution ID -> execution is RUNNING or COMPLETED."""

        # -- Arrange: create agent on disk, patch config to use tmp_path --
        agent_name = "e2e_deploy_run"
        _make_agent_on_disk(tmp_path, agent_name)
        config = _make_config(tmp_path)

        monkeypatch.setattr(
            "autopilot.orchestrator.tools._get_config",
            lambda: config,
        )

        # -- Act: call deploy_agent directly (the @tool function) --
        result = deploy_agent(agent_name)
        print(f"\ndeploy_agent result:\n{result}")

        # -- Assert: result says "deployed successfully" --
        assert "deployed successfully" in result, (
            f"Expected 'deployed successfully' in result, got:\n{result}"
        )

        # -- Assert: result contains an execution ID --
        match = re.search(r"Execution ID:\s*(\S+)", result)
        assert match, f"No execution ID found in result:\n{result}"
        execution_id = match.group(1)
        assert len(execution_id) > 8, f"Execution ID looks invalid: {execution_id}"
        print(f"  Execution ID: {execution_id}")

        # -- Assert: server knows about this execution and it's RUNNING or COMPLETED --
        time.sleep(1)
        details = get_execution(execution_id, config=config)
        server_status = details.get("status", "")
        print(f"  Server status: {server_status}")
        assert server_status in ("RUNNING", "COMPLETED"), (
            f"Expected RUNNING or COMPLETED, got {server_status!r}. "
            f"Full response: {details}"
        )

        # -- Assert: state manager recorded the execution --
        sm = StateManager(tmp_path / "state.json")
        state = sm.get(agent_name)
        assert state is not None, "Agent not found in state manager after deploy"
        assert state.execution_id == execution_id
        assert state.status == "ACTIVE"

        # -- Cleanup: stop the execution so it doesn't run forever --
        try:
            with AgentRuntime() as runtime:
                runtime.stop(execution_id)
        except Exception:
            pass

    def test_deploy_and_run_produces_output(self, tmp_path, monkeypatch):
        """deploy_agent -> start workers -> agent searches web -> real output.

        deploy_agent starts the workflow on the server via HTTP POST.
        Tool workers must run locally to handle tool calls (web_search etc.).
        In production, the orchestrator daemon runs workers continuously.
        Here we start them explicitly via _prepare_workers.
        """

        # -- Arrange --
        agent_name = "e2e_deploy_output"
        agent_dir = _make_agent_on_disk(tmp_path, agent_name)
        config = _make_config(tmp_path)

        monkeypatch.setattr(
            "autopilot.orchestrator.tools._get_config",
            lambda: config,
        )

        # Load agent so we can register its tool workers
        agent = load_agent(agent_dir)

        with AgentRuntime() as runtime:
            # -- Act: deploy via deploy_agent (starts workflow on server) --
            result = deploy_agent(agent_name)
            print(f"\ndeploy_agent result:\n{result}")

            assert "deployed successfully" in result, f"Deploy failed:\n{result}"

            match = re.search(r"Execution ID:\s*(\S+)", result)
            assert match, f"No execution ID in result:\n{result}"
            execution_id = match.group(1)
            print(f"  Execution ID: {execution_id}")

            # Start tool workers so the server can dispatch tool tasks to us.
            # _prepare_workers registers AND starts worker polling threads.
            runtime._prepare_workers(agent)

            # -- Stream events from the deployed execution --
            handle = AgentHandle(execution_id, runtime)
            tool_calls: list[str] = []
            output = ""
            start_time = time.time()

            for event in handle.stream():
                if event.type == EventType.TOOL_CALL:
                    name = event.tool_name or ""
                    tool_calls.append(name)
                    args = {
                        k: v
                        for k, v in (event.args or {}).items()
                        if not k.startswith("__")
                    }
                    print(f"  [{name}] args={args}")

                elif event.type == EventType.TOOL_RESULT:
                    name = event.tool_name or ""
                    result_str = str(event.result or "")
                    if name in ("web_search", "search_and_read"):
                        print(f"  [{name}] -> {len(result_str)} chars")

                elif event.type == EventType.DONE:
                    if event.output:
                        out = event.output
                        if isinstance(out, dict):
                            out = out.get("result", str(out))
                        output = str(out)
                    break

                elif event.type == EventType.ERROR:
                    print(f"  [ERROR] {event.content}")
                    break

                if time.time() - start_time > 90:
                    handle.stop()
                    break

        # -- Verify --
        print(f"\n  Tool calls: {tool_calls}")
        print(f"  Output ({len(output)} chars): {output[:300]}...")

        assert any(
            tc in ("web_search", "search_and_read") for tc in tool_calls
        ), f"Agent never called web_search or search_and_read. Calls: {tool_calls}"

        assert output, "Agent produced no output"
        assert len(output) > 30, f"Output too short ({len(output)} chars): {output}"

    def test_deploy_agent_with_wrong_url_fails_clearly(self, tmp_path, monkeypatch):
        """Bad server URL -> deploy_agent returns 'Error deploying' -> state is ERROR."""

        # -- Arrange: point at a URL that will 404 or connection-refuse --
        agent_name = "e2e_deploy_bad_url"
        _make_agent_on_disk(tmp_path, agent_name)

        # Use a URL that will definitely fail (wrong port)
        bad_config = _make_config(tmp_path, server_url="http://localhost:19999")

        monkeypatch.setattr(
            "autopilot.orchestrator.tools._get_config",
            lambda: bad_config,
        )

        # -- Act --
        result = deploy_agent(agent_name)
        print(f"\ndeploy_agent result (bad URL):\n{result}")

        # -- Assert: result says "Error deploying" --
        assert "Error deploying" in result, (
            f"Expected 'Error deploying' in result, got:\n{result}"
        )

        # -- Assert: state manager shows ERROR --
        sm = StateManager(tmp_path / "state.json")
        state = sm.get(agent_name)
        assert state is not None, "Agent not found in state manager"
        assert state.status == "ERROR", (
            f"Expected ERROR status, got {state.status!r}"
        )
        assert state.execution_id == "", (
            f"Expected empty execution_id on error, got {state.execution_id!r}"
        )
