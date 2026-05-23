/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.model.skill;

import java.util.List;
import java.util.Map;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SkillDetail {
    private String name;
    private String version;
    private String description;
    private String checksum;
    private String packageFileHandleId;
    private String storageType;
    private String status;
    private String ownerId;
    private Long createdAt;
    private Long updatedAt;
    private Long packageSize;
    private Integer fileCount;
    private List<SkillFileEntry> files;
    private Map<String, Object> metadata;
    private Map<String, Object> rawConfig;
}
