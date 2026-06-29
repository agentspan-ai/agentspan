/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.model;

import java.util.List;
import java.util.Map;

import com.netflix.conductor.common.metadata.tasks.Task;

import lombok.Value;

@Value
public class TaskListResponse {
    List<Task> results;
    int totalHits;
    Map<String, Long> summary;
}
