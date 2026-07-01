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
public class EvalRunDto {
    private String id;
    private String agentName;
    private String timestamp;
    private int totalCases;
    private int passedCases;
    private List<String> tags;
    private String createdBy;
    private String name;
    private String strategy;
    private String ranBy;
    /** Name of the stored dataset these cases came from, if any. */
    private String dataset;
    /** Present only in detail responses. */
    private List<EvalCaseDto> cases;
}
