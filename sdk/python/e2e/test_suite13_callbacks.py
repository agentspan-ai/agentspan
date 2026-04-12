"""Suite 13: Callbacks — lifecycle hooks for tool and model events.

Tests that CallbackHandler hooks compile correctly into the workflow
definition and execute as real worker tasks at runtime.

All assertions are algorithmic/deterministic — no LLM output parsing.
Validation uses plan inspection and workflow task status checks.
No mocks. Real server, real LLM.
"""

import os

import pytest
import requests

from agentspan.agents import Agent, CallbackHandler, tool

pytestmark = [pytest.mark.e2e]

MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini")
TIMEOUT = 120


# ═══════════════════════════════════════════════════════════════════════════
# Deterministic tools
# ═══════════════════════════════════════════════════════════════════════════


@tool
def echo_tool(text: str) -> str:
    """Echo the input text back."""
    return f"echo:{text}"


# ═══════════════════════════════════════════════════════════════════════════
# Callback handlers
# ═══════════════════════════════════════════════════════════════════════════


class ToolCallbackHandler(CallbackHandler):
    """Overrides on_tool_start and on_tool_end only."""

    def on_tool_start(self, **kwargs):
        return None

    def on_tool_end(self, **kwargs):
        return None


class ModelCallbackHandler(CallbackHandler):
    """Overrides on_model_start and on_model_end only."""

    def on_model_start(self, **kwargs):
        return None

    def on_model_end(self, **kwargs):
        return None


class BeforeToolCallbackHandler(CallbackHandler):
    """Overrides on_tool_start only."""

    def on_tool_start(self, **kwargs):
        return None


class AfterToolCallbackHandler(CallbackHandler):
    """Overrides on_tool_end only."""

    def on_tool_end(self, **kwargs):
        return None


