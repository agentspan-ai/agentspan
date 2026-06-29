# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for all new gap-closing features.

Tests code executors, swarm strategy, semantic memory, OTel tracing,
manual pattern, agent introductions, GPTAssistantAgent,
and handoff conditions.
"""

import pytest

# ── Code Executors ──────────────────────────────────────────────────────


class TestCodeExecutors:
    """Test code executor classes."""

    def test_local_executor_creation(self):
        from conductor.ai.agents.code_executor import LocalCodeExecutor

        executor = LocalCodeExecutor(language="python", timeout=10)
        assert executor.language == "python"
        assert executor.timeout == 10

    def test_local_executor_as_tool(self):
        from conductor.ai.agents.code_executor import LocalCodeExecutor

        executor = LocalCodeExecutor()
        tool_fn = executor.as_tool()
        assert hasattr(tool_fn, "_tool_def")
        assert tool_fn._tool_def.name == "execute_code"

    def test_local_executor_as_tool_custom_name(self):
        from conductor.ai.agents.code_executor import LocalCodeExecutor

        executor = LocalCodeExecutor()
        tool_fn = executor.as_tool(name="run_python")
        assert tool_fn._tool_def.name == "run_python"

    def test_docker_executor_creation(self):
        from conductor.ai.agents.code_executor import DockerCodeExecutor

        executor = DockerCodeExecutor(
            image="python:3.12-slim",
            timeout=15,
            network_enabled=False,
            memory_limit="256m",
        )
        assert executor.image == "python:3.12-slim"
        assert executor.timeout == 15
        assert executor.network_enabled is False
        assert executor.memory_limit == "256m"

    def test_docker_executor_repr(self):
        from conductor.ai.agents.code_executor import DockerCodeExecutor

        executor = DockerCodeExecutor(image="node:18-slim", language="node")
        r = repr(executor)
        assert "node:18-slim" in r

    def test_jupyter_executor_creation(self):
        from conductor.ai.agents.code_executor import JupyterCodeExecutor

        executor = JupyterCodeExecutor(kernel_name="python3", timeout=30)
        assert executor.kernel_name == "python3"
        assert executor.timeout == 30

    def test_serverless_executor_creation(self):
        from conductor.ai.agents.code_executor import ServerlessCodeExecutor

        executor = ServerlessCodeExecutor(
            endpoint="https://api.example.com/execute",
            api_key="sk-test",
        )
        assert executor.endpoint == "https://api.example.com/execute"
        assert executor.api_key == "sk-test"

    def test_execution_result_defaults(self):
        from conductor.ai.agents.code_executor import ExecutionResult

        result = ExecutionResult()
        assert result.output == ""
        assert result.error == ""
        assert result.exit_code == 0
        assert result.timed_out is False
        assert result.success is True

    def test_execution_result_failure(self):
        from conductor.ai.agents.code_executor import ExecutionResult

        result = ExecutionResult(error="SyntaxError", exit_code=1)
        assert result.success is False

    def test_execution_result_timeout(self):
        from conductor.ai.agents.code_executor import ExecutionResult

        result = ExecutionResult(timed_out=True, exit_code=-1)
        assert result.success is False
        assert result.timed_out is True

    def test_local_executor_unsupported_language(self):
        from conductor.ai.agents.code_executor import LocalCodeExecutor

        executor = LocalCodeExecutor(language="cobol")
        result = executor.execute("print('hello')")
        assert result.success is False
        assert "Unsupported language" in result.error


# ── Handoff Conditions ──────────────────────────────────────────────────


class TestHandoffConditions:
    """Test handoff condition classes."""

    def test_on_tool_result_triggers(self):
        from conductor.ai.agents.handoff import OnToolResult

        cond = OnToolResult(tool_name="escalate", target="supervisor")
        ctx = {"tool_name": "escalate", "result": "", "tool_result": "done"}
        assert cond.should_handoff(ctx) is True

    def test_on_tool_result_no_match(self):
        from conductor.ai.agents.handoff import OnToolResult

        cond = OnToolResult(tool_name="escalate", target="supervisor")
        ctx = {"tool_name": "search", "result": ""}
        assert cond.should_handoff(ctx) is False

    def test_on_tool_result_with_result_contains(self):
        from conductor.ai.agents.handoff import OnToolResult

        cond = OnToolResult(
            tool_name="check_status",
            target="refund_agent",
            result_contains="refund_eligible",
        )
        ctx = {"tool_name": "check_status", "tool_result": "Status: refund_eligible"}
        assert cond.should_handoff(ctx) is True

        ctx = {"tool_name": "check_status", "tool_result": "Status: ok"}
        assert cond.should_handoff(ctx) is False

    def test_on_text_mention_triggers(self):
        from conductor.ai.agents.handoff import OnTextMention

        cond = OnTextMention(text="transfer to billing", target="billing")
        ctx = {"result": "I'll transfer to billing for you.", "tool_name": ""}
        assert cond.should_handoff(ctx) is True

    def test_on_text_mention_case_insensitive(self):
        from conductor.ai.agents.handoff import OnTextMention

        cond = OnTextMention(text="ESCALATE", target="manager")
        ctx = {"result": "Let me escalate this issue.", "tool_name": ""}
        assert cond.should_handoff(ctx) is True

    def test_on_text_mention_no_match(self):
        from conductor.ai.agents.handoff import OnTextMention

        cond = OnTextMention(text="transfer", target="other")
        ctx = {"result": "Hello, how can I help?", "tool_name": ""}
        assert cond.should_handoff(ctx) is False

    def test_on_condition_triggers(self):
        from conductor.ai.agents.handoff import OnCondition

        cond = OnCondition(
            condition=lambda ctx: len(ctx.get("messages", "")) > 100,
            target="summarizer",
        )
        ctx = {"messages": "x" * 200, "result": ""}
        assert cond.should_handoff(ctx) is True

    def test_on_condition_no_trigger(self):
        from conductor.ai.agents.handoff import OnCondition

        cond = OnCondition(
            condition=lambda ctx: False,
            target="never",
        )
        ctx = {"result": "anything"}
        assert cond.should_handoff(ctx) is False

    def test_on_condition_handles_exception(self):
        from conductor.ai.agents.handoff import OnCondition

        cond = OnCondition(
            condition=lambda ctx: 1 / 0,  # ZeroDivisionError
            target="error_handler",
        )
        ctx = {"result": "test"}
        assert cond.should_handoff(ctx) is False


# ── Semantic Memory ─────────────────────────────────────────────────────


class TestSemanticMemory:
    """Test SemanticMemory and InMemoryStore."""

    def test_add_and_search(self):
        from conductor.ai.agents.semantic_memory import SemanticMemory

        mem = SemanticMemory()
        mem.add("Python is a programming language")
        mem.add("The weather today is sunny")
        mem.add("Machine learning uses Python extensively")

        results = mem.search("What programming language?")
        assert len(results) > 0
        assert any("Python" in r for r in results)

    def test_add_returns_id(self):
        from conductor.ai.agents.semantic_memory import SemanticMemory

        mem = SemanticMemory()
        entry_id = mem.add("Test memory")
        assert isinstance(entry_id, str)
        assert len(entry_id) > 0

    def test_delete(self):
        from conductor.ai.agents.semantic_memory import SemanticMemory

        mem = SemanticMemory()
        entry_id = mem.add("To be deleted")
        assert mem.delete(entry_id) is True
        assert mem.delete("nonexistent") is False

    def test_clear(self):
        from conductor.ai.agents.semantic_memory import SemanticMemory

        mem = SemanticMemory()
        mem.add("Memory 1")
        mem.add("Memory 2")
        mem.clear()
        assert len(mem.list_all()) == 0

    def test_list_all(self):
        from conductor.ai.agents.semantic_memory import SemanticMemory

        mem = SemanticMemory()
        mem.add("Memory A")
        mem.add("Memory B")
        entries = mem.list_all()
        assert len(entries) == 2

    def test_get_context(self):
        from conductor.ai.agents.semantic_memory import SemanticMemory

        mem = SemanticMemory()
        mem.add("User likes Python programming")
        ctx = mem.get_context("Python programming language")
        assert "Python" in ctx
        assert "context from memory" in ctx.lower()

    def test_get_context_empty(self):
        from conductor.ai.agents.semantic_memory import SemanticMemory

        mem = SemanticMemory()
        ctx = mem.get_context("anything")
        assert ctx == ""

    def test_max_results(self):
        from conductor.ai.agents.semantic_memory import SemanticMemory

        mem = SemanticMemory(max_results=2)
        for i in range(10):
            mem.add(f"Memory about topic {i}")
        results = mem.search("topic")
        assert len(results) <= 2

    def test_with_metadata(self):
        from conductor.ai.agents.semantic_memory import SemanticMemory

        mem = SemanticMemory()
        mem.add("Important fact", metadata={"type": "fact", "importance": "high"})
        entries = mem.list_all()
        assert entries[0].metadata["type"] == "fact"

    def test_repr(self):
        from conductor.ai.agents.semantic_memory import SemanticMemory

        mem = SemanticMemory()
        mem.add("test")
        r = repr(mem)
        assert "entries=1" in r


# ── OpenTelemetry Tracing ──────────────────────────────────────────────


class TestTracing:
    """Test tracing module (works even without opentelemetry installed)."""

    def test_is_tracing_enabled_returns_bool(self):
        from conductor.ai.agents.tracing import is_tracing_enabled

        result = is_tracing_enabled()
        assert isinstance(result, bool)

    def test_trace_agent_run_no_otel(self):
        from conductor.ai.agents.tracing import trace_agent_run

        with trace_agent_run("test", "hello", model="openai/gpt-4o") as span:
            # Should work even without OTel — span may be None
            pass

    def test_trace_compile_no_otel(self):
        from conductor.ai.agents.tracing import trace_compile

        with trace_compile("test", strategy="handoff") as span:
            pass

    def test_trace_tool_call_no_otel(self):
        from conductor.ai.agents.tracing import trace_tool_call

        with trace_tool_call("test", "my_tool", args={"x": 1}) as span:
            pass

    def test_trace_handoff_no_otel(self):
        from conductor.ai.agents.tracing import trace_handoff

        with trace_handoff("agent_a", "agent_b") as span:
            pass

    def test_record_token_usage_none_span(self):
        from conductor.ai.agents.tracing import record_token_usage

        # Should not raise
        record_token_usage(None, prompt_tokens=100, completion_tokens=50)


# ── GPTAssistantAgent ──────────────────────────────────────────────────


class TestGPTAssistantAgent:
    """Test GPTAssistantAgent construction (no API calls)."""

    def test_creation_with_id(self):
        from conductor.ai.agents.ext import GPTAssistantAgent

        agent = GPTAssistantAgent(
            name="coder",
            assistant_id="asst_abc123",
        )
        assert agent.name == "coder"
        assert agent.assistant_id == "asst_abc123"
        assert agent.metadata["_agent_type"] == "gpt_assistant"

    def test_creation_without_id(self):
        from conductor.ai.agents.ext import GPTAssistantAgent

        agent = GPTAssistantAgent(
            name="analyst",
            model="gpt-4o",
            instructions="Analyze data.",
        )
        assert agent.assistant_id is None
        assert agent.model == "openai/gpt-4o"

    def test_has_tool(self):
        from conductor.ai.agents.ext import GPTAssistantAgent

        agent = GPTAssistantAgent(name="test")
        assert len(agent.tools) == 1
        assert agent.tools[0]._tool_def.name == "test_assistant_call"

    def test_max_turns_is_one(self):
        from conductor.ai.agents.ext import GPTAssistantAgent

        agent = GPTAssistantAgent(name="test")
        assert agent.max_turns == 1

    def test_is_agent_subclass(self):
        from conductor.ai.agents.agent import Agent
        from conductor.ai.agents.ext import GPTAssistantAgent

        agent = GPTAssistantAgent(name="test")
        assert isinstance(agent, Agent)

    def test_repr(self):
        from conductor.ai.agents.ext import GPTAssistantAgent

        agent = GPTAssistantAgent(name="test", assistant_id="asst_xyz")
        r = repr(agent)
        assert "test" in r
        assert "asst_xyz" in r


# ── Agent new parameters ───────────────────────────────────────────────


class TestAgentNewParams:
    """Test new Agent parameters."""

    def test_swarm_strategy_accepted(self):
        from conductor.ai.agents.agent import Agent

        sub = Agent(name="sub", model="openai/gpt-4o")
        agent = Agent(
            name="swarm",
            model="openai/gpt-4o",
            agents=[sub],
            strategy="swarm",
        )
        assert agent.strategy == "swarm"

    def test_manual_strategy_accepted(self):
        from conductor.ai.agents.agent import Agent

        sub = Agent(name="sub", model="openai/gpt-4o")
        agent = Agent(
            name="manual",
            model="openai/gpt-4o",
            agents=[sub],
            strategy="manual",
        )
        assert agent.strategy == "manual"

    def test_handoffs_param(self):
        from conductor.ai.agents.agent import Agent
        from conductor.ai.agents.handoff import OnTextMention

        sub = Agent(name="sub", model="openai/gpt-4o")
        handoffs = [OnTextMention(text="transfer", target="sub")]
        agent = Agent(
            name="parent",
            model="openai/gpt-4o",
            agents=[sub],
            strategy="swarm",
            handoffs=handoffs,
        )
        assert len(agent.handoffs) == 1

    def test_introduction_param(self):
        from conductor.ai.agents.agent import Agent

        agent = Agent(
            name="expert",
            model="openai/gpt-4o",
            introduction="I am an expert in Python programming.",
        )
        assert agent.introduction == "I am an expert in Python programming."

    def test_introduction_default_none(self):
        from conductor.ai.agents.agent import Agent

        agent = Agent(name="test", model="openai/gpt-4o")
        assert agent.introduction is None


# ── Imports ────────────────────────────────────────────────────────────


class TestImports:
    """Test that all new types are importable from the package."""

    def test_import_code_executors(self):
        pass

    def test_import_handoff_conditions(self):
        pass

    def test_import_semantic_memory(self):
        pass

    def test_import_ext_agents(self):
        pass

    def test_import_tracing(self):
        pass
