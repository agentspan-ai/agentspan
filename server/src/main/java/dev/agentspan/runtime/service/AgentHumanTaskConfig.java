/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import static com.netflix.conductor.common.metadata.tasks.TaskType.TASK_TYPE_HUMAN;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

/**
 * Registers {@link AgentHumanTask} as the primary HUMAN task implementation,
 * overriding Conductor's default {@code Human} system task.
 */
@Configuration
public class AgentHumanTaskConfig {

    @Bean(TASK_TYPE_HUMAN)
    @Primary
    public AgentHumanTask agentHumanTask(AgentStreamRegistry streamRegistry) {
        return new AgentHumanTask(streamRegistry);
    }
}
