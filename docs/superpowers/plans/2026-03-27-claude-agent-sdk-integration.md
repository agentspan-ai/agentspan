# Claude Agent SDK Integration — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Claude Agent SDK as a passthrough framework in agentspan with hook-based observability.

**Architecture:** Users pass `ClaudeCodeOptions` (from `claude-code-sdk`) to `runtime.run()`. The SDK detects the framework, serializes a minimal config, and runs the entire `query()` inside a single Conductor worker task. Agentspan injects instrumentation hooks that push stream events and persist metadata.

**Tech Stack:** Python (`claude-code-sdk`), Java/Spring (`@Component` normalizer), Conductor workflows

**Note:** The actual SDK package is `claude-code-sdk` (PyPI), which exports `ClaudeCodeOptions`. Detection handles both `ClaudeCodeOptions` and `ClaudeAgentOptions` for forward-compatibility.

**Spec:** `docs/superpowers/specs/2026-03-27-claude-agent-sdk-integration-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `sdk/python/src/agentspan/agents/frameworks/claude_agent_sdk.py` | **New** — Serializer, passthrough worker, hooks, event push |
| `sdk/python/src/agentspan/agents/frameworks/serializer.py` | **Modify** — Add detection + serialize_agent short-circuit |
| `sdk/python/src/agentspan/agents/runtime/runtime.py` | **Modify** — Add `_build_passthrough_func` branch |
| `server/.../normalizer/ClaudeAgentSdkNormalizer.java` | **New** — Java passthrough normalizer |
| `sdk/python/tests/unit/test_claude_agent_sdk_worker.py` | **New** — Worker and serializer unit tests |
| `sdk/python/tests/unit/test_framework_detection.py` | **Modify** — Add detection test |
| `sdk/python/tests/unit/test_passthrough_registration.py` | **Modify** — Add dispatch test |
| `server/.../normalizer/ClaudeAgentSdkNormalizerTest.java` | **New** — Java normalizer test |
| `sdk/python/examples/claude_agent_sdk/01_basic_agent.py` | **New** — Minimal example |

---

## Chunk 1: Framework Detection + Serializer

### Task 1: Framework detection

**Files:**
- Modify: `sdk/python/src/agentspan/agents/frameworks/serializer.py:49-62`
- Test: `sdk/python/tests/unit/test_framework_detection.py`

- [ ] **Step 1: Write the failing test**

Add to `sdk/python/tests/unit/test_framework_detection.py`:

```python
def test_detect_claude_code_options():
    from agentspan.agents.frameworks.serializer import detect_framework
    obj = _make_obj_with_class_name("ClaudeCodeOptions")
    assert detect_framework(obj) == "claude_agent_sdk"


def test_detect_claude_agent_options_alias():
    """Forward-compat: if the SDK renames to ClaudeAgentOptions, still detect it."""
    from agentspan.agents.frameworks.serializer import detect_framework
    obj = _make_obj_with_class_name("ClaudeAgentOptions")
    assert detect_framework(obj) == "claude_agent_sdk"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sdk/python && uv run pytest tests/unit/test_framework_detection.py::test_detect_claude_code_options tests/unit/test_framework_detection.py::test_detect_claude_agent_options_alias -v`
Expected: FAIL — returns `None` instead of `"claude_agent_sdk"`

- [ ] **Step 3: Add detection to `serializer.py`**

In `detect_framework()`, after the LangChain `AgentExecutor` check (line 55) and before the module prefix fallback (line 58), add:

```python
    # Claude Agent SDK (claude-code-sdk package)
    if type_name in ("ClaudeCodeOptions", "ClaudeAgentOptions"):
        return "claude_agent_sdk"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sdk/python && uv run pytest tests/unit/test_framework_detection.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/frameworks/serializer.py sdk/python/tests/unit/test_framework_detection.py
git commit -m "feat: detect ClaudeCodeOptions/ClaudeAgentOptions as claude_agent_sdk framework"
```

### Task 2: Serializer function

**Files:**
- Create: `sdk/python/src/agentspan/agents/frameworks/claude_agent_sdk.py`
- Modify: `sdk/python/src/agentspan/agents/frameworks/serializer.py:96-104`
- Test: `sdk/python/tests/unit/test_claude_agent_sdk_worker.py`

- [ ] **Step 1: Write the failing tests**

Create `sdk/python/tests/unit/test_claude_agent_sdk_worker.py`:

```python
"""Unit tests for the Claude Agent SDK passthrough integration."""
from unittest.mock import MagicMock


def _make_options(system_prompt="You are a reviewer"):
    """Create a mock ClaudeCodeOptions (from claude-code-sdk package)."""
    options = MagicMock()
    type(options).__name__ = "ClaudeCodeOptions"
    options.system_prompt = system_prompt
    options.hooks = {}
    return options


