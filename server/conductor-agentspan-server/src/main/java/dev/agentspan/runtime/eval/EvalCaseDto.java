/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */
package dev.agentspan.runtime.eval;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder(toBuilder = true)
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class EvalCaseDto {
    private String id;
    private String evalRunId;
    private String name;
    private boolean passed;
    private String error;
    private String agentName;
    private String model;
    private List<String> tags;
    private String prompt;
    private String output;
    private List<EvalCheckDto> checks;
}
