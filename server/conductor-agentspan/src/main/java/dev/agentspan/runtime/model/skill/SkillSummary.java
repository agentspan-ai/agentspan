/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.model.skill;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SkillSummary {
    private String name;
    private String version;
    private String description;
    private String checksum;
    private String status;
    private String ownerId;
    private Long createdAt;
    private Long updatedAt;
    private Long packageSize;
    private Integer fileCount;
    private Integer scriptCount;
    private Integer subAgentCount;
    private Integer resourceCount;
}