class AllCallbackHandler(CallbackHandler):
    """Overrides all 6 lifecycle methods."""

    def on_agent_start(self, **kwargs):
        return None

    def on_agent_end(self, **kwargs):
        return None

    def on_model_start(self, **kwargs):
        return None

    def on_model_end(self, **kwargs):
        return None

    def on_tool_start(self, **kwargs):
        return None

    def on_tool_end(self, **kwargs):
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _get_workflow(execution_id):
    """Fetch workflow execution from server API."""
    base = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
    base_url = base.rstrip("/").replace("/api", "")
    resp = requests.get(f"{base_url}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _run_diagnostic(result):
    """Build a diagnostic string from a run result for error messages."""
    parts = [f"status={result.status}", f"execution_id={result.execution_id}"]
    output = result.output
    if isinstance(output, dict):
        parts.append(f"output_keys={list(output.keys())}")
        if "finishReason" in output:
            parts.append(f"finishReason={output['finishReason']}")
    return " | ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.timeout(300)
class TestSuite13Callbacks:
    """Callbacks — lifecycle hooks for tool and model events."""

    # ── Compilation: tool callbacks ───────────────────────────────────

    def test_tool_callbacks_compile(self, runtime, model):
        """CallbackHandler with on_tool_start + on_tool_end compiles into
        the plan as before_tool and after_tool callback entries.

        Counterfactual: if callback compilation is broken, the callbacks
        key is absent or missing the expected entries.
        """
        agent = Agent(
            name="e2e_s13_tool_cb",
            model=model,
            max_turns=3,
            instructions="You are a helpful assistant. Use the echo tool.",
            tools=[echo_tool],
            callbacks=[ToolCallbackHandler()],
        )
        plan = runtime.plan(agent)
        ad = plan["workflowDef"]["metadata"]["agentDef"]
        callbacks = ad.get("callbacks", [])

        assert len(callbacks) >= 2, (
            f"[tool_callbacks_compile] Expected at least 2 callback entries "
            f"(before_tool + after_tool), got {len(callbacks)}. "
            f"Callbacks: {callbacks}"
        )

        positions = {cb["position"] for cb in callbacks}
        assert "before_tool" in positions, (
            f"[tool_callbacks_compile] 'before_tool' not found in callback "
            f"positions: {positions}. Callbacks: {callbacks}"
        )
        assert "after_tool" in positions, (
            f"[tool_callbacks_compile] 'after_tool' not found in callback "
            f"positions: {positions}. Callbacks: {callbacks}"
        )

        # Verify taskName format
        before_tool_entries = [
            cb for cb in callbacks if cb["position"] == "before_tool"
        ]
        assert any(
            cb["taskName"] == "e2e_s13_tool_cb_before_tool"
            for cb in before_tool_entries
        ), (
            f"[tool_callbacks_compile] Expected taskName "
            f"'e2e_s13_tool_cb_before_tool' in before_tool entries: "
            f"{before_tool_entries}"
        )

        after_tool_entries = [
            cb for cb in callbacks if cb["position"] == "after_tool"
        ]
        assert any(
            cb["taskName"] == "e2e_s13_tool_cb_after_tool"
            for cb in after_tool_entries
        ), (
            f"[tool_callbacks_compile] Expected taskName "
            f"'e2e_s13_tool_cb_after_tool' in after_tool entries: "
            f"{after_tool_entries}"
        )

    # ── Compilation: model callbacks ──────────────────────────────────

    def test_model_callbacks_compile(self, runtime, model):
        """CallbackHandler with on_model_start + on_model_end compiles into
        the plan as before_model and after_model callback entries.

        Counterfactual: if callback compilation is broken, the callbacks
        key is absent or missing the expected entries.
        """
        agent = Agent(
            name="e2e_s13_model_cb",
            model=model,
            max_turns=3,
            instructions="You are a helpful assistant.",
            callbacks=[ModelCallbackHandler()],
        )
        plan = runtime.plan(agent)
        ad = plan["workflowDef"]["metadata"]["agentDef"]
        callbacks = ad.get("callbacks", [])

        assert len(callbacks) >= 2, (
            f"[model_callbacks_compile] Expected at least 2 callback entries "
            f"(before_model + after_model), got {len(callbacks)}. "
            f"Callbacks: {callbacks}"
        )

        positions = {cb["position"] for cb in callbacks}
        assert "before_model" in positions, (
            f"[model_callbacks_compile] 'before_model' not found in callback "
            f"positions: {positions}. Callbacks: {callbacks}"
        )
        assert "after_model" in positions, (
            f"[model_callbacks_compile] 'after_model' not found in callback "
            f"positions: {positions}. Callbacks: {callbacks}"
        )

        # Verify taskName format
        before_model_entries = [
            cb for cb in callbacks if cb["position"] == "before_model"
        ]
        assert any(
            cb["taskName"] == "e2e_s13_model_cb_before_model"
            for cb in before_model_entries
        ), (
            f"[model_callbacks_compile] Expected taskName "
            f"'e2e_s13_model_cb_before_model' in before_model entries: "
            f"{before_model_entries}"
        )

        after_model_entries = [
            cb for cb in callbacks if cb["position"] == "after_model"
        ]
        assert any(
            cb["taskName"] == "e2e_s13_model_cb_after_model"
            for cb in after_model_entries
        ), (
            f"[model_callbacks_compile] Expected taskName "
            f"'e2e_s13_model_cb_after_model' in after_model entries: "
            f"{after_model_entries}"
        )

    # ── Runtime: before_tool callback executes ────────────────────────

    def test_before_tool_callback_executes(self, runtime, model):
        """An agent with on_tool_start callback produces a before_tool
        worker task that reaches COMPLETED status at runtime.

        Counterfactual: if the callback is broken, the before_tool task
        is missing or does not reach COMPLETED status.
        """
        agent = Agent(
            name="e2e_s13_before_tool",
            model=model,
            max_turns=3,
            instructions=(
                "You are a helpful assistant. You MUST call the echo_tool "
                "with text='hello' to answer the user. Always use the tool."
            ),
            tools=[echo_tool],
            callbacks=[BeforeToolCallbackHandler()],
        )
        result = runtime.run(agent, "Say hello using the echo tool.", timeout=TIMEOUT)
        diag = _run_diagnostic(result)

        assert result.execution_id, (
            f"[before_tool_callback] No execution_id. {diag}"
        )
        assert result.status in ("COMPLETED", "TERMINATED"), (
            f"[before_tool_callback] Expected COMPLETED or TERMINATED, "
            f"got '{result.status}'. {diag}"
        )

        wf = _get_workflow(result.execution_id)
        all_tasks = wf.get("tasks", [])
        before_tool_tasks = [
            t for t in all_tasks
            if "before_tool" in t.get("referenceTaskName", "")
        ]

        assert len(before_tool_tasks) > 0, (
            f"[before_tool_callback] No task with 'before_tool' in "
            f"referenceTaskName found. All task refs: "
            f"{[t.get('referenceTaskName', '?') for t in all_tasks]}. {diag}"
        )

        completed = [
            t for t in before_tool_tasks
            if t.get("status") == "COMPLETED"
        ]
        assert len(completed) > 0, (
            f"[before_tool_callback] before_tool task(s) exist but none "
            f"reached COMPLETED. Statuses: "
            f"{[t.get('status') for t in before_tool_tasks]}. {diag}"
        )

    # ── Runtime: after_tool callback executes ─────────────────────────

    def test_after_tool_callback_executes(self, runtime, model):
        """An agent with on_tool_end callback produces an after_tool
        worker task that reaches COMPLETED status at runtime.

        Counterfactual: if the callback is broken, the after_tool task
        is missing or does not reach COMPLETED status.
        """
        agent = Agent(
            name="e2e_s13_after_tool",
            model=model,
            max_turns=3,
            instructions=(
                "You are a helpful assistant. You MUST call the echo_tool "
                "with text='world' to answer the user. Always use the tool."
            ),
            tools=[echo_tool],
            callbacks=[AfterToolCallbackHandler()],
        )
        result = runtime.run(agent, "Say world using the echo tool.", timeout=TIMEOUT)
        diag = _run_diagnostic(result)

        assert result.execution_id, (
            f"[after_tool_callback] No execution_id. {diag}"
        )
        assert result.status in ("COMPLETED", "TERMINATED"), (
            f"[after_tool_callback] Expected COMPLETED or TERMINATED, "
            f"got '{result.status}'. {diag}"
        )

        wf = _get_workflow(result.execution_id)
        all_tasks = wf.get("tasks", [])
        after_tool_tasks = [
            t for t in all_tasks
            if "after_tool" in t.get("referenceTaskName", "")
        ]

        assert len(after_tool_tasks) > 0, (
            f"[after_tool_callback] No task with 'after_tool' in "
            f"referenceTaskName found. All task refs: "
            f"{[t.get('referenceTaskName', '?') for t in all_tasks]}. {diag}"
        )

        completed = [
            t for t in after_tool_tasks
            if t.get("status") == "COMPLETED"
        ]
        assert len(completed) > 0, (
            f"[after_tool_callback] after_tool task(s) exist but none "
            f"reached COMPLETED. Statuses: "
            f"{[t.get('status') for t in after_tool_tasks]}. {diag}"
        )

    # ── Runtime: all callbacks don't block execution ──────────────────

    def test_all_callbacks_dont_block_execution(self, runtime, model):
        """An agent with ALL 6 callback hooks still completes successfully
        and the tool task executes normally.

        Counterfactual: if callbacks crash or block the workflow, status
        will not be COMPLETED or the tool task will be missing/failed.
        """
        agent = Agent(
            name="e2e_s13_all_cb",
            model=model,
            max_turns=3,
            instructions=(
                "You are a helpful assistant. You MUST call the echo_tool "
                "with text='test' to answer the user. Always use the tool."
            ),
            tools=[echo_tool],
            callbacks=[AllCallbackHandler()],
        )
        result = runtime.run(agent, "Use the echo tool with 'test'.", timeout=TIMEOUT)
        diag = _run_diagnostic(result)

        assert result.execution_id, (
            f"[all_callbacks] No execution_id. {diag}"
        )
        assert result.status == "COMPLETED", (
            f"[all_callbacks] Expected COMPLETED, got '{result.status}'. "
            f"All 6 callbacks should not interfere with normal execution. "
            f"{diag}"
        )

        # Verify the echo_tool actually ran by finding its task
        wf = _get_workflow(result.execution_id)
        all_tasks = wf.get("tasks", [])
        tool_tasks = [
            t for t in all_tasks
            if "echo_tool" in t.get("referenceTaskName", "")
        ]

        assert len(tool_tasks) > 0, (
            f"[all_callbacks] No task with 'echo_tool' in "
            f"referenceTaskName found. Callbacks may have blocked tool "
            f"execution. All task refs: "
            f"{[t.get('referenceTaskName', '?') for t in all_tasks]}. {diag}"
        )

        completed_tools = [
            t for t in tool_tasks
            if t.get("status") == "COMPLETED"
        ]
        assert len(completed_tools) > 0, (
            f"[all_callbacks] echo_tool task(s) exist but none reached "
            f"COMPLETED. Callbacks may have interfered with tool execution. "
            f"Statuses: {[t.get('status') for t in tool_tasks]}. {diag}"
        )
