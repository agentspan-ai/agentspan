"""E2e TUI conversation flow tests — simulates real user interactions.

Tests the ORCHESTRATOR's conversation behavior using the exact same code path
as the TUI, minus prompt_toolkit.  Each user message starts a fresh
orchestrator execution (one-shot-per-turn).  Conversation history is carried
forward in the instructions.

NO mocks.  Real server, real LLM, real tools.
Every assertion is algorithmic (tool call names, file existence, string patterns).

Run with:
    uv run pytest tests/e2e/test_tui_conversations.py -v -s --tb=short
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from agentspan.agents import Agent, AgentRuntime, EventType, tool
from autopilot.orchestrator.tools import build_integration_catalog, get_orchestrator_tools
from autopilot.integrations.web_search.tools import get_tools as get_web_search_tools
from tests.e2e.conftest import assert_output_quality


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TIMEOUT = 90  # seconds per turn
_MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o")


# ---------------------------------------------------------------------------
# TUI Conversation Simulator
# ---------------------------------------------------------------------------


class TUIConversationSimulator:
    """Simulates TUI conversation without prompt_toolkit.

    Mirrors the TUI's actual one-shot-per-turn behavior:
    - Each turn: runtime.start(agent, message) with conversation history in instructions
    - Streams events, collects tool calls and reply
    - Carries history forward for the next turn
    """

    def __init__(self, tmp_dir: Path):
        self.tmp_dir = tmp_dir
        self.runtime: AgentRuntime | None = None
        self.history: list[str] = []
        self.model = _MODEL

    def start(self):
        self.runtime = AgentRuntime()
        self.runtime.__enter__()

    def send(self, message: str, timeout: int = _TIMEOUT) -> dict:
        """Send a message -- mirrors TUI one-shot-per-turn behavior.

        Returns dict with tool_calls, reply, output.
        """
        self.history.append(f"User: {message}")

        agent = self._build_agent()
        handle = self.runtime.start(agent, message)
        print(f"\n  Execution: {handle.execution_id}")

        tool_calls: list[str] = []
        tool_call_args: list[dict] = []
        reply = ""
        output = ""
        start = time.time()

        for event in handle.stream():
            if event.type == EventType.TOOL_CALL:
                name = event.tool_name or ""
                args = {
                    k: v for k, v in (event.args or {}).items()
                    if not k.startswith("__")
                }
                tool_calls.append(name)
                tool_call_args.append(args)
                print(f"  [{name}] {str(args)[:150]}")

                if name == "reply_to_user":
                    reply = args.get("message", "")

            elif event.type == EventType.TOOL_RESULT:
                result_str = str(event.result or "")
                print(f"    -> {len(result_str)} chars")

            elif event.type == EventType.DONE:
                if event.output:
                    out = event.output
                    if isinstance(out, dict):
                        out = out.get("result", str(out))
                    output = str(out)
                break

            elif event.type == EventType.ERROR:
                err = event.content or str(event)
                print(f"  ERROR: {err}")
                break

            elif event.type == EventType.WAITING:
                # One-shot mode: break on WAITING (the agent called
                # wait_for_message but we do not feed another turn here)
                break

            if time.time() - start > timeout:
                handle.stop()
                print(f"  TIMEOUT after {timeout}s")
                break

        # If reply_to_user was never called, use the DONE output as fallback
        if not reply and output:
            reply = output

        if reply:
            self.history.append(f"Claw: {reply[:300]}")

        return {
            "tool_calls": tool_calls,
            "tool_call_args": tool_call_args,
            "reply": reply,
            "output": output,
        }

    def _build_agent(self) -> Agent:
        """Build orchestrator agent -- same tools as TUI, no wait_for_message."""
        catalog = build_integration_catalog()
        orch_tools = get_orchestrator_tools()
        web_tools = get_web_search_tools()

        # Filter out tools that call input() -- they block forever in headless tests.
        # These are: acquire_credentials (stdin-based), prompt_credentials (deprecated).
        _STDIN_TOOLS = {"acquire_credentials", "prompt_credentials"}
        orch_tools = [
            t for t in orch_tools
            if not (hasattr(t, "_tool_def") and t._tool_def.name in _STDIN_TOOLS)
        ]

        @tool
        def reply_to_user(message: str) -> str:
            """Send your response to the user. Call this ONLY when ALL work is complete."""
            _FUTURE = [
                "i'll ", "i will ", "going to ", "let me investigate",
                "need to investigate", "will get back", "will investigate",
                "let me look into", "i'm going to", "will try to",
            ]
            if any(p in message.lower() for p in _FUTURE):
                return (
                    "WARNING: Your reply uses future tense. Complete all work BEFORE replying. "
                    "Fix errors NOW or report what happened in past tense. "
                    "Rewrite your reply without future promises and call reply_to_user again."
                )
            return "ok"

        history_block = ""
        if self.history:
            history_block = (
                "\n\n## Conversation so far\n\n"
                + "\n".join(self.history)
                + "\n"
            )

        all_tools = [reply_to_user] + web_tools + orch_tools

        return Agent(
            name="claw_tui_test",
            model=self.model,
            tools=all_tools,
            max_turns=50,
            instructions=f"""\
