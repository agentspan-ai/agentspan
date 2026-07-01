"""Suite 10: Code Execution — compilation and runtime behavior of code execution agents.

Tests the code execution feature across executor types:
  - Compilation: CodeExecutionConfig reflected in plan JSON
  - Tool naming: multi-agent name-prefix avoids collisions
  - Local Python and Bash execution with deterministic output
  - Language restriction enforcement
  - Timeout enforcement
  - Docker execution (skipped if Docker unavailable)
  - Docker network isolation (skipped if Docker unavailable)
  - Jupyter stateful execution (skipped if jupyter_client unavailable)

Each test uses a purpose-built agent to isolate behavior.
Validation is algorithmic — check workflow task data for deterministic code output.
No LLM output parsing. No mocks. Real server, real LLM.
"""

import os
import subprocess

import pytest
import requests

from conductor.ai.agents import Agent, CodeExecutionConfig
from conductor.ai.agents.code_executor import (
    DockerCodeExecutor,
    JupyterCodeExecutor,
    LocalCodeExecutor,
)

pytestmark = [
    pytest.mark.e2e,
]

TIMEOUT = 300  # Code execution needs extra time for worker registration + execution


# ===================================================================
# Skip condition helpers
# ===================================================================


def _docker_available() -> bool:
    """Return True if Docker daemon is running and healthy."""
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def _jupyter_available() -> bool:
    """Return True if jupyter_client is importable."""
    try:
        import jupyter_client  # noqa: F401

        return True
    except ImportError:
        return False


skip_no_docker = pytest.mark.skipif(not _docker_available(), reason="Docker not available")
skip_no_jupyter = pytest.mark.skipif(
    not _jupyter_available(), reason="jupyter_client not installed"
)


# ===================================================================
# Helpers
# ===================================================================


