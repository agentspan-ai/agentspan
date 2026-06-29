// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;

import org.conductoross.conductor.ai.annotations.Tool;
import org.conductoross.conductor.ai.enums.Strategy;
import org.conductoross.conductor.ai.internal.AgentConfigSerializer;
import org.conductoross.conductor.ai.internal.ToolRegistry;
import org.conductoross.conductor.ai.model.ToolDef;
import org.conductoross.conductor.ai.termination.MaxMessageTermination;
import org.conductoross.conductor.ai.termination.TextMentionTermination;
import org.junit.jupiter.api.Test;

/**
 * Unit tests for Agent builder, ToolRegistry, and AgentConfigSerializer.
 */
class AgentBuilderTest {

    // ── Agent builder tests ───────────────────────────────────────────────

    @Test
    void testBasicAgentBuilder() {
        Agent agent = Agent.builder()
                .name("test_agent")
                .model("openai/gpt-4o")
                .instructions("You are a test agent.")
                .build();

        assertEquals("test_agent", agent.getName());
        assertEquals("openai/gpt-4o", agent.getModel());
        assertEquals("You are a test agent.", agent.getInstructions());
        assertFalse(agent.isExternal());
        assertEquals(25, agent.getMaxTurns());
    }

    @Test
    void testExternalAgent() {
        Agent external = Agent.builder().name("external_agent").build(); // No model = external

        assertTrue(external.isExternal());
    }

