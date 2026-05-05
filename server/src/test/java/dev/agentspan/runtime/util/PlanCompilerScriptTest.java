/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.util;

import static org.assertj.core.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.Value;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.*;

class PlanCompilerScriptTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private Context graalCtx;

    @BeforeEach
    void setUp() {
        graalCtx = Context.newBuilder("js").allowAllAccess(true).build();
    }

    @AfterEach
    void tearDown() {
        graalCtx.close();
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> compilePlan(String planJson) throws Exception {
        String script = JavaScriptBuilder.compilePlanToWorkflowScript();
        String wrappedScript = "var $ = {"
                + "planJson: " + MAPPER.writeValueAsString(planJson) + ","
                + "parentName: 'test_harness',"
                + "model: 'openai/gpt-4o-mini'"
                + "}; var __result = " + script + ";";
        graalCtx.eval("js", wrappedScript);
        Value resultVal = graalCtx.eval("js", "__result");
        String resultJson = resultVal.getMember("workflow_def").asString();
        assertThat(resultJson).as("workflow_def should be non-null").isNotNull();
        List<Map<String, Object>> wfList = MAPPER.readValue(resultJson,
                MAPPER.getTypeFactory().constructCollectionType(List.class, Map.class));
        return wfList.get(0);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> allTasks(Map<String, Object> wf) {
        List<Map<String, Object>> all = new ArrayList<>();
        collectTasks((List<Map<String, Object>>) wf.get("tasks"), all);
        return all;
    }

    @SuppressWarnings("unchecked")
    private void collectTasks(List<Map<String, Object>> tasks, List<Map<String, Object>> out) {
        if (tasks == null) return;
        for (var t : tasks) {
            out.add(t);
            if ("FORK_JOIN".equals(t.get("type"))) {
                var forkTasks = (List<List<Map<String, Object>>>) t.get("forkTasks");
                if (forkTasks != null) forkTasks.forEach(branch -> collectTasks(branch, out));
            }
        }
    }

    @Test
    void testSuccessConditionProducesEvalInlineTask() throws Exception {
        String planJson = """
                {
                  "steps": [{"id": "s1", "parallel": false, "operations": [
                    {"tool": "run_cmd", "args": {"command": "echo hello"}}
                  ]}],
                  "validation": [{"tool": "run_tests", "success_condition": "$.exit_code === 0"}]
                }""";

        Map<String, Object> wf = compilePlan(planJson);
        List<Map<String, Object>> tasks = allTasks(wf);

        boolean hasEvalTask = tasks.stream()
                .filter(t -> "INLINE".equals(t.get("type")))
                .anyMatch(t -> {
                    @SuppressWarnings("unchecked")
                    var inputs = (Map<String, Object>) t.get("inputParameters");
                    if (inputs == null) return false;
                    String expr = String.valueOf(inputs.getOrDefault("expression", ""));
                    return expr.contains("exit_code") && expr.contains("passed");
                });
        assertThat(hasEvalTask)
                .as("Expected an INLINE task evaluating success_condition '$.exit_code === 0'")
                .isTrue();

        // Verify the INLINE eval task's toolOut input parameter references the SIMPLE validation task's output
        Map<String, Object> valSimpleTask = tasks.stream()
                .filter(t -> "SIMPLE".equals(t.get("type")) && "run_tests".equals(t.get("name")))
                .findFirst()
                .orElseThrow(() -> new AssertionError("No SIMPLE validation task found for run_tests"));

        String simpleRef = (String) valSimpleTask.get("taskReferenceName");

        Map<String, Object> evalTask = tasks.stream()
                .filter(t -> "INLINE".equals(t.get("type")))
                .filter(t -> {
                    @SuppressWarnings("unchecked")
                    var inp = (Map<String, Object>) t.get("inputParameters");
                    if (inp == null) return false;
                    String expr = String.valueOf(inp.getOrDefault("expression", ""));
                    return expr.contains("exit_code") && expr.contains("passed");
                })
                .findFirst()
                .orElseThrow(() -> new AssertionError("No INLINE eval task with success_condition found"));

        @SuppressWarnings("unchecked")
        Map<String, Object> evalInputs = (Map<String, Object>) evalTask.get("inputParameters");
        String toolOutRef = (String) evalInputs.get("toolOut");
        assertThat(toolOutRef)
                .as("INLINE eval task's toolOut must reference the SIMPLE validation task output")
                .contains(simpleRef)
                .contains(".output.result");
    }

    @Test
    void testNoSuccessConditionUsesDefaultPassCheck() throws Exception {
        String planJson = """
                {
                  "steps": [{"id": "s1", "parallel": false, "operations": [
                    {"tool": "noop", "args": {}}
                  ]}],
                  "validation": [{"tool": "check_file"}]
                }""";

        Map<String, Object> wf = compilePlan(planJson);
        List<Map<String, Object>> tasks = allTasks(wf);

        boolean hasDefaultEvalTask = tasks.stream()
                .filter(t -> "INLINE".equals(t.get("type")))
                .anyMatch(t -> {
                    @SuppressWarnings("unchecked")
                    var inputs = (Map<String, Object>) t.get("inputParameters");
                    if (inputs == null) return false;
                    String expr = String.valueOf(inputs.getOrDefault("expression", ""));
                    return expr.contains("passed");
                });
        assertThat(hasDefaultEvalTask)
                .as("Expected an INLINE eval task wrapping the validation SIMPLE task even without success_condition")
                .isTrue();
    }

    @Test
    void testMultipleValidationsUseForkJoin() throws Exception {
        String planJson = """
                {
                  "steps": [{"id": "s1", "parallel": false, "operations": [
                    {"tool": "noop", "args": {}}
                  ]}],
                  "validation": [
                    {"tool": "lint", "success_condition": "$.passed === true"},
                    {"tool": "run_tests", "success_condition": "$.exit_code === 0"}
                  ]
                }""";

        Map<String, Object> wf = compilePlan(planJson);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> topTasks = (List<Map<String, Object>>) wf.get("tasks");

        boolean hasForkJoin = topTasks.stream().anyMatch(t -> "FORK_JOIN".equals(t.get("type")));
        assertThat(hasForkJoin).as("Multiple validations should compile to a FORK_JOIN").isTrue();

        @SuppressWarnings("unchecked")
        Map<String, Object> forkTask = topTasks.stream()
                .filter(t -> "FORK_JOIN".equals(t.get("type")))
                .findFirst().orElseThrow();
        @SuppressWarnings("unchecked")
        var forkTasks = (List<List<Map<String, Object>>>) forkTask.get("forkTasks");
        assertThat(forkTasks).hasSize(2);

        // Each branch must be [SIMPLE, INLINE] — the tool task + eval task
        assertThat(forkTasks.get(0)).hasSize(2);
        assertThat(forkTasks.get(1)).hasSize(2);

        // First task in each branch should be SIMPLE (tool call)
        Map<String, Object> branch0task0 = forkTasks.get(0).get(0);
        Map<String, Object> branch0task1 = forkTasks.get(0).get(1);
        assertThat(branch0task0.get("type")).isEqualTo("SIMPLE");
        assertThat(branch0task1.get("type")).isEqualTo("INLINE");

        Map<String, Object> branch1task0 = forkTasks.get(1).get(0);
        Map<String, Object> branch1task1 = forkTasks.get(1).get(1);
        assertThat(branch1task0.get("type")).isEqualTo("SIMPLE");
        assertThat(branch1task1.get("type")).isEqualTo("INLINE");
    }

    @Test
    void testSingleValidationDoesNotUseForkJoin() throws Exception {
        String planJson = """
                {
                  "steps": [{"id": "s1", "parallel": false, "operations": [
                    {"tool": "noop", "args": {}}
                  ]}],
                  "validation": [{"tool": "run_tests", "success_condition": "$.exit_code === 0"}]
                }""";

        Map<String, Object> wf = compilePlan(planJson);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> topTasks = (List<Map<String, Object>>) wf.get("tasks");

        boolean hasForkJoin = topTasks.stream().anyMatch(t -> "FORK_JOIN".equals(t.get("type")));
        assertThat(hasForkJoin).as("Single validation should NOT use FORK_JOIN").isFalse();
    }
}
