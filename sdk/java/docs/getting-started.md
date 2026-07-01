# Getting Started

## Prerequisites

- Java 21+
- Gradle 7+ or Maven 3.6+
- A running Agentspan server — see the [Agentspan repo](https://github.com/agentspan-ai/agentspan) or start one locally:

```bash
docker run -p 6767:6767 agentspan/server:latest
```

## Add the dependency

=== "Gradle"

    ```groovy
    dependencies {
        implementation 'org.conductoross.conductor:conductor-agent-sdk:0.1.0'
    }
    ```

=== "Maven"

    ```xml
    <dependency>
        <groupId>org.conductoross.conductor</groupId>
        <artifactId>conductor-agent-sdk</artifactId>
        <version>0.1.0</version>
    </dependency>
    ```

## Configure the connection

The SDK reads connection settings from environment variables by default:

```bash
export AGENTSPAN_SERVER_URL=http://localhost:6767/api
export OPENAI_API_KEY=<YOUR-KEY>
export AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini
export AGENTSPAN_AUTH_KEY=your-key                 # optional
export AGENTSPAN_AUTH_SECRET=your-secret           # optional
```

Or construct an `ApiClient` explicitly:

```java
import io.orkes.conductor.client.ApiClient;
import org.conductoross.conductor.ai.AgentRuntime;

// No auth (local dev)
ApiClient client = AgentRuntime.client("http://localhost:6767");

// With key/secret
ApiClient client = AgentRuntime.client("http://myserver:6767", "key", "secret");

AgentRuntime runtime = new AgentRuntime(client);
```

## Run your first agent

```java
import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.model.AgentResult;

Agent agent = Agent.builder()
    .name("hello_agent")
    .model("anthropic/claude-sonnet-4-6")
    .instructions("You are a concise assistant. Answer in one sentence.")
    .build();

try (AgentRuntime runtime = new AgentRuntime()) {
    AgentResult result = runtime.run(agent, "What is 2 + 2?");
    System.out.println(result.getOutput());
    // → "2 + 2 equals 4."
}
```

## Add a tool

Tools are Java methods wrapped as Conductor worker tasks. The method runs locally in your process; the agent calls it remotely via Conductor.

```java
import org.conductoross.conductor.ai.internal.ToolRegistry;
import org.conductoross.conductor.ai.annotations.Tool;

public class WeatherTools {

    @Tool(name = "get_weather", description = "Get current weather for a city")
    public String getWeather(String city) {
        // real implementation would call a weather API
        return "Sunny, 22°C in " + city;
    }
}

Agent agent = Agent.builder()
    .name("weather_agent")
    .model("anthropic/claude-sonnet-4-6")
    .instructions("Answer weather questions using the get_weather tool.")
    .tools(ToolRegistry.fromInstance(new WeatherTools()))
    .build();

try (AgentRuntime runtime = new AgentRuntime()) {
    AgentResult result = runtime.run(agent, "What's the weather in Tokyo?");
    System.out.println(result.getOutput());
}
```

!!! tip "Tool methods run as Conductor tasks"
    The `@Tool` method executes in your local JVM, but Conductor manages its lifecycle. If your process restarts mid-run, Conductor re-dispatches the task to the next available worker.

## Streaming

Use `stream()` to get events as they happen:

```java
import org.conductoross.conductor.ai.model.AgentStream;
import org.conductoross.conductor.ai.model.AgentEvent;
import org.conductoross.conductor.ai.enums.EventType;

try (AgentRuntime runtime = new AgentRuntime();
     AgentStream stream = runtime.stream(agent, "Tell me a story")) {

    for (AgentEvent event : stream) {
        if (event.getType() == EventType.MESSAGE) {
            System.out.print(event.getContent());
        }
    }
}
```

## Next steps

- [Concepts → Agents](concepts/agents.md) — full builder API reference
- [Concepts → Tools](concepts/tools.md) — tool types: HTTP, MCP, human, CLI
- [Concepts → Multi-Agent](concepts/multi-agent.md) — sequential, parallel, handoff, swarm
- [Spring Boot](spring-boot.md) — auto-configuration for Spring Boot apps
