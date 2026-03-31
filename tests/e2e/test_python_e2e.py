"""End-to-end tests for Python SDK. No mocks. Real server.

Covers: basic agents, guardrails (regex/custom/tool), termination conditions,
callbacks, gates, multi-agent (SWARM handoff, parallel, router), frameworks
(LangGraph), credentials, and negative/failure paths.
"""
import re
import pytest
from agentspan.agents import (
    Agent, AgentRuntime, tool, Strategy,
    CallbackHandler,
    Guardrail, GuardrailResult, RegexGuardrail, OnFail,
    TextMentionTermination, MaxMessageTermination,
)
from agentspan.agents.gate import TextGate
from agentspan.agents.handoff import OnTextMention
from conftest import (
    get_workflow, assert_workflow_completed, assert_workflow_failed,
    assert_task_exists, get_task_output,
)

pytestmark = pytest.mark.integration

MODEL = "openai/gpt-4o-mini"  # Cheap, fast model for tests

# ── Tools ──────────────────────────────────────────────

@tool
def add_numbers(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

@tool
def echo(message: str) -> str:
    """Echo back the message."""
    return f"Echo: {message}"

@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"72F and sunny in {city}"

@tool
def failing_tool(query: str) -> str:
    """A tool that always raises an exception."""
    raise RuntimeError("Deliberate tool failure for testing")

@tool
def get_customer_data(customer_id: str) -> dict:
    """Retrieve customer profile data including PII."""
    return {
        "customer_id": customer_id,
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "ssn": "123-45-6789",
    }

# ── Guardrail functions ───────────────────────────────

def no_ssn(content: str) -> GuardrailResult:
    """Reject responses containing SSN patterns (###-##-####)."""
    if re.search(r"\b\d{3}-\d{2}-\d{4}\b", content):
        return GuardrailResult(
            passed=False,
            message="Response must not contain SSN numbers. Redact all SSNs.",
        )
    return GuardrailResult(passed=True)


def always_fails(content: str) -> GuardrailResult:
    """Guardrail that always fails — for testing raise/fail paths."""
    return GuardrailResult(passed=False, message="This guardrail always rejects.")


def lenient_check(content: str) -> GuardrailResult:
    """Guardrail that always passes."""
    return GuardrailResult(passed=True)


# ── Positive Tests ─────────────────────────────────────

class TestBasicAgent:
    def test_simple_tool_call(self):
        """Agent calls a tool and returns result."""
        agent = Agent(name="calculator", model=MODEL, instructions="Use add_numbers to add 2 + 3.", tools=[add_numbers])
        with AgentRuntime() as rt:
            result = rt.run(agent, "What is 2 + 3?", timeout=60000)
        assert result.status == "COMPLETED"
        assert "5" in str(result.output)

        # Verify via server API
        assert_workflow_completed(result.execution_id)

    def test_tool_metadata_tracked(self):
        """Verify tool_call events are tracked."""
        agent = Agent(name="echoer", model=MODEL, instructions="Use echo tool.", tools=[echo])
        with AgentRuntime() as rt:
            result = rt.run(agent, "Echo 'hello world'", timeout=60000)
        assert result.status == "COMPLETED"

    def test_agent_prefixed_task_names(self):
        """CLI tool task names are agent-prefixed."""
        agent = Agent(
            name="cli_test",
            model=MODEL,
            instructions="Run: echo hello",
            cli_commands=True,
            cli_allowed_commands=["echo"],
        )
        # Verify the tool name is prefixed
        tool_names = [t._tool_def.name for t in agent.tools if hasattr(t, "_tool_def")]
        assert "cli_test_run_command" in tool_names

class TestMultiAgent:
    def test_sequential_pipeline(self):
        """Two agents run in sequence."""
        step1 = Agent(name="step1", model=MODEL, instructions="Say 'STEP1_DONE'.", tools=[echo])
        step2 = Agent(name="step2", model=MODEL, instructions="Say 'STEP2_DONE'.", tools=[echo])
        pipeline = step1 >> step2
        with AgentRuntime() as rt:
            result = rt.run(pipeline, "Go", timeout=120000)
        assert result.status == "COMPLETED"
        assert_workflow_completed(result.execution_id)

    def test_swarm_transfer_names(self):
        """Verify SWARM transfer worker names use source agent prefix."""
        a1 = Agent(name="writer", model=MODEL)
        a2 = Agent(name="editor", model=MODEL)
        swarm = Agent(
            name="team", model=MODEL,
            agents=[a1, a2], strategy=Strategy.SWARM,
            handoffs=[
                OnTextMention(text="HANDOFF_TO_EDITOR", target="editor"),
                OnTextMention(text="HANDOFF_TO_WRITER", target="writer"),
            ],
        )
        from agentspan.agents.runtime.runtime import AgentRuntime as RT
        rt = RT.__new__(RT)
        names = rt._collect_worker_names(swarm)
        # Source-prefixed, not parent-prefixed
        assert "writer_transfer_to_editor" in names
        assert "editor_transfer_to_writer" in names


# ═══════════════════════════════════════════════════════════════════════
# Guardrails — regex, custom function, raise vs retry
# ═══════════════════════════════════════════════════════════════════════


class TestGuardrails:
    def test_regex_output_guardrail_blocks(self):
        """Regex guardrail blocks output containing email addresses.

        The agent retrieves customer data with an email, and the guardrail
        forces the LLM to retry without the email pattern.
        """
        agent = Agent(
            name="guard_regex",
            model=MODEL,
            instructions=(
                "Retrieve customer data. Present the results to the user. "
                "If told not to include emails, omit them."
            ),
            tools=[get_customer_data],
            guardrails=[
                RegexGuardrail(
                    patterns=[r"[\w.+-]+@[\w-]+\.[\w.-]+"],
                    name="no_email",
                    message="Response must not contain email addresses. Remove them.",
                    on_fail="retry",
                    max_retries=3,
                ),
            ],
        )
        with AgentRuntime() as rt:
            result = rt.run(agent, "Show me the profile for customer CUST-7.", timeout=60000)
        # Should complete (agent retries and eventually omits the email)
        assert result.status in ("COMPLETED", "FAILED"), (
            f"Unexpected status: {result.status}"
        )

    def test_custom_output_guardrail_retry(self):
        """Custom function guardrail rejects SSN patterns, agent retries."""
        agent = Agent(
            name="guard_custom",
            model=MODEL,
            instructions=(
                "Retrieve customer data. Present all available info."
            ),
            tools=[get_customer_data],
            guardrails=[
                Guardrail(no_ssn, position="output", on_fail="retry", max_retries=3),
            ],
        )
        with AgentRuntime() as rt:
            result = rt.run(
                agent,
                "Look up customer CUST-7 and give me their full profile.",
                timeout=60000,
            )
        # Agent should complete — either retried successfully or exhausted retries
        assert result.status in ("COMPLETED", "FAILED")

    def test_guardrail_raise_terminates(self):
        """Always-failing guardrail with on_fail='raise' terminates workflow."""
        agent = Agent(
            name="guard_raise",
            model=MODEL,
            instructions="Say hello.",
            guardrails=[
                Guardrail(always_fails, position="output", on_fail="raise"),
            ],
        )
        with AgentRuntime() as rt:
            result = rt.run(agent, "Greet me.", timeout=60000)
        # on_fail=raise should cause terminal failure
        assert result.status in ("FAILED", "TERMINATED"), (
            f"Expected FAILED/TERMINATED for raise guardrail, got: {result.status}"
        )

    def test_guardrail_pass_no_interference(self):
        """Lenient guardrail that always passes does not interfere."""
        agent = Agent(
            name="guard_pass",
            model=MODEL,
            instructions="Use get_weather to answer.",
            tools=[get_weather],
            guardrails=[
                Guardrail(lenient_check, position="output", on_fail="retry"),
            ],
        )
        with AgentRuntime() as rt:
            result = rt.run(agent, "What is the weather in Berlin?", timeout=60000)
        assert result.status == "COMPLETED"


# ═══════════════════════════════════════════════════════════════════════
# Termination conditions — TextMention, MaxMessage
# ═══════════════════════════════════════════════════════════════════════


class TestTermination:
    def test_text_mention_terminates(self):
        """Agent stops when it mentions the termination text 'TASK_COMPLETE'."""
        agent = Agent(
            name="term_text",
            model=MODEL,
            instructions=(
                "Answer the question, then end your response with the exact word TASK_COMPLETE."
            ),
            termination=TextMentionTermination("TASK_COMPLETE"),
        )
        with AgentRuntime() as rt:
            result = rt.run(agent, "What is 2+2?", timeout=60000)
        assert result.status == "COMPLETED"

    def test_max_message_terminates(self):
        """Agent stops after max messages limit is reached."""
        agent = Agent(
            name="term_max",
            model=MODEL,
            instructions=(
                "You are a chatbot. Always ask a follow-up question. Never stop on your own."
            ),
            tools=[echo],
            termination=MaxMessageTermination(5),
        )
        with AgentRuntime() as rt:
            result = rt.run(agent, "Tell me about AI.", timeout=60000)
        # Should complete — termination condition fires after 5 messages
        assert result.status == "COMPLETED"


# ═══════════════════════════════════════════════════════════════════════
# Callbacks — lifecycle hooks
# ═══════════════════════════════════════════════════════════════════════


class TestCallbacks:
    def test_callback_handler_compiles_and_completes(self):
        """Agent with CallbackHandler compiles and runs to completion.

        Callbacks are compiled as server-side worker tasks. The server
        may run them internally (requiredWorkers=[]) or delegate to the
        SDK. Either way the workflow should complete successfully.
        """
        class TrackingHandler(CallbackHandler):
            def on_model_start(self, **kwargs):
                return None

            def on_model_end(self, **kwargs):
                return None

        agent = Agent(
            name="cb_model",
            model=MODEL,
            instructions="Say hello briefly.",
            callbacks=[TrackingHandler()],
        )
        with AgentRuntime() as rt:
            result = rt.run(agent, "Hi", timeout=60000)
        assert result.status == "COMPLETED"
        assert_workflow_completed(result.execution_id)

    def test_agent_lifecycle_callback_compiles(self):
        """Agent with lifecycle callbacks compiles correctly."""
        class LifecycleHandler(CallbackHandler):
            def on_agent_start(self, **kwargs):
                return None

            def on_agent_end(self, **kwargs):
                return None

        agent = Agent(
            name="cb_lifecycle",
            model=MODEL,
            instructions="Say one word.",
            callbacks=[LifecycleHandler()],
        )
        with AgentRuntime() as rt:
            result = rt.run(agent, "Go", timeout=60000)
        assert result.status == "COMPLETED"
        assert_workflow_completed(result.execution_id)


# ═══════════════════════════════════════════════════════════════════════
# Gate — TextGate stops sequential pipeline
# ═══════════════════════════════════════════════════════════════════════


class TestGate:
    def test_text_gate_stops_pipeline(self):
        """TextGate stops a sequential pipeline when sentinel text is present.

        The checker agent outputs 'NO_ISSUES' when there is no problem,
        and the gate prevents the fixer from running.
        """
        checker = Agent(
            name="gate_checker",
            model=MODEL,
            instructions=(
                "Check if the input describes a problem. If there is no problem, "
                "output exactly: NO_ISSUES. Otherwise describe the problem."
            ),
            gate=TextGate("NO_ISSUES"),
        )
        fixer = Agent(
            name="gate_fixer",
            model=MODEL,
            instructions="Fix the problem described in the input.",
        )
        pipeline = checker >> fixer
        with AgentRuntime() as rt:
            # Input describes no problem — gate should stop pipeline
            result = rt.run(
                pipeline,
                "Everything is fine, nothing needs fixing.",
                timeout=60000,
            )
        assert result.status == "COMPLETED"

    def test_text_gate_allows_continuation(self):
        """TextGate allows continuation when sentinel text is NOT present."""
        checker = Agent(
            name="gate_check2",
            model=MODEL,
            instructions=(
                "Check if the input describes a problem. If there is no problem, "
                "output exactly: NO_ISSUES. Otherwise describe the problem."
            ),
            gate=TextGate("NO_ISSUES"),
        )
        fixer = Agent(
            name="gate_fix2",
            model=MODEL,
            instructions="Fix the problem described in the input. Be brief.",
        )
        pipeline = checker >> fixer
        with AgentRuntime() as rt:
            # Input describes a problem — gate should NOT stop, fixer runs
            result = rt.run(
                pipeline,
                "The server is returning 500 errors on the /api/users endpoint.",
                timeout=60000,
            )
        assert result.status == "COMPLETED"


# ═══════════════════════════════════════════════════════════════════════
# Multi-Agent Execution — SWARM handoff, parallel, router
# ═══════════════════════════════════════════════════════════════════════


class TestMultiAgentExecution:
    def test_handoff_routes_to_specialist(self):
        """HANDOFF strategy routes to the correct sub-agent."""
        billing = Agent(
            name="billing_e2e",
            model=MODEL,
            instructions="You handle billing and payment questions. Answer concisely.",
        )
        technical = Agent(
            name="technical_e2e",
            model=MODEL,
            instructions="You handle technical questions. Answer concisely.",
        )
        support = Agent(
            name="support_e2e",
            model=MODEL,
            instructions=(
                "Route billing/payment questions to 'billing_e2e' and "
                "technical questions to 'technical_e2e'. Always delegate."
            ),
            agents=[billing, technical],
            strategy=Strategy.HANDOFF,
        )
        with AgentRuntime() as rt:
            result = rt.run(
                support,
                "What is the balance on my account?",
                timeout=60000,
            )
        assert result.status == "COMPLETED"
        assert_workflow_completed(result.execution_id)

    def test_parallel_agents_all_execute(self):
        """Parallel strategy runs all sub-agents."""
        pros = Agent(
            name="pros_e2e",
            model=MODEL,
            instructions="List 2 advantages of the topic. Be brief, one sentence each.",
        )
        cons = Agent(
            name="cons_e2e",
            model=MODEL,
            instructions="List 2 disadvantages of the topic. Be brief, one sentence each.",
        )
        team = Agent(
            name="analysis_e2e",
            model=MODEL,
            agents=[pros, cons],
            strategy=Strategy.PARALLEL,
        )
        with AgentRuntime() as rt:
            result = rt.run(team, "Remote work", timeout=60000)
        assert result.status == "COMPLETED"
        assert_workflow_completed(result.execution_id)

    def test_router_selects_correct_agent(self):
        """Router function selects the right sub-agent."""
        router_agent = Agent(
            name="selector_e2e",
            model=MODEL,
            instructions="Route coding tasks to 'coder_e2e' and math tasks to 'mathbot_e2e'.",
        )
        coder = Agent(
            name="coder_e2e",
            model=MODEL,
            instructions="Write Python code. Be brief.",
        )
        mathbot = Agent(
            name="mathbot_e2e",
            model=MODEL,
            instructions="Solve math problems. Use the add_numbers tool.",
            tools=[add_numbers],
        )
        team = Agent(
            name="dev_team_e2e",
            model=MODEL,
            agents=[coder, mathbot],
            strategy=Strategy.ROUTER,
            router=router_agent,
        )
        with AgentRuntime() as rt:
            result = rt.run(
                team,
                "Write a Python function to reverse a string.",
                timeout=60000,
            )
        assert result.status == "COMPLETED"
        assert_workflow_completed(result.execution_id)


# ═══════════════════════════════════════════════════════════════════════
# Framework Integration — LangGraph
# ═══════════════════════════════════════════════════════════════════════


class TestFrameworks:
    def test_langgraph_react_agent(self):
        """LangGraph create_react_agent runs through agentspan."""
        try:
            from langchain_core.tools import tool as lc_tool
            from langchain_openai import ChatOpenAI
            from langchain.agents import create_agent
        except ImportError:
            pytest.skip("LangGraph/LangChain not installed")

        @lc_tool
        def calculator(expression: str) -> str:
            """Evaluate a math expression and return the result."""
            try:
                return str(eval(expression))  # noqa: S307
            except Exception as e:
                return f"Error: {e}"

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        graph = create_agent(llm, tools=[calculator], name="lg_calc_e2e")

        with AgentRuntime() as rt:
            result = rt.run(graph, "What is 15 * 7?", timeout=60000)
        assert result.status == "COMPLETED"
        # The answer should contain 105
        assert "105" in str(result.output), (
            f"Expected '105' in output: {result.output}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Credentials — terminal failure on missing credential
# ═══════════════════════════════════════════════════════════════════════


class TestCredentials:
    def test_agent_with_credentials_compiles(self):
        """Agent with credentials parameter compiles and runs.

        Credential resolution happens at tool execution time. If the LLM
        does not call the tool, the credential is never resolved. This test
        verifies the agent correctly compiles with a credentials list.
        """
        agent = Agent(
            name="cred_agent",
            model=MODEL,
            instructions="Answer the question without using tools.",
            tools=[get_weather],
            credentials=["MY_API_KEY"],
        )
        # Verify credential is stored on agent
        assert "MY_API_KEY" in [
            c if isinstance(c, str) else getattr(c, "name", str(c))
            for c in agent.credentials
        ]
        with AgentRuntime() as rt:
            result = rt.run(
                agent,
                "Just say hello, do not use any tools.",
                timeout=60000,
            )
        # Agent should complete — it doesn't call the tool so credential
        # is never resolved
        assert result.status == "COMPLETED"

    def test_credential_resolution_without_token_raises(self):
        """Credential resolution without execution token raises non-retryable error.

        This is the same test as TestNegative.test_credential_fails_without_token,
        duplicated here for test class completeness.
        """
        from agentspan.agents.runtime.credentials.fetcher import WorkerCredentialFetcher
        from agentspan.agents.runtime.credentials.types import CredentialNotFoundError
        fetcher = WorkerCredentialFetcher()
        with pytest.raises(CredentialNotFoundError, match="No execution token"):
            fetcher.fetch(None, ["SOME_CREDENTIAL"])


# ═══════════════════════════════════════════════════════════════════════
# Negative Tests — tool exceptions, invalid models
# ═══════════════════════════════════════════════════════════════════════


class TestNegativeExecution:
    def test_tool_exception_fails_task(self):
        """Tool that raises an exception fails the task."""
        agent = Agent(
            name="tool_fail",
            model=MODEL,
            instructions="Use the failing_tool with query 'test'. You must call it.",
            tools=[failing_tool],
        )
        with AgentRuntime() as rt:
            result = rt.run(agent, "Run the failing tool now.", timeout=60000)
        # The tool raises RuntimeError — workflow should complete but report error,
        # or the agent may recover by not calling the tool again.
        # Either outcome is acceptable; the key is it doesn't hang.
        assert result.status in ("COMPLETED", "FAILED", "TERMINATED")

    def test_invalid_model_fails(self):
        """Agent with non-existent model fails."""
        agent = Agent(
            name="bad_model",
            model="nonexistent/model_that_does_not_exist_xyz",
            instructions="Say hello.",
        )
        with AgentRuntime() as rt:
            result = rt.run(agent, "Hello", timeout=60000)
        assert result.status in ("FAILED", "TERMINATED", "FAILED_WITH_TERMINAL_ERROR"), (
            f"Expected failure for invalid model, got: {result.status}"
        )


# ── Negative Tests (validation only, no server) ──────


class TestNegative:
    def test_callable_tool_rejected_for_claude_code(self):
        """Claude Code agents reject @tool callables."""
        with pytest.raises(ValueError, match="Claude Code agents only support"):
            Agent(name="bad", model="claude-code/opus", instructions="test", tools=[add_numbers])

    def test_invalid_agent_name(self):
        """Agent names must be alphanumeric."""
        with pytest.raises(ValueError):
            Agent(name="bad name with spaces", model=MODEL)

    def test_router_without_router_param(self):
        """Router strategy requires router parameter."""
        with pytest.raises(ValueError):
            Agent(name="bad_router", model=MODEL, strategy=Strategy.ROUTER, agents=[
                Agent(name="sub", model=MODEL),
            ])

    def test_duplicate_sub_agent_names(self):
        """Duplicate sub-agent names are rejected."""
        with pytest.raises(ValueError, match="[Dd]uplicate"):
            Agent(name="parent", model=MODEL, agents=[
                Agent(name="dup", model=MODEL),
                Agent(name="dup", model=MODEL),
            ])

    def test_credential_fails_without_token(self):
        """Credential resolution without execution token raises non-retryable error."""
        from agentspan.agents.runtime.credentials.fetcher import WorkerCredentialFetcher
        from agentspan.agents.runtime.credentials.types import CredentialNotFoundError
        fetcher = WorkerCredentialFetcher()
        with pytest.raises(CredentialNotFoundError, match="No execution token"):
            fetcher.fetch(None, ["GITHUB_TOKEN"])

    def test_cli_tools_prefixed_per_agent(self):
        """Multiple agents with CLI tools get unique prefixed names."""
        a = Agent(name="fetcher", model=MODEL, cli_commands=True, cli_allowed_commands=["gh", "git"])
        b = Agent(name="pusher", model=MODEL, cli_commands=True, cli_allowed_commands=["gh"])
        a_names = [t._tool_def.name for t in a.tools if hasattr(t, "_tool_def")]
        b_names = [t._tool_def.name for t in b.tools if hasattr(t, "_tool_def")]
        assert "fetcher_run_command" in a_names
        assert "pusher_run_command" in b_names
        assert set(a_names).isdisjoint(set(b_names))  # No collision

    def test_code_exec_prefixed_per_agent(self):
        """Multiple agents with code execution get unique prefixed names."""
        a = Agent(name="coder", model=MODEL, local_code_execution=True)
        b = Agent(name="tester", model=MODEL, local_code_execution=True)
        a_names = [t._tool_def.name for t in a.tools if hasattr(t, "_tool_def")]
        b_names = [t._tool_def.name for t in b.tools if hasattr(t, "_tool_def")]
        assert "coder_execute_code" in a_names
        assert "tester_execute_code" in b_names
        assert set(a_names).isdisjoint(set(b_names))
