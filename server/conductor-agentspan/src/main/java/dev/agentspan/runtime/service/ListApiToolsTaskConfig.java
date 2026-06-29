/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Registers {@link ListApiToolsTask} as a Conductor system task bean.
 */
@Configuration
public class ListApiToolsTaskConfig {

    @Bean(ListApiToolsTask.TASK_TYPE)
    public ListApiToolsTask listApiToolsTask() {
        return new ListApiToolsTask();
    }
}