class TestSerializeClaudeAgentSdk:
    def test_returns_single_worker_with_func_none(self):
        from agentspan.agents.frameworks.claude_agent_sdk import serialize_claude_agent_sdk

        options = _make_options()
        raw_config, workers = serialize_claude_agent_sdk(options)

        assert len(workers) == 1
        assert workers[0].func is None

    def test_raw_config_has_name_and_worker_name(self):
        from agentspan.agents.frameworks.claude_agent_sdk import serialize_claude_agent_sdk

        options = _make_options()
        raw_config, workers = serialize_claude_agent_sdk(options)

        assert "name" in raw_config
        assert raw_config["_worker_name"] == raw_config["name"]

    def test_worker_has_prompt_input_schema(self):
        from agentspan.agents.frameworks.claude_agent_sdk import serialize_claude_agent_sdk

        options = _make_options()
        _, workers = serialize_claude_agent_sdk(options)

        schema = workers[0].input_schema
        assert schema["type"] == "object"
        assert "prompt" in schema["properties"]
        assert "session_id" in schema["properties"]

    def test_default_name_when_no_system_prompt(self):
        from agentspan.agents.frameworks.claude_agent_sdk import serialize_claude_agent_sdk

        options = _make_options(system_prompt=None)
        raw_config, _ = serialize_claude_agent_sdk(options)

        assert raw_config["name"] == "claude_agent_sdk_agent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sdk/python && uv run pytest tests/unit/test_claude_agent_sdk_worker.py::TestSerializeClaudeAgentSdk -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentspan.agents.frameworks.claude_agent_sdk'`

- [ ] **Step 3: Create `claude_agent_sdk.py` with serializer**

Create `sdk/python/src/agentspan/agents/frameworks/claude_agent_sdk.py`:

```python
# sdk/python/src/agentspan/agents/frameworks/claude_agent_sdk.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Claude Agent SDK passthrough worker support.

Provides:
- serialize_claude_agent_sdk(options) -> (raw_config, [WorkerInfo])
- make_claude_agent_sdk_worker(options, name, server_url, auth_key, auth_secret) -> tool_worker
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Tuple

from agentspan.agents.frameworks.serializer import WorkerInfo

logger = logging.getLogger("agentspan.agents.frameworks.claude_agent_sdk")

_DEFAULT_NAME = "claude_agent_sdk_agent"


def serialize_claude_agent_sdk(options: Any) -> Tuple[Dict[str, Any], List[WorkerInfo]]:
    """Serialize Claude Agent SDK options into (raw_config, [WorkerInfo]).

    Always produces a passthrough config — the entire query() runs in one worker.
    """
    name = _extract_name(options)
    logger.info("Claude Agent SDK '%s': passthrough", name)

    raw_config: Dict[str, Any] = {"name": name, "_worker_name": name}
    worker = WorkerInfo(
        name=name,
        description=f"Claude Agent SDK passthrough worker for {name}",
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "session_id": {"type": "string"},
            },
        },
        func=None,  # Filled by _build_passthrough_func()
    )
    return raw_config, [worker]


def _extract_name(options: Any) -> str:
    """Extract a sanitized name from options, falling back to default."""
    system_prompt = getattr(options, "system_prompt", None) or getattr(
        options, "systemPrompt", None
    )
    if not system_prompt or not isinstance(system_prompt, str):
        return _DEFAULT_NAME
    # Take first 40 chars, sanitize to alphanumeric + underscore
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", system_prompt[:40]).strip("_").lower()
    return slug or _DEFAULT_NAME
```

- [ ] **Step 4: Add short-circuit in `serialize_agent()`**

In `sdk/python/src/agentspan/agents/frameworks/serializer.py`, after the `langchain` branch (line 104), add:

```python
    if framework == "claude_agent_sdk":
        from agentspan.agents.frameworks.claude_agent_sdk import serialize_claude_agent_sdk

        return serialize_claude_agent_sdk(agent_obj)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd sdk/python && uv run pytest tests/unit/test_claude_agent_sdk_worker.py::TestSerializeClaudeAgentSdk -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Add dispatch test to passthrough registration tests**

Add to `sdk/python/tests/unit/test_passthrough_registration.py` in `TestSerializeAgentDispatching`:

```python
    def test_claude_agent_sdk_dispatches_to_serialize_claude_agent_sdk(self):
        from agentspan.agents.frameworks.serializer import serialize_agent

        options = MagicMock()
        type(options).__name__ = "ClaudeCodeOptions"

        with patch(
            "agentspan.agents.frameworks.claude_agent_sdk.serialize_claude_agent_sdk"
        ) as mock_serialize:
            mock_serialize.return_value = ({"name": "test_agent"}, [])
            serialize_agent(options)
            mock_serialize.assert_called_once_with(options)
```

- [ ] **Step 7: Run full test suite for serializer + passthrough**

Run: `cd sdk/python && uv run pytest tests/unit/test_framework_detection.py tests/unit/test_passthrough_registration.py tests/unit/test_claude_agent_sdk_worker.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add sdk/python/src/agentspan/agents/frameworks/claude_agent_sdk.py sdk/python/src/agentspan/agents/frameworks/serializer.py sdk/python/tests/unit/test_claude_agent_sdk_worker.py sdk/python/tests/unit/test_passthrough_registration.py
git commit -m "feat: add Claude Agent SDK serializer and serialize_agent dispatch"
```

---

## Chunk 2: Passthrough Worker + Hooks

### Task 3: Passthrough worker

**Files:**
- Modify: `sdk/python/src/agentspan/agents/frameworks/claude_agent_sdk.py`
- Test: `sdk/python/tests/unit/test_claude_agent_sdk_worker.py`

- [ ] **Step 1: Write the failing tests**

Add to `sdk/python/tests/unit/test_claude_agent_sdk_worker.py`:

```python
import asyncio
from unittest.mock import patch, AsyncMock