    @Test
    void testInvalidAgentName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> Agent.builder().name("123invalid").build());
        assertThrows(
                IllegalArgumentException.class, () -> Agent.builder().name("").build());
        assertThrows(
                IllegalArgumentException.class, () -> Agent.builder().name(null).build());
    }

    @Test
    void testValidAgentNames() {
        assertDoesNotThrow(() -> Agent.builder().name("my_agent").build());
        assertDoesNotThrow(() -> Agent.builder().name("MyAgent123").build());
        assertDoesNotThrow(() -> Agent.builder().name("_private_agent").build());
        assertDoesNotThrow(() -> Agent.builder().name("agent-with-hyphen").build());
    }

    @Test
    void testAgentMaxTurnsValidation() {
        assertThrows(
                IllegalArgumentException.class,
                () -> Agent.builder().name("test").maxTurns(0).build());
    }

    @Test
    void testSequentialPipeline() {
        Agent a = Agent.builder().name("a").model("openai/gpt-4o").build();
        Agent b = Agent.builder().name("b").model("openai/gpt-4o").build();
        Agent c = Agent.builder().name("c").model("openai/gpt-4o").build();

        Agent pipeline = a.then(b).then(c);

        assertEquals(Strategy.SEQUENTIAL, pipeline.getStrategy());
        assertEquals(3, pipeline.getAgents().size());
        assertEquals("a_b_c", pipeline.getName());
    }

    // ── ToolRegistry tests ───────────────────────────────────────────────

    static class SampleTools {
        @Tool(name = "get_weather", description = "Get weather for a city")
        public String getWeather(String city) {
            return "Sunny, 72F in " + city;
        }

        @Tool(name = "add_numbers", description = "Add two numbers")
        public int addNumbers(int a, int b) {
            return a + b;
        }

        public void notATool() {
            // should be ignored
        }
    }

    @Test
    void testToolRegistryDiscovery() {
        SampleTools tools = new SampleTools();
        List<ToolDef> toolDefs = ToolRegistry.fromInstance(tools);

        assertEquals(2, toolDefs.size());

        ToolDef weatherTool = toolDefs.stream()
                .filter(t -> t.getName().equals("get_weather"))
                .findFirst()
                .orElseThrow();

        assertEquals("get_weather", weatherTool.getName());
        assertEquals("Get weather for a city", weatherTool.getDescription());
        assertEquals("worker", weatherTool.getToolType());
        assertNotNull(weatherTool.getFunc());
    }

    @Test
    void testToolExecution() {
        SampleTools tools = new SampleTools();
        List<ToolDef> toolDefs = ToolRegistry.fromInstance(tools);

        ToolDef weatherTool = toolDefs.stream()
                .filter(t -> t.getName().equals("get_weather"))
                .findFirst()
                .orElseThrow();

        // Use the actual parameter name from the schema
        @SuppressWarnings("unchecked")
        Map<String, Object> props =
                (Map<String, Object>) weatherTool.getInputSchema().get("properties");
        String paramName = props.keySet().iterator().next();

        Map<String, Object> input = Map.of(paramName, "Paris");
        Object result = weatherTool.getFunc().apply(input);

        assertTrue(result.toString().contains("Paris"), "Expected result to contain 'Paris' but was: " + result);
    }

    @Test
    void testToolSchemaGeneration() {
        SampleTools tools = new SampleTools();
        List<ToolDef> toolDefs = ToolRegistry.fromInstance(tools);

        ToolDef addTool = toolDefs.stream()
                .filter(t -> t.getName().equals("add_numbers"))
                .findFirst()
                .orElseThrow();

        Map<String, Object> schema = addTool.getInputSchema();
        assertNotNull(schema);
        assertEquals("object", schema.get("type"));

        @SuppressWarnings("unchecked")
        Map<String, Object> props = (Map<String, Object>) schema.get("properties");
        assertNotNull(props);
        assertTrue(props.containsKey("a") || props.containsKey("arg0")); // depends on -parameters flag
    }

    // ── AgentConfigSerializer tests ──────────────────────────────────────

    @Test
    void testSerializeBasicAgent() {
        Agent agent = Agent.builder()
                .name("basic_agent")
                .model("openai/gpt-4o")
                .instructions("You are helpful.")
                .maxTurns(5)
                .build();

        AgentConfigSerializer serializer = new AgentConfigSerializer();
        Map<String, Object> config = serializer.serialize(agent);

        assertEquals("basic_agent", config.get("name"));
        assertEquals("openai/gpt-4o", config.get("model"));
        assertEquals("You are helpful.", config.get("instructions"));
        assertEquals(5, config.get("maxTurns"));
    }

    @Test
    void testSerializeExternalAgent() {
        Agent external = Agent.builder().name("external_workflow").build();

        AgentConfigSerializer serializer = new AgentConfigSerializer();
        Map<String, Object> config = serializer.serialize(external);

        assertEquals("external_workflow", config.get("name"));
        assertNull(config.get("model"));
        assertEquals(true, config.get("external"));
    }

    @Test
    void testSerializeMultiAgent() {
        Agent researcher =
                Agent.builder().name("researcher").model("openai/gpt-4o").build();
        Agent writer = Agent.builder().name("writer").model("openai/gpt-4o").build();

        Agent pipeline = Agent.builder()
                .name("pipeline")
                .model("openai/gpt-4o")
                .agents(researcher, writer)
                .strategy(Strategy.SEQUENTIAL)
                .build();

        AgentConfigSerializer serializer = new AgentConfigSerializer();
        Map<String, Object> config = serializer.serialize(pipeline);

        assertEquals("sequential", config.get("strategy"));

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> agents = (List<Map<String, Object>>) config.get("agents");
        assertNotNull(agents);
        assertEquals(2, agents.size());
    }

    // ── Termination condition tests ──────────────────────────────────────

    @Test
    void testTerminationConditions() {
        var maxMsg = MaxMessageTermination.of(10);
        var textMention = TextMentionTermination.of("DONE");

        Map<String, Object> maxMap = maxMsg.toMap();
        assertEquals("max_message", maxMap.get("type"));
        assertEquals(10, maxMap.get("maxMessages"));

        Map<String, Object> textMap = textMention.toMap();
        assertEquals("text_mention", textMap.get("type"));
        assertEquals("DONE", textMap.get("text"));

        // Combined
        var combined = maxMsg.or(textMention);
        Map<String, Object> combinedMap = combined.toMap();
        assertEquals("or", combinedMap.get("type"));
    }

    // ── AgentConfig tests ────────────────────────────────────────────────

    @Test
    void testAgentConfigFromEnv() {
        AgentConfig config = AgentConfig.fromEnv();
        assertTrue(config.getWorkerPollIntervalMs() > 0);
        assertTrue(config.getWorkerThreadCount() > 0);
    }

    @Test
    void testAgentConfigExplicit() {
        // AgentConfig now carries worker tuning only — server URL / auth moved to the client.
        AgentConfig config = new AgentConfig(200, 10);
        assertEquals(200, config.getWorkerPollIntervalMs());
        assertEquals(10, config.getWorkerThreadCount());
    }

    @Test
    void testConductorClientBuiltFromServerUrl() {
        // Connection (server URL + auth) lives on the Conductor client, not AgentConfig.
        var client = AgentRuntime.client("http://myserver:8080/api", "my-key", "my-secret");
        assertEquals("http://myserver:8080/api", client.getBasePath());
    }
}
