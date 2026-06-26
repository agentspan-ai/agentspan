# Conductor Agent Java SDK

Build durable AI agents in Java, backed by [Conductor](https://conductor.netflix.com/) workflows. Your agents survive process crashes, tool calls scale independently, and human approvals can take days — all without managing state yourself.

```java
Agent agent = Agent.builder()
    .name("assistant")
    .model("openai/gpt-4o-mini")
    .instructions("You are a helpful assistant.")
    .build();

try (AgentRuntime runtime = new AgentRuntime()) {
    AgentResult result = runtime.run(agent, "What is the capital of France?");
    System.out.println(result.getOutput());
}
```

Namespace: `org.conductoross.conductor.ai`. Requires Java 21+.

## Documentation map

The docs are organized into five areas:

### a) Get started

- **[Getting Started](getting-started.md)** — install (Maven/Gradle), set env vars, run your first agent in under 30 seconds.

### b) Writing agents

- **[Agents](concepts/agents.md)** — the full `Agent.builder()` API, dynamic instructions, `@AgentDef`/`Agent.fromInstance`.
- **[Tools](concepts/tools.md)** — `@Tool` + `ToolRegistry.fromInstance`, and built-ins: HTTP, MCP, Human, Media (image/audio/video), PDF, RAG, WaitForMessage, AgentTool.
- **[Multi-Agent](concepts/multi-agent.md)** — sequential, parallel, handoff, router, swarm, round-robin, plan-execute.
- **[Guardrails](concepts/guardrails.md)** · **[Termination](concepts/termination.md)** — validation and early-exit conditions.
- **[Callbacks](concepts/callbacks.md)** — lifecycle hooks (`CallbackHandler`).
- **[Streaming & Human-in-the-Loop](concepts/streaming-hitl.md)** — event streams and approval flows.
- **[Stateful Agents](concepts/stateful.md)** — sessions, conversation memory, multi-turn.
- **[Structured Output](concepts/structured-output.md)** — typed results via `outputType`.
- **[Scheduling](concepts/scheduling.md)** · **[Skills](concepts/skills.md)**.

### c) Framework agents

Run agents authored in another framework on the durable Agentspan runtime.

- **[OpenAI Agents SDK](frameworks/openai.md)** · **[Google ADK](frameworks/google-adk.md)** · **[LangChain4j](frameworks/langchain4j.md)** · **[LangGraph4j](frameworks/langgraph4j.md)**.

### d) Operating agents

- **[Deploy · Serve · Run · Plan](concepts/deploy-serve-run.md)** — the four runtime modes.
- **[Spring Boot](spring-boot.md)** — auto-configuration and `@AgentDef` bean discovery.
- **[Agent Field Reference](agent-structure.md)** · **[Agent JSON Schema](agent-schema.md)** — the wire format.

### e) API reference

- **[Public API summary](api-reference.md)** — every public signature on one page.
- **[AgentRuntime](agent-runtime-api.md)** — the entry-point class in detail.
- **[AgentClient (internal)](agent-client-api.md)** — the `/api/agent/*` control plane.

## Installation

=== "Gradle"

    ```groovy
    implementation 'org.conductoross.conductor:conductor-agent-sdk:0.1.0'
    ```

=== "Maven"

    ```xml
    <dependency>
        <groupId>org.conductoross.conductor</groupId>
        <artifactId>conductor-agent-sdk</artifactId>
        <version>0.1.0</version>
    </dependency>
    ```

**Requirements:** Java 21+ · an Agentspan server (see [Getting Started](getting-started.md)).

## What makes it different

| Feature | Agentspan | Thread-based SDKs |
|---|---|---|
| Survives crashes | ✅ Conductor workflow | ❌ State lost |
| Tool workers | ✅ Distributed tasks | ❌ In-process only |
| Long-running | ✅ Days / weeks | ❌ Minutes |
| Human-in-the-loop | ✅ Native approval flow | ❌ Polling hacks |
| Observability | ✅ Full workflow audit log | ❌ Log scraping |