def _get_workflow(execution_id):
    """Fetch workflow execution from server API."""
    base = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
    base_url = base.rstrip("/").replace("/api", "")
    resp = requests.get(f"{base_url}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _get_output_text(result):
    """Extract the text output from a run result."""
    output = result.output
    if isinstance(output, dict):
        results = output.get("result", [])
        if results:
            texts = []
            for r in results:
                if isinstance(r, dict):
                    texts.append(r.get("text", r.get("content", str(r))))
                else:
                    texts.append(str(r))
            return "".join(texts)
        return str(output)
    return str(output) if output else ""


def _run_diagnostic(result):
    """Build a diagnostic string from a run result for error messages."""
    parts = [f"status={result.status}", f"execution_id={result.execution_id}"]
    output = result.output
    if isinstance(output, dict):
        parts.append(f"output_keys={list(output.keys())}")
        if "finishReason" in output:
            parts.append(f"finishReason={output['finishReason']}")
    return " | ".join(parts)


def _find_execute_code_tasks(execution_id):
    """Find tasks in a workflow whose referenceTaskName or taskDefName contains 'execute_code'."""
    wf = _get_workflow(execution_id)
    matched = []
    for task in wf.get("tasks", []):
        ref = task.get("referenceTaskName", "")
        task_def = task.get("taskDefName", "")
        if "execute_code" in ref or "execute_code" in task_def:
            matched.append(task)
    return matched


def _task_output_str(task):
    """Convert a task's outputData to a string for searching."""
    return str(task.get("outputData", {}))


# ===================================================================
# Agent factories
# ===================================================================


def _agent_code_compile(model):
    """Agent with explicit CodeExecutionConfig for compilation testing."""
    return Agent(
        name="e2e_ce_compile",
        model=model,
        code_execution=CodeExecutionConfig(
            allowed_languages=["python", "bash"],
            timeout=30,
        ),
        instructions="You can execute Python and Bash code.",
    )


def _agent_local_code(model):
    """Agent with local code execution, Python + Bash."""
    return Agent(
        name="e2e_ce_local",
        model=model,
        local_code_execution=True,
        allowed_languages=["python", "bash"],
        instructions=(
            "You can execute code. When asked to compute something, "
            "write code in the specified language that prints the result "
            "and execute it using the execute_code tool."
        ),
    )


def _agent_python_only(model):
    """Agent restricted to Python only — no Bash."""
    return Agent(
        name="e2e_ce_local",  # Same name as _agent_local_code to reuse worker
        model=model,
        local_code_execution=True,
        allowed_languages=["python"],
        instructions=(
            "You can execute code. When asked to run code, execute it using "
            "your execute_code tool. You MUST use the tool."
        ),
    )


def _agent_short_timeout(model):
    """Agent with a very short timeout for timeout testing."""
    return Agent(
        name="e2e_ce_local",  # Same name to reuse worker
        model=model,
        max_turns=2,  # Don't let LLM retry many times after timeout
        code_execution=CodeExecutionConfig(
            allowed_languages=["python"],
            executor=LocalCodeExecutor(language="python", timeout=3),
            timeout=3,
        ),
        instructions=(
            "You can execute Python code. When asked to run code, execute it "
            "using your execute_code tool exactly as provided. Do not modify the code."
        ),
    )


def _agent_docker_python(model):
    """Agent with DockerCodeExecutor for Python."""
    return Agent(
        name="e2e_ce_docker_py",
        model=model,
        code_execution=CodeExecutionConfig(
            allowed_languages=["python"],
            executor=DockerCodeExecutor(image="python:3.12-slim", timeout=30),
            timeout=30,
        ),
        instructions=(
            "You can execute Python code in a Docker container. "
            "When asked to compute something, write Python code that prints "
            "the result and execute it."
        ),
    )


def _agent_docker_no_network(model):
    """Agent with DockerCodeExecutor, network disabled."""
    return Agent(
        name="e2e_ce_docker_nonet",
        model=model,
        code_execution=CodeExecutionConfig(
            allowed_languages=["python"],
            executor=DockerCodeExecutor(
                image="python:3.12-slim",
                timeout=30,
                network_enabled=False,
            ),
            timeout=30,
        ),
        instructions=(
            "You can execute Python code in a Docker container with no network. "
            "When asked to run code, execute it using your execute_code tool."
        ),
    )


def _agent_jupyter(model):
    """Agent with JupyterCodeExecutor for stateful execution."""
    return Agent(
        name="e2e_ce_jupyter",
        model=model,
        code_execution=CodeExecutionConfig(
            allowed_languages=["python"],
            executor=JupyterCodeExecutor(timeout=30),
            timeout=30,
        ),
        instructions=(
            "You can execute Python code in a Jupyter kernel. State persists "
            "across calls. When asked to run code, execute it using your "
            "execute_code tool exactly as provided."
        ),
    )


# ===================================================================
# Tests
# ===================================================================


@pytest.fixture(scope="class")
def ce_runtime():
    """Fresh runtime for code execution tests — avoids stale workers from other suites."""
    from conductor.ai.agents import AgentRuntime

    with AgentRuntime() as rt:
        yield rt


@pytest.mark.timeout(1800)
class TestSuite10CodeExecution:
    """Code execution: compilation, local/docker/jupyter execution, restrictions."""

    # -- Compilation -------------------------------------------------------

    def test_code_execution_compiles(self, runtime, model):
        """CodeExecutionConfig is reflected correctly in plan JSON.

        Asserts:
          - agentDef has codeExecution.enabled == True
          - codeExecution.allowedLanguages contains python and bash
          - codeExecution.timeout == 30
          - A tool named *_execute_code exists with toolType worker
        """
        agent = _agent_code_compile(model)
        plan = runtime.plan(agent)

        ad = plan["workflowDef"]["metadata"]["agentDef"]

        # codeExecution block
        ce = ad.get("codeExecution")
        assert ce is not None, (
            f"[Compile] agentDef missing 'codeExecution'. agentDef keys: {list(ad.keys())}"
        )
        assert ce["enabled"] is True, (
            f"[Compile] codeExecution.enabled is {ce['enabled']}, expected True"
        )
        allowed_langs = ce.get("allowedLanguages", [])
        assert "python" in allowed_langs, (
            f"[Compile] 'python' not in allowedLanguages: {allowed_langs}"
        )
        assert "bash" in allowed_langs, f"[Compile] 'bash' not in allowedLanguages: {allowed_langs}"
        assert ce.get("timeout") == 30, (
            f"[Compile] codeExecution.timeout is {ce.get('timeout')}, expected 30"
        )

        # Tool named *_execute_code
        tools = ad.get("tools", [])
        exec_tools = [t for t in tools if "execute_code" in t.get("name", "")]
        assert len(exec_tools) >= 1, (
            f"[Compile] No tool containing 'execute_code' in agentDef.tools. "
            f"Tool names: {[t.get('name') for t in tools]}"
        )
        exec_tool = exec_tools[0]
        assert exec_tool.get("name") == "e2e_ce_compile_execute_code", (
            f"[Compile] Expected tool name 'e2e_ce_compile_execute_code', "
            f"got '{exec_tool.get('name')}'"
        )
        assert exec_tool.get("toolType") == "worker", (
            f"[Compile] Expected toolType 'worker', got '{exec_tool.get('toolType')}'"
        )

    # -- Multi-agent tool naming -------------------------------------------

    def test_tool_naming_multi_agent(self, runtime, model):
        """Two agents with code execution have non-colliding tool names.

        agent_a gets agent_a_execute_code, agent_b gets agent_b_execute_code.
        Plan-only test.
        """
        agent_a = Agent(
            name="agent_a",
            model=model,
            code_execution=CodeExecutionConfig(allowed_languages=["python"]),
            instructions="Agent A.",
        )
        agent_b = Agent(
            name="agent_b",
            model=model,
            code_execution=CodeExecutionConfig(allowed_languages=["python"]),
            instructions="Agent B.",
        )

        plan_a = runtime.plan(agent_a)
        plan_b = runtime.plan(agent_b)

        ad_a = plan_a["workflowDef"]["metadata"]["agentDef"]
        ad_b = plan_b["workflowDef"]["metadata"]["agentDef"]

        tools_a = [t.get("name") for t in ad_a.get("tools", [])]
        tools_b = [t.get("name") for t in ad_b.get("tools", [])]

        assert "agent_a_execute_code" in tools_a, (
            f"[MultiAgent] 'agent_a_execute_code' not in agent_a tools: {tools_a}"
        )
        assert "agent_b_execute_code" in tools_b, (
            f"[MultiAgent] 'agent_b_execute_code' not in agent_b tools: {tools_b}"
        )
        # Verify no collision: agent_a should NOT have agent_b's tool name
        assert "agent_b_execute_code" not in tools_a, (
            f"[MultiAgent] agent_a has agent_b's tool name! tools_a={tools_a}"
        )
        assert "agent_a_execute_code" not in tools_b, (
            f"[MultiAgent] agent_b has agent_a's tool name! tools_b={tools_b}"
        )

    # -- Local Python execution --------------------------------------------

    def test_local_python_execution(self, ce_runtime, model):
        """Agent with LocalCodeExecutor runs Python and produces correct output.

        Prompt: compute 42 * 73 = 3066
        Asserts: COMPLETED, workflow contains execute_code task, output has '3066'.
        """
        agent = _agent_local_code(model)
        result = ce_runtime.run(
            agent,
            "Run this exact Python code using execute_code: print(42 * 73)",
            timeout=TIMEOUT,
        )
        diag = _run_diagnostic(result)

        assert result.execution_id, f"[LocalPy] No execution_id. {diag}"
        assert result.status == "COMPLETED", (
            f"[LocalPy] Expected COMPLETED, got '{result.status}'. {diag}"
        )

        # Find execute_code tasks in workflow
        exec_tasks = _find_execute_code_tasks(result.execution_id)
        assert len(exec_tasks) >= 1, f"[LocalPy] No execute_code tasks found in workflow. {diag}"

        # At least one task output should contain "3066"
        found = any("3066" in _task_output_str(t) for t in exec_tasks)
        assert found, (
            f"[LocalPy] '3066' not found in any execute_code task output. "
            f"Task outputs: {[_task_output_str(t)[:200] for t in exec_tasks]}"
        )

    # -- Local Bash execution ----------------------------------------------

    def test_local_bash_execution(self, ce_runtime, model):
        """Agent with LocalCodeExecutor runs Bash and produces correct output.

        Prompt: echo $((17 + 29)) = 46
        Asserts: output contains '46'.
        """
        agent = _agent_local_code(model)
        result = ce_runtime.run(
            agent,
            "Run a bash script that prints the result of: echo $((17 + 29))",
            timeout=TIMEOUT,
        )
        diag = _run_diagnostic(result)

        assert result.execution_id, f"[LocalBash] No execution_id. {diag}"
        assert result.status == "COMPLETED", (
            f"[LocalBash] Expected COMPLETED, got '{result.status}'. {diag}"
        )

        exec_tasks = _find_execute_code_tasks(result.execution_id)
        assert len(exec_tasks) >= 1, f"[LocalBash] No execute_code tasks found in workflow. {diag}"

        found = any("46" in _task_output_str(t) for t in exec_tasks)
        assert found, (
            f"[LocalBash] '46' not found in any execute_code task output. "
            f"Task outputs: {[_task_output_str(t)[:200] for t in exec_tasks]}"
        )

    # -- Language restriction -----------------------------------------------

    def test_language_restriction(self, ce_runtime, model):
        """Agent restricted to Python only — Bash not in allowedLanguages.

        Validates via plan compilation (algorithmic, no LLM execution):
        - allowedLanguages contains only "python"
        - "bash" is NOT in allowedLanguages
        """
        agent = _agent_python_only(model)
        plan = ce_runtime.plan(agent)
        ad = plan["workflowDef"]["metadata"]["agentDef"]

        code_exec = ad.get("codeExecution", {})
        allowed = code_exec.get("allowedLanguages", [])
        assert "python" in allowed, (
            f"[LangRestrict] 'python' not in allowedLanguages: {allowed}"
        )
        assert "bash" not in allowed, (
            f"[LangRestrict] 'bash' should NOT be in allowedLanguages: {allowed}"
        )

    # -- Timeout enforcement ------------------------------------------------

    def test_local_timeout(self, ce_runtime, model):
        """Agent with timeout=3 kills long-running code.

        Prompt: sleep for 30 seconds then print. Should time out.
        Asserts: terminal status, output does NOT contain 'done'.
        """
        agent = _agent_short_timeout(model)
        result = ce_runtime.run(
            agent,
            (
                "Run this exact Python code using execute_code, preserving "
                "the line breaks exactly:\n"
                "```python\n"
                "import time\n"
                "time.sleep(30)\n"
                'print("done")\n'
                "```"
            ),
            timeout=60,  # Generous — we expect the 3s executor timeout to kill it
        )
        diag = _run_diagnostic(result)

        assert result.execution_id, f"[Timeout] No execution_id. {diag}"
        # The agent may still be RUNNING if the LLM hasn't finished processing
        # the timeout error. The key assertion is that the code execution DID
        # timeout (checked below), not that the agent itself terminated.
        assert result.status in ("COMPLETED", "FAILED", "TERMINATED", "RUNNING"), (
            f"[Timeout] Unexpected status '{result.status}'. {diag}"
        )

        # The execute_code task output should NOT contain "done" as stdout.
        #
        # Scope the assertion to tasks that actually ran the *sleep* code.
        # With ``max_turns=2`` the agent gets a second LLM turn after the
        # first task's timeout, and the model often "fixes" the issue by
        # re-running ``print("done")`` *without* the sleep — that follow-up
        # task legitimately completes with ``stdout="done\n"``. The
        # contract is "the sleeping code timed out", not "no code ever
        # completed across the whole run".
        exec_tasks = _find_execute_code_tasks(result.execution_id)

        def _ran_sleep(task) -> bool:
            inp = task.get("inputData") or {}
            code = inp.get("code") or inp.get("source") or ""
            return "sleep" in str(code).lower()

        sleep_tasks = [t for t in exec_tasks if _ran_sleep(t)]
        assert sleep_tasks, (
            f"[Timeout] No execute_code task ran the sleep code — the LLM "
            f"never invoked the tool with the sleep snippet. "
            f"exec_tasks={len(exec_tasks)} | {diag}"
        )

        # Deterministic contract: with timeout=3s, a 30s sleep cannot have
        # *successfully* run to completion. Either the executor killed it
        # (status='error', stderr mentions timeout) OR the LLM emitted code
        # the executor refused to run (status='error', syntax error, etc.).
        # Both outcomes satisfy the property under test — the property is
        # "the agent cannot let runaway code complete", not "the LLM emits
        # well-formed code". Asserting on the specific error *string* would
        # couple the test to LLM output shape, which is non-deterministic.
        for task in sleep_tasks:
            output_data = task.get("outputData", {})
            stdout = ""
            status = ""
            if isinstance(output_data, dict):
                result_data = output_data.get("result", output_data)
                if isinstance(result_data, dict):
                    stdout = str(result_data.get("stdout", ""))
                    status = str(result_data.get("status", ""))
            assert "done" not in stdout, (
                f"[Timeout] Sleep code completed despite timeout=3! "
                f"stdout={stdout[:200]}"
            )
            assert status != "success", (
                f"[Timeout] Sleep task reported success despite timeout=3! "
                f"output={_task_output_str(task)[:200]}"
            )

    # -- Docker Python execution -------------------------------------------

    @skip_no_docker
    def test_docker_python_execution(self, ce_runtime, model):
        """Agent with DockerCodeExecutor runs Python in container.

        Same prompt as local Python: 42 * 73 = 3066.
        Asserts: COMPLETED, output contains '3066'.
        """
        agent = _agent_docker_python(model)
        result = ce_runtime.run(
            agent,
            "Run this exact Python code using execute_code: print(42 * 73)",
            timeout=300,  # Docker needs extra time for image pull + container start
        )
        diag = _run_diagnostic(result)

        assert result.execution_id, f"[DockerPy] No execution_id. {diag}"
        assert result.status == "COMPLETED", (
            f"[DockerPy] Expected COMPLETED, got '{result.status}'. {diag}"
        )

        exec_tasks = _find_execute_code_tasks(result.execution_id)
        assert len(exec_tasks) >= 1, f"[DockerPy] No execute_code tasks found in workflow. {diag}"

        found = any("3066" in _task_output_str(t) for t in exec_tasks)
        assert found, (
            f"[DockerPy] '3066' not found in any execute_code task output. "
            f"Task outputs: {[_task_output_str(t)[:200] for t in exec_tasks]}"
        )

    # -- Docker network disabled -------------------------------------------

    @skip_no_docker
    def test_docker_network_disabled(self, ce_runtime, model):
        """DockerCodeExecutor with network_enabled=False blocks network access.

        Prompt: fetch http://example.com using urllib.
        Asserts: output contains error about network/connection.
        """
        agent = _agent_docker_no_network(model)
        result = ce_runtime.run(
            agent,
            (
                "Run this exact Python code using execute_code: "
                "import urllib.request; "
                "r = urllib.request.urlopen('http://example.com'); "
                "print(r.read()[:100])"
            ),
            timeout=300,  # Docker needs extra time
        )
        diag = _run_diagnostic(result)

        assert result.execution_id, f"[DockerNoNet] No execution_id. {diag}"
        assert result.status in ("COMPLETED", "FAILED", "TERMINATED"), (
            f"[DockerNoNet] Expected terminal status, got '{result.status}'. {diag}"
        )

        exec_tasks = _find_execute_code_tasks(result.execution_id)
        assert len(exec_tasks) >= 1, (
            f"[DockerNoNet] No execute_code tasks found in workflow. {diag}"
        )

        # Task output should contain a network/connection error
        any_net_error = any(
            any(
                keyword in _task_output_str(t).lower()
                for keyword in [
                    "network",
                    "connection",
                    "urlopen",
                    "unreachable",
                    "refused",
                    "errno",
                    "error",
                    "failed",
                    "resolve",
                    "gaierror",
                ]
            )
            for t in exec_tasks
        )
        assert any_net_error, (
            f"[DockerNoNet] Expected network error in execute_code output. "
            f"Task outputs: {[_task_output_str(t)[:300] for t in exec_tasks]}"
        )

    # -- Jupyter stateful execution ----------------------------------------

    @skip_no_jupyter
    def test_jupyter_stateful(self, ce_runtime, model):
        """JupyterCodeExecutor preserves state across calls.

        First call: x = 42
        Second call: print(x * 73) -> 3066
        Asserts: second run output contains '3066'.
        """
        agent = _agent_jupyter(model)

        # First run: define variable
        result1 = ce_runtime.run(
            agent,
            "Run this exact Python code using execute_code: x = 42",
            timeout=TIMEOUT,
        )
        diag1 = _run_diagnostic(result1)
        assert result1.status in ("COMPLETED", "FAILED", "TERMINATED"), (
            f"[JupyterState] First run unexpected status. {diag1}"
        )

        # Second run: use the variable
        result2 = ce_runtime.run(
            agent,
            "Run this exact Python code using execute_code: print(x * 73)",
            timeout=TIMEOUT,
        )
        diag2 = _run_diagnostic(result2)
        assert result2.execution_id, f"[JupyterState] No execution_id (run 2). {diag2}"
        assert result2.status == "COMPLETED", (
            f"[JupyterState] Second run expected COMPLETED, got '{result2.status}'. {diag2}"
        )

        exec_tasks = _find_execute_code_tasks(result2.execution_id)
        assert len(exec_tasks) >= 1, (
            f"[JupyterState] No execute_code tasks in second run workflow. {diag2}"
        )

        found = any("3066" in _task_output_str(t) for t in exec_tasks)
        assert found, (
            f"[JupyterState] '3066' not found in second run execute_code output. "
            f"State did not persist. "
            f"Task outputs: {[_task_output_str(t)[:200] for t in exec_tasks]}"
        )