def _make_task(prompt="Hello", session_id="", execution_id="wf-123", cwd=""):
    from conductor.client.http.models.task import Task
    task = MagicMock(spec=Task)
    task.input_data = {"prompt": prompt, "session_id": session_id, "cwd": cwd}
    task.workflow_instance_id = execution_id
    task.task_id = "task-456"
    return task


class TestMakeClaudeAgentSdkWorker:
    def test_worker_returns_completed_on_success(self):
        from agentspan.agents.frameworks.claude_agent_sdk import make_claude_agent_sdk_worker

        options = _make_options()
        task = _make_task(prompt="Review the code")

        # Mock asyncio.run to simulate _run_query returning a result
        with patch(
            "agentspan.agents.frameworks.claude_agent_sdk.asyncio"
        ) as mock_asyncio, patch(
            "agentspan.agents.frameworks.claude_agent_sdk._push_event_nonblocking"
        ):
            mock_asyncio.run.return_value = ("The code looks good", None)
            worker_fn = make_claude_agent_sdk_worker(
                options, "test_agent", "http://localhost:6767", "key", "secret"
            )
            result = worker_fn(task)

        assert result.status == "COMPLETED"
        assert result.output_data["result"] == "The code looks good"

    def test_worker_returns_failed_on_exception(self):
        from agentspan.agents.frameworks.claude_agent_sdk import make_claude_agent_sdk_worker

        options = _make_options()
        task = _make_task()

        with patch(
            "agentspan.agents.frameworks.claude_agent_sdk.asyncio"
        ) as mock_asyncio, patch(
            "agentspan.agents.frameworks.claude_agent_sdk._push_event_nonblocking"
        ):
            mock_asyncio.run.side_effect = RuntimeError("SDK error")
            worker_fn = make_claude_agent_sdk_worker(
                options, "test_agent", "http://localhost:6767", "key", "secret"
            )
            result = worker_fn(task)

        assert result.status == "FAILED"
        assert "SDK error" in result.reason_for_incompletion

    def test_worker_includes_metadata_in_output(self):
        from agentspan.agents.frameworks.claude_agent_sdk import make_claude_agent_sdk_worker

        options = _make_options()
        task = _make_task()

        with patch(
            "agentspan.agents.frameworks.claude_agent_sdk.asyncio"
        ) as mock_asyncio, patch(
            "agentspan.agents.frameworks.claude_agent_sdk._push_event_nonblocking"
        ):
            mock_asyncio.run.return_value = ("result", {"input_tokens": 100})
            worker_fn = make_claude_agent_sdk_worker(
                options, "test_agent", "http://localhost:6767", "key", "secret"
            )
            result = worker_fn(task)

        assert result.output_data["tool_call_count"] == 0
        assert result.output_data["tool_error_count"] == 0
        assert result.output_data["subagent_count"] == 0
        assert result.output_data["tools_used"] == []
        assert result.output_data["token_usage"] == {"input_tokens": 100}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sdk/python && uv run pytest tests/unit/test_claude_agent_sdk_worker.py::TestMakeClaudeAgentSdkWorker -v`
Expected: FAIL — `ImportError: cannot import name 'make_claude_agent_sdk_worker'`

- [ ] **Step 3: Implement the worker in `claude_agent_sdk.py`**

Append to `sdk/python/src/agentspan/agents/frameworks/claude_agent_sdk.py`:

```python
import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import is_dataclass, replace

_EVENT_PUSH_POOL = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="claude-agent-sdk-event-push"
)


def make_claude_agent_sdk_worker(
    options: Any,
    name: str,
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> Any:
    """Build a pre-wrapped tool_worker(task) -> TaskResult for Claude Agent SDK."""
    from conductor.client.http.models.task import Task
    from conductor.client.http.models.task_result import TaskResult
    from conductor.client.http.models.task_result_status import TaskResultStatus

    def tool_worker(task: Task) -> TaskResult:
        execution_id = task.workflow_instance_id
        prompt = task.input_data.get("prompt", "")
        cwd = task.input_data.get("cwd", "")
        _injected_cred_keys: List[str] = []

        try:
            _injected_cred_keys = _inject_credentials(task, execution_id)

            metadata: Dict[str, Any] = {
                "tool_call_count": 0,
                "tool_error_count": 0,
                "subagent_count": 0,
                "tools_used": set(),
            }

            agentspan_hooks = _build_agentspan_hooks(
                execution_id, server_url, auth_key, auth_secret, metadata
            )
            merged_options = _merge_hooks(options, agentspan_hooks)

            # Set cwd if provided
            if cwd:
                merged_options = _set_option(merged_options, "cwd", cwd)

            result_output, token_usage = asyncio.run(
                _run_query(prompt, merged_options)
            )

            output_data: Dict[str, Any] = {
                "result": result_output,
                "tool_call_count": metadata["tool_call_count"],
                "tool_error_count": metadata["tool_error_count"],
                "subagent_count": metadata["subagent_count"],
                "tools_used": sorted(metadata["tools_used"]),
            }
            if token_usage:
                output_data["token_usage"] = token_usage

            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=execution_id,
                status=TaskResultStatus.COMPLETED,
                output_data=output_data,
            )
        except Exception as exc:
            logger.error(
                "Claude Agent SDK worker error (execution_id=%s): %s",
                execution_id,
                exc,
            )
            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=execution_id,
                status=TaskResultStatus.FAILED,
                reason_for_incompletion=str(exc),
            )
        finally:
            _cleanup_credentials(_injected_cred_keys)

    return tool_worker


