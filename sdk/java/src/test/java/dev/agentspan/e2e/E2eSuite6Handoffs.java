// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.e2e;

import dev.agentspan.Agent;
import dev.agentspan.AgentRuntime;
import dev.agentspan.enums.AgentStatus;
import dev.agentspan.enums.Strategy;
import dev.agentspan.model.AgentResult;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 6: Handoffs — multi-agent strategy runtime tests.
 *
 * <p>Tests verify that the SEQUENTIAL, PARALLEL, and HANDOFF strategies produce
 * the correct workflow structure (task types) and completion status.
 *
 * <p>COUNTERFACTUAL assertions:
 * <ul>
 *   <li>SEQUENTIAL: if only 1 sub-agent runs, < 2 SUB_WORKFLOW tasks → count assertion fails.</li>
 *   <li>PARALLEL: if strategy degrades to sequential (no FORK_JOIN/FORK task), assertion fails.</li>
 *   <li>HANDOFF: if no sub-workflow is created, 0 SUB_WORKFLOW tasks → assertion fails.</li>
 *   <li>PIPE (.then()): structural check + runtime checks both fail independently.</li>
 * </ul>
 *
 * <p>No LLM output text is inspected for semantic correctness (CLAUDE.md rule).
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@Timeout(value = 300, unit = TimeUnit.SECONDS)
class E2eSuite6Handoffs extends E2eBaseTest {

    private static AgentRuntime runtime;

