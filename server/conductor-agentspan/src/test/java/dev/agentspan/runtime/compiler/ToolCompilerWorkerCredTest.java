/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.compiler;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;

import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.Value;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.netflix.conductor.common.metadata.workflow.WorkflowTask;

import dev.agentspan.runtime.model.AgentConfig;
import dev.agentspan.runtime.model.ToolConfig;
import dev.agentspan.runtime.util.EmbeddedMode;

/**
 * Verifies EMBEDDED mode stamps {@code __resolved_credentials__ = { NAME: "${workflow.secrets.NAME}" }}
 * onto SIMPLE worker-tool tasks (via the enrich script), and that standalone / non-worker tools are
 * left untouched. In embedded, the host resolves the references from its secret store at poll time.
 */
class ToolCompilerWorkerCredTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @AfterEach
    void resetEmbedded() {
        new EmbeddedMode().setEmbedded(false);
    }

    private static ToolConfig worker(String name, String... creds) {
        return ToolConfig.builder()
                .name(name)
                .description(name)
                .toolType("worker")
                .config(Map.of("credentials", List.of(creds)))
                .build();
    }

    private static ToolCompiler compilerFor(AgentConfig config) {
        ToolCompiler tc = new ToolCompiler();
        tc.setWorkerCreds(AgentCompiler.collectToolCredentials(config));
        return tc;
    }

    private static String enrichScript(ToolCompiler tc, List<ToolConfig> tools) {
        Object[] r = tc.buildEnrichTask("agent", "agent_llm", tools, "");
        return (String) ((WorkflowTask) r[0]).getInputParameters().get("expression");
    }

    /** Execute the enrich script through GraalJS for one tool call; return that task's built map. */
    @SuppressWarnings("unchecked")
    private static Map<String, Object> runEnrichForTool(String script, String toolName) throws Exception {
        String wrapped = "var $ = {toolCalls: [{name: '" + toolName + "', taskReferenceName: 'call_1',"
                + " inputParameters: {}}], agentState: {}, userPrompt: 'test'};"
                + " JSON.stringify(" + script + ");";
        try (Context ctx = Context.newBuilder("js").allowAllAccess(true).build()) {
            Value v = ctx.eval("js", wrapped);
            Map<String, Object> outer = MAPPER.readValue(v.asString(), Map.class);
            List<Map<String, Object>> tasks = (List<Map<String, Object>>) outer.get("dynamicTasks");
            return tasks.stream()
                    .filter(t -> toolName.equals(t.get("name")))
                    .findFirst()
                    .orElseThrow();
        }
    }

    @Test
    void embedded_stampsPerToolSecretReference() {
        new EmbeddedMode().setEmbedded(true);
        ToolConfig gh = worker("gh", "GITHUB_TOKEN");
        AgentConfig config = AgentConfig.builder()
                .name("a")
                .model("openai/gpt-4o")
                .tools(List.of(gh))
                .build();

        String script = enrichScript(compilerFor(config), List.of(gh));

        assertThat(script).contains("\"gh\":{\"GITHUB_TOKEN\":\"${workflow.secrets.GITHUB_TOKEN}\"}");
    }

    @Test
    @SuppressWarnings("unchecked")
    void embedded_injectsResolvedCredentialsOntoSimpleTask() throws Exception {
        new EmbeddedMode().setEmbedded(true);
        ToolConfig gh = worker("gh", "GITHUB_TOKEN");
        AgentConfig config = AgentConfig.builder()
                .name("a")
                .model("openai/gpt-4o")
                .tools(List.of(gh))
                .build();

        Map<String, Object> task = runEnrichForTool(enrichScript(compilerFor(config), List.of(gh)), "gh");

        Map<String, Object> input = (Map<String, Object>) task.get("inputParameters");
        Map<String, Object> resolved = (Map<String, Object>) input.get("__resolved_credentials__");
        assertThat(resolved).containsEntry("GITHUB_TOKEN", "${workflow.secrets.GITHUB_TOKEN}");
    }

    @Test
    @SuppressWarnings("unchecked")
    void standalone_leavesWorkerTaskUntouched() throws Exception {
        new EmbeddedMode().setEmbedded(false);
        ToolConfig gh = worker("gh", "GITHUB_TOKEN");
        AgentConfig config = AgentConfig.builder()
                .name("a")
                .model("openai/gpt-4o")
                .tools(List.of(gh))
                .build();

        String script = enrichScript(compilerFor(config), List.of(gh));
        assertThat(script).doesNotContain("__resolved_credentials__\":{\"GITHUB_TOKEN");

        Map<String, Object> task = runEnrichForTool(script, "gh");
        Map<String, Object> input = (Map<String, Object>) task.get("inputParameters");
        assertThat(input).doesNotContainKey("__resolved_credentials__");
    }
}