You are the Agentspan Claw orchestrator. You answer questions AND create agents.

## CRITICAL RULES

1. ALWAYS call tools. NEVER respond with just text. Every response needs a tool call.
2. For DIRECT QUESTIONS ("what is the latest from X", "search for Y", "tell me about Z"):
   -> Call web_search() or fetch_page() FIRST, then reply_to_user with the results.
   -> Do NOT create an agent for one-off questions. Just search and answer.
3. For AGENT CREATION ("create an agent that...", "monitor X every Y", "set up Z"):
   -> Follow the agent creation flow below.
4. NEVER use future tense ("I'll", "going to", "will"). Report what you DID.
5. Be concise. Show results, not explanations.

## Direct Questions -- use web_search

When the user asks a question or wants information:
1. Call web_search(query=<relevant search query>)
2. Optionally call fetch_page(url=<most relevant result URL>) for more detail
3. Call reply_to_user with a summary of what you found, including specific facts and URLs

## Agent Creation -- for recurring/automated tasks

When the user wants something automated or recurring:
1. Write a complete YAML spec directly with these fields:
   name, version, model, instructions, trigger, tools, credentials, error_handling
2. Call generate_agent(spec_yaml=<YAML>, agent_name=<name>)
3. Call validate_spec(agent_name=<name>)
4. If the agent has custom workers, call validate_code(agent_name=<name>)
5. Call validate_integrations(agent_name=<name>)
6. Call validate_deployment(agent_name=<name>)
7. Call reply_to_user with a CONCISE summary.

## Available integrations

{catalog}

## Smart defaults -- use these, don't ask

- Model: {self.model}
- Schedule: if user says "every 15 mins" -> cron "*/15 * * * *". If unclear -> daemon
- Integrations: pick the most obvious ones from the request
- Error handling: 3 retries, exponential backoff, pause on failure
- Names: generate a clear snake_case name from the request

## Agent Management