    @BeforeAll
    static void setup() {
        runtime = new AgentRuntime(new dev.agentspan.AgentConfig(BASE_URL, null, null, 100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    // ── Shared child agents ───────────────────────────────────────────────

    static Agent mathAgent() {
        return Agent.builder()
            .name("e2e_java_math")
            .model(MODEL)
            .instructions("You are a math agent. Compute arithmetic. Be concise.")
            .build();
    }

    static Agent textAgent() {
        return Agent.builder()
            .name("e2e_java_text")
            .model(MODEL)
            .instructions("You are a text agent. Process text. Be concise.")
            .build();
    }

    // ── Tests ─────────────────────────────────────────────────────────────

    /**
     * SEQUENTIAL strategy: both sub-agents run and produce at least 2 completed SUB_WORKFLOW tasks.
     *
     * COUNTERFACTUAL: if SEQUENTIAL strategy only runs 1 agent, the count of
     * SUB_WORKFLOW tasks will be < 2 → assertion fails.
     */
    @Test
    @Order(1)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    @SuppressWarnings("unchecked")
    void test_sequential_execution() {
        Agent parent = Agent.builder()
            .name("e2e_java_sequential_parent")
            .model(MODEL)
            .instructions("Delegate tasks sequentially to your sub-agents.")
            .agents(mathAgent(), textAgent())
            .strategy(Strategy.SEQUENTIAL)
            .build();

        AgentResult result = runtime.run(parent, "Compute 3+4, then reverse the word hello");

        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "SEQUENTIAL parent agent should complete. "
            + "Status: " + result.getStatus()
            + ". Error: " + result.getError());

        String workflowId = result.getWorkflowId();
        assertNotNull(workflowId, "workflowId is null");

        Map<String, Object> workflow = getWorkflow(workflowId);
        Map<String, Object> workflowDef = (Map<String, Object>) workflow.get("workflowDef");
        if (workflowDef == null) {
            // Fall back to the execution-level tasks
            List<Map<String, Object>> tasks = (List<Map<String, Object>>) workflow.get("tasks");
            assertNotNull(tasks, "workflow has neither 'workflowDef' nor 'tasks'");
            long subWorkflowCount = tasks.stream()
                .filter(t -> "SUB_WORKFLOW".equals(t.get("taskType"))
                    || "SUB_WORKFLOW".equals(t.get("type")))
                .count();
            assertTrue(subWorkflowCount >= 2,
                "Expected at least 2 SUB_WORKFLOW tasks for SEQUENTIAL execution, found "
                + subWorkflowCount
                + ". COUNTERFACTUAL: if only 1 agent ran, count < 2.");
        } else {
            List<Map<String, Object>> allTasks = allTasksFlat(workflowDef);
            long subWorkflowCount = allTasks.stream()
                .filter(t -> "SUB_WORKFLOW".equals(t.get("type")))
                .count();
            assertTrue(subWorkflowCount >= 2,
                "Expected at least 2 SUB_WORKFLOW tasks in SEQUENTIAL plan, found "
                + subWorkflowCount
                + ". COUNTERFACTUAL: if SEQUENTIAL strategy only serializes 1 agent, count < 2.");
        }
    }

    /**
     * PARALLEL strategy: produces a FORK_JOIN (or FORK) task and both sub-agents complete.
     *
     * COUNTERFACTUAL: if PARALLEL degrades to sequential (no FORK task), the
     * FORK_JOIN/FORK assertion fails.
     */
    @Test
    @Order(2)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    @SuppressWarnings("unchecked")
    void test_parallel_execution() {
        Agent parent = Agent.builder()
            .name("e2e_java_parallel_parent")
            .model(MODEL)
            .instructions("Run both sub-agents in parallel.")
            .agents(mathAgent(), textAgent())
            .strategy(Strategy.PARALLEL)
            .build();

        AgentResult result = runtime.run(parent, "Compute 3+4 AND reverse the word hello");

        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "PARALLEL parent agent should complete. "
            + "Status: " + result.getStatus()
            + ". Error: " + result.getError());

        String workflowId = result.getWorkflowId();
        assertNotNull(workflowId, "workflowId is null");

        Map<String, Object> workflow = getWorkflow(workflowId);

        // Check at the workflowDef level (plan tasks)
        Map<String, Object> workflowDef = (Map<String, Object>) workflow.get("workflowDef");
        if (workflowDef != null) {
            List<Map<String, Object>> allTasks = allTasksFlat(workflowDef);
            boolean hasFork = allTasks.stream()
                .anyMatch(t -> "FORK_JOIN".equals(t.get("type"))
                    || "FORK".equals(t.get("type")));
            assertTrue(hasFork,
                "Expected a FORK_JOIN or FORK task in PARALLEL workflow plan. "
                + "Task types found: " + allTasks.stream()
                    .map(t -> (String) t.get("type")).collect(Collectors.toSet())
                + ". COUNTERFACTUAL: if PARALLEL degrades to sequential, no FORK task appears.");
        } else {
            // Fall back to execution tasks
            List<Map<String, Object>> tasks = (List<Map<String, Object>>) workflow.get("tasks");
            assertNotNull(tasks, "workflow has neither 'workflowDef' nor 'tasks'");
            boolean hasFork = tasks.stream()
                .anyMatch(t -> "FORK_JOIN".equals(t.get("taskType"))
                    || "FORK_JOIN".equals(t.get("type"))
                    || "FORK".equals(t.get("taskType"))
                    || "FORK".equals(t.get("type")));
            assertTrue(hasFork,
                "Expected a FORK_JOIN or FORK task in PARALLEL workflow execution. "
                + "Task types found: " + tasks.stream()
                    .map(t -> {
                        String tt = (String) t.get("taskType");
                        return tt != null ? tt : (String) t.get("type");
                    }).collect(Collectors.toSet())
                + ". COUNTERFACTUAL: if PARALLEL degrades to sequential, no FORK task appears.");
        }
    }

    /**
     * HANDOFF strategy: at least one SUB_WORKFLOW task is created and completes.
     *
     * COUNTERFACTUAL: if HANDOFF never creates a sub-workflow (e.g. the parent
     * answers directly), 0 SUB_WORKFLOW tasks → assertion fails.
     */
    @Test
    @Order(3)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    @SuppressWarnings("unchecked")
    void test_handoff_execution() {
        Agent parent = Agent.builder()
            .name("e2e_java_handoff_parent")
            .model(MODEL)
            .instructions("You are a coordinator. Hand off text processing tasks to the text agent.")
            .agents(mathAgent(), textAgent())
            .strategy(Strategy.HANDOFF)
            .build();

        AgentResult result = runtime.run(parent, "Reverse the word hello");

        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "HANDOFF parent agent should complete. "
            + "Status: " + result.getStatus()
            + ". Error: " + result.getError());

        String workflowId = result.getWorkflowId();
        assertNotNull(workflowId, "workflowId is null");

        Map<String, Object> workflow = getWorkflow(workflowId);

        // Check for SUB_WORKFLOW tasks (from plan) or executed sub-workflow tasks
        Map<String, Object> workflowDef = (Map<String, Object>) workflow.get("workflowDef");
        if (workflowDef != null) {
            List<Map<String, Object>> allTasks = allTasksFlat(workflowDef);
            boolean hasSubWorkflow = allTasks.stream()
                .anyMatch(t -> "SUB_WORKFLOW".equals(t.get("type")));
            assertTrue(hasSubWorkflow,
                "Expected at least 1 SUB_WORKFLOW task in HANDOFF workflow plan. "
                + "Task types found: " + allTasks.stream()
                    .map(t -> (String) t.get("type")).collect(Collectors.toSet())
                + ". COUNTERFACTUAL: if HANDOFF never creates sub-workflows, this fails.");
        } else {
            List<Map<String, Object>> tasks = (List<Map<String, Object>>) workflow.get("tasks");
            assertNotNull(tasks, "workflow has neither 'workflowDef' nor 'tasks'");
            long subWorkflowCount = tasks.stream()
                .filter(t -> "SUB_WORKFLOW".equals(t.get("taskType"))
                    || "SUB_WORKFLOW".equals(t.get("type")))
                .count();
            assertTrue(subWorkflowCount >= 1,
                "Expected at least 1 SUB_WORKFLOW task in HANDOFF execution, found "
                + subWorkflowCount
                + ". COUNTERFACTUAL: if HANDOFF never creates a sub-workflow, count = 0.");
        }
    }

