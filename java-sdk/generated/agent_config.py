"""AUTO-GENERATED from agent-schema.json by generate.py — do not edit."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class AgentConfig:
    name: Optional[str] = None
    description: Optional[str] = None
    model: Optional[str] = None
    external: Optional[bool] = None
    baseUrl: Optional[str] = None
    instructions: Optional[Any] = None
    introduction: Optional[str] = None
    tools: Optional[List[Tool]] = None
    agents: Optional[List[AgentConfig]] = None
    strategy: Optional[str] = None
    router: Optional[Any] = None
    guardrails: Optional[List[Guardrail]] = None
    maxTurns: Optional[int] = None
    maxTokens: Optional[int] = None
    temperature: Optional[float] = None
    timeoutSeconds: Optional[int] = None
    reasoningEffort: Optional[str] = None
    contextWindowBudget: Optional[int] = None
    thinkingConfig: Optional[ThinkingConfig] = None
    memory: Optional[Memory] = None
    termination: Optional[Termination] = None
    outputType: Optional[OutputType] = None
    handoffs: Optional[List[Handoff]] = None
    allowedTransitions: Optional[Dict[str, Any]] = None
    callbacks: Optional[List[Callback]] = None
    gate: Optional[Gate] = None
    stopWhen: Optional[WorkerRef] = None
    enablePlanning: Optional[bool] = None
    planner: Optional[AgentConfig] = None
    fallback: Optional[AgentConfig] = None
    fallbackMaxTurns: Optional[int] = None
    plannerContext: Optional[List[PlannerContextEntry]] = None
    planSource: Optional[Dict[str, Any]] = None
    synthesize: Optional[bool] = None
    stateful: Optional[bool] = None
    sessionId: Optional[str] = None
    includeContents: Optional[str] = None
    requiredTools: Optional[List[str]] = None
    prefillTools: Optional[List[PrefillTool]] = None
    credentials: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    localCodeExecution: Optional[bool] = None
    codeExecution: Optional[CodeExecution] = None
    cliConfig: Optional[CliConfig] = None
    maskedFields: Optional[List[str]] = None


@dataclass
class PromptTemplate:
    type: Optional[str] = None
    name: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    version: Optional[int] = None


@dataclass
class Tool:
    name: Optional[str] = None
    description: Optional[str] = None
    inputSchema: Optional[Dict[str, Any]] = None
    outputSchema: Optional[Dict[str, Any]] = None
    toolType: Optional[str] = None
    approvalRequired: Optional[bool] = None
    stateful: Optional[bool] = None
    timeoutSeconds: Optional[int] = None
    maxCalls: Optional[int] = None
    config: Optional[Dict[str, Any]] = None
    guardrails: Optional[List[Guardrail]] = None


@dataclass
class Guardrail:
    name: Optional[str] = None
    guardrailType: Optional[str] = None
    position: Optional[str] = None
    onFail: Optional[str] = None
    maxRetries: Optional[int] = None
    taskName: Optional[str] = None
    patterns: Optional[List[str]] = None
    mode: Optional[str] = None
    message: Optional[str] = None
    model: Optional[str] = None
    policy: Optional[str] = None
    maxTokens: Optional[int] = None


@dataclass
class Termination:
    type: Optional[str] = None
    text: Optional[str] = None
    caseSensitive: Optional[bool] = None
    stopMessage: Optional[str] = None
    maxMessages: Optional[int] = None
    maxTotalTokens: Optional[int] = None
    maxPromptTokens: Optional[int] = None
    maxCompletionTokens: Optional[int] = None
    conditions: Optional[List[Termination]] = None


@dataclass
class Handoff:
    type: Optional[str] = None
    target: Optional[str] = None
    toolName: Optional[str] = None
    resultContains: Optional[str] = None
    text: Optional[str] = None
    taskName: Optional[str] = None


@dataclass
class Callback:
    position: Optional[str] = None
    taskName: Optional[str] = None


@dataclass
class Memory:
    messages: Optional[List[Message]] = None
    maxMessages: Optional[int] = None


@dataclass
class Message:
    role: Optional[str] = None
    message: Optional[str] = None


@dataclass
class CodeExecution:
    enabled: Optional[bool] = None
    allowedLanguages: Optional[List[str]] = None
    allowedCommands: Optional[List[str]] = None
    timeout: Optional[int] = None


@dataclass
class CliConfig:
    enabled: Optional[bool] = None
    allowedCommands: Optional[List[str]] = None
    timeout: Optional[int] = None
    allowShell: Optional[bool] = None
    workingDir: Optional[str] = None


@dataclass
class ThinkingConfig:
    enabled: Optional[bool] = None
    budgetTokens: Optional[int] = None


@dataclass
class PrefillTool:
    toolName: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None


@dataclass
class PlannerContextEntry:
    text: Optional[str] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, Any]] = None
    required: Optional[bool] = None
    maxBytes: Optional[int] = None


@dataclass
class OutputType:
    schema: Optional[Dict[str, Any]] = None
    className: Optional[str] = None


@dataclass
class Gate:
    type: Optional[str] = None
    text: Optional[str] = None
    caseSensitive: Optional[bool] = None
    taskName: Optional[str] = None


@dataclass
class WorkerRef:
    taskName: Optional[str] = None
