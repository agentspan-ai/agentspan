/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.controller;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.agentspan.runtime.AgentRuntime;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.*;

/**
 * End-to-end tests for the agent compile endpoint.
 *
 * <p>Boots the full Spring context with in-memory SQLite, sends real HTTP
 * requests to {@code POST /api/agent/compile}, and verifies the compiled
 * workflow structure. No mocks — exercises the complete normalization →
 * compilation pipeline.</p>
 */
@SpringBootTest(
        classes = AgentRuntime.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@ActiveProfiles("test")
class AgentCompileE2ETest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @LocalServerPort
    private int port;

    // ── HTTP helpers ─────────────────────────────────────────────────

    private String compileUrl() {
        return "http://localhost:" + port + "/api/agent/compile";
    }

    private String startUrl() {
        return "http://localhost:" + port + "/api/agent/start";
    }

    private String statusUrl(String workflowId) {
        return "http://localhost:" + port + "/api/agent/" + workflowId + "/status";
    }

    private JsonNode postCompile(Map<String, Object> body) throws Exception {
        return post(compileUrl(), body);
    }

    private JsonNode postStart(Map<String, Object> body) throws Exception {
        return post(startUrl(), body);
    }

    private JsonNode get(String url) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) URI.create(url).toURL().openConnection();
        conn.setRequestMethod("GET");
        conn.setRequestProperty("Accept", "application/json");
        assertThat(conn.getResponseCode()).isEqualTo(200);
        return MAPPER.readTree(conn.getInputStream());
    }

    private JsonNode post(String url, Map<String, Object> body) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) URI.create(url).toURL().openConnection();
        conn.setRequestMethod("POST");
        conn.setRequestProperty("Content-Type", "application/json");
        conn.setRequestProperty("Accept", "application/json");
        conn.setDoOutput(true);
        byte[] json = MAPPER.writeValueAsBytes(body);
        try (OutputStream os = conn.getOutputStream()) {
            os.write(json);
        }
        int code = conn.getResponseCode();
        if (code != 200) {
            String errBody = new String(conn.getErrorStream() != null
                    ? conn.getErrorStream().readAllBytes() : new byte[0], StandardCharsets.UTF_8);
            fail("Expected 200 but got " + code + ": " + errBody);
        }
        return MAPPER.readTree(conn.getInputStream());
    }

    /** Build a minimal agent config map. */
    private Map<String, Object> agentConfig(String name, String model, String instructions) {
        Map<String, Object> config = new LinkedHashMap<>();
        config.put("name", name);
        config.put("model", model);
        config.put("instructions", instructions);
        return config;
    }

    /** Wrap an agentConfig in a StartRequest body. */
    private Map<String, Object> request(Map<String, Object> agentConfig) {
        return Map.of("agentConfig", agentConfig, "prompt", "test prompt");
    }

    /** Extract task list from compiled workflow JSON. */
    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getTasks(JsonNode response) {
        JsonNode wf = response.get("workflowDef");
        return MAPPER.convertValue(wf.get("tasks"), new TypeReference<>() {});
    }

    /** Find a task in the list by type. */
    private Map<String, Object> findTaskByType(List<Map<String, Object>> tasks, String type) {
        return tasks.stream()
                .filter(t -> type.equals(t.get("type")))
                .findFirst()
                .orElse(null);
    }

    /** Find a task by taskReferenceName. */
    private Map<String, Object> findTaskByRef(List<Map<String, Object>> tasks, String ref) {
        return tasks.stream()
                .filter(t -> ref.equals(t.get("taskReferenceName")))
                .findFirst()
                .orElse(null);
    }

    /** Recursively find all tasks of a given type, including inside DO_WHILE loopOver. */
    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> findAllTasksByType(List<Map<String, Object>> tasks, String type) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (Map<String, Object> t : tasks) {
            if (type.equals(t.get("type"))) {
                result.add(t);
            }
            // Recurse into DO_WHILE loopOver
            if (t.containsKey("loopOver")) {
                result.addAll(findAllTasksByType((List<Map<String, Object>>) t.get("loopOver"), type));
            }
            // Recurse into FORK_JOIN forkTasks
            if (t.containsKey("forkTasks")) {
                for (List<Map<String, Object>> branch : (List<List<Map<String, Object>>>) t.get("forkTasks")) {
                    result.addAll(findAllTasksByType(branch, type));
                }
            }
            // Recurse into SWITCH decisionCases
            if (t.containsKey("decisionCases")) {
                Map<String, List<Map<String, Object>>> cases = (Map<String, List<Map<String, Object>>>) t.get("decisionCases");
                for (List<Map<String, Object>> branch : cases.values()) {
                    result.addAll(findAllTasksByType(branch, type));
                }
            }
            if (t.containsKey("defaultCase")) {
                result.addAll(findAllTasksByType((List<Map<String, Object>>) t.get("defaultCase"), type));
            }
        }
        return result;
    }

    // ── Tests ────────────────────────────────────────────────────────

    @Test
    void compileSimpleAgent() throws Exception {
        Map<String, Object> config = agentConfig("simple_e2e", "openai/gpt-4o", "You are helpful.");
        JsonNode resp = postCompile(request(config));

        JsonNode wf = resp.get("workflowDef");
        assertThat(wf.get("name").asText()).isEqualTo("simple_e2e");
        assertThat(wf.get("version").asInt()).isEqualTo(1);

        List<Map<String, Object>> tasks = getTasks(resp);
        // Simple agent = single LLM_CHAT_COMPLETE task
        assertThat(tasks).hasSize(1);
        assertThat(tasks.get(0).get("type")).isEqualTo("LLM_CHAT_COMPLETE");
    }

    @Test
    void compileLlmTaskHasCorrectProviderAndModel() throws Exception {
        Map<String, Object> config = agentConfig("model_e2e", "anthropic/claude-sonnet-4-20250514", "Test.");
        JsonNode resp = postCompile(request(config));

        List<Map<String, Object>> tasks = getTasks(resp);
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) tasks.get(0).get("inputParameters");
        assertThat(inputs.get("llmProvider")).isEqualTo("anthropic");
        assertThat(inputs.get("model")).isEqualTo("claude-sonnet-4-20250514");
    }

    @Test
    void compileAgentWithTools() throws Exception {
        Map<String, Object> tool = Map.of(
                "name", "search",
                "description", "Search the web",
                "inputSchema", Map.of("type", "object",
                        "properties", Map.of("query", Map.of("type", "string"))),
                "toolType", "worker"
        );
        Map<String, Object> config = agentConfig("tool_e2e", "openai/gpt-4o", "Search agent.");
        config.put("tools", List.of(tool));

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Tool agent = DO_WHILE containing LLM + SWITCH + FORK_JOIN_DYNAMIC
        Map<String, Object> doWhile = findTaskByType(tasks, "DO_WHILE");
        assertThat(doWhile).isNotNull();

        // Inside the loop: should have LLM_CHAT_COMPLETE
        List<Map<String, Object>> llmTasks = findAllTasksByType(tasks, "LLM_CHAT_COMPLETE");
        assertThat(llmTasks).isNotEmpty();

        // Should have FORK_JOIN_DYNAMIC for tool dispatch
        List<Map<String, Object>> forkTasks = findAllTasksByType(tasks, "FORK_JOIN_DYNAMIC");
        assertThat(forkTasks).isNotEmpty();
    }

    @Test
    void compileAgentWithToolsIncludesToolSpecs() throws Exception {
        Map<String, Object> tool = Map.of(
                "name", "calculate",
                "description", "Do math",
                "inputSchema", Map.of("type", "object",
                        "properties", Map.of("expr", Map.of("type", "string"))),
                "toolType", "worker"
        );
        Map<String, Object> config = agentConfig("toolspec_e2e", "openai/gpt-4o", "Calculator.");
        config.put("tools", List.of(tool));

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> llmTasks = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        assertThat(llmTasks).isNotEmpty();

        @SuppressWarnings("unchecked")
        Map<String, Object> llmInputs = (Map<String, Object>) llmTasks.get(0).get("inputParameters");
        assertThat(llmInputs).containsKey("tools");

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> toolSpecs = (List<Map<String, Object>>) llmInputs.get("tools");
        assertThat(toolSpecs).hasSize(1);
        assertThat(toolSpecs.get(0).get("name")).isEqualTo("calculate");
    }

    @Test
    void compileSequentialMultiAgent() throws Exception {
        Map<String, Object> agent1 = agentConfig("researcher_e2e", "openai/gpt-4o", "Research.");
        Map<String, Object> agent2 = agentConfig("writer_e2e", "openai/gpt-4o", "Write.");

        Map<String, Object> pipeline = agentConfig("pipeline_e2e", "openai/gpt-4o", "Coordinate.");
        pipeline.put("agents", List.of(agent1, agent2));
        pipeline.put("strategy", "sequential");

        JsonNode resp = postCompile(request(pipeline));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Sequential compiles sub-agents as SUB_WORKFLOW tasks
        List<Map<String, Object>> subWfTasks = findAllTasksByType(tasks, "SUB_WORKFLOW");
        assertThat(subWfTasks).hasSizeGreaterThanOrEqualTo(2);

        // Verify agent names are in task reference names
        List<String> refs = subWfTasks.stream()
                .map(t -> (String) t.get("taskReferenceName"))
                .toList();
        assertThat(refs).anyMatch(r -> r.contains("researcher_e2e"));
        assertThat(refs).anyMatch(r -> r.contains("writer_e2e"));
    }

    @Test
    void compileSequentialHasCoercionBetweenStages() throws Exception {
        // Tool-using sub-agent in a sequential pipeline should get coercion
        Map<String, Object> tool = Map.of(
                "name", "lookup", "description", "Lookup data",
                "inputSchema", Map.of("type", "object"),
                "toolType", "worker"
        );
        Map<String, Object> agent1 = agentConfig("tooluser_e2e", "openai/gpt-4o", "Use tools.");
        agent1.put("tools", List.of(tool));
        Map<String, Object> agent2 = agentConfig("summarizer_e2e", "openai/gpt-4o", "Summarize.");

        Map<String, Object> pipeline = agentConfig("coerce_pipeline_e2e", "openai/gpt-4o", "Coordinate.");
        pipeline.put("agents", List.of(agent1, agent2));
        pipeline.put("strategy", "sequential");

        JsonNode resp = postCompile(request(pipeline));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Should have INLINE coercion task between stages
        List<Map<String, Object>> inlineTasks = findAllTasksByType(tasks, "INLINE");
        assertThat(inlineTasks).isNotEmpty()
                .anyMatch(t -> ((String) t.get("taskReferenceName")).contains("coerce"));
    }

    @Test
    void compileParallelMultiAgent() throws Exception {
        Map<String, Object> agent1 = agentConfig("analyst_e2e", "openai/gpt-4o", "Analyze.");
        Map<String, Object> agent2 = agentConfig("reviewer_e2e", "openai/gpt-4o", "Review.");

        Map<String, Object> parallel = agentConfig("parallel_e2e", "openai/gpt-4o", "Coordinate.");
        parallel.put("agents", List.of(agent1, agent2));
        parallel.put("strategy", "parallel");

        JsonNode resp = postCompile(request(parallel));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Parallel = FORK_JOIN with branches
        Map<String, Object> fork = findTaskByType(tasks, "FORK_JOIN");
        assertThat(fork).isNotNull();
    }

    @Test
    void compileHandoffMultiAgent() throws Exception {
        Map<String, Object> agent1 = agentConfig("sales_e2e", "openai/gpt-4o", "Handle sales.");
        Map<String, Object> agent2 = agentConfig("support_e2e", "openai/gpt-4o", "Handle support.");

        Map<String, Object> coordinator = agentConfig("coordinator_e2e", "openai/gpt-4o", "Route requests.");
        coordinator.put("agents", List.of(agent1, agent2));
        coordinator.put("strategy", "handoff");

        JsonNode resp = postCompile(request(coordinator));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Handoff = DO_WHILE with SWITCH inside
        Map<String, Object> doWhile = findTaskByType(tasks, "DO_WHILE");
        assertThat(doWhile).isNotNull();

        List<Map<String, Object>> switches = findAllTasksByType(tasks, "SWITCH");
        assertThat(switches).isNotEmpty();
    }

    @Test
    void compileWithAllowedTransitions() throws Exception {
        Map<String, Object> agent1 = agentConfig("collector_e2e", "openai/gpt-4o", "Collect.");
        Map<String, Object> agent2 = agentConfig("analyzer_e2e", "openai/gpt-4o", "Analyze.");

        Map<String, Object> coordinator = agentConfig("constrained_e2e", "openai/gpt-4o", "Route.");
        coordinator.put("agents", List.of(agent1, agent2));
        coordinator.put("strategy", "handoff");
        coordinator.put("allowedTransitions", Map.of(
                "collector_e2e", List.of("analyzer_e2e"),
                "analyzer_e2e", List.of("constrained_e2e")
        ));

        // Should compile without error — transitions are metadata for runtime enforcement
        JsonNode resp = postCompile(request(coordinator));
        assertThat(resp.get("workflowDef")).isNotNull();
        assertThat(resp.get("workflowDef").get("name").asText()).isEqualTo("constrained_e2e");
    }

    @Test
    void compileAgentTool() throws Exception {
        Map<String, Object> childAgent = agentConfig("researcher_e2e", "openai/gpt-4o", "Research topics.");
        Map<String, Object> agentTool = new LinkedHashMap<>();
        agentTool.put("name", "research_tool");
        agentTool.put("description", "Research a topic in depth");
        agentTool.put("inputSchema", Map.of("type", "object",
                "properties", Map.of("request", Map.of("type", "string")),
                "required", List.of("request")));
        agentTool.put("toolType", "agent_tool");
        agentTool.put("config", Map.of("agent", childAgent));

        Map<String, Object> config = agentConfig("manager_e2e", "openai/gpt-4o", "Manage research.");
        config.put("tools", List.of(agentTool));

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Agent tool produces DO_WHILE with LLM + SWITCH + FORK_JOIN_DYNAMIC
        Map<String, Object> doWhile = findTaskByType(tasks, "DO_WHILE");
        assertThat(doWhile).isNotNull();

        // FORK_JOIN_DYNAMIC dispatches tools dynamically (including agent_tool as SUB_WORKFLOW at runtime)
        List<Map<String, Object>> forkDynamic = findAllTasksByType(tasks, "FORK_JOIN_DYNAMIC");
        assertThat(forkDynamic).isNotEmpty();

        // Tool specs in LLM inputs should include the agent tool
        List<Map<String, Object>> llmTasks = findAllTasksByType(tasks, "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> llmInputs = (Map<String, Object>) llmTasks.get(0).get("inputParameters");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> toolSpecs = (List<Map<String, Object>>) llmInputs.get("tools");
        assertThat(toolSpecs).anyMatch(t -> "research_tool".equals(t.get("name")));
    }

    @Test
    void compileWithCallbacks() throws Exception {
        // Callbacks require a tool-using agent (DO_WHILE loop) for before/after_model
        Map<String, Object> tool = Map.of(
                "name", "search", "description", "Search",
                "inputSchema", Map.of("type", "object"),
                "toolType", "worker"
        );
        Map<String, Object> config = agentConfig("callback_e2e", "openai/gpt-4o", "Test.");
        config.put("tools", List.of(tool));
        config.put("callbacks", List.of(
                Map.of("position", "before_model", "taskName", "callback_e2e_before_model"),
                Map.of("position", "after_model", "taskName", "callback_e2e_after_model")
        ));

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Callbacks should produce SIMPLE tasks inside the DO_WHILE loop
        List<Map<String, Object>> simpleTasks = findAllTasksByType(tasks, "SIMPLE");
        List<String> simpleRefs = simpleTasks.stream()
                .map(t -> (String) t.get("taskReferenceName"))
                .toList();
        assertThat(simpleRefs).anyMatch(ref -> ref.contains("before_model"));
        assertThat(simpleRefs).anyMatch(ref -> ref.contains("after_model"));
    }

    @Test
    void compileWithPlanner() throws Exception {
        Map<String, Object> config = agentConfig("planner_e2e", "openai/gpt-4o", "You are a planner.");
        config.put("planner", true);

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Planner enhances instructions with plan-then-execute prompt
        Map<String, Object> llm = findAllTasksByType(tasks, "LLM_CHAT_COMPLETE").get(0);
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get("inputParameters");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> messages = (List<Map<String, Object>>) inputs.get("messages");
        String systemMsg = messages.stream()
                .filter(m -> "system".equals(m.get("role")))
                .map(m -> (String) m.get("message"))
                .findFirst().orElse("");
        assertThat(systemMsg).contains("step-by-step plan");
    }

    @Test
    void compileWithThinkingConfig() throws Exception {
        Map<String, Object> config = agentConfig("thinker_e2e", "openai/gpt-4o", "Think deeply.");
        config.put("thinkingConfig", Map.of("enabled", true, "budgetTokens", 2048));

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> llmTasks = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        assertThat(llmTasks).isNotEmpty();

        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llmTasks.get(0).get("inputParameters");
        assertThat(inputs).containsKey("thinkingConfig");

        @SuppressWarnings("unchecked")
        Map<String, Object> thinking = (Map<String, Object>) inputs.get("thinkingConfig");
        assertThat(thinking.get("enabled")).isEqualTo(true);
        assertThat(thinking.get("budgetTokens")).isEqualTo(2048);
    }

    @Test
    void compileWithIncludeContents() throws Exception {
        // Sub-agents are compiled as SUB_WORKFLOW tasks.
        // include_contents=none means the sub-agent should signal to skip parent context.
        Map<String, Object> sub = agentConfig("isolated_e2e", "openai/gpt-4o", "Work alone.");
        sub.put("includeContents", "none");

        Map<String, Object> parent = agentConfig("parent_e2e", "openai/gpt-4o", "Coordinate.");
        parent.put("agents", List.of(sub));
        parent.put("strategy", "sequential");

        JsonNode resp = postCompile(request(parent));
        List<Map<String, Object>> tasks = getTasks(resp);

        // The sequential pipeline should compile sub-agents as SUB_WORKFLOW tasks
        List<Map<String, Object>> subWfTasks = findAllTasksByType(tasks, "SUB_WORKFLOW");
        assertThat(subWfTasks).isNotEmpty();

        // Verify the sub-agent with includeContents=none passes include_contents input
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) subWfTasks.get(0).get("inputParameters");
        assertThat(inputs).containsKey("include_contents");
        assertThat(inputs.get("include_contents")).isEqualTo("none");
    }

    @Test
    void compileWithOutputType() throws Exception {
        Map<String, Object> config = agentConfig("structured_e2e", "openai/gpt-4o", "Return structured data.");
        config.put("outputType", Map.of(
                "schema", Map.of(
                        "type", "object",
                        "properties", Map.of(
                                "name", Map.of("type", "string"),
                                "score", Map.of("type", "number")
                        )
                ),
                "className", "Result"
        ));

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> llmTasks = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        assertThat(llmTasks).isNotEmpty();

        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llmTasks.get(0).get("inputParameters");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> messages = (List<Map<String, Object>>) inputs.get("messages");
        String systemMsg = messages.stream()
                .filter(m -> "system".equals(m.get("role")))
                .map(m -> (String) m.get("message"))
                .findFirst().orElse("");
        assertThat(systemMsg).contains("JSON");
    }

    @Test
    void compileWithGuardrails() throws Exception {
        Map<String, Object> guardrail = new LinkedHashMap<>();
        guardrail.put("name", "content_filter");
        guardrail.put("position", "output");
        guardrail.put("onFail", "retry");
        guardrail.put("maxRetries", 3);
        guardrail.put("guardrailType", "regex");
        guardrail.put("patterns", List.of("\\b(password|secret)\\b"));
        guardrail.put("mode", "reject");

        Map<String, Object> config = agentConfig("guarded_e2e", "openai/gpt-4o", "Be safe.");
        config.put("guardrails", List.of(guardrail));

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Guardrails produce INLINE tasks for regex checks
        List<Map<String, Object>> inlineTasks = findAllTasksByType(tasks, "INLINE");
        assertThat(inlineTasks).isNotEmpty();
    }

    @Test
    void compileWithMaxTokensAndTemperature() throws Exception {
        Map<String, Object> config = agentConfig("params_e2e", "openai/gpt-4o", "Test.");
        config.put("maxTokens", 500);
        config.put("temperature", 0.7);

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> llmTasks = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");

        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llmTasks.get(0).get("inputParameters");
        assertThat(inputs.get("maxTokens")).isEqualTo(500);
        assertThat(inputs.get("temperature")).isEqualTo(0.7);
    }

    @Test
    void compileWithMemory() throws Exception {
        Map<String, Object> config = agentConfig("memory_e2e", "openai/gpt-4o", "Remember context.");
        config.put("memory", Map.of(
                "messages", List.of(
                        Map.of("role", "user", "message", "My name is Alice."),
                        Map.of("role", "assistant", "message", "Hello Alice!")
                )
        ));

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> llmTasks = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");

        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llmTasks.get(0).get("inputParameters");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> messages = (List<Map<String, Object>>) inputs.get("messages");
        // System + 2 memory + user = at least 4 messages
        assertThat(messages.size()).isGreaterThanOrEqualTo(4);
    }

    @Test
    void compileNestedSequentialParallel() throws Exception {
        Map<String, Object> a1 = agentConfig("analyst1_e2e", "openai/gpt-4o", "Analyze markets.");
        Map<String, Object> a2 = agentConfig("analyst2_e2e", "openai/gpt-4o", "Analyze risks.");

        Map<String, Object> parallel = agentConfig("research_e2e", "openai/gpt-4o", "Research.");
        parallel.put("agents", List.of(a1, a2));
        parallel.put("strategy", "parallel");

        Map<String, Object> summarizer = agentConfig("summary_e2e", "openai/gpt-4o", "Summarize.");

        Map<String, Object> pipeline = agentConfig("nested_e2e", "openai/gpt-4o", "Pipeline.");
        pipeline.put("agents", List.of(parallel, summarizer));
        pipeline.put("strategy", "sequential");

        JsonNode resp = postCompile(request(pipeline));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Both multi-agent (parallel) and simple sub-agents become SUB_WORKFLOW
        List<Map<String, Object>> subWorkflows = findAllTasksByType(tasks, "SUB_WORKFLOW");
        assertThat(subWorkflows).hasSizeGreaterThanOrEqualTo(2);

        // Total tasks: SUB_WORKFLOW(parallel) + coercion INLINE + SUB_WORKFLOW(summarizer)
        assertThat(tasks.size()).isGreaterThanOrEqualTo(3);
    }

    // ── Google ADK normalization e2e ─────────────────────────────────

    @Test
    void compileGoogleAdkBasicAgent() throws Exception {
        Map<String, Object> rawConfig = new LinkedHashMap<>();
        rawConfig.put("name", "adk_basic_e2e");
        rawConfig.put("model", "gemini-2.0-flash");
        rawConfig.put("instruction", "You are helpful.");  // ADK uses singular

        Map<String, Object> body = Map.of(
                "framework", "google_adk",
                "rawConfig", rawConfig,
                "prompt", "Hello"
        );

        JsonNode resp = postCompile(body);
        JsonNode wf = resp.get("workflowDef");
        assertThat(wf.get("name").asText()).isEqualTo("adk_basic_e2e");

        // Model should be prefixed with google_gemini/ (or overridden by AGENT_DEFAULT_MODEL)
        List<Map<String, Object>> llmTasks = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llmTasks.get(0).get("inputParameters");
        String model = (String) inputs.get("model");
        assertThat(model).isNotNull();
    }

    @Test
    void compileGoogleAdkSequentialAgent() throws Exception {
        Map<String, Object> sub1 = new LinkedHashMap<>();
        sub1.put("name", "step1_e2e");
        sub1.put("model", "gemini-2.0-flash");
        sub1.put("instruction", "Step 1.");

        Map<String, Object> sub2 = new LinkedHashMap<>();
        sub2.put("name", "step2_e2e");
        sub2.put("model", "gemini-2.0-flash");
        sub2.put("instruction", "Step 2.");

        Map<String, Object> rawConfig = new LinkedHashMap<>();
        rawConfig.put("name", "adk_seq_e2e");
        rawConfig.put("_type", "SequentialAgent");
        rawConfig.put("sub_agents", List.of(sub1, sub2));

        Map<String, Object> body = Map.of(
                "framework", "google_adk",
                "rawConfig", rawConfig,
                "prompt", "Go"
        );

        JsonNode resp = postCompile(body);
        List<Map<String, Object>> tasks = getTasks(resp);

        // Sequential compiles simple sub-agents as SUB_WORKFLOW tasks
        List<Map<String, Object>> subWorkflows = findAllTasksByType(tasks, "SUB_WORKFLOW");
        assertThat(subWorkflows).hasSizeGreaterThanOrEqualTo(2);

        List<String> refs = subWorkflows.stream()
                .map(t -> (String) t.get("taskReferenceName"))
                .toList();
        assertThat(refs).anyMatch(r -> r.contains("step1_e2e"));
        assertThat(refs).anyMatch(r -> r.contains("step2_e2e"));
    }

    @Test
    void compileGoogleAdkParallelAgent() throws Exception {
        Map<String, Object> sub1 = new LinkedHashMap<>();
        sub1.put("name", "branch1_e2e");
        sub1.put("model", "gemini-2.0-flash");
        sub1.put("instruction", "Branch 1.");

        Map<String, Object> sub2 = new LinkedHashMap<>();
        sub2.put("name", "branch2_e2e");
        sub2.put("model", "gemini-2.0-flash");
        sub2.put("instruction", "Branch 2.");

        Map<String, Object> rawConfig = new LinkedHashMap<>();
        rawConfig.put("name", "adk_par_e2e");
        rawConfig.put("_type", "ParallelAgent");
        rawConfig.put("sub_agents", List.of(sub1, sub2));

        Map<String, Object> body = Map.of(
                "framework", "google_adk",
                "rawConfig", rawConfig,
                "prompt", "Go"
        );

        JsonNode resp = postCompile(body);
        List<Map<String, Object>> tasks = getTasks(resp);

        Map<String, Object> fork = findTaskByType(tasks, "FORK_JOIN");
        assertThat(fork).isNotNull();
    }

    @Test
    void compileGoogleAdkAgentTool() throws Exception {
        Map<String, Object> childAgent = new LinkedHashMap<>();
        childAgent.put("name", "researcher_adk_e2e");
        childAgent.put("model", "gemini-2.0-flash");
        childAgent.put("instruction", "Research topics.");

        Map<String, Object> agentTool = new LinkedHashMap<>();
        agentTool.put("_type", "AgentTool");
        agentTool.put("name", "research_tool");
        agentTool.put("description", "Research something");
        agentTool.put("agent", childAgent);

        Map<String, Object> rawConfig = new LinkedHashMap<>();
        rawConfig.put("name", "adk_agenttool_e2e");
        rawConfig.put("model", "gemini-2.0-flash");
        rawConfig.put("instruction", "Manage research.");
        rawConfig.put("tools", List.of(agentTool));

        Map<String, Object> body = Map.of(
                "framework", "google_adk",
                "rawConfig", rawConfig,
                "prompt", "Research AI"
        );

        JsonNode resp = postCompile(body);
        List<Map<String, Object>> tasks = getTasks(resp);

        // Agent tool produces DO_WHILE with FORK_JOIN_DYNAMIC for dynamic tool dispatch
        assertThat(findTaskByType(tasks, "DO_WHILE")).isNotNull();
        assertThat(findAllTasksByType(tasks, "FORK_JOIN_DYNAMIC")).isNotEmpty();

        // Tool spec should include the agent tool name
        List<Map<String, Object>> llmTasks = findAllTasksByType(tasks, "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> llmInputs = (Map<String, Object>) llmTasks.get(0).get("inputParameters");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> toolSpecs = (List<Map<String, Object>>) llmInputs.get("tools");
        assertThat(toolSpecs).anyMatch(t -> "research_tool".equals(t.get("name")));
    }

    @Test
    void compileGoogleAdkWithTransferControl() throws Exception {
        Map<String, Object> sub1 = new LinkedHashMap<>();
        sub1.put("name", "agent_a_e2e");
        sub1.put("model", "gemini-2.0-flash");
        sub1.put("instruction", "Agent A.");
        sub1.put("disallow_transfer_to_parent", true);

        Map<String, Object> sub2 = new LinkedHashMap<>();
        sub2.put("name", "agent_b_e2e");
        sub2.put("model", "gemini-2.0-flash");
        sub2.put("instruction", "Agent B.");
        sub2.put("disallow_transfer_to_peers", true);

        Map<String, Object> rawConfig = new LinkedHashMap<>();
        rawConfig.put("name", "adk_transfer_e2e");
        rawConfig.put("model", "gemini-2.0-flash");
        rawConfig.put("instruction", "Coordinate.");
        rawConfig.put("sub_agents", List.of(sub1, sub2));

        Map<String, Object> body = Map.of(
                "framework", "google_adk",
                "rawConfig", rawConfig,
                "prompt", "Go"
        );

        // Should compile without error
        JsonNode resp = postCompile(body);
        assertThat(resp.get("workflowDef").get("name").asText()).isEqualTo("adk_transfer_e2e");
    }

    @Test
    void compileGoogleAdkWithPlannerEnhancesInstructions() throws Exception {
        Map<String, Object> rawConfig = new LinkedHashMap<>();
        rawConfig.put("name", "adk_planner_e2e");
        rawConfig.put("model", "gemini-2.0-flash");
        rawConfig.put("instruction", "You are a researcher.");
        rawConfig.put("planner", Map.of("_type", "BuiltInPlanner"));

        Map<String, Object> body = Map.of(
                "framework", "google_adk",
                "rawConfig", rawConfig,
                "prompt", "Research AI safety"
        );

        JsonNode resp = postCompile(body);
        List<Map<String, Object>> llmTasks = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");

        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llmTasks.get(0).get("inputParameters");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> messages = (List<Map<String, Object>>) inputs.get("messages");
        String systemMsg = messages.stream()
                .filter(m -> "system".equals(m.get("role")))
                .map(m -> (String) m.get("message"))
                .findFirst().orElse("");
        assertThat(systemMsg).contains("step-by-step plan");
    }

    // ── Start + Status e2e (workflow actually starts) ────────────────

    @Test
    void startAgentCreatesWorkflow() throws Exception {
        Map<String, Object> config = agentConfig("start_e2e", "openai/gpt-4o", "You are helpful.");
        Map<String, Object> body = Map.of(
                "agentConfig", config,
                "prompt", "Hello world"
        );

        JsonNode resp = postStart(body);
        assertThat(resp.get("workflowId")).isNotNull();
        assertThat(resp.get("workflowId").asText()).isNotEmpty();
        assertThat(resp.get("workflowName").asText()).isEqualTo("start_e2e");
    }

    @Test
    void startAgentStatusEndpointWorks() throws Exception {
        Map<String, Object> config = agentConfig("status_e2e", "openai/gpt-4o", "You are helpful.");
        Map<String, Object> body = Map.of(
                "agentConfig", config,
                "prompt", "Hello"
        );

        JsonNode startResp = postStart(body);
        String workflowId = startResp.get("workflowId").asText();

        // The workflow should be running (waiting on LLM task since AI is disabled)
        JsonNode statusResp = get(statusUrl(workflowId));
        assertThat(statusResp.get("status")).isNotNull();
        String status = statusResp.get("status").asText();
        // Could be RUNNING (waiting on LLM) or FAILED (no AI provider) — both are valid
        assertThat(status).isIn("RUNNING", "FAILED");
    }

    @Test
    void startMultipleCallsProduceDifferentWorkflows() throws Exception {
        Map<String, Object> config = agentConfig("multi_e2e", "openai/gpt-4o", "You are helpful.");
        Map<String, Object> body1 = new LinkedHashMap<>();
        body1.put("agentConfig", config);
        body1.put("prompt", "Hello 1");

        Map<String, Object> body2 = new LinkedHashMap<>();
        body2.put("agentConfig", config);
        body2.put("prompt", "Hello 2");

        JsonNode resp1 = postStart(body1);
        JsonNode resp2 = postStart(body2);

        // Each start should produce a unique workflow ID
        assertThat(resp1.get("workflowId").asText()).isNotEqualTo(resp2.get("workflowId").asText());
        assertThat(resp1.get("workflowName").asText()).isEqualTo("multi_e2e");
        assertThat(resp2.get("workflowName").asText()).isEqualTo("multi_e2e");
    }

    // ══════════════════════════════════════════════════════════════════
    // OpenAI Normalizer e2e tests
    // ══════════════════════════════════════════════════════════════════

    /** Build an OpenAI framework request body. */
    private Map<String, Object> openaiRequest(Map<String, Object> rawConfig) {
        return Map.of("framework", "openai", "rawConfig", rawConfig, "prompt", "test");
    }

    @Test
    void openaiBasicAgent() throws Exception {
        // Mirrors: examples/openai/01_basic_agent.py
        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("name", "oai_basic_e2e");
        raw.put("model", "gpt-4o");
        raw.put("instructions", "You are a helpful assistant.");

        JsonNode resp = postCompile(openaiRequest(raw));
        JsonNode wf = resp.get("workflowDef");
        assertThat(wf.get("name").asText()).isEqualTo("oai_basic_e2e");

        List<Map<String, Object>> llmTasks = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        assertThat(llmTasks).hasSize(1);

        // Model should be prefixed with "openai/"
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llmTasks.get(0).get("inputParameters");
        assertThat(inputs.get("llmProvider")).isEqualTo("openai");
        assertThat(inputs.get("model")).isEqualTo("gpt-4o");
    }

    @Test
    void openaiModelPrefixing() throws Exception {
        // Model without provider should get "openai/" prefix
        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("name", "oai_model_e2e");
        raw.put("model", "gpt-4o-mini");
        raw.put("instructions", "Test.");

        JsonNode resp = postCompile(openaiRequest(raw));
        List<Map<String, Object>> llm = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");
        assertThat(inputs.get("llmProvider")).isEqualTo("openai");
        assertThat(inputs.get("model")).isEqualTo("gpt-4o-mini");
    }

    @Test
    void openaiModelWithProviderPassesThrough() throws Exception {
        // Model with explicit provider should not get double-prefixed
        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("name", "oai_provider_e2e");
        raw.put("model", "anthropic/claude-sonnet-4-20250514");
        raw.put("instructions", "Test.");

        JsonNode resp = postCompile(openaiRequest(raw));
        List<Map<String, Object>> llm = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");
        assertThat(inputs.get("llmProvider")).isEqualTo("anthropic");
        assertThat(inputs.get("model")).isEqualTo("claude-sonnet-4-20250514");
    }

    @Test
    void openaiDefaultModelWhenMissing() throws Exception {
        // No model specified — should default to openai/gpt-4o
        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("name", "oai_default_e2e");
        raw.put("instructions", "Test.");

        JsonNode resp = postCompile(openaiRequest(raw));
        List<Map<String, Object>> llm = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");
        assertThat(inputs.get("llmProvider")).isEqualTo("openai");
        assertThat(inputs.get("model")).isEqualTo("gpt-4o");
    }

    @Test
    void openaiFunctionTools() throws Exception {
        // Mirrors: examples/openai/02_function_tools.py
        // Tools arrive as _worker_ref from the generic serializer
        Map<String, Object> tool1 = new LinkedHashMap<>();
        tool1.put("_worker_ref", "get_weather");
        tool1.put("description", "Get current weather");
        tool1.put("parameters", Map.of("type", "object",
                "properties", Map.of("city", Map.of("type", "string")),
                "required", List.of("city")));

        Map<String, Object> tool2 = new LinkedHashMap<>();
        tool2.put("_worker_ref", "calculate");
        tool2.put("description", "Do math");
        tool2.put("parameters", Map.of("type", "object",
                "properties", Map.of("expr", Map.of("type", "string"))));

        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("name", "oai_tools_e2e");
        raw.put("model", "gpt-4o");
        raw.put("instructions", "Use tools to help.");
        raw.put("tools", List.of(tool1, tool2));

        JsonNode resp = postCompile(openaiRequest(raw));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Tool agent = DO_WHILE loop
        assertThat(findTaskByType(tasks, "DO_WHILE")).isNotNull();

        // Two tool specs in LLM inputs
        List<Map<String, Object>> llm = findAllTasksByType(tasks, "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> toolSpecs = (List<Map<String, Object>>) inputs.get("tools");
        assertThat(toolSpecs).hasSize(2);
        assertThat(toolSpecs.stream().map(t -> t.get("name")).toList())
                .containsExactlyInAnyOrder("get_weather", "calculate");
    }

    @Test
    void openaiWebSearchTool() throws Exception {
        // WebSearchTool is a typed tool (non-callable)
        Map<String, Object> tool = new LinkedHashMap<>();
        tool.put("_type", "WebSearchTool");

        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("name", "oai_websearch_e2e");
        raw.put("model", "gpt-4o");
        raw.put("instructions", "Search the web.");
        raw.put("tools", List.of(tool));

        JsonNode resp = postCompile(openaiRequest(raw));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Should produce DO_WHILE with tool loop
        assertThat(findTaskByType(tasks, "DO_WHILE")).isNotNull();

        // Tool spec should be "web_search" with HTTP type
        List<Map<String, Object>> llm = findAllTasksByType(tasks, "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> toolSpecs = (List<Map<String, Object>>) inputs.get("tools");
        assertThat(toolSpecs).hasSize(1);
        assertThat(toolSpecs.get(0).get("name")).isEqualTo("web_search");
        assertThat(toolSpecs.get(0).get("type")).isEqualTo("HTTP");
    }

    @Test
    void openaiFileSearchTool() throws Exception {
        Map<String, Object> tool = new LinkedHashMap<>();
        tool.put("_type", "FileSearchTool");

        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("name", "oai_filesearch_e2e");
        raw.put("model", "gpt-4o");
        raw.put("instructions", "Search files.");
        raw.put("tools", List.of(tool));

        JsonNode resp = postCompile(openaiRequest(raw));
        List<Map<String, Object>> llm = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> toolSpecs = (List<Map<String, Object>>) inputs.get("tools");
        assertThat(toolSpecs).hasSize(1);
        assertThat(toolSpecs.get(0).get("name")).isEqualTo("file_search");
        assertThat(toolSpecs.get(0).get("type")).isEqualTo("SIMPLE");
    }

    @Test
    void openaiCodeInterpreterIsFilteredFromTools() throws Exception {
        // CodeInterpreterTool should NOT produce a tool spec — only real tools remain
        Map<String, Object> codeInterp = new LinkedHashMap<>();
        codeInterp.put("_type", "CodeInterpreterTool");

        Map<String, Object> regularTool = new LinkedHashMap<>();
        regularTool.put("_worker_ref", "analyze");
        regularTool.put("description", "Analyze data");
        regularTool.put("parameters", Map.of("type", "object",
                "properties", Map.of("data", Map.of("type", "string"))));

        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("name", "oai_code_e2e");
        raw.put("model", "gpt-4o");
        raw.put("instructions", "Run code.");
        raw.put("tools", List.of(regularTool, codeInterp));

        JsonNode resp = postCompile(openaiRequest(raw));
        List<Map<String, Object>> llm = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");

        // CodeInterpreter is filtered out, only "analyze" remains
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> toolSpecs = (List<Map<String, Object>>) inputs.get("tools");
        assertThat(toolSpecs).hasSize(1);
        assertThat(toolSpecs.get(0).get("name")).isEqualTo("analyze");

        // Code execution instructions should be appended to system message
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> messages = (List<Map<String, Object>>) inputs.get("messages");
        String sysMsg = messages.stream()
                .filter(m -> "system".equals(m.get("role")))
                .map(m -> (String) m.get("message"))
                .findFirst().orElse("");
        assertThat(sysMsg).contains("code execution");
    }

    @Test
    void openaiFunctionToolType() throws Exception {
        // FunctionTool type (serialized non-callable with name)
        Map<String, Object> tool = new LinkedHashMap<>();
        tool.put("_type", "FunctionTool");
        tool.put("name", "summarize");
        tool.put("description", "Summarize text");
        tool.put("parameters", Map.of("type", "object",
                "properties", Map.of("text", Map.of("type", "string"))));

        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("name", "oai_functype_e2e");
        raw.put("model", "gpt-4o");
        raw.put("instructions", "Summarize.");
        raw.put("tools", List.of(tool));

        JsonNode resp = postCompile(openaiRequest(raw));
        List<Map<String, Object>> llm = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> toolSpecs = (List<Map<String, Object>>) inputs.get("tools");
        assertThat(toolSpecs.get(0).get("name")).isEqualTo("summarize");
        assertThat(toolSpecs.get(0).get("type")).isEqualTo("SIMPLE");
    }

    @Test
    void openaiHandoffs() throws Exception {
        // Mirrors: examples/openai/04_handoffs.py
        // Triage agent with handoffs to specialist agents (each with tools)
        Map<String, Object> orderTool = new LinkedHashMap<>();
        orderTool.put("_worker_ref", "check_order_status");
        orderTool.put("description", "Check order status");
        orderTool.put("parameters", Map.of("type", "object",
                "properties", Map.of("order_id", Map.of("type", "string"))));

        Map<String, Object> orderAgent = new LinkedHashMap<>();
        orderAgent.put("name", "order_specialist");
        orderAgent.put("model", "gpt-4o");
        orderAgent.put("instructions", "Handle orders.");
        orderAgent.put("tools", List.of(orderTool));

        Map<String, Object> refundTool = new LinkedHashMap<>();
        refundTool.put("_worker_ref", "process_refund");
        refundTool.put("description", "Process refund");
        refundTool.put("parameters", Map.of("type", "object"));

        Map<String, Object> refundAgent = new LinkedHashMap<>();
        refundAgent.put("name", "refund_specialist");
        refundAgent.put("model", "gpt-4o");
        refundAgent.put("instructions", "Handle refunds.");
        refundAgent.put("tools", List.of(refundTool));

        Map<String, Object> salesAgent = new LinkedHashMap<>();
        salesAgent.put("name", "sales_specialist");
        salesAgent.put("model", "gpt-4o");
        salesAgent.put("instructions", "Handle sales.");

        Map<String, Object> triage = new LinkedHashMap<>();
        triage.put("name", "oai_handoff_e2e");
        triage.put("model", "gpt-4o");
        triage.put("instructions", "Route to specialist.");
        triage.put("handoffs", List.of(orderAgent, refundAgent, salesAgent));

        JsonNode resp = postCompile(openaiRequest(triage));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Handoff = DO_WHILE with SWITCH inside
        assertThat(findTaskByType(tasks, "DO_WHILE")).isNotNull();
        List<Map<String, Object>> switches = findAllTasksByType(tasks, "SWITCH");
        assertThat(switches).isNotEmpty();
    }

    @Test
    void openaiStructuredOutput() throws Exception {
        // Mirrors: examples/openai/03_structured_output.py
        // output_type is a Pydantic JSON schema
        Map<String, Object> schema = Map.of(
                "type", "object",
                "title", "MovieList",
                "properties", Map.of(
                        "recommendations", Map.of("type", "array",
                                "items", Map.of("type", "object")),
                        "theme", Map.of("type", "string")
                ),
                "required", List.of("recommendations", "theme")
        );

        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("name", "oai_output_e2e");
        raw.put("model", "gpt-4o");
        raw.put("instructions", "Recommend movies.");
        raw.put("output_type", schema);
        raw.put("model_settings", Map.of("temperature", 0.3, "max_tokens", 1000));

        JsonNode resp = postCompile(openaiRequest(raw));
        List<Map<String, Object>> llm = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");

        // System message should contain JSON schema
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> messages = (List<Map<String, Object>>) inputs.get("messages");
        String sysMsg = messages.stream()
                .filter(m -> "system".equals(m.get("role")))
                .map(m -> (String) m.get("message"))
                .findFirst().orElse("");
        assertThat(sysMsg).contains("JSON");

        // Model settings should be applied
        assertThat(inputs.get("temperature")).isEqualTo(0.3);
        assertThat(inputs.get("maxTokens")).isEqualTo(1000);
    }

    @Test
    void openaiModelSettings() throws Exception {
        // Mirrors: examples/openai/06_model_settings.py
        // model_settings nested under that key
        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("name", "oai_settings_e2e");
        raw.put("model", "gpt-4o");
        raw.put("instructions", "Be creative.");
        raw.put("model_settings", Map.of("temperature", 0.9, "max_tokens", 500));

        JsonNode resp = postCompile(openaiRequest(raw));
        List<Map<String, Object>> llm = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");

        assertThat(inputs.get("temperature")).isEqualTo(0.9);
        assertThat(inputs.get("maxTokens")).isEqualTo(500);
    }

    @Test
    void openaiTopLevelTempOverridesModelSettings() throws Exception {
        // When both model_settings and top-level are present, top-level wins
        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("name", "oai_override_e2e");
        raw.put("model", "gpt-4o");
        raw.put("instructions", "Test.");
        raw.put("model_settings", Map.of("temperature", 0.5));
        raw.put("temperature", 0.1);

        JsonNode resp = postCompile(openaiRequest(raw));
        List<Map<String, Object>> llm = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");
        // Top-level should override model_settings
        assertThat(inputs.get("temperature")).isEqualTo(0.1);
    }

    @Test
    void openaiGuardrails() throws Exception {
        // Mirrors: examples/openai/05_guardrails.py
        // Input guardrail with _worker_ref
        Map<String, Object> inputGuardrail = new LinkedHashMap<>();
        inputGuardrail.put("_type", "InputGuardrail");
        inputGuardrail.put("name", "pii_check");
        inputGuardrail.put("_worker_ref", "check_for_pii");

        // Output guardrail with _worker_ref
        Map<String, Object> outputGuardrail = new LinkedHashMap<>();
        outputGuardrail.put("_type", "OutputGuardrail");
        outputGuardrail.put("name", "safety_check");
        outputGuardrail.put("_worker_ref", "check_output_safety");

        Map<String, Object> tool = new LinkedHashMap<>();
        tool.put("_worker_ref", "get_account_balance");
        tool.put("description", "Look up balance");
        tool.put("parameters", Map.of("type", "object",
                "properties", Map.of("account_id", Map.of("type", "string"))));

        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("name", "oai_guard_e2e");
        raw.put("model", "gpt-4o");
        raw.put("instructions", "Secure banking assistant.");
        raw.put("tools", List.of(tool));
        raw.put("guardrails", List.of(inputGuardrail, outputGuardrail));

        JsonNode resp = postCompile(openaiRequest(raw));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Should have DO_WHILE for tool loop
        assertThat(findTaskByType(tasks, "DO_WHILE")).isNotNull();

        // Guardrails produce SIMPLE tasks for custom workers
        List<Map<String, Object>> simpleTasks = findAllTasksByType(tasks, "SIMPLE");
        // At minimum the guardrail workers should be present
        assertThat(simpleTasks).isNotEmpty();
    }

    @Test
    void openaiDynamicInstructions() throws Exception {
        // Mirrors: examples/openai/09_dynamic_instructions.py
        // Dynamic instructions arrive as _worker_ref
        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("name", "oai_dynamic_e2e");
        raw.put("model", "gpt-4o");
        // Dynamic instructions: the serializer replaces the callable with a worker ref
        raw.put("instructions", Map.of("_worker_ref", "get_dynamic_instructions",
                "description", "Generate dynamic instructions"));

        Map<String, Object> tool = new LinkedHashMap<>();
        tool.put("_worker_ref", "get_todo_list");
        tool.put("description", "Get todos");
        tool.put("parameters", Map.of("type", "object"));

        raw.put("tools", List.of(tool));

        // Should compile without error — instructions may be string or object
        JsonNode resp = postCompile(openaiRequest(raw));
        assertThat(resp.get("workflowDef")).isNotNull();
    }

    @Test
    void openaiAgentAsTool() throws Exception {
        // Mirrors: examples/openai/08_agent_as_tool.py
        // as_tool() produces a _worker_ref with embedded agent config
        // The serializer serializes this as a tool with the agent's full config
        Map<String, Object> sentimentTool = new LinkedHashMap<>();
        sentimentTool.put("_worker_ref", "analyze_sentiment");
        sentimentTool.put("description", "Analyze sentiment");
        sentimentTool.put("parameters", Map.of("type", "object",
                "properties", Map.of("text", Map.of("type", "string"))));

        Map<String, Object> sentimentAgent = new LinkedHashMap<>();
        sentimentAgent.put("name", "sentiment_analyzer");
        sentimentAgent.put("model", "gpt-4o");
        sentimentAgent.put("instructions", "Analyze sentiment.");
        sentimentAgent.put("tools", List.of(sentimentTool));

        // as_tool() serializes the agent as a tool with name/description
        Map<String, Object> agentTool = new LinkedHashMap<>();
        agentTool.put("name", "sentiment_analyzer");
        agentTool.put("description", "Analyze text sentiment");
        agentTool.put("parameters", Map.of("type", "object",
                "properties", Map.of("request", Map.of("type", "string"))));
        // In the OpenAI SDK, as_tool() produces a _worker_ref for the wrapper
        agentTool.put("_worker_ref", "sentiment_analyzer");

        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("name", "oai_manager_e2e");
        raw.put("model", "gpt-4o");
        raw.put("instructions", "Manage analysis.");
        raw.put("tools", List.of(agentTool));

        JsonNode resp = postCompile(openaiRequest(raw));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Manager should have DO_WHILE with tool dispatch
        assertThat(findTaskByType(tasks, "DO_WHILE")).isNotNull();

        // Tool spec should include the agent-as-tool
        List<Map<String, Object>> llm = findAllTasksByType(tasks, "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> toolSpecs = (List<Map<String, Object>>) inputs.get("tools");
        assertThat(toolSpecs).anyMatch(t -> "sentiment_analyzer".equals(t.get("name")));
    }

    @Test
    void openaiMultiModelHandoff() throws Exception {
        // Mirrors: examples/openai/10_multi_model.py
        // Triage with gpt-4o-mini, specialists with gpt-4o
        Map<String, Object> specialist = new LinkedHashMap<>();
        specialist.put("name", "expert_e2e");
        specialist.put("model", "gpt-4o");
        specialist.put("instructions", "Expert analysis.");

        Map<String, Object> triage = new LinkedHashMap<>();
        triage.put("name", "oai_multimodel_e2e");
        triage.put("model", "gpt-4o-mini");
        triage.put("instructions", "Route to expert.");
        triage.put("handoffs", List.of(specialist));

        JsonNode resp = postCompile(openaiRequest(triage));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Handoff agent: DO_WHILE + SWITCH
        assertThat(findTaskByType(tasks, "DO_WHILE")).isNotNull();

        // Verify the triage LLM uses gpt-4o-mini
        List<Map<String, Object>> llm = findAllTasksByType(tasks, "LLM_CHAT_COMPLETE");
        boolean hasMini = llm.stream().anyMatch(t -> {
            @SuppressWarnings("unchecked")
            Map<String, Object> inp = (Map<String, Object>) t.get("inputParameters");
            return "gpt-4o-mini".equals(inp.get("model"));
        });
        assertThat(hasMini).isTrue();
    }

    // ══════════════════════════════════════════════════════════════════
    // ToolCompiler e2e tests
    // ══════════════════════════════════════════════════════════════════

    @Test
    void toolCompilerAgentToolType() throws Exception {
        // Agent tool type should map to SUB_WORKFLOW in tool specs
        Map<String, Object> childAgent = agentConfig("child_e2e", "openai/gpt-4o", "Helper.");
        Map<String, Object> agentTool = new LinkedHashMap<>();
        agentTool.put("name", "helper_tool");
        agentTool.put("description", "Helper agent");
        agentTool.put("inputSchema", Map.of("type", "object"));
        agentTool.put("toolType", "agent_tool");
        agentTool.put("config", Map.of("agent", childAgent));

        Map<String, Object> config = agentConfig("tc_agent_e2e", "openai/gpt-4o", "Manager.");
        config.put("tools", List.of(agentTool));

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> llm = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> toolSpecs = (List<Map<String, Object>>) inputs.get("tools");

        // Agent tool type should be mapped to SUB_WORKFLOW
        assertThat(toolSpecs).hasSize(1);
        assertThat(toolSpecs.get(0).get("type")).isEqualTo("SUB_WORKFLOW");
        assertThat(toolSpecs.get(0).get("name")).isEqualTo("helper_tool");
    }

    @Test
    void toolCompilerHttpToolType() throws Exception {
        Map<String, Object> httpTool = new LinkedHashMap<>();
        httpTool.put("name", "fetch_data");
        httpTool.put("description", "Fetch data from API");
        httpTool.put("inputSchema", Map.of("type", "object",
                "properties", Map.of("url", Map.of("type", "string"))));
        httpTool.put("toolType", "http");
        httpTool.put("config", Map.of("baseUrl", "https://api.example.com"));

        Map<String, Object> config = agentConfig("tc_http_e2e", "openai/gpt-4o", "Fetch data.");
        config.put("tools", List.of(httpTool));

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> llm = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> toolSpecs = (List<Map<String, Object>>) inputs.get("tools");

        assertThat(toolSpecs).hasSize(1);
        assertThat(toolSpecs.get(0).get("type")).isEqualTo("HTTP");
    }

    @Test
    void toolCompilerMcpToolType() throws Exception {
        Map<String, Object> mcpTool = new LinkedHashMap<>();
        mcpTool.put("name", "mcp_search");
        mcpTool.put("description", "Search via MCP");
        mcpTool.put("inputSchema", Map.of("type", "object"));
        mcpTool.put("toolType", "mcp");
        mcpTool.put("config", Map.of("server_url", "http://mcp.example.com",
                "headers", Map.of("Authorization", "Bearer token")));

        Map<String, Object> config = agentConfig("tc_mcp_e2e", "openai/gpt-4o", "MCP agent.");
        config.put("tools", List.of(mcpTool));

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> tasks = getTasks(resp);

        // MCP tools produce discovery tasks (LIST_MCP_TOOLS)
        List<Map<String, Object>> listTasks = findAllTasksByType(tasks, "LIST_MCP_TOOLS");
        assertThat(listTasks).isNotEmpty();

        // Should have INLINE prepare/resolve tasks
        List<Map<String, Object>> inlineTasks = findAllTasksByType(tasks, "INLINE");
        assertThat(inlineTasks).isNotEmpty();
    }

    @Test
    void toolCompilerMixedToolTypes() throws Exception {
        // Mix of worker + http + mcp tools
        Map<String, Object> workerTool = new LinkedHashMap<>();
        workerTool.put("name", "local_calc");
        workerTool.put("description", "Calculate");
        workerTool.put("inputSchema", Map.of("type", "object"));
        workerTool.put("toolType", "worker");

        Map<String, Object> mcpTool = new LinkedHashMap<>();
        mcpTool.put("name", "remote_search");
        mcpTool.put("description", "Remote search");
        mcpTool.put("inputSchema", Map.of("type", "object"));
        mcpTool.put("toolType", "mcp");
        mcpTool.put("config", Map.of("server_url", "http://mcp.example.com"));

        Map<String, Object> config = agentConfig("tc_mixed_e2e", "openai/gpt-4o", "Mixed tools.");
        config.put("tools", List.of(workerTool, mcpTool));

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> tasks = getTasks(resp);

        // MCP present → should have discovery tasks
        assertThat(findAllTasksByType(tasks, "LIST_MCP_TOOLS")).isNotEmpty();
        // Should still have DO_WHILE
        assertThat(findTaskByType(tasks, "DO_WHILE")).isNotNull();
    }

    @Test
    void toolCompilerApprovalGate() throws Exception {
        // Tool with approvalRequired=true should produce HUMAN task in workflow
        Map<String, Object> safeTool = new LinkedHashMap<>();
        safeTool.put("name", "read_data");
        safeTool.put("description", "Read data");
        safeTool.put("inputSchema", Map.of("type", "object"));
        safeTool.put("toolType", "worker");

        Map<String, Object> dangerousTool = new LinkedHashMap<>();
        dangerousTool.put("name", "delete_record");
        dangerousTool.put("description", "Delete a record");
        dangerousTool.put("inputSchema", Map.of("type", "object"));
        dangerousTool.put("toolType", "worker");
        dangerousTool.put("approvalRequired", true);

        Map<String, Object> config = agentConfig("tc_approval_e2e", "openai/gpt-4o", "Admin agent.");
        config.put("tools", List.of(safeTool, dangerousTool));

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Approval gate produces HUMAN task
        List<Map<String, Object>> humanTasks = findAllTasksByType(tasks, "HUMAN");
        assertThat(humanTasks).isNotEmpty();

        // Should have approval SWITCH with "needs_approval" / "approved" cases
        List<Map<String, Object>> switches = findAllTasksByType(tasks, "SWITCH");
        List<String> switchRefs = switches.stream()
                .map(t -> (String) t.get("taskReferenceName"))
                .toList();
        assertThat(switchRefs).anyMatch(r -> r.contains("approval"));
    }

    @Test
    void toolCompilerMultipleMcpServers() throws Exception {
        // Two MCP tools from different servers → two LIST_MCP_TOOLS tasks
        Map<String, Object> mcp1 = new LinkedHashMap<>();
        mcp1.put("name", "search_a");
        mcp1.put("description", "Search A");
        mcp1.put("inputSchema", Map.of("type", "object"));
        mcp1.put("toolType", "mcp");
        mcp1.put("config", Map.of("server_url", "http://mcp-a.example.com"));

        Map<String, Object> mcp2 = new LinkedHashMap<>();
        mcp2.put("name", "search_b");
        mcp2.put("description", "Search B");
        mcp2.put("inputSchema", Map.of("type", "object"));
        mcp2.put("toolType", "mcp");
        mcp2.put("config", Map.of("server_url", "http://mcp-b.example.com"));

        Map<String, Object> config = agentConfig("tc_multi_mcp_e2e", "openai/gpt-4o", "Multi MCP.");
        config.put("tools", List.of(mcp1, mcp2));

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> listTasks = findAllTasksByType(getTasks(resp), "LIST_MCP_TOOLS");
        // Two different servers → two LIST_MCP_TOOLS tasks
        assertThat(listTasks).hasSize(2);
    }

    @Test
    void toolCompilerDuplicateMcpServerDeduplication() throws Exception {
        // Two MCP tools from the SAME server → only one LIST_MCP_TOOLS task
        Map<String, Object> mcp1 = new LinkedHashMap<>();
        mcp1.put("name", "tool_x");
        mcp1.put("description", "Tool X");
        mcp1.put("inputSchema", Map.of("type", "object"));
        mcp1.put("toolType", "mcp");
        mcp1.put("config", Map.of("server_url", "http://same-server.example.com"));

        Map<String, Object> mcp2 = new LinkedHashMap<>();
        mcp2.put("name", "tool_y");
        mcp2.put("description", "Tool Y");
        mcp2.put("inputSchema", Map.of("type", "object"));
        mcp2.put("toolType", "mcp");
        mcp2.put("config", Map.of("server_url", "http://same-server.example.com"));

        Map<String, Object> config = agentConfig("tc_dedup_e2e", "openai/gpt-4o", "Dedup MCP.");
        config.put("tools", List.of(mcp1, mcp2));

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> listTasks = findAllTasksByType(getTasks(resp), "LIST_MCP_TOOLS");
        // Same server → deduplicated to one LIST_MCP_TOOLS task
        assertThat(listTasks).hasSize(1);
    }

    @Test
    void toolCompilerMediaToolTypes() throws Exception {
        // Media tool types: generate_image, generate_audio, generate_video
        Map<String, Object> imageTool = new LinkedHashMap<>();
        imageTool.put("name", "create_image");
        imageTool.put("description", "Generate an image");
        imageTool.put("inputSchema", Map.of("type", "object",
                "properties", Map.of("prompt", Map.of("type", "string"))));
        imageTool.put("toolType", "generate_image");

        Map<String, Object> config = agentConfig("tc_media_e2e", "openai/gpt-4o", "Image agent.");
        config.put("tools", List.of(imageTool));

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> llm = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> toolSpecs = (List<Map<String, Object>>) inputs.get("tools");

        assertThat(toolSpecs).hasSize(1);
        assertThat(toolSpecs.get(0).get("type")).isEqualTo("GENERATE_IMAGE");
    }

    @Test
    void toolCompilerEnrichTaskPresentForHttpTools() throws Exception {
        // HTTP tools should produce an INLINE enrich task in the tool_call case
        Map<String, Object> httpTool = new LinkedHashMap<>();
        httpTool.put("name", "api_call");
        httpTool.put("description", "Call API");
        httpTool.put("inputSchema", Map.of("type", "object"));
        httpTool.put("toolType", "http");
        httpTool.put("config", Map.of("baseUrl", "https://api.example.com"));

        Map<String, Object> config = agentConfig("tc_enrich_e2e", "openai/gpt-4o", "API agent.");
        config.put("tools", List.of(httpTool));

        JsonNode resp = postCompile(request(config));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Should have INLINE enrich task inside the tool routing
        List<Map<String, Object>> inlineTasks = findAllTasksByType(tasks, "INLINE");
        assertThat(inlineTasks).anyMatch(t ->
                ((String) t.get("taskReferenceName")).contains("enrich"));
    }

    // ══════════════════════════════════════════════════════════════════
    // Vercel AI SDK Normalizer e2e tests
    // ══════════════════════════════════════════════════════════════════

    /** Build a Vercel AI framework request body. */
    private Map<String, Object> vercelAiRequest(Map<String, Object> rawConfig) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("framework", "vercel_ai");
        body.put("rawConfig", rawConfig);
        body.put("prompt", "test");
        return body;
    }

    @Test
    void compileVercelAiBasicAgent() throws Exception {
        Map<String, Object> rawConfig = new LinkedHashMap<>();
        rawConfig.put("name", "test_vercel_agent");
        rawConfig.put("model", "gpt-4o");
        rawConfig.put("system", "You are a helpful assistant.");

        JsonNode resp = postCompile(vercelAiRequest(rawConfig));
        JsonNode wf = resp.get("workflowDef");
        assertThat(wf).isNotNull();
        assertThat(wf.get("name").asText()).isEqualTo("test_vercel_agent");

        List<Map<String, Object>> tasks = getTasks(resp);
        // Real extraction: simple agent = single LLM_CHAT_COMPLETE task (not passthrough _fw_task)
        assertThat(tasks).hasSize(1);
        assertThat(tasks.get(0).get("type")).isEqualTo("LLM_CHAT_COMPLETE");
    }

    @Test
    void compileVercelAiModelPrefixing() throws Exception {
        // Bare model name should get "openai/" prefix
        Map<String, Object> rawConfig = new LinkedHashMap<>();
        rawConfig.put("name", "vercel_model_e2e");
        rawConfig.put("model", "gpt-4o-mini");
        rawConfig.put("system", "Test.");

        JsonNode resp = postCompile(vercelAiRequest(rawConfig));
        List<Map<String, Object>> llm = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");
        assertThat(inputs.get("llmProvider")).isEqualTo("openai");
        assertThat(inputs.get("model")).isEqualTo("gpt-4o-mini");
    }

    @Test
    void compileVercelAiModelWithProviderPassesThrough() throws Exception {
        // Model with explicit provider should not get double-prefixed
        Map<String, Object> rawConfig = new LinkedHashMap<>();
        rawConfig.put("name", "vercel_provider_e2e");
        rawConfig.put("model", "anthropic/claude-sonnet-4-20250514");
        rawConfig.put("system", "Test.");

        JsonNode resp = postCompile(vercelAiRequest(rawConfig));
        List<Map<String, Object>> llm = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");
        assertThat(inputs.get("llmProvider")).isEqualTo("anthropic");
        assertThat(inputs.get("model")).isEqualTo("claude-sonnet-4-20250514");
    }

    @Test
    void compileVercelAiWithWorkerRefTools() throws Exception {
        // Tools arrive as _worker_ref from the generic serializer
        Map<String, Object> tool1 = new LinkedHashMap<>();
        tool1.put("_worker_ref", "get_weather");
        tool1.put("description", "Get current weather");
        tool1.put("parameters", Map.of("type", "object",
                "properties", Map.of("city", Map.of("type", "string")),
                "required", List.of("city")));

        Map<String, Object> tool2 = new LinkedHashMap<>();
        tool2.put("_worker_ref", "calculate");
        tool2.put("description", "Do math");
        tool2.put("parameters", Map.of("type", "object",
                "properties", Map.of("expr", Map.of("type", "string"))));

        Map<String, Object> rawConfig = new LinkedHashMap<>();
        rawConfig.put("name", "vercel_tools_e2e");
        rawConfig.put("model", "gpt-4o");
        rawConfig.put("system", "Use tools to help.");
        rawConfig.put("tools", List.of(tool1, tool2));

        JsonNode resp = postCompile(vercelAiRequest(rawConfig));
        List<Map<String, Object>> tasks = getTasks(resp);

        // Tool agent = DO_WHILE loop (not single SIMPLE _fw_task)
        assertThat(findTaskByType(tasks, "DO_WHILE")).isNotNull();

        // Two tool specs in LLM inputs
        List<Map<String, Object>> llm = findAllTasksByType(tasks, "LLM_CHAT_COMPLETE");
        assertThat(llm).isNotEmpty();
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> toolSpecs = (List<Map<String, Object>>) inputs.get("tools");
        assertThat(toolSpecs).hasSize(2);
        assertThat(toolSpecs.stream().map(t -> t.get("name")).toList())
                .containsExactlyInAnyOrder("get_weather", "calculate");

        // FORK_JOIN_DYNAMIC for tool dispatch (SIMPLE tasks for each tool)
        List<Map<String, Object>> forkTasks = findAllTasksByType(tasks, "FORK_JOIN_DYNAMIC");
        assertThat(forkTasks).isNotEmpty();
    }

    @Test
    void compileVercelAiWithTemperatureAndMaxTokens() throws Exception {
        Map<String, Object> rawConfig = new LinkedHashMap<>();
        rawConfig.put("name", "vercel_params_e2e");
        rawConfig.put("model", "gpt-4o");
        rawConfig.put("system", "Test.");
        rawConfig.put("temperature", 0.7);
        rawConfig.put("maxTokens", 500);

        JsonNode resp = postCompile(vercelAiRequest(rawConfig));
        List<Map<String, Object>> llm = findAllTasksByType(getTasks(resp), "LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        Map<String, Object> inputs = (Map<String, Object>) llm.get(0).get("inputParameters");
        assertThat(inputs.get("temperature")).isEqualTo(0.7);
        assertThat(inputs.get("maxTokens")).isEqualTo(500);
    }

    @Test
    void startVercelAiAgent() throws Exception {
        Map<String, Object> rawConfig = new LinkedHashMap<>();
        rawConfig.put("name", "vercel_start_e2e");
        rawConfig.put("model", "gpt-4o");
        rawConfig.put("system", "You are helpful.");

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("framework", "vercel_ai");
        body.put("rawConfig", rawConfig);
        body.put("prompt", "Hello from Vercel AI");

        JsonNode resp = postStart(body);
        assertThat(resp.get("workflowId")).isNotNull();
        assertThat(resp.get("workflowId").asText()).isNotEmpty();
    }
}