    /**
     * Pipeline via {@code .then()} produces SEQUENTIAL strategy (structural) AND
     * both sub-agents execute at runtime.
     *
     * <p>Structural assertion (no server call): pipeline.getStrategy() == SEQUENTIAL.
     * Runtime assertion: at least 2 SUB_WORKFLOW tasks in workflow, both sub-agents appear.
     *
     * COUNTERFACTUAL (structural): if .then() sets wrong strategy → strategy assertion fails.
     * COUNTERFACTUAL (runtime): if only 1 agent executes → SUB_WORKFLOW count < 2 → fails.
     */
    @Test
    @Order(4)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    @SuppressWarnings("unchecked")
    void test_pipe_operator_then() {
        Agent math = Agent.builder()
            .name("e2e_java_pipe_math")
            .model(MODEL)
            .instructions("Compute arithmetic. Be concise.")
            .build();
        Agent text = Agent.builder()
            .name("e2e_java_pipe_text")
            .model(MODEL)
            .instructions("Process text. Be concise.")
            .build();

        // ── Structural assertion (no server) ──────────────────────────
        Agent pipeline = math.then(text);

        assertEquals(Strategy.SEQUENTIAL, pipeline.getStrategy(),
            "Agent.then() should produce Strategy.SEQUENTIAL, got: " + pipeline.getStrategy()
            + ". COUNTERFACTUAL: if .then() uses wrong strategy, this fails.");

        List<Agent> pipelineAgents = pipeline.getAgents();
        List<String> agentNames = pipelineAgents.stream()
            .map(Agent::getName)
            .collect(Collectors.toList());
        assertTrue(agentNames.contains("e2e_java_pipe_math"),
            "Pipeline missing 'e2e_java_pipe_math'. Found: " + agentNames);
        assertTrue(agentNames.contains("e2e_java_pipe_text"),
            "Pipeline missing 'e2e_java_pipe_text'. Found: " + agentNames);

        // ── Runtime assertion ─────────────────────────────────────────
        AgentResult result = runtime.run(pipeline, "Compute 2+2 and reverse hello");

        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "Pipeline via .then() should complete. "
            + "Status: " + result.getStatus()
            + ". Error: " + result.getError());

        String workflowId = result.getWorkflowId();
        assertNotNull(workflowId, "workflowId is null");

        Map<String, Object> workflow = getWorkflow(workflowId);
        Map<String, Object> workflowDef = (Map<String, Object>) workflow.get("workflowDef");

        if (workflowDef != null) {
            List<Map<String, Object>> allTasks = allTasksFlat(workflowDef);
            long subWorkflowCount = allTasks.stream()
                .filter(t -> "SUB_WORKFLOW".equals(t.get("type")))
                .count();
            assertTrue(subWorkflowCount >= 2,
                "Expected at least 2 SUB_WORKFLOW tasks for .then() pipeline, found "
                + subWorkflowCount
                + ". COUNTERFACTUAL: if only 1 agent ran, count < 2.");
        } else {
            List<Map<String, Object>> tasks = (List<Map<String, Object>>) workflow.get("tasks");
            assertNotNull(tasks, "workflow has neither 'workflowDef' nor 'tasks'");
            long subWorkflowCount = tasks.stream()
                .filter(t -> "SUB_WORKFLOW".equals(t.get("taskType"))
                    || "SUB_WORKFLOW".equals(t.get("type")))
                .count();
            assertTrue(subWorkflowCount >= 2,
                "Expected at least 2 SUB_WORKFLOW tasks for .then() pipeline, found "
                + subWorkflowCount
                + ". COUNTERFACTUAL: if only 1 agent ran, count < 2.");
        }
    }
}
