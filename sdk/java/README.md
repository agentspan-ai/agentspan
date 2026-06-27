# Conductor Agents Java SDK

Java SDK for the [Conductor Agents](https://agentspan.dev) agent orchestration platform. Build, deploy, and run AI agents backed by Conductor workflows.

## Requirements

- Java 21+
- Maven 3.6+ or Gradle 7+
- A running Conductor Agents server

## Installation

Maven (`pom.xml`):

```xml
<dependency>
    <groupId>org.conductoross.conductor</groupId>
    <artifactId>conductor-agent-sdk</artifactId>
    <version>0.1.0</version>
</dependency>
```

Gradle (`build.gradle`):

```groovy
implementation 'org.conductoross.conductor:conductor-agent-sdk:0.1.0'
```

### Spring Boot starter

For Spring Boot apps, add the auto-configuration starter instead:

```xml
<dependency>
    <groupId>org.conductoross.conductor</groupId>
    <artifactId>conductor-agent-sdk-spring</artifactId>
    <version>0.1.0</version>
</dependency>
```

```groovy
implementation 'org.conductoross.conductor:conductor-agent-sdk-spring:0.1.0'
```

## Quick Start

```java
import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.model.AgentResult;

public class Main {
    public static void main(String[] args) {
        Agent agent = Agent.builder()
            .name("assistant")
            .model("openai/gpt-4o")
            .instructions("You are a helpful assistant.")
            .build();

        // AgentRuntime is AutoCloseable — try-with-resources shuts down workers cleanly.
        try (AgentRuntime runtime = new AgentRuntime()) {
            AgentResult result = runtime.run(agent, "What is the capital of France?");
            result.printResult();
        }
    }
}
```

> In Spring, inject the auto-configured `AgentRuntime` bean instead of constructing one.

## Configuration

Set environment variables:

```bash
export AGENTSPAN_SERVER_URL=http://localhost:6767/api
export AGENTSPAN_AUTH_KEY=your-key
export AGENTSPAN_AUTH_SECRET=your-secret
export AGENTSPAN_LLM_MODEL=openai/gpt-4o
```

Or configure programmatically. Connection (server URL + auth) is owned by the
Conductor `ApiClient`; `AgentConfig` carries only worker-runner tuning:

```java
import io.orkes.conductor.client.ApiClient;
import org.conductoross.conductor.ai.AgentConfig;
import org.conductoross.conductor.ai.AgentRuntime;

// Build the Conductor client (server URL + optional key/secret auth)…
ApiClient client = AgentRuntime.client("http://localhost:6767", "my-key", "my-secret");
// …and pass worker tuning (poll interval ms, worker threads).
AgentRuntime runtime = new AgentRuntime(client, new AgentConfig(100, 5));
```

> Or just `new AgentRuntime()` / `new AgentRuntime(new AgentConfig(100, 5))` to
> build the client from `AGENTSPAN_SERVER_URL` / `AGENTSPAN_AUTH_KEY` /
> `AGENTSPAN_AUTH_SECRET`.

## Tools

Define tools using the `@Tool` annotation:

```java
import org.conductoross.conductor.ai.annotations.Tool;
import org.conductoross.conductor.ai.internal.ToolRegistry;

public class WeatherTools {
    @Tool(name = "get_weather", description = "Get weather for a city")
    public String getWeather(String city) {
        return "Sunny, 72F in " + city;
    }
}

// Register with agent
WeatherTools tools = new WeatherTools();
Agent agent = Agent.builder()
    .name("weather_agent")
    .model("openai/gpt-4o")
    .tools(ToolRegistry.fromInstance(tools))
    .build();
```

## Multi-Agent

```java
Agent researcher = Agent.builder().name("researcher").model("openai/gpt-4o")
    .instructions("Research the topic.").build();
Agent writer = Agent.builder().name("writer").model("openai/gpt-4o")
    .instructions("Write based on research.").build();

// Sequential pipeline
Agent pipeline = researcher.then(writer);
try (AgentRuntime runtime = new AgentRuntime()) {
    AgentResult result = runtime.run(pipeline, "Write about AI trends");
}
```

## Streaming

```java
try (AgentRuntime runtime = new AgentRuntime()) {
    AgentStream stream = runtime.stream(agent, "Tell me a story");
    for (AgentEvent event : stream) {
        System.out.println(event.getType() + ": " + event.getContent());
    }
    AgentResult result = stream.getResult();
}
```

## Examples

See the `examples/` directory for complete working examples:

- `Example01BasicAgent` — Hello world
- `Example02Tools` — Tool-using agents
- `Example03StructuredOutput` — Typed output
- `Example05Handoffs` — Multi-agent handoffs
- `Example06SequentialPipeline` — Sequential chains
- `Example07ParallelAgents` — Parallel execution
- `Example08RouterAgent` — Router pattern
- `Example09HumanInTheLoop` — HITL approvals
- `Example10Guardrails` — Input/output guardrails
- `Example11Streaming` — Event streaming

## License

MIT License. See [LICENSE](../../LICENSE).
