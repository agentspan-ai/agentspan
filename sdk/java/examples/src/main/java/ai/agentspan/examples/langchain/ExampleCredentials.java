// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langchain;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.Tool;
import ai.agentspan.internal.ToolRegistry;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.ToolDef;
import ai.agentspan.frameworks.LangChainBridge;

import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

import java.util.ArrayList;
import java.util.List;

/**
 * Example Lc4j 03 — LangChain4j Agent with Credential-Aware Tools (native LangChain4j SDK)
 *
 * <p>Demonstrates mixing:
 * <ul>
 *   <li>Native LangChain4j {@code @Tool} methods that perform pure computation (no secrets)</li>
 *   <li>An Agentspan {@link Tool}-annotated method that reads a credential injected
 *       as an environment variable by the server (via the {@code credentials} field)</li>
 * </ul>
 *
 * <p>Credential injection pattern:
 * <ol>
 *   <li>Declare credential names in {@code @Tool(credentials = {"MY_API_KEY"})}</li>
 *   <li>Store the secret once via the CLI: {@code agentspan credentials set --name MY_API_KEY}</li>
 *   <li>At runtime, the server resolves the credential and injects it as
 *       an environment variable before invoking the worker. Read it with
 *       {@code System.getenv("MY_API_KEY")}.</li>
 * </ol>
 *
 * <p>This pattern keeps secrets out of source code and out of agent configs.
 *
 * <p>Requirements:
 * <ul>
 *   <li>{@code AGENTSPAN_SERVER_URL=http://localhost:6767}</li>
 *   <li>langchain4j on the classpath (see examples/build.gradle)</li>
 *   <li>Agentspan server with OpenAI credentials configured server-side.</li>
 *   <li>Credential {@code WEATHER_API_KEY} registered in Agentspan (optional — example
 *       works without it, falling back to a stubbed response)</li>
 * </ul>
 */
public class ExampleCredentials {

    // ── LangChain4j tool class: pure computation, no secrets ──────────────────

    static class UnitTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "celsius_to_fahrenheit",
            value = "Convert a temperature from Celsius to Fahrenheit"
        )
        public double celsiusToFahrenheit(@dev.langchain4j.agent.tool.P("celsius") double celsius) {
            return (celsius * 9.0 / 5.0) + 32.0;
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "fahrenheit_to_celsius",
            value = "Convert a temperature from Fahrenheit to Celsius"
        )
        public double fahrenheitToCelsius(@dev.langchain4j.agent.tool.P("fahrenheit") double fahrenheit) {
            return (fahrenheit - 32.0) * 5.0 / 9.0;
        }
    }

    // ── Agentspan @Tool class: reads a credential injected by the server ──────

    static class WeatherTools {

        /**
         * Fetches current weather for a city.
         *
         * <p>The server resolves {@code WEATHER_API_KEY} from the Agentspan credential
         * store and injects it as an environment variable before calling this worker.
         * The tool reads it via {@code System.getenv("WEATHER_API_KEY")}.
         */
        @Tool(
            name = "get_weather",
            description = "Get the current weather for a city. Requires WEATHER_API_KEY credential.",
            credentials = {"WEATHER_API_KEY"}
        )
        public String getWeather(String city) {
            String apiKey = System.getenv("WEATHER_API_KEY");
            boolean hasKey = apiKey != null && !apiKey.isEmpty();

            // In a real implementation, call the weather API with the key.
            // Here we return a stub to keep the example self-contained.
            if (hasKey) {
                return "Weather in " + city + ": 22°C, Partly cloudy (fetched with API key)";
            } else {
                return "Weather in " + city + ": 22°C, Partly cloudy (stub — set WEATHER_API_KEY credential)";
            }
        }
    }

    public static void main(String[] args) {
        // apiKey is required by LangChain4j's builder but unused — Agentspan
        // runs the LLM call on the server with server-registered credentials.
        ChatModel model = OpenAiChatModel.builder()
            .apiKey("agentspan-server-handles-credentials")
            .modelName("gpt-4o-mini")
            .build();

        // Build the LangChain4j-backed agent (unit conversion tools) via the
        // advanced LangChainBridge.agentBuilder(...) path so we can merge in
        // Agentspan @Tool credential-aware tools before .build().
        Agent lc4jAgent = LangChainBridge.agentBuilder(
            "lc4j_weather_agent",
            model,
            "You are a weather assistant. You can fetch weather data and convert temperatures. "
            + "Always show temperatures in both Celsius and Fahrenheit.",
            new UnitTools())
            .build();

        // Agentspan @Tool tools (credential-aware) — build separately and merge in.
        List<ToolDef> credentialTools = ToolRegistry.fromInstance(new WeatherTools());

        // Merge the credential-aware tool into the agent by rebuilding it.
        // Both the LangChain4j tools and the @Tool credentials method end up in the same agent.
        List<ToolDef> allTools = new ArrayList<>(lc4jAgent.getTools());
        allTools.addAll(credentialTools);

        Agent fullAgent = Agent.builder()
            .name(lc4jAgent.getName())
            .model(lc4jAgent.getModel())
            .instructions(lc4jAgent.getInstructions())
            .tools(allTools)
            .build();

        System.out.println("Agent: " + fullAgent.getName());
        System.out.println("Tools: " + fullAgent.getTools().size());
        fullAgent.getTools().forEach(t -> System.out.println("  - " + t.getName()));

        AgentResult result = Agentspan.run(fullAgent,
            "What is the weather in Paris, and what is 22°C in Fahrenheit?");
        result.printResult();

        Agentspan.shutdown();
    }
}
