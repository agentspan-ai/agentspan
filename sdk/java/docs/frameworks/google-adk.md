# Google ADK

Use Google's Agent Development Kit (ADK) agents directly with Agentspan. The `AdkBridge` converts a native `LlmAgent` (or any `BaseAgent`) into an Agentspan `Agent`, serialising its tools, instructions, and sub-agent graph into the format the server's `GoogleADKNormalizer` understands.

## Dependency

```groovy
implementation 'org.conductoross.conductor:conductor-agent-sdk:0.1.0'
compileOnly 'com.google.adk:google-adk:1.3.0'
```

## Usage

```java
import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.Annotations;
import com.google.adk.tools.FunctionTool;
import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.frameworks.AdkBridge;

// A FunctionTool target — ADK reflects the method and its @Schema params
public static class WeatherService {
    public static Map<String, Object> getWeather(
            @Annotations.Schema(name = "city", description = "City to query") String city) {
        return Map.of("city", city, "condition", "Sunny", "tempC", 22);
    }
}

// Build a native ADK LlmAgent
LlmAgent adkAgent = LlmAgent.builder()
    .name("weather_agent")
    .model("gemini-2.0-flash")
    .instruction("Answer weather questions. Use the getWeather tool.")
    .tools(FunctionTool.create(WeatherService.class, "getWeather"))
    .build();

// Convert to Agentspan Agent
Agent agent = AdkBridge.toAgentspan(adkAgent);

// Run via AgentRuntime
try (AgentRuntime runtime = new AgentRuntime()) {
    AgentResult result = runtime.run(agent, "What's the weather in London?");
    System.out.println(result.getOutput());
}
```

## agentBuilder — attach extra Agentspan features

If you want to mix ADK agent structure with Agentspan-only features (guardrails, credentials, callbacks), use `agentBuilder()` which returns an `Agent.Builder` you can continue configuring:

```java
import org.conductoross.conductor.ai.guardrail.RegexGuardrail;
import org.conductoross.conductor.ai.enums.Position;
import org.conductoross.conductor.ai.enums.OnFail;

Agent agent = AdkBridge.agentBuilder(adkAgent)
    .credentials("WEATHER_API_KEY")
    .guardrails(RegexGuardrail.builder()
        .name("no_pii").position(Position.OUTPUT)
        .patterns("\\b\\d{3}-\\d{2}-\\d{4}\\b")   // SSN-like
        .onFail(OnFail.RAISE).build())
    .maxTurns(10)
    .build();
```

## What gets mapped

| ADK concept | Agentspan mapping |
|---|---|
| `LlmAgent.name()` | `Agent.name` |
| `LlmAgent.model()` | `Agent.model` |
| `LlmAgent.instruction()` | `Agent.instructions` |
| `FunctionTool` | Conductor worker task (via `WorkerManager`) |
| `AgentTool` | Sub-agent (nested `Agent`) |
| `GoogleSearchTool` | HTTP tool |
| `BuiltInCodeExecutionTool` | Code execution tool |
| Sub-agents (`.subAgents()`) | `Agent.agents` |
| `LoopAgent` / `SequentialAgent` | `Strategy.SEQUENTIAL` |

!!! note "Model requirement"
    Google ADK agents require a Gemini model (e.g. `gemini-2.0-flash`). Make sure your Agentspan server has a Google AI or Vertex AI provider configured with the appropriate API key.
