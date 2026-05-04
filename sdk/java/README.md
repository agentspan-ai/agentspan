# Agentspan Java SDK

Java SDK for the [Agentspan](https://agentspan.dev) agent orchestration platform. Build, deploy, and run AI agents backed by Conductor workflows.

## Requirements

- Java 21+
- Maven 3.6+ or Gradle 7+
- A running Agentspan server

## Installation

Maven (`pom.xml`):

```xml
<dependency>
    <groupId>ai.agentspan</groupId>
    <artifactId>java-sdk</artifactId>
    <version>0.1.0</version>
</dependency>
```

Gradle (`build.gradle`):

```groovy
implementation 'ai.agentspan:java-sdk:0.1.0'
```

### Spring Boot starter

For Spring Boot apps, add the auto-configuration starter instead:

```xml
<dependency>
    <groupId>ai.agentspan</groupId>
    <artifactId>java-sdk-spring</artifactId>
    <version>0.1.0</version>
</dependency>
```

```groovy
implementation 'ai.agentspan:java-sdk-spring:0.1.0'
```

## Quick Start

```java
import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

public class Main {
    public static void main(String[] args) {
        Agent agent = Agent.builder()
            .name("assistant")
            .model("openai/gpt-4o")
            .instructions("You are a helpful assistant.")
            .build();

        AgentResult result = Agentspan.run(agent, "What is the capital of France?");
        result.printResult();
        Agentspan.shutdown();
    }
}
```

## Configuration

Set environment variables:

```bash
export AGENTSPAN_SERVER_URL=http://localhost:6767/api
export AGENTSPAN_AUTH_KEY=your-key
export AGENTSPAN_AUTH_SECRET=your-secret
export AGENTSPAN_LLM_MODEL=openai/gpt-4o
```

Or configure programmatically:

```java
import ai.agentspan.AgentConfig;
import ai.agentspan.Agentspan;

AgentConfig config = new AgentConfig(
    "http://localhost:6767/api",
    "my-key",
    "my-secret",
    100,  // poll interval ms
    5     // worker threads
);
Agentspan.configure(config);
```

## Tools

Define tools using the `@Tool` annotation:

```java
import ai.agentspan.annotations.Tool;
import ai.agentspan.internal.ToolRegistry;

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
AgentResult result = Agentspan.run(pipeline, "Write about AI trends");
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
