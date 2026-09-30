# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Agent → AgentConfig JSON serializer for server-side compilation.

Converts a Python :class:`Agent` tree into a JSON-serializable dict
matching the Java ``AgentConfig`` DTO structure.  Callables (tools,
guardrails, stop_when, router, handoffs) are registered as workers
on the SDK side and sent as task-name references.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from conductor.ai.agents.agent import Agent

logger = logging.getLogger("conductor.ai.agents.config_serializer")


class AgentConfigSerializer:
    """Serialize an :class:`Agent` tree into a server-compatible AgentConfig dict."""

    def serialize(self, agent: "Agent") -> dict:
        """Serialize an Agent into an AgentConfig JSON dict.

        Recursively serializes the agent and all sub-agents.  Callables
        are resolved (instructions → string) or registered as workers
        (stop_when, router, handoffs) and sent as task-name references.

        Args:
            agent: The root agent to serialize.

        Returns:
            A dict matching the Java ``AgentConfig`` DTO structure.
        """
        return self._serialize_agent(agent)

    def _serialize_agent(self, agent: "Agent") -> dict:
        from conductor.ai.agents.agent import PromptTemplate

        # Skill agents — emit the raw skill config so the server's
        # SkillNormalizer can compile sub-agents (e.g. gilfoyle, dinesh)
        # and tools (scripts, read_skill_file) into the workflow.
        if getattr(agent, "_framework", None) == "skill":
            raw_config = getattr(agent, "_framework_config", {})
            return {
                "name": agent.name,
                "model": agent.model or None,
                "_framework": "skill",
                **raw_config,
            }

        # Claude-code agents emit a passthrough stub — all config is consumed
        # by the worker closure, not sent to the server.
        if getattr(agent, "is_claude_code", False):
            stub: Dict[str, Any] = {
                "name": agent.name,
                "model": agent.model,
                "metadata": {"_framework_passthrough": True},
                "tools": [
                    {
                        "name": agent.name,
                        "toolType": "worker",
                        "description": "Claude Agent SDK passthrough worker",
                    }
                ],
            }
            # Declared credential names — wire-format key is "credentials"
            # to match AgentConfig#credentials on the server (see note above).
            if hasattr(agent, "credentials") and agent.credentials:
                stub["credentials"] = [c for c in agent.credentials if isinstance(c, str)]
            return stub

        # Strategy is emitted when the agent has any sub-agent declaration:
        # legacy ``agents=[…]`` OR PLAN_EXECUTE's named slots (``planner``,
        # ``fallback``). Without the slot check, a PLAN_EXECUTE coordinator
        # built with ``planner=…`` would have ``strategy: None`` on the wire
        # and the server's dispatch would fall to compileWithTools.
        has_sub_agents = (
            bool(agent.agents)
            or getattr(agent, "planner", None) is not None
            or getattr(agent, "fallback", None) is not None
        )
        config: Dict[str, Any] = {
            "name": agent.name,
            "model": agent.model or None,
            "baseUrl": getattr(agent, "base_url", None),
            "strategy": agent.strategy if has_sub_agents else None,
            "maxTurns": agent.max_turns,
            "timeoutSeconds": agent.timeout_seconds,
            "external": agent.external,
        }

        # Instructions
        if isinstance(agent.instructions, PromptTemplate):
            config["instructions"] = {
                "type": "prompt_template",
                "name": agent.instructions.name,
                "variables": agent.instructions.variables or None,
                "version": agent.instructions.version,
            }
        elif callable(agent.instructions):
            config["instructions"] = agent.instructions()
        else:
            config["instructions"] = agent.instructions or None

        # Tools
        if agent.tools:
            agent_stateful = getattr(agent, "stateful", False)
            config["tools"] = [
                self._serialize_tool(t, agent_stateful=agent_stateful) for t in agent.tools
            ]

        # Sub-agents (recursive)
        if agent.agents:
            config["agents"] = [self._serialize_agent(a) for a in agent.agents]

        # Router
        if agent.router is not None:
            config["router"] = self._serialize_router(agent)

        # Output type
        if agent.output_type is not None:
            config["outputType"] = self._serialize_output_type(agent.output_type)

        # Guardrails
        if agent.guardrails:
            config["guardrails"] = [self._serialize_guardrail(g) for g in agent.guardrails]

        # Memory (short-term conversation)
        if hasattr(agent, "memory") and agent.memory:
            config["memory"] = self._serialize_memory(agent.memory)

        # Long-term (OCG-backed) memory. When present, the server-side compiler
        # inlines retrieval (pre-loop) + distill/save/feedback (post-loop) steps
        # so memory works on the deployed/webhook path — not just client run().
        ltm = self._serialize_long_term_memory(agent)
        if ltm is not None:
            config["longTermMemory"] = ltm
            # feedback_sink delivers the human good/bad capability links out-of-band.
            # Emit a worker ref so the compiled path can call the Python sink worker.
            if getattr(agent, "feedback_sink", None) is not None:
                config["feedbackSink"] = {"taskName": f"{agent.name}_feedback_sink"}

        # Max tokens
        if agent.max_tokens is not None:
            config["maxTokens"] = agent.max_tokens

        # Context window budget for proactive condensation
        if agent.context_window_budget is not None:
            config["contextWindowBudget"] = agent.context_window_budget

        # Temperature
        if agent.temperature is not None:
            config["temperature"] = agent.temperature

        # Reasoning effort (OpenAI reasoning models)
        if getattr(agent, "reasoning_effort", None) is not None:
            config["reasoningEffort"] = agent.reasoning_effort

        # Stop when
        if agent.stop_when is not None:
            task_name = f"{agent.name}_stop_when"
            config["stopWhen"] = {"taskName": task_name}

        # Termination
        if agent.termination is not None:
            config["termination"] = self._serialize_termination(agent.termination)

        # Handoffs
        if agent.handoffs:
            config["handoffs"] = [self._serialize_handoff(h, agent.name) for h in agent.handoffs]

        # Allowed transitions
        if agent.allowed_transitions:
            config["allowedTransitions"] = agent.allowed_transitions

        # Introduction
        if agent.introduction:
            config["introduction"] = agent.introduction

        # Metadata
        if agent.metadata:
            config["metadata"] = agent.metadata

        # Plan-first preamble (Google ADK feature; renamed from ``planner``
        # boolean to ``enable_planning`` to free the ``planner`` JSON slot
        # for the PLAN_EXECUTE sub-agent below).
        if getattr(agent, "enable_planning", False):
            config["enablePlanning"] = True

        # PLAN_EXECUTE named slots: planner (required) + fallback (optional).
        # Both serialize as nested AgentConfig dicts. The server reads them
        # in MultiAgentCompiler.compilePlanExecute; the parent's ``tools``
        # list (already serialized above) becomes ``knownToolNames`` on PAC.
        planner_agent = getattr(agent, "planner", None)
        if planner_agent is not None and not isinstance(planner_agent, bool):
            config["planner"] = self._serialize_agent(planner_agent)
        fallback_agent = getattr(agent, "fallback", None)
        if fallback_agent is not None:
            config["fallback"] = self._serialize_agent(fallback_agent)

        # Callbacks — emit for any position that has handlers or legacy callables
        from conductor.ai.agents.callback import (
            _LEGACY_ATTR_TO_POSITION,
            POSITION_TO_METHOD,
            _chain_callbacks_for_position,
        )

        handlers = getattr(agent, "callbacks", None) or []
        callbacks = []
        for position in POSITION_TO_METHOD:
            legacy_attr = next(
                (attr for attr, pos in _LEGACY_ATTR_TO_POSITION.items() if pos == position),
                None,
            )
            legacy_fn = getattr(agent, legacy_attr, None) if legacy_attr else None
            if _chain_callbacks_for_position(position, handlers, legacy_fn) is not None:
                task_name = f"{agent.name}_{position}"
                callbacks.append({"position": position, "taskName": task_name})
        if callbacks:
            config["callbacks"] = callbacks

        # Include contents
        if getattr(agent, "include_contents", None) is not None:
            config["includeContents"] = agent.include_contents

        # Thinking config
        if getattr(agent, "thinking_budget_tokens", None) is not None:
            config["thinkingConfig"] = {
                "enabled": True,
                "budgetTokens": agent.thinking_budget_tokens,
            }

        # Required tools
        if getattr(agent, "required_tools", None):
            config["requiredTools"] = agent.required_tools

        if getattr(agent, "prefill_tools", None):
            config["prefillTools"] = [
                {"toolName": pt.tool_name, "arguments": pt.arguments} for pt in agent.prefill_tools
            ]

        if getattr(agent, "fallback_max_turns", None) is not None:
            config["fallbackMaxTurns"] = agent.fallback_max_turns

        if getattr(agent, "plan_source", None) is not None:
            config["planSource"] = agent.plan_source

        if getattr(agent, "planner_context", None):
            # Entries are Context dataclasses (normalised by Agent.__init__)
            # or raw dicts when hand-rolled. Call .to_dict() when present;
            # otherwise pass through.
            wire_entries = []
            for entry in agent.planner_context:
                if hasattr(entry, "to_dict"):
                    wire_entries.append(entry.to_dict())
                else:
                    wire_entries.append(entry)
            config["plannerContext"] = wire_entries

        # Synthesize flag — whether to append a final LLM synthesis step
        # after specialist agents complete. Default true; pass through only
        # when explicitly disabled to keep payloads small.
        if not getattr(agent, "synthesize", True):
            config["synthesize"] = False

        # Masked fields — input/output field names to redact in execution
        # history and UI. Maps to Conductor's WorkflowDef.maskedFields.
        if getattr(agent, "masked_fields", None):
            config["maskedFields"] = list(agent.masked_fields)

        # Gate condition (for sequential pipelines)
        if getattr(agent, "gate", None) is not None:
            config["gate"] = self._serialize_gate(agent)

        # Code execution
        if hasattr(agent, "code_execution_config") and agent.code_execution_config:
            cfg = agent.code_execution_config
            config["codeExecution"] = {
                "enabled": cfg.enabled,
                "allowedLanguages": cfg.allowed_languages,
                "allowedCommands": cfg.allowed_commands,
                "timeout": cfg.timeout,
            }

        # CLI command execution
        if hasattr(agent, "cli_config") and agent.cli_config:
            cfg = agent.cli_config
            config["cliConfig"] = {
                "enabled": cfg.enabled,
                "allowedCommands": cfg.allowed_commands,
                "timeout": cfg.timeout,
                "allowShell": cfg.allow_shell,
            }

        # Agent-level declared credentials — wire key is "credentials" to
        # match the server's AgentConfig#credentials field.
        if hasattr(agent, "credentials") and agent.credentials:
            config["credentials"] = [c for c in agent.credentials if isinstance(c, str)]

        # Remove None values for cleaner JSON
        return {k: v for k, v in config.items() if v is not None}

    def _serialize_tool(self, tool_obj: Any, *, agent_stateful: bool = False) -> dict:
        """Serialize a tool to a ToolConfig dict."""
        from conductor.ai.agents.tool import get_tool_def

        td = get_tool_def(tool_obj)
        result: Dict[str, Any] = {
            "name": td.name,
            "description": td.description,
            "inputSchema": td.input_schema,
            "toolType": td.tool_type,
        }

        if td.output_schema:
            result["outputSchema"] = td.output_schema

        if td.approval_required:
            result["approvalRequired"] = True

        if agent_stateful or getattr(td, "stateful", False):
            result["stateful"] = True

        if td.timeout_seconds is not None:
            result["timeoutSeconds"] = td.timeout_seconds

        if td.max_calls is not None:
            result["maxCalls"] = td.max_calls

        if td.config:
            if td.tool_type == "agent_tool" and "agent" in td.config:
                serialized_config = dict(td.config)
                serialized_config["agentConfig"] = self._serialize_agent(
                    serialized_config.pop("agent")
                )
                result["config"] = serialized_config
            else:
                result["config"] = td.config

        if td.guardrails:
            result["guardrails"] = [self._serialize_guardrail(g) for g in td.guardrails]

        # Declared credential names — must land in config so the server can
        # extract them into the execution token's declared_names list (bounds
        # /api/workers/credentials resolution). The wire-format key is "credentials"
        # because the server-side compiler (AgentService#collectCredentialsRecursive)
        # reads `tool.config["credentials"]`. The SDK-facing parameter is named
        # `credentials=` after the user-facing rename; only the wire key kept the
        # old name to avoid a cross-language compiler/serializer fan-out.
        if td.credentials:
            cred_names = [c if isinstance(c, str) else c.env_var for c in td.credentials]
            if "config" not in result:
                result["config"] = {}
            result["config"]["credentials"] = cred_names

        return result

    def _serialize_guardrail(self, guardrail: Any) -> dict:
        """Serialize a Guardrail to a GuardrailConfig dict."""
        from conductor.ai.agents.guardrail import LLMGuardrail, RegexGuardrail

        result: Dict[str, Any] = {
            "name": guardrail.name,
            "position": guardrail.position,
            "onFail": guardrail.on_fail,
            "maxRetries": guardrail.max_retries,
        }

        if isinstance(guardrail, RegexGuardrail):
            result["guardrailType"] = "regex"
            result["patterns"] = guardrail._pattern_strings
            result["mode"] = guardrail._mode
            if guardrail._custom_message:
                result["message"] = guardrail._custom_message
        elif isinstance(guardrail, LLMGuardrail):
            result["guardrailType"] = "llm"
            result["model"] = guardrail._model
            result["policy"] = guardrail._policy
            if guardrail._max_tokens:
                result["maxTokens"] = guardrail._max_tokens
        elif guardrail.external:
            result["guardrailType"] = "external"
            result["taskName"] = guardrail.name
        else:
            # Custom @guardrail function
            result["guardrailType"] = "custom"
            result["taskName"] = guardrail.name

        return result

    def _serialize_termination(self, condition: Any) -> dict:
        """Serialize a TerminationCondition to a TerminationConfig dict."""
        from conductor.ai.agents.termination import (
            MaxMessageTermination,
            StopMessageTermination,
            TextMentionTermination,
            TokenUsageTermination,
            _AndTermination,
            _OrTermination,
        )

        if isinstance(condition, TextMentionTermination):
            return {
                "type": "text_mention",
                "text": condition.text,
                "caseSensitive": condition.case_sensitive,
            }
        elif isinstance(condition, StopMessageTermination):
            return {
                "type": "stop_message",
                "stopMessage": condition.stop_message,
            }
        elif isinstance(condition, MaxMessageTermination):
            return {
                "type": "max_message",
                "maxMessages": condition.max_messages,
            }
        elif isinstance(condition, TokenUsageTermination):
            result: Dict[str, Any] = {"type": "token_usage"}
            if condition.max_total_tokens is not None:
                result["maxTotalTokens"] = condition.max_total_tokens
            if condition.max_prompt_tokens is not None:
                result["maxPromptTokens"] = condition.max_prompt_tokens
            if condition.max_completion_tokens is not None:
                result["maxCompletionTokens"] = condition.max_completion_tokens
            return result
        elif isinstance(condition, _AndTermination):
            return {
                "type": "and",
                "conditions": [self._serialize_termination(c) for c in condition.conditions],
            }
        elif isinstance(condition, _OrTermination):
            return {
                "type": "or",
                "conditions": [self._serialize_termination(c) for c in condition.conditions],
            }
        else:
            logger.warning("Unknown termination condition type: %s", type(condition))
            return {"type": "unknown"}

    def _serialize_handoff(self, handoff: Any, agent_name: str) -> dict:
        """Serialize a HandoffCondition to a HandoffConfig dict."""
        from conductor.ai.agents.handoff import OnCondition, OnTextMention, OnToolResult

        result: Dict[str, Any] = {"target": handoff.target}

        if isinstance(handoff, OnToolResult):
            result["type"] = "on_tool_result"
            result["toolName"] = handoff.tool_name
            if handoff.result_contains:
                result["resultContains"] = handoff.result_contains
        elif isinstance(handoff, OnTextMention):
            result["type"] = "on_text_mention"
            result["text"] = handoff.text
        elif isinstance(handoff, OnCondition):
            result["type"] = "on_condition"
            task_name = f"{agent_name}_handoff_{handoff.target}"
            result["taskName"] = task_name
        else:
            result["type"] = "unknown"

        return result

    def _serialize_router(self, agent: "Agent") -> Any:
        """Serialize a router to either an AgentConfig or a WorkerRef."""
        from conductor.ai.agents.agent import Agent as AgentClass

        router = agent.router
        if isinstance(router, AgentClass) or (hasattr(router, "model") and router.model):
            return self._serialize_agent(router)
        elif callable(router):
            task_name = f"{agent.name}_router_fn"
            return {"taskName": task_name}
        else:
            return None

    def _serialize_output_type(self, output_type: type) -> dict:
        """Serialize a Pydantic model class to an OutputTypeConfig dict."""
        try:
            from conductor.ai.agents._internal.schema_utils import schema_from_pydantic

            schema = schema_from_pydantic(output_type)
            return {
                "schema": schema,
                "className": output_type.__name__,
            }
        except (TypeError, ImportError):
            return {
                "className": output_type.__name__,
            }

    def _serialize_gate(self, agent: "Agent") -> dict:
        """Serialize a gate condition to a GateConfig dict."""
        from conductor.ai.agents.gate import TextGate

        gate = agent.gate
        if isinstance(gate, TextGate):
            return {
                "type": "text_contains",
                "text": gate.text,
                "caseSensitive": gate.case_sensitive,
            }
        elif callable(gate):
            task_name = f"{agent.name}_gate"
            return {"taskName": task_name}
        else:
            raise ValueError(f"Unsupported gate type: {type(gate)}")

    def _serialize_memory(self, memory: Any) -> dict:
        """Serialize memory to a MemoryConfig dict."""
        result: Dict[str, Any] = {}
        if hasattr(memory, "messages") and memory.messages:
            result["messages"] = memory.messages
        if hasattr(memory, "max_messages") and memory.max_messages:
            result["maxMessages"] = memory.max_messages
        return result

    def _serialize_long_term_memory(self, agent: "Agent") -> "Any":
        """Serialize an agent's OCG-backed semantic memory to a LongTermMemoryConfig dict.

        Returns ``None`` (no-op) unless the agent has a ``semantic_memory`` whose
        store exposes an OCG base url. Reads the OCG instance url, scope owner,
        user and scope off the store; the credential is a SERVER-resolvable secret
        NAME (e.g. ``OCG_PUBLIC_KEY``) — never the raw client token. The summary
        model falls back to the agent's own model when not explicitly set.
        """
        sm = getattr(agent, "semantic_memory", None)
        if sm is None:
            return None
        store = getattr(sm, "store", None)
        # Only OCG-backed stores compile server-side (need a base url to call).
        base = getattr(store, "_base", None) if store is not None else None
        if not base:
            return None

        result: Dict[str, Any] = {
            "ocgUrl": base,
            "credential": getattr(store, "_credential", None) or "OCG_PUBLIC_KEY",
            "agent": getattr(store, "_agent", None),
            "scope": getattr(store, "_scope", None) or "agent",
            "maxResults": getattr(sm, "max_results", None),
            "summaryModel": getattr(agent, "memory_summary_model", None) or (agent.model or None),
        }
        user = getattr(store, "_user", None)
        if user:
            result["user"] = user
        return {k: v for k, v in result.items() if v is not None}
