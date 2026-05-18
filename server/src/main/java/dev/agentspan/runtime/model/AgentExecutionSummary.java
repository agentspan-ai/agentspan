/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.model;

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
public class AgentExecutionSummary {

    private String executionId;
    private String agentName;
    private int version;
    private String status;
    private String startTime;
    private String endTime;
    private String updateTime;
    private long executionTime;
    private String input;
    private String output;
    private String createdBy;
}
