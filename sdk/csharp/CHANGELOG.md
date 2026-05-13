# Changelog

All notable changes to the Agentspan .NET SDK will be documented in this file.

## [0.1.0] - 2026-05-09

### Initial Release

First public release of the Agentspan .NET SDK.

#### Core SDK (`Agentspan` NuGet package)

- **`Agent`** — define agents with model, instructions, tools, guardrails, strategies, and sub-agents
- **`AgentRuntime`** — run agents with `RunAsync`, start long-running agents with `StartAsync`, send messages with `SendMessageAsync`
- **`AgentHandle`** — control running agents: `StopAsync`, `WaitAsync`, `ExecutionId`
- **`ToolDef` / `ToolDefFactory`** — define custom tools with typed handlers
- **`ToolRegistry`** — auto-discover tools from class instances via `[Tool]` attribute
- **`WaitForMessageTool`** — server-side blocking message queue for stateful agents
- **`ApiTools`** — generate tools from OpenAPI/Swagger specs
- **`HttpTool`** — direct HTTP call tool
- **Strategies** — `Sequential`, `Parallel`, `Router`, `Swarm`, `RoundRobin`, `RandomRobin`, `ManualSelection`
- **Guardrails** — regex, LLM, and custom guardrails with `RAISE` / `CONTINUE` / `FIX` policies on any position (input/output, agent/tool)
- **Termination** — composable stop conditions: `MaxTurns`, `TextMentioned`, `ExternalStop`, `FunctionCall`, `All`, `Any`, `Not`
- **Structured output** — `OutputType<T>` with JSON schema generation
- **Code execution** — local, Docker, and sandboxed Python execution
- **Semantic memory** — vector-store backed long-term memory
- **OpenTelemetry tracing** — distributed tracing support
- **Streaming** — token-by-token streaming via `StreamAsync`
- **Human-in-the-loop** — interrupt and resume workflows with human approval
- **Credentials** — per-execution credential isolation for tool calls
- **Callbacks** — `BeforeModel` / `AfterModel` / `BeforeTool` / `AfterTool` lifecycle hooks
- **Thinking config** — extended thinking budget for supported models
- **Shared state** — typed shared state across agents in a workflow
- **Planner** — agent planning mode
- **UserProxyAgent** / **GPTAssistantAgent** — compatibility agents
- **`DeployAsync` / `ServeAsync` / `RunByNameAsync`** — deploy, serve, and trigger named agents

#### Examples (93 total)

Covers all major patterns: basic agents, tools, structured output, HTTP tools, handoffs, sequential/parallel/swarm/router/hierarchical pipelines, HITL, guardrails, streaming, long-running agents, credentials, strategies, code execution, semantic memory, tracing, multimodal, external workers, scatter-gather, fan-out/fan-in, stateful resume, and more.
