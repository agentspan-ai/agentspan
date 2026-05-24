/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.model;

import java.util.Map;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Request DTO for {@code POST /api/agent/inspect-plan}.
 *
 * <p>/dg #6: gives callers visibility into what PAC would compile from a
 * given plan, without actually dispatching the SUB_WORKFLOW. Useful for
 * IDE tooling, plan-debug REPLs, and CI checks that validate a plan
 * compiles cleanly against a fixed agent config before deploy.
 *
 * <p>Mirrors {@link StartRequest} for the {@code agentConfig} field so
 * the same agent definition users hand to {@code /start} can be reused
 * here — they just add a {@code plan} field with the same shape PAC's
 * planner LLM would emit.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class InspectPlanRequest {

    /** PLAN_EXECUTE harness config — same shape used by {@code /start}. */
    private AgentConfig agentConfig;

    /**
     * Plan to compile. Same shape PAC's planner LLM produces and the
     * compile path accepts: {@code {"steps": [{"id": "...", "operations":
     * [{"tool": "...", "args": {...}}]}, ...]}}.
     */
    private Map<String, Object> plan;
}
