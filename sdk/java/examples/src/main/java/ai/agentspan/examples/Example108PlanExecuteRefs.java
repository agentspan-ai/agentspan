// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.AgentConfig;
import ai.agentspan.AgentRuntime;
import ai.agentspan.enums.Strategy;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.ToolDef;
import ai.agentspan.plans.Op;
import ai.agentspan.plans.Plan;
import ai.agentspan.plans.Ref;
import ai.agentspan.plans.Step;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * 108 — Plan-Execute with cross-step output piping via {@link Ref}.
 *
 * <p>The {@code new Ref("step_id")} helper wires the whole output of an
 * upstream step into a downstream step's args. No JSON path, no field
 * selection, no internal task-ref naming to memorise — one expression
 * and the runtime substitutes the value at execution time.
 *
 * <p>This example runs three steps:
 * <pre>{@code
 *     produce → enrich → report
 * }</pre>
 * {@code produce} emits a record dict, {@code enrich} adds a derived field
 * via {@code Ref("produce")}, and {@code report} reads {@code Ref("enrich")}
 * to format a final summary. The plan is fully deterministic — no planner
 * LLM required — because we pass it directly to {@code runtime.run}.
 *
 * <p>Run: {@code ./gradlew :examples:run -PmainClass=ai.agentspan.examples.Example108PlanExecuteRefs}
 */
public class Example108PlanExecuteRefs {

    private static final String MODEL =
        System.getenv().getOrDefault("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini");
    private static final String BASE_URL =
        System.getenv().getOrDefault("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
            .replace("/api", "");

    public static void main(String[] args) throws Exception {
        ToolDef produce = ToolDef.builder()
            .name("produce")
            .description("Return a fixed payload.")
            .inputSchema(Map.of(
                "type", "object",
                "properties", Map.of("record_id", Map.of("type", "string")),
                "required", List.of("record_id")))
            .toolType("worker")
            .func(input -> Map.of(
                "record_id", input.get("record_id"),
                "value", 42,
                "tags", List.of("alpha", "beta")))
            .build();

        ToolDef enrich = ToolDef.builder()
            .name("enrich")
            .description("Append a derived field. Reads the whole `produce` output via Ref.")
            .inputSchema(Map.of(
                "type", "object",
                "properties", Map.of("record", Map.of("type", "object")),
                "required", List.of("record")))
            .toolType("worker")
            .func(input -> {
                @SuppressWarnings("unchecked")
                Map<String, Object> record = (Map<String, Object>) input.get("record");
                Map<String, Object> out = new LinkedHashMap<>(record);
                int value = ((Number) record.getOrDefault("value", 0)).intValue();
                out.put("value_squared", value * value);
                return out;
            })
            .build();

        ToolDef report = ToolDef.builder()
            .name("report")
            .description("Format the final report. Reads BOTH upstream steps via Refs.")
            .inputSchema(Map.of(
                "type", "object",
                "properties", Map.of(
                    "record", Map.of("type", "object"),
                    "enriched", Map.of("type", "object")),
                "required", List.of("record", "enriched")))
            .toolType("worker")
            .func(input -> {
                @SuppressWarnings("unchecked")
                Map<String, Object> record = (Map<String, Object>) input.get("record");
                @SuppressWarnings("unchecked")
                Map<String, Object> enriched = (Map<String, Object>) input.get("enriched");
                @SuppressWarnings("unchecked")
                List<Object> tags = (List<Object>) record.get("tags");
                Map<String, Object> out = new LinkedHashMap<>();
                out.put("id", record.get("record_id"));
                out.put("original_value", record.get("value"));
                out.put("squared", enriched.get("value_squared"));
                out.put("tags_joined", String.join(
                    ", ", tags.stream().map(Object::toString).toList()));
                out.put(
                    "summary",
                    "record=" + record.get("record_id")
                        + " value=" + record.get("value")
                        + " squared=" + enriched.get("value_squared")
                        + " tags=" + tags);
                return out;
            })
            .build();

        Agent planner = Agent.builder()
            .name("ref_demo_planner")
            .model(MODEL)
            .instructions("(planner unused; static plan supplied)")
            .build();

        Agent harness = Agent.builder()
            .name("ref_demo")
            .model(MODEL)
            .strategy(Strategy.PLAN_EXECUTE)
            .planner(planner)
            .tools(List.of(produce, enrich, report))
            .build();

        // Typed plan — no JSON strings, no field selectors. Each Ref serialises
        // to {"$ref":"<step_id>"} which the server rewrites to the right
        // Conductor template at compile time.
        Plan plan = Plan.builder()
            .step(Step.builder("produce")
                .operation(Op.builder("produce")
                    .args(Map.of("record_id", "r-001"))
                    .build())
                .build())
            .step(Step.builder("enrich")
                .dependsOn("produce")
                .operation(Op.builder("enrich")
                    .args(Map.of("record", new Ref("produce")))
                    .build())
                .build())
            .step(Step.builder("report")
                .dependsOn("produce", "enrich")
                .operation(Op.builder("report")
                    .args(Map.of(
                        "record", new Ref("produce"),
                        "enriched", new Ref("enrich")))
                    .build())
                .build())
            .build();

        try (AgentRuntime runtime = new AgentRuntime(
                new AgentConfig(BASE_URL + "/api", null, null, 100, 1))) {
            AgentResult result = runtime.run(harness, "demo", plan);
            System.out.println("status=" + result.getStatus()
                + " executionId=" + result.getExecutionId());
            showPipelineOutputs(result.getExecutionId());
        }
    }

    @SuppressWarnings("unchecked")
    private static void showPipelineOutputs(String executionId) throws Exception {
        HttpClient http = HttpClient.newHttpClient();
        ObjectMapper mapper = new ObjectMapper();

        Map<String, Object> parent = fetchWorkflow(http, mapper, executionId);
        String subId = null;
        for (Map<String, Object> t : (List<Map<String, Object>>) parent.getOrDefault("tasks", List.of())) {
            String ref = String.valueOf(t.getOrDefault("referenceTaskName", ""));
            if (ref.endsWith("_plan_exec")) {
                Map<String, Object> out = (Map<String, Object>) t.get("outputData");
                subId = out == null ? null : (String) out.get("subWorkflowId");
                break;
            }
        }
        if (subId == null) return;

        Map<String, Object> sub = fetchWorkflow(http, mapper, subId);
        System.out.println("\n── pipeline trace (Ref data flow) ────────────────────────");
        for (Map<String, Object> t : (List<Map<String, Object>>) sub.getOrDefault("tasks", List.of())) {
            String name = String.valueOf(t.get("taskDefName"));
            if (name.equals("produce") || name.equals("enrich") || name.equals("report")) {
                System.out.println("\n" + name + ":");
                System.out.println(
                    mapper.writerWithDefaultPrettyPrinter().writeValueAsString(t.get("outputData")));
            }
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> fetchWorkflow(
            HttpClient http, ObjectMapper mapper, String id) throws Exception {
        HttpResponse<String> resp = http.send(
            HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/api/workflow/" + id + "?includeTasks=true"))
                .GET()
                .build(),
            HttpResponse.BodyHandlers.ofString());
        return mapper.readValue(resp.body(), Map.class);
    }
}