async def _run_query(prompt: str, options: Any) -> Tuple[str, Any]:
    """Run Claude Agent SDK query() and collect result."""
    # Lazy import — claude-code-sdk is optional
    from claude_code_sdk import query, AssistantMessage, ResultMessage

    result_output = ""
    collected_text: List[str] = []
    token_usage = None

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if hasattr(block, "text"):
                    collected_text.append(block.text)
        elif isinstance(message, ResultMessage):
            result_output = getattr(message, "result", "") or ""
            token_usage = getattr(message, "usage", None)

    if not result_output and collected_text:
        result_output = "\n".join(collected_text)

    return result_output, token_usage


def _inject_credentials(task: Any, execution_id: str) -> List[str]:
    """Resolve execution-level credentials and inject into os.environ."""
    injected: List[str] = []
    try:
        import os as _os

        from agentspan.agents.runtime._dispatch import (
            _extract_execution_token,
            _get_credential_fetcher,
            _workflow_credentials,
            _workflow_credentials_lock,
        )

        wf_id = execution_id or ""
        with _workflow_credentials_lock:
            cred_names = list(_workflow_credentials.get(wf_id, []))
        if cred_names:
            token = _extract_execution_token(task)
            if token:
                fetcher = _get_credential_fetcher()
                resolved = fetcher.fetch(token, cred_names)
                for k, v in resolved.items():
                    if isinstance(v, str):
                        _os.environ[k] = v
                        injected.append(k)
    except Exception as err:
        logger.warning("Failed to resolve credentials: %s", err)
    return injected


def _cleanup_credentials(keys: List[str]) -> None:
    """Remove injected credentials from os.environ."""
    import os as _os

    for k in keys:
        _os.environ.pop(k, None)


