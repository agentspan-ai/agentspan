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

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class AgentExecutionDetail {

    private String executionId;
    private String agentName;
    private int version;
    private String status;
    private Map<String, Object> input;
    private Map<String, Object> output;
    private CurrentTask currentTask;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class CurrentTask {
        private String taskRefName;
        private String taskType;
        private String status;
        private Map<String, Object> inputData;
        private Map<String, Object> outputData;
    }
}
