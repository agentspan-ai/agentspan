/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.model;

import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Request DTO for POST /api/agent/start.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class StartRequest {

    private AgentConfig agentConfig;
    private String prompt;
    private String sessionId;
    private List<String> media;
    private Map<String, Object> context;
    private String idempotencyKey;
    private List<String> credentials;

    /** Framework identifier for foreign agents (e.g. "openai", "google_adk"). Null for native agents. */
    private String framework;

    /** Raw framework-specific agent config. Used when {@code framework} is non-null. */
    private Map<String, Object> rawConfig;

    /** Per-call timeout override (seconds). Applied server-side to the workflow definition. */
    private Integer timeoutSeconds;

    /**
     * Per-execution isolation key for stateful agents.
     *
     * <p>When set, the server maps every worker tool task to this domain via
     * {@code taskToDomain} in the {@link StartWorkflowRequest}.  The Python SDK
     * registers the corresponding workers under the same domain so that Conductor
     * routes tasks exclusively to the workers that belong to this execution,
     * preventing cross-instance reply mixing when multiple concurrent instances of
     * the same agent script are running.
     */
    private String runId;

    /**
     * Optional deterministic plan for {@code Strategy.PLAN_EXECUTE} harnesses.
     * The SDK forwards a user-supplied {@code Plan}/dict here; the server
     * stuffs it into {@code workflow.input.static_plan} so PAC's extract_json
     * INLINE picks it up as Case-0 (highest priority) and discards whatever
     * the planner LLM emitted. Lets callers replay a recorded plan or run a
     * fully deterministic pipeline without an LLM planner.
     */
    @com.fasterxml.jackson.annotation.JsonProperty("static_plan")
    private Map<String, Object> staticPlan;
}