def _set_option(options: Any, key: str, value: Any) -> Any:
    """Set a field on the options object (duck-typed)."""
    if isinstance(options, dict):
        return {**options, key: value}
    try:
        new_opts = copy.copy(options)
        setattr(new_opts, key, value)
        return new_opts
    except Exception:
        return options
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd sdk/python && uv run pytest tests/unit/test_claude_agent_sdk_worker.py::TestMakeClaudeAgentSdkWorker -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/frameworks/claude_agent_sdk.py sdk/python/tests/unit/test_claude_agent_sdk_worker.py
git commit -m "feat: add Claude Agent SDK passthrough worker"
```

### Task 4: Hook injection and event push

**Files:**
- Modify: `sdk/python/src/agentspan/agents/frameworks/claude_agent_sdk.py`
- Test: `sdk/python/tests/unit/test_claude_agent_sdk_worker.py`

- [ ] **Step 0: Verify Claude Agent SDK hook API**

Install the SDK and inspect the actual hook interface:
```bash
cd sdk/python && uv add --dev claude-code-sdk
uv run python -c "from claude_code_sdk import ClaudeCodeOptions; import inspect; print(inspect.signature(ClaudeCodeOptions))"
```

Verify:
- What type is `hooks`? (dict, dataclass, class instance?)
- What is the callback signature? (async? sync? what params?)
- What is the matcher structure? (`HookMatcher` class? plain dict?)

If the actual API differs from the assumed `{"EventName": [{"hooks": [fn]}]}` structure, adapt the implementation and tests below before proceeding. The spec (Section 4, lines 155-158) explicitly calls this out as requiring verification.

- [ ] **Step 1: Write the failing tests**

Add to `sdk/python/tests/unit/test_claude_agent_sdk_worker.py`:

```python
class TestAgentspanHooks:
    def test_build_hooks_returns_dict_with_expected_keys(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _build_agentspan_hooks

        metadata = {"tool_call_count": 0, "tool_error_count": 0, "subagent_count": 0, "tools_used": set()}
        hooks = _build_agentspan_hooks("wf-1", "http://localhost", "k", "s", metadata)

        assert "PreToolUse" in hooks
        assert "PostToolUse" in hooks
        assert "PostToolUseFailure" in hooks
        assert "SubagentStart" in hooks
        assert "SubagentStop" in hooks
        assert "Notification" in hooks
        assert "Stop" in hooks

    def test_pre_tool_use_hook_increments_metadata(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _build_agentspan_hooks

        metadata = {"tool_call_count": 0, "tool_error_count": 0, "subagent_count": 0, "tools_used": set()}

        with patch("agentspan.agents.frameworks.claude_agent_sdk._push_event_nonblocking"):
            hooks = _build_agentspan_hooks("wf-1", "http://localhost", "k", "s", metadata)

            # Extract the hook function from the first matcher
            pre_hook = hooks["PreToolUse"][0]["hooks"][0]
            result = asyncio.run(pre_hook(
                {"tool_name": "Read", "tool_input": {}, "hook_event_name": "PreToolUse"},
                "tu-1",
                None,
            ))

        assert metadata["tool_call_count"] == 1
        assert "Read" in metadata["tools_used"]
        assert result == {}

    def test_post_tool_use_failure_increments_error_count(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _build_agentspan_hooks

        metadata = {"tool_call_count": 0, "tool_error_count": 0, "subagent_count": 0, "tools_used": set()}

        with patch("agentspan.agents.frameworks.claude_agent_sdk._push_event_nonblocking"):
            hooks = _build_agentspan_hooks("wf-1", "http://localhost", "k", "s", metadata)

            error_hook = hooks["PostToolUseFailure"][0]["hooks"][0]
            asyncio.run(error_hook(
                {"tool_name": "Bash", "error": "command failed", "hook_event_name": "PostToolUseFailure"},
                "tu-2",
                None,
            ))

        assert metadata["tool_error_count"] == 1

    def test_hooks_push_events(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _build_agentspan_hooks

        pushed = []
        metadata = {"tool_call_count": 0, "tool_error_count": 0, "subagent_count": 0, "tools_used": set()}

        def capture_push(wf_id, event, *args):
            pushed.append(event)

        with patch(
            "agentspan.agents.frameworks.claude_agent_sdk._push_event_nonblocking",
            side_effect=capture_push,
        ):
            hooks = _build_agentspan_hooks("wf-1", "http://localhost", "k", "s", metadata)

            pre_hook = hooks["PreToolUse"][0]["hooks"][0]
            asyncio.run(pre_hook({"tool_name": "Edit", "tool_input": {}, "hook_event_name": "PreToolUse"}, "tu-3", None))

        assert len(pushed) == 1
        assert pushed[0]["type"] == "tool_call"
        assert pushed[0]["toolName"] == "Edit"
        assert pushed[0]["toolUseId"] == "tu-3"

    def test_hooks_are_defensive(self):
        """Hooks must not raise even if event push fails."""
        from agentspan.agents.frameworks.claude_agent_sdk import _build_agentspan_hooks

        metadata = {"tool_call_count": 0, "tool_error_count": 0, "subagent_count": 0, "tools_used": set()}

        with patch(
            "agentspan.agents.frameworks.claude_agent_sdk._push_event_nonblocking",
            side_effect=RuntimeError("network down"),
        ):
            hooks = _build_agentspan_hooks("wf-1", "http://localhost", "k", "s", metadata)
            pre_hook = hooks["PreToolUse"][0]["hooks"][0]
            # Should NOT raise
            result = asyncio.run(pre_hook({"tool_name": "Read", "tool_input": {}, "hook_event_name": "PreToolUse"}, "tu-4", None))

        assert result == {}
        # metadata still updated despite push failure
        assert metadata["tool_call_count"] == 1


class TestMergeHooks:
    def test_merge_with_no_user_hooks(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _merge_hooks

        options = _make_options()
        options.hooks = {}

        agentspan_hooks = {"PreToolUse": [{"hooks": ["fake"]}]}
        merged = _merge_hooks(options, agentspan_hooks)

        result_hooks = merged.hooks if hasattr(merged, "hooks") else merged.get("hooks", {})
        assert len(result_hooks["PreToolUse"]) == 1

    def test_merge_preserves_user_hooks_first(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _merge_hooks

        options = _make_options()
        user_matcher = {"matcher": "Bash", "hooks": ["user_hook"]}
        options.hooks = {"PreToolUse": [user_matcher]}

        agentspan_matcher = {"hooks": ["agentspan_hook"]}
        agentspan_hooks = {"PreToolUse": [agentspan_matcher]}

        merged = _merge_hooks(options, agentspan_hooks)
        result_hooks = merged.hooks if hasattr(merged, "hooks") else merged.get("hooks", {})

        assert len(result_hooks["PreToolUse"]) == 2
        assert result_hooks["PreToolUse"][0] == user_matcher  # user first
        assert result_hooks["PreToolUse"][1] == agentspan_matcher  # agentspan second
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sdk/python && uv run pytest tests/unit/test_claude_agent_sdk_worker.py::TestAgentspanHooks tests/unit/test_claude_agent_sdk_worker.py::TestMergeHooks -v`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement hooks and merge in `claude_agent_sdk.py`**

Append to `sdk/python/src/agentspan/agents/frameworks/claude_agent_sdk.py`:

```python
def _build_agentspan_hooks(
    execution_id: str,
    server_url: str,
    auth_key: str,
    auth_secret: str,
    metadata: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    """Build agentspan instrumentation hooks for Claude Agent SDK.

    All hooks are defensive (try/except) — instrumentation must never crash the agent.
    Returns a dict of hook_event_name -> list of matcher dicts.
    """

    async def _pre_tool_use(input_data: Dict, tool_use_id: Any, context: Any) -> Dict:
        try:
            tool_name = input_data.get("tool_name", "")
            metadata["tool_call_count"] += 1
            metadata["tools_used"].add(tool_name)
            _push_event_nonblocking(
                execution_id,
                {"type": "tool_call", "toolName": tool_name, "toolUseId": tool_use_id},
                server_url,
                auth_key,
                auth_secret,
            )
        except Exception as exc:
            logger.debug("Agentspan PreToolUse hook error: %s", exc)
        return {}

    async def _post_tool_use(input_data: Dict, tool_use_id: Any, context: Any) -> Dict:
        try:
            tool_name = input_data.get("tool_name", "")
            _push_event_nonblocking(
                execution_id,
                {"type": "tool_result", "toolName": tool_name, "toolUseId": tool_use_id},
                server_url,
                auth_key,
                auth_secret,
            )
        except Exception as exc:
            logger.debug("Agentspan PostToolUse hook error: %s", exc)
        return {}

    async def _post_tool_use_failure(input_data: Dict, tool_use_id: Any, context: Any) -> Dict:
        try:
            tool_name = input_data.get("tool_name", "")
            error = input_data.get("error", "")
            metadata["tool_error_count"] += 1
            _push_event_nonblocking(
                execution_id,
                {"type": "tool_error", "toolName": tool_name, "error": str(error)},
                server_url,
                auth_key,
                auth_secret,
            )
        except Exception as exc:
            logger.debug("Agentspan PostToolUseFailure hook error: %s", exc)
        return {}

    async def _subagent_start(input_data: Dict, tool_use_id: Any, context: Any) -> Dict:
        try:
            agent_id = input_data.get("agent_id", "")
            metadata["subagent_count"] += 1
            _push_event_nonblocking(
                execution_id,
                {"type": "subagent_start", "agent_id": agent_id},
                server_url,
                auth_key,
                auth_secret,
            )
        except Exception as exc:
            logger.debug("Agentspan SubagentStart hook error: %s", exc)
        return {}

    async def _subagent_stop(input_data: Dict, tool_use_id: Any, context: Any) -> Dict:
        try:
            agent_id = input_data.get("agent_id", "")
            _push_event_nonblocking(
                execution_id,
                {"type": "subagent_stop", "agent_id": agent_id},
                server_url,
                auth_key,
                auth_secret,
            )
        except Exception as exc:
            logger.debug("Agentspan SubagentStop hook error: %s", exc)
        return {}

    async def _notification(input_data: Dict, tool_use_id: Any, context: Any) -> Dict:
        try:
            message = input_data.get("message", "")
            _push_event_nonblocking(
                execution_id,
                {"type": "notification", "message": message},
                server_url,
                auth_key,
                auth_secret,
            )
        except Exception as exc:
            logger.debug("Agentspan Notification hook error: %s", exc)
        return {}

    async def _stop(input_data: Dict, tool_use_id: Any, context: Any) -> Dict:
        try:
            _push_event_nonblocking(
                execution_id,
                {"type": "agent_stop"},
                server_url,
                auth_key,
                auth_secret,
            )
        except Exception as exc:
            logger.debug("Agentspan Stop hook error: %s", exc)
        return {}

    return {
        "PreToolUse": [{"hooks": [_pre_tool_use]}],
        "PostToolUse": [{"hooks": [_post_tool_use]}],
        "PostToolUseFailure": [{"hooks": [_post_tool_use_failure]}],
        "SubagentStart": [{"hooks": [_subagent_start]}],
        "SubagentStop": [{"hooks": [_subagent_stop]}],
        "Notification": [{"hooks": [_notification]}],
        "Stop": [{"hooks": [_stop]}],
    }


def _merge_hooks(options: Any, agentspan_hooks: Dict[str, List]) -> Any:
    """Create a copy of options with agentspan hooks appended after user hooks."""
    user_hooks = getattr(options, "hooks", None) or {}
    if isinstance(options, dict):
        user_hooks = options.get("hooks", {})

    merged: Dict[str, List] = {}
    all_events = set(list(user_hooks.keys()) + list(agentspan_hooks.keys()))
    for event_name in all_events:
        user_matchers = user_hooks.get(event_name, [])
        as_matchers = agentspan_hooks.get(event_name, [])
        merged[event_name] = list(user_matchers) + as_matchers

    return _copy_options_with_hooks(options, merged)


def _copy_options_with_hooks(options: Any, hooks: Dict) -> Any:
    """Duck-typed copy of options with hooks replaced."""
    if isinstance(options, dict):
        return {**options, "hooks": hooks}
    if hasattr(options, "model_copy"):  # Pydantic v2
        return options.model_copy(update={"hooks": hooks})
    if is_dataclass(options) and not isinstance(options, type):
        return replace(options, hooks=hooks)
    # Fallback: shallow copy + setattr
    new_opts = copy.copy(options)
    new_opts.hooks = hooks
    return new_opts


def _push_event_nonblocking(
    execution_id: str,
    event: Dict[str, Any],
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> None:
    """Fire-and-forget HTTP POST to {server_url}/agent/events/{executionId}."""

    def _do_push():
        try:
            import requests

            url = f"{server_url}/agent/events/{execution_id}"
            headers: Dict[str, str] = {}
            if auth_key:
                headers["X-Auth-Key"] = auth_key
            if auth_secret:
                headers["X-Auth-Secret"] = auth_secret
            requests.post(url, json=event, headers=headers, timeout=5)
        except Exception as exc:
            logger.debug("Event push failed (execution_id=%s): %s", execution_id, exc)

    _EVENT_PUSH_POOL.submit(_do_push)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd sdk/python && uv run pytest tests/unit/test_claude_agent_sdk_worker.py::TestAgentspanHooks tests/unit/test_claude_agent_sdk_worker.py::TestMergeHooks -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test file**

Run: `cd sdk/python && uv run pytest tests/unit/test_claude_agent_sdk_worker.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add sdk/python/src/agentspan/agents/frameworks/claude_agent_sdk.py sdk/python/tests/unit/test_claude_agent_sdk_worker.py
git commit -m "feat: add Claude Agent SDK hooks and event push"
```

---

## Chunk 3: Runtime Integration + Java Normalizer

### Task 5: Runtime `_build_passthrough_func` branch

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/runtime.py:2653-2667`
- Test: `sdk/python/tests/unit/test_passthrough_registration.py`

- [ ] **Step 1: Write the failing test**

Add to `sdk/python/tests/unit/test_passthrough_registration.py` in `TestBuildPassthroughFunc`:

```python
    def test_build_passthrough_func_passes_auth_to_claude_agent_sdk_worker(self):
        from agentspan.agents.runtime.runtime import AgentRuntime
        from agentspan.agents.runtime.config import AgentConfig

        config = AgentConfig(
            server_url="http://testserver:6767/api",
            auth_key="my_key",
            auth_secret="my_secret",
        )

        options = MagicMock()
        type(options).__name__ = "ClaudeCodeOptions"

        with patch(
            "agentspan.agents.frameworks.claude_agent_sdk.make_claude_agent_sdk_worker"
        ) as mock_worker:
            mock_worker.return_value = MagicMock()
            runtime = AgentRuntime.__new__(AgentRuntime)
            runtime._config = config
            runtime._build_passthrough_func(options, "claude_agent_sdk", "test_agent")

        mock_worker.assert_called_once_with(
            options, "test_agent", "http://testserver:6767/api", "my_key", "my_secret"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sdk/python && uv run pytest tests/unit/test_passthrough_registration.py::TestBuildPassthroughFunc::test_build_passthrough_func_passes_auth_to_claude_agent_sdk_worker -v`
Expected: FAIL — `ValueError: Unknown passthrough framework: claude_agent_sdk`

- [ ] **Step 3: Add the branch in `runtime.py`**

In `_build_passthrough_func()` at line 2667, before `raise ValueError(...)`, add:

```python
        elif framework == "claude_agent_sdk":
            from agentspan.agents.frameworks.claude_agent_sdk import make_claude_agent_sdk_worker

            return make_claude_agent_sdk_worker(agent_obj, name, server_url, auth_key, auth_secret)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sdk/python && uv run pytest tests/unit/test_passthrough_registration.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run broader regression check**

Run: `cd sdk/python && uv run pytest tests/unit/test_framework_detection.py tests/unit/test_passthrough_registration.py tests/unit/test_claude_agent_sdk_worker.py tests/unit/test_langchain_worker.py tests/unit/test_langgraph_worker.py -v`
Expected: All tests PASS (no regressions to existing frameworks)

- [ ] **Step 6: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/runtime.py sdk/python/tests/unit/test_passthrough_registration.py
git commit -m "feat: add claude_agent_sdk branch to _build_passthrough_func"
```

### Task 6: Java normalizer

**Files:**
- Create: `server/src/main/java/dev/agentspan/runtime/normalizer/ClaudeAgentSdkNormalizer.java`
- Create: `server/src/test/java/dev/agentspan/runtime/normalizer/ClaudeAgentSdkNormalizerTest.java`

- [ ] **Step 1: Write the failing test**

Create `server/src/test/java/dev/agentspan/runtime/normalizer/ClaudeAgentSdkNormalizerTest.java`:

```java
/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.normalizer;

import dev.agentspan.runtime.model.AgentConfig;
import org.junit.jupiter.api.Test;
import java.util.Map;
import static org.assertj.core.api.Assertions.*;

class ClaudeAgentSdkNormalizerTest {

    private final ClaudeAgentSdkNormalizer normalizer = new ClaudeAgentSdkNormalizer();

    @Test
    void frameworkIdIsClaudeAgentSdk() {
        assertThat(normalizer.frameworkId()).isEqualTo("claude_agent_sdk");
    }

    @Test
    void normalizeProducesPassthroughConfig() {
        Map<String, Object> raw = Map.of(
            "name", "my_agent",
            "_worker_name", "my_agent"
        );

        AgentConfig config = normalizer.normalize(raw);

        assertThat(config.getName()).isEqualTo("my_agent");
        assertThat(config.getModel()).isNull();
        assertThat(config.getMetadata()).containsEntry("_framework_passthrough", true);
        assertThat(config.getTools()).hasSize(1);
        assertThat(config.getTools().get(0).getName()).isEqualTo("my_agent");
        assertThat(config.getTools().get(0).getToolType()).isEqualTo("worker");
    }

    @Test
    void normalizeUsesDefaultNameWhenMissing() {
        AgentConfig config = normalizer.normalize(Map.of());

        assertThat(config.getName()).isEqualTo("claude_agent_sdk_agent");
        assertThat(config.getMetadata()).containsEntry("_framework_passthrough", true);
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && ./gradlew test --tests "dev.agentspan.runtime.normalizer.ClaudeAgentSdkNormalizerTest" 2>&1 | tail -20`
Expected: FAIL — class not found

- [ ] **Step 3: Create the normalizer**

Create `server/src/main/java/dev/agentspan/runtime/normalizer/ClaudeAgentSdkNormalizer.java`:

```java
/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.normalizer;

import dev.agentspan.runtime.model.AgentConfig;
import dev.agentspan.runtime.model.ToolConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.*;

/**
 * Normalizes Claude Agent SDK rawConfig into a passthrough AgentConfig.
 */
@Component
public class ClaudeAgentSdkNormalizer implements AgentConfigNormalizer {

    private static final Logger log = LoggerFactory.getLogger(ClaudeAgentSdkNormalizer.class);
    private static final String DEFAULT_NAME = "claude_agent_sdk_agent";

    @Override
    public String frameworkId() {
        return "claude_agent_sdk";
    }

    @Override
    public AgentConfig normalize(Map<String, Object> raw) {
        String name = getString(raw, "name", DEFAULT_NAME);
        String workerName = getString(raw, "_worker_name", name);
        log.info("Normalizing Claude Agent SDK agent: {}", name);

        AgentConfig config = new AgentConfig();
        config.setName(name);

        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("_framework_passthrough", true);
        config.setMetadata(metadata);

        ToolConfig worker = ToolConfig.builder()
            .name(workerName)
            .description("Claude Agent SDK passthrough worker")
            .toolType("worker")
            .build();
        config.setTools(List.of(worker));

        return config;
    }

    private String getString(Map<String, Object> map, String key, String defaultValue) {
        Object v = map.get(key);
        return v instanceof String ? (String) v : defaultValue;
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && ./gradlew test --tests "dev.agentspan.runtime.normalizer.ClaudeAgentSdkNormalizerTest" 2>&1 | tail -20`
Expected: All 3 tests PASS

- [ ] **Step 5: Run all normalizer tests for regression**

Run: `cd server && ./gradlew test --tests "dev.agentspan.runtime.normalizer.*" 2>&1 | tail -20`
Expected: All normalizer tests PASS

- [ ] **Step 6: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/normalizer/ClaudeAgentSdkNormalizer.java server/src/test/java/dev/agentspan/runtime/normalizer/ClaudeAgentSdkNormalizerTest.java
git commit -m "feat: add ClaudeAgentSdkNormalizer for passthrough compilation"
```

---

## Chunk 4: Example + Smoke Test

### Task 7: Basic example

**Files:**
- Create: `sdk/python/examples/claude_agent_sdk/01_basic_agent.py`

- [ ] **Step 1: Create example directory and file**

```bash
mkdir -p sdk/python/examples/claude_agent_sdk
```

Create `sdk/python/examples/claude_agent_sdk/01_basic_agent.py`:

```python
#!/usr/bin/env python3
"""Basic Claude Agent SDK agent running through agentspan.

Prerequisites:
    pip install claude-code-sdk  # or: uv add claude-code-sdk
    export ANTHROPIC_API_KEY=sk-...

Usage:
    # Start the agentspan server first, then:
    uv run python examples/claude_agent_sdk/01_basic_agent.py
"""

from claude_code_sdk import ClaudeCodeOptions

from agentspan.agents import AgentRuntime


def main():
    options = ClaudeCodeOptions(
        allowed_tools=["Read", "Glob", "Grep"],
        max_turns=5,
    )

    with AgentRuntime() as runtime:
        result = runtime.run(
            options,
            prompt="List the Python files in the current directory and summarize what each one does.",
        )
        print(f"\n--- Result ---\n{result.output}")
        print(f"\n--- Metadata ---")
        print(f"Execution ID: {result.execution_id}")
        print(f"Status: {result.status}")
        if result.token_usage:
            print(f"Token usage: {result.token_usage}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the example is syntactically valid**

Run: `cd sdk/python && uv run python -c "import ast; ast.parse(open('examples/claude_agent_sdk/01_basic_agent.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add sdk/python/examples/claude_agent_sdk/01_basic_agent.py
git commit -m "feat: add Claude Agent SDK basic example"
```

### Task 8: End-to-end smoke test

- [ ] **Step 1: Run the full Python test suite**

Run: `cd sdk/python && uv run pytest tests/unit/ -v --tb=short 2>&1 | tail -30`
Expected: All tests PASS, no regressions

- [ ] **Step 2: Run the Java test suite**

Run: `cd server && ./gradlew test 2>&1 | tail -20`
Expected: All tests PASS

- [ ] **Step 3: Manual smoke test (requires running server + API key)**

```bash
cd sdk/python
export ANTHROPIC_API_KEY=sk-...
# Start server in another terminal: agentspan server start
uv run python examples/claude_agent_sdk/01_basic_agent.py
```

Expected: Agent runs, lists files, prints result. Check server logs for:
- `Normalizing Claude Agent SDK agent: ...`
- Stream events arriving at `/api/agent/events/`

- [ ] **Step 4: Verify all changes committed**

All files should already be committed from Tasks 1-7. Verify with:
```bash
git status
git log --oneline -7
```
Expected: clean working tree, 7 commits from this plan visible in log.
