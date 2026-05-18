/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.compiler;

import static org.assertj.core.api.Assertions.*;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

import com.netflix.conductor.common.metadata.workflow.WorkflowTask;

import dev.agentspan.runtime.model.GuardrailConfig;
import dev.agentspan.runtime.model.ToolConfig;

class ToolCompilerTest {

    @Test
    void testCompileToolSpecs_Worker() {
        ToolConfig tool = ToolConfig.builder()
                .name("search")
                .description("Search the web")
                .inputSchema(Map.of("type", "object"))
                .toolType("worker")
                .build();

        ToolCompiler tc = new ToolCompiler();
        List<Map<String, Object>> specs = tc.compileToolSpecs(List.of(tool));

        assertThat(specs).hasSize(1);
        assertThat(specs.get(0).get("name")).isEqualTo("search");
        assertThat(specs.get(0).get("type")).isEqualTo("SIMPLE");
    }

    @Test
    void testCompileToolSpecs_Http() {
        ToolConfig tool = ToolConfig.builder()
                .name("weather_api")
                .description("Get weather")
                .toolType("http")
                .config(Map.of("url", "https://api.weather.com", "method", "GET"))
                .build();

        ToolCompiler tc = new ToolCompiler();
        List<Map<String, Object>> specs = tc.compileToolSpecs(List.of(tool));

        assertThat(specs.get(0).get("type")).isEqualTo("HTTP");
    }

    @Test
    void testCompileToolSpecs_Mcp() {
        ToolConfig tool = ToolConfig.builder()
                .name("mcp_tool")
                .description("MCP tool")
                .toolType("mcp")
                .config(Map.of("server_url", "http://mcp.example.com", "headers", Map.of("auth", "key")))
                .build();

        ToolCompiler tc = new ToolCompiler();
        List<Map<String, Object>> specs = tc.compileToolSpecs(List.of(tool));

        assertThat(specs.get(0).get("type")).isEqualTo("CALL_MCP_TOOL");
        @SuppressWarnings("unchecked")
        Map<String, Object> configParams = (Map<String, Object>) specs.get(0).get("configParams");
        assertThat(configParams.get("mcpServer")).isEqualTo("http://mcp.example.com");
    }

    @Test
    void testBuildToolCallRouting() {
        ToolCompiler tc = new ToolCompiler();
        WorkflowTask router = tc.buildToolCallRouting("agent", "agent_llm", null, false, "");

        assertThat(router.getType()).isEqualTo("SWITCH");
        assertThat(router.getTaskReferenceName()).isEqualTo("agent_tool_router");
        assertThat(router.getDecisionCases()).containsKey("tool_call");
    }

    @Test
    void testBuildDynamicFork() {
        ToolCompiler tc = new ToolCompiler();
        WorkflowTask fork = tc.buildDynamicFork("agent", "${ref}", "");

        assertThat(fork.getType()).isEqualTo("FORK_JOIN_DYNAMIC");
        assertThat(fork.getDynamicForkTasksParam()).isEqualTo("dynamicTasks");
    }

    @Test
    void testCompileToolSpecs_AgentTool() {
        ToolConfig tool = ToolConfig.builder()
                .name("research_agent")
                .description("Invoke the research agent")
                .toolType("agent_tool")
                .inputSchema(Map.of(
                        "type", "object",
                        "properties", Map.of("request", Map.of("type", "string")),
                        "required", List.of("request")))
                .config(Map.of("workflowName", "research_agent_wf"))
                .build();

        ToolCompiler tc = new ToolCompiler();
        List<Map<String, Object>> specs = tc.compileToolSpecs(List.of(tool));

        assertThat(specs).hasSize(1);
        assertThat(specs.get(0).get("name")).isEqualTo("research_agent");
        assertThat(specs.get(0).get("type")).isEqualTo("SUB_WORKFLOW");
    }

