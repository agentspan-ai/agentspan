/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.compiler;

import static org.assertj.core.api.Assertions.*;

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
 * Verifies that EMBEDDED mode stamps {@code __resolved_credentials__} secret references into the
 * enrich script's {@code workerCredCfg} for SIMPLE worker tools, and that standalone / non-worker
 * tools are left untouched.
 */
class ToolCompilerWorkerCredTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @AfterEach
    void resetEmbedded() {
        new EmbeddedMode().setEmbedded(false);
    }

    /**
     * Run the enrich script through GraalJS for a single tool call and return the built task map.
     * This exercises the SIMPLE-block injection itself — not just the {@code workerCredCfg} literal.
     */
    @SuppressWarnings("unchecked")
    private static Map<String, Object> runEnrichForTool(String script, String toolName) throws Exception {
        String wrapped = "var $ = {toolCalls: [{name: '" + toolName + "', taskReferenceName: 'call_1',"
                + " inputParameters: {}}], agentState: {}, userPrompt: 'test'};"
                + " JSON.stringify(" + script + ");";
        try (Context ctx = Context.newBuilder("js").allowAllAccess(true).build()) {
            Value v = ctx.eval("js", wrapped);
            Map<String, Object> outer = MAPPER.readValue(v.asString(), Map.class);
            List<Map<String, Object>> tasks = (List<Map<String, Object>>) outer.get("dynamicTasks");
            return tasks.stream().filter(t -> toolName.equals(t.get("name"))).findFirst().orElseThrow();
        }
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

    private static String enrichScriptDynamic(ToolCompiler tc, List<ToolConfig> tools) {
        Object[] r = tc.buildEnrichTaskDynamic("agent", "agent_llm", tools, "", "${prep.output.mcpConfig}", null);
        return (String) ((WorkflowTask) r[0]).getInputParameters().get("expression");
    }

    private static ToolConfig worker(String name, String... creds) {
        return ToolConfig.builder()
                .name(name)
                .description(name)
                .toolType("worker")
                .config(Map.of("credentials", List.of(creds)))
                .build();
    }

    @Test
    void embedded_stampsPerToolSecretReferences() {
        new EmbeddedMode().setEmbedded(true);
        ToolConfig gh = worker("gh", "GITHUB_TOKEN");
        ToolConfig sl = worker("sl", "SLACK_TOKEN");
        AgentConfig config = AgentConfig.builder().name("a").model("openai/gpt-4o").tools(List.of(gh, sl)).build();

        String script = enrichScript(compilerFor(config), List.of(gh, sl));

        assertThat(script).contains("\"gh\":{\"GITHUB_TOKEN\":\"${workflow.secrets.GITHUB_TOKEN}\"}");
        assertThat(script).contains("\"sl\":{\"SLACK_TOKEN\":\"${workflow.secrets.SLACK_TOKEN}\"}");
        // Per-tool, NOT a union: gh's entry must not also carry SLACK_TOKEN.
        assertThat(script).doesNotContain("\"GITHUB_TOKEN\":\"${workflow.secrets.GITHUB_TOKEN}\",\"SLACK_TOKEN\"");
    }

    @Test
    void notEmbedded_stampsEmptyConfig() {
        new EmbeddedMode().setEmbedded(false);
        ToolConfig gh = worker("gh", "GITHUB_TOKEN");
        AgentConfig config = AgentConfig.builder().name("a").model("openai/gpt-4o").tools(List.of(gh)).build();

        String script = enrichScript(compilerFor(config), List.of(gh));

        assertThat(script).contains("var workerCredCfg = {};");
        assertThat(script).doesNotContain("workflow.secrets.GITHUB_TOKEN");
    }

    @Test
    void embedded_excludesHttpTool() {
        new EmbeddedMode().setEmbedded(true);
        // An HTTP tool's secrets travel as ${workflow.secrets.NAME} headers, NOT __resolved_credentials__.
        ToolConfig http = ToolConfig.builder()
                .name("api_call")
                .description("api")
                .toolType("http")
                .config(Map.of("url", "https://x", "credentials", List.of("HTTP_TOKEN")))
                .build();
        AgentConfig config = AgentConfig.builder().name("a").model("openai/gpt-4o").tools(List.of(http)).build();

        String script = enrichScript(compilerFor(config), List.of(http));

        assertThat(script).contains("var workerCredCfg = {};");
        assertThat(script).doesNotContain("workflow.secrets.HTTP_TOKEN");
    }

    @Test
    void embedded_appliesAgentLevelCredentialFallback() {
        new EmbeddedMode().setEmbedded(true);
        // The tool declares no own credentials → it inherits the agent-level credentials.
        ToolConfig tool = worker("lookup"); // no own creds
        AgentConfig config = AgentConfig.builder()
                .name("a")
                .model("openai/gpt-4o")
                .credentials(List.of("AGENT_TOKEN"))
                .tools(List.of(tool))
                .build();

        String script = enrichScript(compilerFor(config), List.of(tool));

        assertThat(script).contains("\"lookup\":{\"AGENT_TOKEN\":\"${workflow.secrets.AGENT_TOKEN}\"}");
    }

    @Test
    @SuppressWarnings("unchecked")
    void embedded_injectsResolvedCredentialsOntoSimpleTask() throws Exception {
        // Behavioral: execute the enrich script and assert the built SIMPLE task actually carries
        // __resolved_credentials__ (proves the SIMPLE-block injection, not just the config literal).
        new EmbeddedMode().setEmbedded(true);
        ToolConfig gh = worker("gh", "GITHUB_TOKEN");
        AgentConfig config = AgentConfig.builder().name("a").model("openai/gpt-4o").tools(List.of(gh)).build();

        Map<String, Object> task = runEnrichForTool(enrichScript(compilerFor(config), List.of(gh)), "gh");

        assertThat(task.get("type")).isEqualTo("SIMPLE");
        Map<String, Object> input = (Map<String, Object>) task.get("inputParameters");
        Map<String, Object> resolved = (Map<String, Object>) input.get("__resolved_credentials__");
        assertThat(resolved).containsEntry("GITHUB_TOKEN", "${workflow.secrets.GITHUB_TOKEN}");
    }

    @Test
    @SuppressWarnings("unchecked")
    void notEmbedded_noResolvedCredentialsOnSimpleTask() throws Exception {
        new EmbeddedMode().setEmbedded(false);
        ToolConfig gh = worker("gh", "GITHUB_TOKEN");
        AgentConfig config = AgentConfig.builder().name("a").model("openai/gpt-4o").tools(List.of(gh)).build();

        Map<String, Object> task = runEnrichForTool(enrichScript(compilerFor(config), List.of(gh)), "gh");

        Map<String, Object> input = (Map<String, Object>) task.get("inputParameters");
        assertThat(input).doesNotContainKey("__resolved_credentials__");
    }

    @Test
    void embedded_stampsInDynamicEnrichVariant() {
        new EmbeddedMode().setEmbedded(true);
        ToolConfig gh = worker("gh", "GITHUB_TOKEN");
        AgentConfig config = AgentConfig.builder().name("a").model("openai/gpt-4o").tools(List.of(gh)).build();

        String script = enrichScriptDynamic(compilerFor(config), List.of(gh));

        assertThat(script).contains("\"gh\":{\"GITHUB_TOKEN\":\"${workflow.secrets.GITHUB_TOKEN}\"}");
    }
}
