"""Long-running e2e conversation test.

Uses one-shot executions per turn (no wait_for_message) because
the LLM doesn't reliably stay in the wait loop. Each turn starts
a fresh execution with conversation context carried forward.

Run: cd autopilot && uv run pytest tests/e2e/test_long_conversation.py -v -s
"""

from __future__ import annotations

import os
import sys
import time
import yaml
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from agentspan.agents import Agent, AgentRuntime, EventType, tool
from autopilot.orchestrator.tools import get_orchestrator_tools, build_integration_catalog


class ConversationRunner:
    """One-shot-per-turn conversation runner. Each message = one execution."""

    def __init__(self, tmp_dir: Path):
        self.tmp_dir = tmp_dir
        self.agents_dir = tmp_dir / "agents"
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self.runtime: AgentRuntime | None = None
        self.turn_count = 0
        self.history: list[str] = []  # conversation history for context
        self.all_tool_calls: list[tuple[str, dict]] = []
        self.all_replies: list[str] = []
        self.errors: list[str] = []

    def _build_agent(self, prompt: str) -> Agent:
        model = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o")

        @tool
        def reply_to_user(message: str) -> str:
            """Send response to user."""
            return "ok"

        orch_tools = get_orchestrator_tools()
        catalog = build_integration_catalog()

        # Include conversation history for context
        history_text = ""
        if self.history:
            recent = self.history[-6:]  # last 3 exchanges
            history_text = (
                "Previous conversation (for context, do NOT repeat):\n"
                + "\n".join(recent)
                + "\n\n"
            )

        return Agent(
            name="claw_longtest",
            model=model,
            tools=[reply_to_user] + orch_tools,
            max_turns=25,
            instructions=f"""You are the Agentspan Claw orchestrator. Turn user requests into agents.

RULES:
1. Smart-default EVERYTHING. No questions. Just build immediately.
2. Write a YAML spec and call generate_agent.
3. Run validation gates: validate_spec, validate_integrations, validate_deployment.
4. Call reply_to_user with a CONCISE summary.
5. NEVER use future tense. Report what you DID.

{history_text}

Available integrations:
{catalog}
""",
        )

    def start(self):
        self.runtime = AgentRuntime()
        self.runtime.__enter__()
        self._started = False  # Defer first execution to first send()
        print(f"\n  Runtime started")

    def send(self, message: str, timeout: float = 120) -> dict:
        """Send a message via a fresh one-shot execution."""
        self.turn_count += 1
        print(f"\n  --- Turn {self.turn_count} ---")
        print(f"  User: {message}")
        self.history.append(f"User: {message}")

        agent = self._build_agent(message)
        handle = self.runtime.start(agent, message)
        print(f"  Execution: {handle.execution_id}")

        tool_calls = []
        reply = ""
        turn_errors = []

        start = time.time()
        for event in handle.stream():
            if event.type == EventType.TOOL_CALL:
                name = event.tool_name or ""
                args = {k: v for k, v in (event.args or {}).items() if not k.startswith("__")}
                tool_calls.append((name, args))
                self.all_tool_calls.append((name, args))

                if name == "reply_to_user":
                    reply = args.get("message", "")
                    self.all_replies.append(reply)
                    self.history.append(f"Claw: {reply[:300]}")
                    print(f"  Claw: {reply[:200]}{'...' if len(reply) > 200 else ''}")
                elif name in ("generate_agent", "validate_spec", "validate_integrations",
                              "validate_deployment", "deploy_agent", "list_agents",
                              "get_agent_status", "validate_code"):
                    print(f"    [{name}]")

            elif event.type == EventType.TOOL_RESULT:
                name = event.tool_name or ""
                result = str(event.result or "")[:150]
                if "validate" in name:
                    status = "PASS" if "PASS" in result else "FAIL" if "FAIL" in result else "?"
                    print(f"    -> {name}: {status}")
                elif name == "generate_agent" and "successfully" in result.lower():
                    print(f"    -> Agent created")

            elif event.type == EventType.ERROR:
                err = event.content or "Unknown error"
                turn_errors.append(err)
                self.errors.append(err)
                print(f"  [ERROR] {err}")
                break

            elif event.type in (EventType.DONE, EventType.WAITING):
                break

            if time.time() - start > timeout:
                print(f"  [TIMEOUT]")
                try:
                    handle.stop()
                except Exception:
                    pass
                break

        tool_names = [n for n, _ in tool_calls]
        return {
            "tool_calls": tool_calls,
            "tool_names": tool_names,
            "reply": reply,
            "errors": turn_errors,
            "execution_id": handle.execution_id,
        }

    def stop(self):
        if self.runtime:
            try:
                self.runtime.__exit__(None, None, None)
            except Exception:
                pass

    def get_created_agents(self) -> list[Path]:
        if not self.agents_dir.exists():
            return []
        return [d for d in self.agents_dir.iterdir()
                if d.is_dir() and (d / "agent.yaml").exists()]

    def get_agent_config(self, agent_dir: Path) -> dict:
        return yaml.safe_load((agent_dir / "agent.yaml").read_text()) or {}


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOPILOT_BASE_DIR", str(tmp_path))
    (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
    r = ConversationRunner(tmp_path)
    yield r
    r.stop()


@pytest.mark.e2e
class TestLongConversation:

    def test_full_lifecycle(self, runner: ConversationRunner):
        """
        Turn 1: Create a HN monitoring agent
        Turn 2: List agents
        Turn 3: Create a file monitoring agent
        Turn 4: List agents again (should show 2)
        """
        runner.start()

        # ── Turn 1: Create first agent ──
        print("\n" + "=" * 60)
        print("TURN 1: Create HN monitoring agent")
        print("=" * 60)

        r1 = runner.send(
            "create an agent that checks hackernews top stories every 30 minutes "
            "and saves a summary to a local file"
        )

        assert "generate_agent" in r1["tool_names"], \
            f"Turn 1: expected generate_agent, got {r1['tool_names']}"

        agents = runner.get_created_agents()
        assert len(agents) >= 1, f"Expected >= 1 agent, found {len(agents)}"
        a1 = agents[0]
        c1 = runner.get_agent_config(a1)
        print(f"  Created: {c1.get('name')} at {a1.name}")
        assert c1.get("name")
        assert c1.get("instructions")

        has_validation = any("validate" in n for n in r1["tool_names"])
        assert has_validation, f"Expected validation in {r1['tool_names']}"

        # ── Turn 2: List agents ──
        print("\n" + "=" * 60)
        print("TURN 2: List agents")
        print("=" * 60)

        r2 = runner.send("what agents do I have?")
        assert "list_agents" in r2["tool_names"], \
            f"Turn 2: expected list_agents, got {r2['tool_names']}"

        # ── Turn 3: Create second agent ──
        print("\n" + "=" * 60)
        print("TURN 3: Create file monitoring agent")
        print("=" * 60)

        r3 = runner.send(
            "create another agent that watches /tmp/reports for new PDF files "
            "and reads them with the document reader tool"
        )

        assert "generate_agent" in r3["tool_names"], \
            f"Turn 3: expected generate_agent, got {r3['tool_names']}"

        agents_after = runner.get_created_agents()
        assert len(agents_after) >= 2, \
            f"Expected >= 2 agents, found {len(agents_after)}"

        # ── Turn 4: List again ──
        print("\n" + "=" * 60)
        print("TURN 4: List all agents")
        print("=" * 60)

        r4 = runner.send("list all my agents")
        assert any(n in ("list_agents", "get_agent_status") for n in r4["tool_names"]), \
            f"Turn 4: expected list/status, got {r4['tool_names']}"

        # ── Summary ──
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  Turns: {runner.turn_count}")
        print(f"  Tool calls: {len(runner.all_tool_calls)}")
        print(f"  Agents created: {len(agents_after)}")
        print(f"  Errors: {len(runner.errors)}")

        for i, a in enumerate(agents_after):
            c = runner.get_agent_config(a)
            print(f"  Agent {i+1}: {c.get('name')} | trigger: {c.get('trigger', {}).get('type', '?')} | tools: {c.get('tools', [])}")

        assert len(runner.errors) == 0, f"Errors: {runner.errors}"
        assert len(agents_after) >= 2
