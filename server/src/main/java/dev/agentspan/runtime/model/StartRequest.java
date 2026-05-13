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
     * Working directory injected into {@code workflow.input.cwd}.
     *
     * <p>Filesystem-bound tools (read_file, run_command, etc.) read this from the
     * compiled plan via {@code ${workflow.input.cwd}}. Without it the input is
     * null and tools resolve paths against the worker's CWD — usually wrong.
     */
    private String cwd;

    /**
     * Static plan injection for {@code Strategy.PLAN_EXECUTE} harnesses.
     *
     * <p>When set, PAC's {@code extract_json} reads this as Case 0 (highest
     * priority) and uses it instead of the planner LLM's output, turning a
     * PLAN_EXECUTE harness into a fully deterministic pipeline. The planner
     * LLM still runs (the workflow is compiled once) but its output is
     * discarded. Accepts a {@code Map} (typed plan) or a JSON {@code String}.
     *
     * <p>Harmless for non-PLAN_EXECUTE harnesses — they don't read this input.
     */
    private Object staticPlan;
}
