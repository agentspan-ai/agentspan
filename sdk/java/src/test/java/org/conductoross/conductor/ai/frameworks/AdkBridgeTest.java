// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.frameworks;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;

import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.model.ToolDef;
import org.junit.jupiter.api.Test;

import com.google.adk.agents.BaseAgent;
import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.Annotations;
import com.google.adk.tools.FunctionTool;

/**
 * Server-free unit tests for the Google ADK bridge ({@link AdkBridge#toAgentspan}).
 *
 * <p>Mirrors how Python's framework e2e validates serialization (framework tagging,
 * identity, tool extraction with a valid JSON Schema) without needing the model
 * provider — ADK uses Gemini, for which no key is configured in this environment,
 * so the runtime path is intentionally not exercised here (compile/serialize only).
 */
class AdkBridgeTest {

    /** A FunctionTool target: ADK reflects the method + its {@code @Schema} params. */
    public static class WeatherTool {
        public static Map<String, Object> getWeather(
                @Annotations.Schema(name = "city", description = "City to look up") String city) {
            return Map.of("city", city, "tempF", 72);
        }
    }

    private LlmAgent buildAdkAgent() {
        return LlmAgent.builder()
                .name("adk_weather_agent")
                .model("gemini-2.0-flash")
                .instruction("You report the weather. Use the getWeather tool.")
                .tools(FunctionTool.create(WeatherTool.class, "getWeather"))
                .build();
    }

    @Test
    void toAgentspanTagsFrameworkAndCopiesIdentity() {
        Agent a = AdkBridge.toAgentspan(buildAdkAgent());
        assertEquals(
                "google_adk",
                a.getFramework(),
                "ADK agents must be tagged framework='google_adk' so the server routes them through "
                        + "GoogleADKNormalizer. COUNTERFACTUAL: if the bridge omits the tag, normalization is wrong.");
        assertEquals("adk_weather_agent", a.getName(), "agent name must be copied from the ADK LlmAgent");
        assertNotNull(a.getModel(), "model must be carried over from the ADK agent");
        assertTrue(
                a.getModel().toLowerCase().contains("gemini"),
                "model should carry the ADK model name; got: " + a.getModel());
    }

    @Test
    void toAgentspanExtractsFunctionToolWithSchema() {
        Agent a = AdkBridge.toAgentspan(buildAdkAgent());
        List<ToolDef> tools = a.getTools();
        assertNotNull(tools, "tools list must not be null");
        assertFalse(
                tools.isEmpty(),
                "AdkBridge must extract the FunctionTool as a worker tool. "
                        + "COUNTERFACTUAL: if tool extraction is broken, the list is empty.");

        ToolDef wx = tools.stream()
                .filter(t -> "getWeather".equals(t.getName()))
                .findFirst()
                .orElseThrow(() -> new AssertionError("getWeather tool not extracted; got: "
                        + tools.stream().map(ToolDef::getName).toList()));

        Map<String, Object> schema = wx.getInputSchema();
        assertNotNull(schema, "extracted tool must have an input schema");
        assertEquals(
                "object", schema.get("type"), "tool inputSchema.type must be 'object'; got: " + schema.get("type"));
        @SuppressWarnings("unchecked")
        Map<String, Object> props = (Map<String, Object>) schema.get("properties");
        assertNotNull(props, "schema must have 'properties'");
        assertTrue(
                props.containsKey("city"),
                "FunctionTool param 'city' (from @Schema) must appear in the input schema; got: " + props.keySet()
                        + ". COUNTERFACTUAL: if ADK param reflection is dropped, 'city' is missing.");
    }

    @Test
    void nullAgentRejected() {
        assertThrows(
                IllegalArgumentException.class,
                () -> AdkBridge.agentBuilder((BaseAgent) null),
                "agentBuilder(null) must fail fast rather than NPE deeper in serialization");
    }
}
