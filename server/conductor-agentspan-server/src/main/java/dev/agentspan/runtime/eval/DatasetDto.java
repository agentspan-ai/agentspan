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
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class DatasetDto {
    private String name;
    /** ISO-8601 UTC timestamp of last push. */
    private String updatedAt;
    /** Username or script that last pushed this dataset. */
    private String pushedBy;
    /** Number of cases in the dataset — populated on list responses. */
    private Integer caseCount;
    /** Present only in detail responses. */
    private List<DatasetCaseDto> cases;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class DatasetCaseDto {
        private String name;
        private String prompt;
        private List<String> assertions;
        private List<String> tags;
        private String semanticCriteria;
    }
}
