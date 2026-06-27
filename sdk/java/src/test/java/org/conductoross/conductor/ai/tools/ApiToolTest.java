// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.tools;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.internal.AgentConfigSerializer;
import org.conductoross.conductor.ai.model.ToolDef;
import org.junit.jupiter.api.Test;

/**
 * Pure unit tests for the API tool builder + its serialized wire shape.
 *
 * <p>Wire format mirrors the Python SDK {@code api_tool} / C# {@code ApiTools.Create}:
 * {@code toolType:"api"} with config keys {@code url}, {@code headers},
 * {@code tool_names}, {@code max_tools} (default 64).
 */
class ApiToolTest {

    private final AgentConfigSerializer ser = new AgentConfigSerializer();

    @SuppressWarnings("unchecked")
    private Map<String, Object> tool(Map<String, Object> out, String name) {
        List<Map<String, Object>> tools = (List<Map<String, Object>>) out.get("tools");
        assertNotNull(tools, "serialized output has no 'tools' key");
        return tools.stream()
                .filter(t -> name.equals(t.get("name")))
                .findFirst()
                .orElseThrow(() -> new AssertionError("Tool '" + name + "' not found. Available: "
                        + tools.stream().map(t -> (String) t.get("name")).collect(Collectors.toList())));
    }

    @Test
    void apiToolShapeAndDefaults() {
        ToolDef t = ApiTool.builder().url("https://api.stripe.com/openapi.json").build();
        assertEquals("api", t.getToolType());
        // Default name + description match Python/C#.
        assertEquals("api_tools", t.getName());
        assertEquals("API tools from https://api.stripe.com/openapi.json", t.getDescription());
        Map<String, Object> config = t.getConfig();
        assertNotNull(config);
        assertEquals("https://api.stripe.com/openapi.json", config.get("url"));
        // max_tools default is 64 and lives in config under the snake_case key.
        assertEquals(64, config.get("max_tools"));
    }

    @Test
    void apiToolRequiresUrl() {
        assertThrows(IllegalArgumentException.class, () -> ApiTool.builder().build());
    }

    @Test
    @SuppressWarnings("unchecked")
    void apiToolSerializesToToolTypeApiWithMaxToolsDefault() {
        ToolDef t = ApiTool.builder()
                .url("https://example.com/openapi.json")
                .header("Authorization", "Bearer ${API_KEY}")
                .toolNames(List.of("listUsers", "getUser"))
                .credentials("API_KEY")
                .build();

        Agent agent = Agent.builder()
                .name("api_agent")
                .model("openai/gpt-4o-mini")
                .instructions("test")
                .tools(List.of(t))
                .build();

        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> serialized = tool(out, "api_tools");

        assertEquals("api", serialized.get("toolType"), "API tool must serialize with toolType 'api'");

        Map<String, Object> config = (Map<String, Object>) serialized.get("config");
        assertNotNull(config, "API tool must serialize a config block");
        assertEquals("https://example.com/openapi.json", config.get("url"));
        assertEquals(64, config.get("max_tools"), "max_tools default must be 64 on the wire");
        assertEquals(List.of("listUsers", "getUser"), config.get("tool_names"));
        assertEquals(List.of("API_KEY"), config.get("credentials"));
        Map<String, Object> headers = (Map<String, Object>) config.get("headers");
        assertNotNull(headers);
        assertEquals("Bearer ${API_KEY}", headers.get("Authorization"));
        // Wire keys are snake_case (Python parity), not camelCase.
        assertNull(config.get("maxTools"));
        assertNull(config.get("toolNames"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void apiToolMaxToolsOverride() {
        ToolDef t =
                ApiTool.builder().url("https://example.com/spec").maxTools(20).build();
        Agent agent = Agent.builder()
                .name("api_agent2")
                .model("openai/gpt-4o-mini")
                .instructions("test")
                .tools(List.of(t))
                .build();
        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> config =
                (Map<String, Object>) tool(out, "api_tools").get("config");
        assertEquals(20, config.get("max_tools"));
    }

    @Test
    void apiToolHeaderPlaceholderRequiresDeclaredCredential() {
        // ${NAME} in headers must be declared in credentials (Python parity).
        assertTrue(assertThrows(IllegalArgumentException.class, () -> ApiTool.builder()
                        .url("https://example.com/spec")
                        .header("Authorization", "Bearer ${MISSING}")
                        .build())
                .getMessage()
                .contains("MISSING"));
    }
}
