/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.model;

import java.util.Map;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class InjectTaskRequest {
    private String taskDefName;
    private String referenceTaskName;
    private String type; // "SIMPLE" or "SUB_WORKFLOW"
    private Map<String, Object> inputData;
    private String status; // expected: "IN_PROGRESS" (informational only)
    private SubWorkflowParam subWorkflowParam;

    @Data
    @NoArgsConstructor
    public static class SubWorkflowParam {
        private String name;
        private Integer version;
        private String executionId; // pre-created tracking execution ID
    }
}