    @Test
    void testApprovalRejectionUsesCompletedStatus() {
        ToolConfig tool = ToolConfig.builder()
                .name("send_email")
                .description("Send an email")
                .inputSchema(Map.of("type", "object"))
                .toolType("worker")
                .approvalRequired(true)
                .build();

        ToolCompiler tc = new ToolCompiler();
        WorkflowTask router = tc.buildToolCallRouting("agent", "agent_llm", List.of(tool), true, "openai/gpt-4o");

        // Navigate into the tool_call case -> approval routing
        List<WorkflowTask> toolCallTasks = router.getDecisionCases().get("tool_call");
        assertThat(toolCallTasks).isNotEmpty();

        // Find the TERMINATE task for rejection (search recursively through the task tree)
        WorkflowTask terminateTask = findTaskByRef(toolCallTasks, "agent_approval_reject");
        assertThat(terminateTask).isNotNull();
        assertThat(terminateTask.getType()).isEqualTo("TERMINATE");
        assertThat(terminateTask.getInputParameters().get("terminationStatus")).isEqualTo("COMPLETED");

        // Find the SET_VARIABLE task for rejection output
        WorkflowTask setVarTask = findTaskByRef(toolCallTasks, "agent_approval_reject_output");
        assertThat(setVarTask).isNotNull();
        assertThat(setVarTask.getType()).isEqualTo("SET_VARIABLE");
        assertThat(setVarTask.getInputParameters().get("finishReason")).isEqualTo("rejected");
    }

    /** Recursively find a task whose reference name exactly matches. */
    private WorkflowTask findTaskByRef(List<WorkflowTask> tasks, String refName) {
        for (WorkflowTask t : tasks) {
            if (refName.equals(t.getTaskReferenceName())) {
                return t;
            }
            // Check decision cases
            if (t.getDecisionCases() != null) {
                for (List<WorkflowTask> caseTasks : t.getDecisionCases().values()) {
                    WorkflowTask found = findTaskByRef(caseTasks, refName);
                    if (found != null) return found;
                }
            }
            // Check default case
            if (t.getDefaultCase() != null) {
                WorkflowTask found = findTaskByRef(t.getDefaultCase(), refName);
                if (found != null) return found;
            }
            // Check loop body
            if (t.getLoopOver() != null) {
                WorkflowTask found = findTaskByRef(t.getLoopOver(), refName);
                if (found != null) return found;
            }
        }
        return null;
    }

    @Test
    void testBuildEnrichTask_AgentTool() {
        ToolConfig agentTool = ToolConfig.builder()
                .name("researcher")
                .toolType("agent_tool")
                .config(Map.of("workflowName", "researcher_agent_wf"))
                .build();

        ToolCompiler tc = new ToolCompiler();
        Object[] result = tc.buildEnrichTask("agent", "agent_llm", List.of(agentTool), "");

        WorkflowTask enrichTask = (WorkflowTask) result[0];
        assertThat(enrichTask.getType()).isEqualTo("INLINE");

        // The enrichment script should contain the agentToolCfg with the workflow name
        String script = (String) enrichTask.getInputParameters().get("expression");
        assertThat(script).contains("agentToolCfg");
        assertThat(script).contains("researcher_agent_wf");
        assertThat(script).contains("SUB_WORKFLOW");
    }

    @Test
    void testBuildEnrichTask_AgentToolWithRetryConfig() {
        ToolConfig agentTool = ToolConfig.builder()
                .name("researcher")
                .toolType("agent_tool")
                .config(Map.of(
                        "workflowName",
                        "researcher_agent_wf",
                        "retryCount",
                        5,
                        "retryDelaySeconds",
                        10,
                        "optional",
                        false))
                .build();

        ToolCompiler tc = new ToolCompiler();
        Object[] result = tc.buildEnrichTask("agent", "agent_llm", List.of(agentTool), "");

        WorkflowTask enrichTask = (WorkflowTask) result[0];
        String script = (String) enrichTask.getInputParameters().get("expression");

        // The enrichment script should contain the retry overrides baked into agentToolCfg
        assertThat(script).contains("\"retryCount\":5");
        assertThat(script).contains("\"retryDelaySeconds\":10");
        assertThat(script).contains("\"optional\":false");
    }

    // ── Tool-level guardrail tests ──────────────────────────────────────

