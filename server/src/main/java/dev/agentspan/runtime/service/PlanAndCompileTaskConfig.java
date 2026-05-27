/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Registers {@link PlanAndCompileTask} as a Conductor system task bean. The
 * bean name must match {@code PlanAndCompileTask.TASK_TYPE} so Conductor's
 * {@code SystemTaskRegistry} can look it up by task type.
 */
@Configuration
public class PlanAndCompileTaskConfig {

    @Bean(PlanAndCompileTask.TASK_TYPE)
    public PlanAndCompileTask planAndCompileTask() {
        return new PlanAndCompileTask();
    }
}
