# sdk/python/src/agentspan/agents/frameworks/langchain.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""LangChain AgentExecutor worker support — full extraction and passthrough."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.callbacks import BaseCallbackHandler

from agentspan.agents.frameworks.serializer import WorkerInfo

logger = logging.getLogger("agentspan.agents.frameworks.langchain")

_EVENT_PUSH_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="langchain-event-push")
_DEFAULT_NAME = "langchain_agent"


def serialize_langchain(executor: Any) -> Tuple[Dict[str, Any], List[WorkerInfo]]:
    """Serialize a LangChain AgentExecutor into (raw_config, [WorkerInfo]).

    Tries full extraction (model + tools) first, falls back to passthrough.
    """
    name = getattr(executor, "name", None) or _DEFAULT_NAME

    model_str = _extract_model_from_executor(executor)
    tools = getattr(executor, "tools", []) or []

    if model_str and tools:
        logger.info(
            "LangChain '%s': full extraction — model=%s, %d tools",
            name,
            model_str,
            len(tools),
        )
        from agentspan.agents.frameworks.langgraph import _serialize_full_extraction

        return _serialize_full_extraction(name, model_str, tools)

    logger.info("LangChain '%s': passthrough (model=%s, tools=%d)", name, model_str, len(tools))
    raw_config: Dict[str, Any] = {"name": name, "_worker_name": name}
    worker = WorkerInfo(
        name=name,
        description=f"LangChain passthrough worker for {name}",
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "session_id": {"type": "string"},
            },
        },
        func=None,
    )
    return raw_config, [worker]


def _extract_model_from_executor(executor: Any) -> Optional[str]:
    """Try to extract 'provider/model' from an AgentExecutor's LLM."""
    from agentspan.agents.frameworks.langgraph import _try_get_model_string

    # Try common paths to the LLM
    for path in (
        ("agent", "llm"),
        ("agent", "llm_chain", "llm"),
        ("agent", "runnable", "first"),
        ("llm",),
    ):
        obj = executor
        for attr in path:
            obj = getattr(obj, attr, None)
            if obj is None:
                break
        if obj is not None:
            result = _try_get_model_string(obj)
            if result:
                return result
    return None


def make_langchain_worker(
    executor: Any,
    name: str,
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> Any:
    """Build a pre-wrapped tool_worker(task) -> TaskResult for a LangChain AgentExecutor."""
    from conductor.client.http.models.task import Task
    from conductor.client.http.models.task_result import TaskResult
    from conductor.client.http.models.task_result_status import TaskResultStatus

    def tool_worker(task: Task) -> TaskResult:
        workflow_id = task.workflow_instance_id
        prompt = task.input_data.get("prompt", "")
        session_id = (task.input_data.get("session_id") or "").strip()
        if session_id:
            logger.debug(
                "session_id '%s' received but not forwarded — AgentExecutor does not support thread_id natively",
                session_id,
            )

        # Resolve workflow-level credentials and inject into os.environ
        _injected_cred_keys = []
        try:
            import os as _os
            from agentspan.agents.runtime._dispatch import (
                _extract_execution_token,
                _get_credential_fetcher,
                _workflow_credentials,
                _workflow_credentials_lock,
            )
            wf_id = workflow_id or ""
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
                            _injected_cred_keys.append(k)
        except Exception as _cred_err:
            logger.warning("Failed to resolve credentials for LangChain: %s", _cred_err)

        try:
            handler = AgentspanCallbackHandler(workflow_id, server_url, auth_key, auth_secret)
            result = executor.invoke({"input": prompt}, config={"callbacks": [handler]})
            output = result.get("output", "") if isinstance(result, dict) else str(result)
            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=workflow_id,
                status=TaskResultStatus.COMPLETED,
                output_data={"result": output},
            )
        except Exception as exc:
            logger.error("LangChain worker error (workflow_id=%s): %s", workflow_id, exc)
            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=workflow_id,
                status=TaskResultStatus.FAILED,
                reason_for_incompletion=str(exc),
            )
        finally:
            import os as _os
            for k in _injected_cred_keys:
                _os.environ.pop(k, None)

    return tool_worker


class AgentspanCallbackHandler(BaseCallbackHandler):
    """LangChain callback handler that pushes events to Agentspan SSE via HTTP.

    Must inherit from BaseCallbackHandler so LangChain's AgentExecutor
    recognises it as a valid callback. Plain classes are rejected at runtime.
    """

    def __init__(self, workflow_id: str, server_url: str, auth_key: str, auth_secret: str):
        super().__init__()
        self._workflow_id = workflow_id
        self._server_url = server_url
        self._auth_key = auth_key
        self._auth_secret = auth_secret
        self._tool_names: dict = {}

    def on_llm_start(self, serialized, prompts, **kwargs):
        _push_event_nonblocking(
            self._workflow_id,
            {"type": "thinking", "content": "llm"},
            self._server_url,
            self._auth_key,
            self._auth_secret,
        )

    def on_tool_start(self, serialized, input_str, **kwargs):
        tool_name = serialized.get("name", "") if isinstance(serialized, dict) else ""
        run_id = kwargs.get("run_id")
        if run_id is not None:
            self._tool_names[run_id] = tool_name
        _push_event_nonblocking(
            self._workflow_id,
            {"type": "tool_call", "toolName": tool_name, "args": {"input": input_str}},
            self._server_url,
            self._auth_key,
            self._auth_secret,
        )

    def on_tool_end(self, output, **kwargs):
        run_id = kwargs.get("run_id")
        tool_name = self._tool_names.pop(run_id, "") if run_id is not None else ""
        _push_event_nonblocking(
            self._workflow_id,
            {"type": "tool_result", "toolName": tool_name, "result": str(output)},
            self._server_url,
            self._auth_key,
            self._auth_secret,
        )

    def on_tool_error(self, error, **kwargs):
        run_id = kwargs.get("run_id")
        tool_name = self._tool_names.pop(run_id, "") if run_id is not None else ""
        _push_event_nonblocking(
            self._workflow_id,
            {"type": "tool_result", "toolName": tool_name, "result": f"ERROR: {error}"},
            self._server_url,
            self._auth_key,
            self._auth_secret,
        )


def _push_event_nonblocking(
    workflow_id: str,
    event: Dict[str, Any],
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> None:
    """Fire-and-forget HTTP POST to {server_url}/agent/events/{workflowId}."""

    def _do_push():
        try:
            import requests

            url = f"{server_url}/agent/events/{workflow_id}"
            headers = {}
            if auth_key:
                headers["X-Auth-Key"] = auth_key
            if auth_secret:
                headers["X-Auth-Secret"] = auth_secret
            requests.post(url, json=event, headers=headers, timeout=5)
        except Exception as exc:
            logger.debug("Event push failed (workflow_id=%s): %s", workflow_id, exc)

    _EVENT_PUSH_POOL.submit(_do_push)