    @Test
    void testBuildToolCallRoutingWithResult_hasGuardrails() {
        GuardrailConfig guard = GuardrailConfig.builder()
                .name("no_dangerous_cmds")
                .guardrailType("regex")
                .position("input")
                .onFail("raise")
                .patterns(List.of("rm\\s+-rf"))
                .mode("block")
                .build();

        ToolConfig tool = ToolConfig.builder()
                .name("run_command")
                .description("Run a CLI command")
                .inputSchema(Map.of("type", "object"))
                .toolType("worker")
                .guardrails(List.of(guard))
                .build();

        ToolCompiler tc = new ToolCompiler();
        ToolCompiler.ToolCallRoutingResult result =
                tc.buildToolCallRoutingWithResult("agent", "agent_llm", List.of(tool), false, "openai/gpt-4o");

        // Should have a router task
        assertThat(result.getRouterTask().getType()).isEqualTo("SWITCH");

        // Should have guardrail refs
        assertThat(result.getToolGuardrailRefs()).hasSize(1);
        assertThat(result.getToolGuardrailRetryRefs()).hasSize(1);

        // tool_call case should contain format + guardrail tasks before fork chain
        List<WorkflowTask> toolCallTasks =
                result.getRouterTask().getDecisionCases().get("tool_call");
        assertThat(toolCallTasks).isNotEmpty();

        // First task should be the format_tool_calls INLINE
        assertThat(toolCallTasks.get(0).getTaskReferenceName()).isEqualTo("agent_format_tool_calls");
        assertThat(toolCallTasks.get(0).getType()).isEqualTo("INLINE");
    }

    @Test
    void testBuildToolCallRoutingWithResult_noGuardrails() {
        ToolConfig tool = ToolConfig.builder()
                .name("search")
                .description("Search")
                .inputSchema(Map.of("type", "object"))
                .toolType("worker")
                .build();

        ToolCompiler tc = new ToolCompiler();
        ToolCompiler.ToolCallRoutingResult result =
                tc.buildToolCallRoutingWithResult("agent", "agent_llm", List.of(tool), false, "");

        // No guardrails -> empty refs
        assertThat(result.getToolGuardrailRefs()).isEmpty();
        assertThat(result.getToolGuardrailRetryRefs()).isEmpty();

        // tool_call case should start with enrich (not format_tool_calls)
        List<WorkflowTask> toolCallTasks =
                result.getRouterTask().getDecisionCases().get("tool_call");
        assertThat(toolCallTasks.get(0).getTaskReferenceName()).contains("enrich_tools");
    }

    @Test
    void testBuildToolCallRoutingWithResult_guardrailsBeforeApproval() {
        GuardrailConfig guard = GuardrailConfig.builder()
                .name("block_sudo")
                .guardrailType("regex")
                .position("input")
                .onFail("raise")
                .patterns(List.of("sudo"))
                .mode("block")
                .build();

        ToolConfig guardedTool = ToolConfig.builder()
                .name("run_command")
                .description("Run a CLI command")
                .inputSchema(Map.of("type", "object"))
                .toolType("worker")
                .guardrails(List.of(guard))
                .approvalRequired(true)
                .build();

        ToolCompiler tc = new ToolCompiler();
        ToolCompiler.ToolCallRoutingResult result =
                tc.buildToolCallRoutingWithResult("agent", "agent_llm", List.of(guardedTool), true, "openai/gpt-4o");

        List<WorkflowTask> toolCallTasks =
                result.getRouterTask().getDecisionCases().get("tool_call");

        // First task: format_tool_calls (guardrails come first)
        assertThat(toolCallTasks.get(0).getTaskReferenceName()).isEqualTo("agent_format_tool_calls");

        // Approval tasks should come after guardrail tasks
        WorkflowTask checkApproval = findTaskByRef(toolCallTasks, "agent_check_approval");
        assertThat(checkApproval).isNotNull();

        // Verify guardrail refs are populated
        assertThat(result.getToolGuardrailRefs()).hasSize(1);
    }

    @Test
    void testBuildToolCallRoutingWithResult_backwardCompatible() {
        // Existing buildToolCallRouting should still work (returns just the task)
        ToolConfig tool = ToolConfig.builder()
                .name("search")
                .description("Search")
                .inputSchema(Map.of("type", "object"))
                .toolType("worker")
                .build();

        ToolCompiler tc = new ToolCompiler();
        WorkflowTask router = tc.buildToolCallRouting("agent", "agent_llm", List.of(tool), false, "");

        assertThat(router.getType()).isEqualTo("SWITCH");
        assertThat(router.getDecisionCases()).containsKey("tool_call");
    }
}