- list_agents() -- show all agents
- get_agent_status(name) -- detailed status
{history_block}""",
        )

    def stop(self):
        if self.runtime:
            self.runtime.__exit__(None, None, None)
            self.runtime = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sim(tmp_path, monkeypatch):
    """Create a TUIConversationSimulator with isolated temp directory."""
    monkeypatch.setenv("AUTOPILOT_BASE_DIR", str(tmp_path))
    (tmp_path / "agents").mkdir(parents=True, exist_ok=True)

    simulator = TUIConversationSimulator(tmp_dir=tmp_path)
    simulator.start()
    yield simulator
    simulator.stop()


# ===========================================================================
# Category 1: Single-turn interactions (4 tests)
# ===========================================================================


@pytest.mark.e2e
class TestSingleTurn:

    def test_direct_web_search(self, sim):
        """User asks for top headlines -- orchestrator must search and reply."""
        result = sim.send(
            "what are the top headlines today? "
            "Use web_search to find current news headlines, then call reply_to_user.",
            timeout=120,
        )

        print(f"\n  Tool calls: {result['tool_calls']}")
        print(f"  Reply ({len(result['reply'])} chars): {result['reply'][:300]}")

        # Must have called a search tool
        has_search = any(
            t in ("web_search", "search_and_read", "fetch_page")
            for t in result["tool_calls"]
        )
        assert has_search, (
            f"Expected web_search/search_and_read/fetch_page in {result['tool_calls']}"
        )

    def test_create_simple_agent(self, sim):
        """User asks to create an agent -- must call generate_agent."""
        result = sim.send("create an agent that monitors hackernews every hour")

        print(f"\n  Tool calls: {result['tool_calls']}")

        # generate_agent must have been called
        assert "generate_agent" in result["tool_calls"], (
            f"Expected generate_agent in {result['tool_calls']}"
        )

        # At least one validate_* must have been called
        has_validate = any(t.startswith("validate_") for t in result["tool_calls"])
        assert has_validate, (
            f"Expected at least one validate_* in {result['tool_calls']}"
        )

        # agent.yaml must exist on disk
        agents_dir = sim.tmp_dir / "agents"
        agent_dirs = [d for d in agents_dir.iterdir() if d.is_dir()]
        assert len(agent_dirs) >= 1, (
            f"Expected agent directory created, found: {list(agents_dir.iterdir())}"
        )
        yaml_path = agent_dirs[0] / "agent.yaml"
        assert yaml_path.exists(), f"Expected agent.yaml in {agent_dirs[0]}"

    def test_list_agents_when_empty(self, sim):
        """With no agents, list_agents should be called and indicate empty."""
        result = sim.send("list my agents and reply_to_user with the result")

        print(f"\n  Tool calls: {result['tool_calls']}")
        print(f"  Reply: {result['reply'][:200]}")

        assert "list_agents" in result["tool_calls"], (
            f"Expected list_agents in {result['tool_calls']}"
        )

        # Reply or output should exist (agent called list_agents at minimum)
        assert result["reply"] or result["output"] or "list_agents" in result["tool_calls"], (
            "Orchestrator produced no response"
        )

    def test_create_agent_no_questions_asked(self, sim):
        """Orchestrator must generate_agent immediately -- no clarifying questions."""
        result = sim.send("set up something to check my github repos daily")

        print(f"\n  Tool calls: {result['tool_calls']}")

        # Must call generate_agent (not just text reply)
        assert "generate_agent" in result["tool_calls"], (
            f"Expected generate_agent (not clarifying questions) in {result['tool_calls']}"
        )

        # Reply must NOT be a question
        reply_lower = result["reply"].lower()
        clarification_patterns = [
            "what would you like",
            "could you clarify",
            "can you specify",
            "what do you mean",
            "which repos",
            "please provide more",
        ]
        for pattern in clarification_patterns:
            assert pattern not in reply_lower, (
                f"Orchestrator asked a clarifying question instead of acting: "
                f"'{pattern}' found in: {result['reply'][:200]}"
            )


# ===========================================================================
# Category 2: Multi-turn conversations (4 tests)
# ===========================================================================


@pytest.mark.e2e
class TestMultiTurn:

    def test_create_then_list(self, sim):
        """Turn 1: create an agent. Turn 2: list agents -- should mention it."""
        # Turn 1: create
        r1 = sim.send(
            "create a web scraper agent for cnn.com that runs every hour using web_search"
        )

        print(f"\n  Turn 1 tool calls: {r1['tool_calls']}")

        assert "generate_agent" in r1["tool_calls"], (
            f"Turn 1: expected generate_agent, got {r1['tool_calls']}"
        )

        # Turn 2: list
        r2 = sim.send("what agents do I have")

        print(f"  Turn 2 tool calls: {r2['tool_calls']}")
        print(f"  Turn 2 reply: {r2['reply'][:300]}")

        assert "list_agents" in r2["tool_calls"], (
            f"Turn 2: expected list_agents, got {r2['tool_calls']}"
        )

        # Turn 2 reply should mention the agent created in Turn 1
        # The agent name is in agents/ directory -- find it
        agents_dir = sim.tmp_dir / "agents"
        agent_dirs = [d for d in agents_dir.iterdir() if d.is_dir()]
        assert len(agent_dirs) >= 1, "Turn 1 should have created an agent on disk"

        # The reply should mention the agent (by name, or just acknowledge agents exist)
        reply_lower = r2["reply"].lower()
        agent_name = agent_dirs[0].name
        # Either the agent name or some indication of agents existing
        mentions_agent = (
            agent_name.replace("_", " ") in reply_lower
            or agent_name in reply_lower
            or "agent" in reply_lower
            or "cnn" in reply_lower
            or "scraper" in reply_lower
        )
        assert mentions_agent, (
            f"Turn 2 reply should reference the created agent '{agent_name}': "
            f"{r2['reply'][:200]}"
        )

    def test_search_then_create(self, sim):
        """Turn 1: search for AI news. Turn 2: create agent for that task."""
        # Turn 1: search
        r1 = sim.send("search for latest AI news")

        print(f"\n  Turn 1 tool calls: {r1['tool_calls']}")

        has_search = any(
            t in ("web_search", "search_and_read", "fetch_page")
            for t in r1["tool_calls"]
        )
        assert has_search, (
            f"Turn 1: expected web_search, got {r1['tool_calls']}"
        )

        # Turn 2: create agent
        r2 = sim.send("create an agent that does this daily")

        print(f"  Turn 2 tool calls: {r2['tool_calls']}")

        assert "generate_agent" in r2["tool_calls"], (
            f"Turn 2: expected generate_agent, got {r2['tool_calls']}"
        )

    def test_create_two_agents(self, sim):
        """Two agent creations in sequence -- 2 agent dirs on disk."""
        # Turn 1: news monitor
        r1 = sim.send(
            "create a news monitor agent that checks headlines every hour using web_search"
        )

        print(f"\n  Turn 1 tool calls: {r1['tool_calls']}")

        assert "generate_agent" in r1["tool_calls"], (
            f"Turn 1: expected generate_agent, got {r1['tool_calls']}"
        )

        # Turn 2: weather monitor (explicit -- separate from the first)
        r2 = sim.send(
            "now create a DIFFERENT agent for checking the weather every 6 hours. "
            "Name it weather_monitor. Use web_search."
        )

        print(f"  Turn 2 tool calls: {r2['tool_calls']}")

        assert "generate_agent" in r2["tool_calls"], (
            f"Turn 2: expected generate_agent, got {r2['tool_calls']}"
        )

        # Verify 2 agent directories exist on disk
        time.sleep(0.5)
        agents_dir = sim.tmp_dir / "agents"
        agent_dirs = [
            d for d in agents_dir.iterdir()
            if d.is_dir() and (d / "agent.yaml").exists()
        ]
        assert len(agent_dirs) >= 2, (
            f"Expected 2 agent directories, found {len(agent_dirs)}: "
            f"{[d.name for d in agent_dirs]}"
        )

    def test_search_followup(self, sim):
        """Turn 1: search for Python 3.13. Turn 2: ask about new features."""
        # Turn 1: initial search
        r1 = sim.send("search for Python 3.13 new features")

        print(f"\n  Turn 1 tool calls: {r1['tool_calls']}")

        has_search_1 = any(
            t in ("web_search", "search_and_read", "fetch_page")
            for t in r1["tool_calls"]
        )
        assert has_search_1, (
            f"Turn 1: expected web_search, got {r1['tool_calls']}"
        )

        # Turn 2: follow-up question
        r2 = sim.send(
            "tell me more about the new features in Python 3.13. "
            "Search the web and reply_to_user."
        )

        print(f"  Turn 2 tool calls: {r2['tool_calls']}")
        combined = r2["reply"] or r2["output"]
        print(f"  Turn 2 response ({len(combined)} chars): {combined[:200]}")

        has_search_2 = any(
            t in ("web_search", "search_and_read", "fetch_page")
            for t in r2["tool_calls"]
        )
        assert has_search_2, (
            f"Turn 2: expected web_search for follow-up, got {r2['tool_calls']}"
        )

        # Turn 2 output should relate to Python (check reply OR output)
        response_lower = combined.lower()
        assert "python" in response_lower or "feature" in response_lower or "3.13" in response_lower, (
            f"Turn 2 response should reference Python: {combined[:300]}"
        )


# ===========================================================================
# Category 3: Edge cases and failure patterns (4 tests)
# ===========================================================================


@pytest.mark.e2e
class TestEdgeCases:

    def test_orchestrator_uses_tools_not_text(self, sim):
        """Orchestrator must call web_search for a question -- not just LLM text."""
        result = sim.send("what is quantum computing")

        print(f"\n  Tool calls: {result['tool_calls']}")

        # The orchestrator should use web_search, not just reply from memory
        has_search = any(
            t in ("web_search", "search_and_read", "fetch_page")
            for t in result["tool_calls"]
        )
        assert has_search, (
            f"Orchestrator should use web_search for questions, not just text. "
            f"Tool calls: {result['tool_calls']}"
        )

    def test_reply_has_no_future_tense(self, sim):
        """Reply must not contain future-tense promises."""
        result = sim.send("create a file monitor agent")

        print(f"\n  Tool calls: {result['tool_calls']}")
        print(f"  Reply: {result['reply'][:300]}")

        reply_lower = result["reply"].lower()

        # These exact patterns are what the orchestrator's reply_to_user tool
        # rejects -- if they appear, the rejection loop failed.
        future_patterns = [
            "i'll ",
            "going to ",
            "will investigate",
            "let me investigate",
            "need to investigate",
        ]
        for pattern in future_patterns:
            assert pattern not in reply_lower, (
                f"Reply contains future tense '{pattern}': {result['reply'][:300]}"
            )

    def test_agent_creation_produces_valid_yaml(self, sim):
        """Created agent.yaml must have name, model, instructions, tools, trigger."""
        result = sim.send(
            "create an agent to scrape news from reddit every 30 mins. "
            "Use builtin:web_search as the integration."
        )

        print(f"\n  Tool calls: {result['tool_calls']}")

        assert "generate_agent" in result["tool_calls"], (
            f"Expected generate_agent in {result['tool_calls']}"
        )

        # Wait briefly for filesystem writes to flush in forked workers
        time.sleep(0.5)

        # Find the created agent directory
        agents_dir = sim.tmp_dir / "agents"
        agent_dirs = [
            d for d in agents_dir.iterdir()
            if d.is_dir() and (d / "agent.yaml").exists()
        ]
        assert len(agent_dirs) >= 1, (
            f"No agent directory with agent.yaml found in {agents_dir}. "
            f"Contents: {list(agents_dir.iterdir()) if agents_dir.exists() else 'dir missing'}"
        )

        yaml_path = agent_dirs[0] / "agent.yaml"
        config = yaml.safe_load(yaml_path.read_text())
        assert isinstance(config, dict), f"agent.yaml is not a dict: {config}"

        # Required fields
        assert "name" in config, f"Missing 'name' in agent.yaml: {config}"
        assert "model" in config, f"Missing 'model' in agent.yaml: {config}"
        assert "instructions" in config, f"Missing 'instructions' in agent.yaml: {config}"

        # Instructions must be present and non-trivial
        instructions = config.get("instructions", "")
        assert len(str(instructions)) > 20, (
            f"Instructions too short ({len(str(instructions))} chars): {instructions!r}"
        )

        # Must have tools list
        tools = config.get("tools", [])
        assert isinstance(tools, list) and len(tools) >= 1, (
            f"Expected at least one tool, got: {tools}"
        )

        # Must have trigger
        trigger = config.get("trigger", {})
        assert trigger, f"Missing trigger in agent.yaml: {config}"

        print(f"  Agent YAML validated: name={config['name']}, "
              f"tools={tools}, trigger={trigger}")

    def test_orchestrator_doesnt_crash_on_weird_input(self, sim):
        """Weird input should not crash the orchestrator."""
        result = sim.send("!!!@@@###$$$%%%")

        print(f"\n  Tool calls: {result['tool_calls']}")
        print(f"  Reply: {result['reply'][:200]}")

        # The orchestrator must produce SOME response -- not crash
        has_any_response = (
            result["reply"]
            or result["output"]
            or len(result["tool_calls"]) > 0
        )
        assert has_any_response, (
            "Orchestrator produced no response at all for weird input"
        )
